"""The ticker→sector contract, and what the sector features can honestly say.

CEO 2026-11-04 · Phase 1A.

THE DEFECT
----------
`india/sectors.py` exports a FLAT map, 228 tickers onto 17 sectors:

    SECTORS = {"HDFCBANK": "Financials", "TCS": "IT", ...}

Four consumers read it that way. Two - both in the feature store, the
only consumer whose output reaches the snapshot - inverted it and
iterated the VALUE:

    for sec, syms in SECTORS.items():
        for s in syms:          # 'Financials' -> 'F','i','n','a',...
            m[s] = sec

30 entries keyed by single letters. Join rate 0 of 228. That is why
`sector` was empty in every India snapshot and all four `sector_*`
features were 0% - not missing data, a map read backwards, while
`canonical/pit_provenance.py` carried a docstring stating the correct
shape.

THE SECOND PROBLEM, WHICH THE FIRST FIX DOES NOT SOLVE
------------------------------------------------------
Repairing the map takes `sector` to 228/228 but `sector_*` only to
95/228, because a ticker's sector must ALSO name a sector INDEX for a
sector return to exist, and the two vocabularies agree on just 7 of 17
names. Label variance (Consumer/Consumption, Infra/Infrastructure) is
reconciled in configs/india_sector_index_aliases.yaml, reaching 115.
The remaining 113 have no defensible index and must stay NULL.

Which is the third thing fixed here: `sector_is_leader` and
`sector_is_laggard` used to return 0 when the rank was unknown,
asserting that 113 tickers had been measured and found ordinary. Missing
and weak are different answers.

tmp_path-isolated except the explicitly read-only live checks.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from backend.shared.sector_map import (CONTRACT, MalformedSectorMap, coverage,
                                       india_ticker_sector, normalize_ticker,
                                       sector_for, validate_flat_map)

_ROOT = Path(__file__).resolve().parents[2]

FLAT = {"HDFCBANK": "Financials", "SBIN": "Financials", "TCS": "IT",
        "INFY": "IT", "SUNPHARMA": "Pharma"}


class TestTheContractIsEnforced:
    def test_a_flat_map_is_accepted_and_normalised(self):
        m = validate_flat_map(FLAT)
        assert m["TCS"] == "IT"
        assert len(m) == 5

    def test_the_inverted_map_is_refused(self):
        """The exact mistake · sector -> [tickers]."""
        with pytest.raises(MalformedSectorMap) as e:
            validate_flat_map({"Financials": ["HDFCBANK", "SBIN"],
                               "IT": ["TCS"]})
        assert "INVERTED" in str(e.value)

    def test_a_map_with_more_sectors_than_tickers_is_refused(self):
        """A reversed map whose values happen to be strings."""
        with pytest.raises(MalformedSectorMap):
            validate_flat_map({"Financials": "HDFCBANK", "IT": "TCS"})

    def test_non_string_values_are_refused(self):
        with pytest.raises(MalformedSectorMap):
            validate_flat_map({"TCS": 7, "INFY": "IT", "SBIN": "Financials"})

    def test_a_blank_sector_is_refused(self):
        with pytest.raises(MalformedSectorMap) as e:
            validate_flat_map(dict(FLAT, WIPRO="   "))
        assert "blank" in str(e.value)

    def test_an_empty_map_is_refused_not_returned(self):
        with pytest.raises(MalformedSectorMap):
            validate_flat_map({})

    def test_a_non_mapping_is_refused(self):
        with pytest.raises(MalformedSectorMap):
            validate_flat_map([("TCS", "IT")])

    def test_the_contract_is_stated_in_one_place(self):
        assert "ticker" in CONTRACT and "sector" in CONTRACT


class TestLookupIsSuffixTolerant:
    @pytest.mark.parametrize("t", ["TCS", "TCS.NS", "tcs", "TCS.BO", " tcs "])
    def test_every_layer_form_resolves(self, t):
        assert sector_for(validate_flat_map(FLAT), t) == "IT"

    def test_an_unknown_ticker_is_none_not_blank(self):
        assert sector_for(validate_flat_map(FLAT), "NOSUCH") is None

    def test_normalisation_strips_only_known_suffixes(self):
        assert normalize_ticker("AARTIIND.NS") == "AARTIIND"
        assert normalize_ticker("BRK.B") == "BRK.B"   # not an India suffix


class TestTheCharacterIterationCannotReturn:
    def test_no_feature_store_module_inverts_the_map(self):
        """AST · the two offenders must not re-acquire the pattern."""
        import ast
        for rel in ("backend/feature_store/feature_builder.py",
                    "backend/feature_store/features/sector.py"):
            tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.For):
                    continue
                src = ast.unparse(node)
                assert not ("SECTORS.items()" in src and "for s in syms" in src), (
                    "%s inverts SECTORS again" % rel)

    def test_the_old_inversion_really_did_produce_letters(self):
        """Documents the defect so the test is evidence, not assertion."""
        m = {}
        for sec, syms in FLAT.items():
            for s in syms:
                m[s] = sec
        assert "TCS" not in m
        assert all(len(k) == 1 for k in m)


class TestLiveIndiaCoverage:
    def test_the_live_map_classifies_every_india_ticker(self):
        import sys
        sys.path.insert(0, str(_ROOT))
        from india.data_nse import UNIVERSE
        m = india_ticker_sector(_ROOT)
        uni = [s for s in UNIVERSE if not s.startswith("^")]
        c = coverage(m, uni)
        assert c["n_universe"] == 228
        assert c["n_classified"] == 228, c["unclassified"]
        assert c["coverage_pct"] == 100.0
        assert c["n_sectors"] == 17


class TestSectorFeaturesSeparatelyFromTheSectorColumn:
    """The CEO's warning · a populated `sector` does not make the four
    sector_* features valid. They need a sector INDEX too."""

    @staticmethod
    def _compute(tmp_path, labels, tickers_sectors, aliases=None):
        from backend.canonical.schemas import CanonicalDataset, CanonicalFlowProxy
        from backend.feature_store.features import sector as S
        rows = [CanonicalFlowProxy(market="india", symbol=k, label=k,
                                   asof=date(2026, 11, 3), period_days=21,
                                   return_pct=v, avg_dollar_volume=0.0,
                                   currency="INR", source="test")
                for k, v in labels.items()]
        canon = {"flow_proxy": CanonicalDataset(
            kind="flow_proxy", market="india", asof=date(2026, 11, 3),
            n_rows=len(rows), rows=rows, source="test")}
        if aliases is not None:
            (tmp_path / "configs").mkdir(parents=True, exist_ok=True)
            (tmp_path / "configs" / "india_sector_index_aliases.yaml").write_text(
                "aliases:\n" + "".join("  %s: %s\n" % kv for kv in aliases.items()),
                encoding="utf-8")
        import backend.shared.sector_map as SM
        orig = SM.india_ticker_sector
        SM.india_ticker_sector = lambda root=None: dict(tickers_sectors)
        try:
            return S.compute(canon, list(tickers_sectors), date(2026, 11, 3),
                             "india", repo_root=tmp_path)
        finally:
            SM.india_ticker_sector = orig

    def test_a_sector_with_an_index_gets_its_features(self, tmp_path):
        out = self._compute(tmp_path, {"IT": 5.0, "Pharma": 2.0, "Auto": -1.0},
                            {"TCS": "IT"})
        assert out["TCS"]["sector"] == "IT"
        assert out["TCS"]["sector_return_1m_pct"] == 5.0
        assert out["TCS"]["sector_rank"] == 1
        assert out["TCS"]["sector_is_leader"] == 1

    def test_a_sector_with_NO_index_abstains_rather_than_scoring_zero(self,
                                                                     tmp_path):
        """The fabrication · rank unknown used to mean is_leader = 0."""
        out = self._compute(tmp_path, {"IT": 5.0}, {"ULTRACEMCO": "Cement"})
        f = out["ULTRACEMCO"]
        assert f["sector"] == "Cement"          # classification IS known
        assert f["sector_return_1m_pct"] is None
        assert f["sector_rank"] is None
        assert f["sector_is_leader"] is None, (
            "an unmeasured sector must not be reported as 'not a leader'")
        assert f["sector_is_laggard"] is None

    def test_an_alias_reconciles_pure_label_variance(self, tmp_path):
        out = self._compute(tmp_path, {"Consumption": 7.0, "IT": 1.0},
                            {"TITAN": "Consumer"},
                            aliases={"Consumer": "Consumption"})
        assert out["TITAN"]["sector"] == "Consumer"
        assert out["TITAN"]["sector_return_1m_pct"] == 7.0

    def test_without_the_alias_the_same_ticker_abstains(self, tmp_path):
        out = self._compute(tmp_path, {"Consumption": 7.0, "IT": 1.0},
                            {"TITAN": "Consumer"}, aliases={})
        assert out["TITAN"]["sector_return_1m_pct"] is None

    def test_proposed_aliases_are_not_silently_enabled(self):
        """`Financials -> Banking` is a modelling claim, not a string fix."""
        import yaml
        cfg = yaml.safe_load(
            (_ROOT / "configs" / "india_sector_index_aliases.yaml")
            .read_text(encoding="utf-8"))
        assert "Financials" not in (cfg.get("aliases") or {}), (
            "a proxy mapping was enabled without approval")
        prop = cfg.get("proposed_aliases") or {}
        assert prop["Financials"]["status"] == "AWAITING_APPROVAL"
        assert prop["Financials"]["caveat"]

    def test_the_alias_loader_ignores_the_proposed_block(self):
        from backend.feature_store.features.sector import _index_aliases
        a = _index_aliases(_ROOT)
        assert a == {"Consumer": "Consumption", "Infra": "Infrastructure"}


class TestUsaIsUntouched:
    def test_usa_sector_source_is_still_the_universe_file(self, tmp_path):
        """The shared builder change must not reach USA."""
        from backend.feature_store.features.sector import _ticker_sector_map
        import json
        (tmp_path / "usa" / "reports").mkdir(parents=True, exist_ok=True)
        (tmp_path / "usa" / "reports" / "universe.json").write_text(
            json.dumps({"tickers": [{"symbol": "AAPL", "sector": "Tech"}]}),
            encoding="utf-8")
        m = _ticker_sector_map(tmp_path, "usa")
        assert m == {"AAPL": "Tech"}
