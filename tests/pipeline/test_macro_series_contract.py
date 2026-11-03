"""Macro series · units, domains, PIT, staleness, and the UUP refusal.

CEO 2026-11-03 · Phase 1. Two defects motivated this file.

USA `macro_dxy` read 29.0 because `features/macro.py` mapped the symbol
`UUP` to it. UUP is the Invesco DB US Dollar Index Bullish Fund, an ETF -
USA's own data labels it "US Dollar Index (Invesco DB proxy)" - trading
~$29 while the DXY index is ~101.7. The feature registry declares
`macro_dxy` with unit "level", so an ETF share price was serving as an
index level.

India carried 0 of 8 because its canonical source,
`reports/macro_summary.json`, is UNTRACKED (absent on a clean checkout
until the orchestrator writes it) and UNDATED (one run_utc, no per-row
observation date), while seven TRACKED, DATED series sat unused in
data/raw/india/global/.

The load-bearing test here is
`test_a_uup_priced_value_cannot_pass_as_a_dxy_level`: the domain check
does not consult the symbol table, so no future remapping can reintroduce
29.0 as an index level.

tmp_path-isolated. No live series, snapshot or report is read or written.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from backend.feature_store import macro_series as MS
from backend.feature_store.features import macro as MF

_REPO = Path(__file__).resolve().parents[2]


def _write(root: Path, filename: str, pairs) -> Path:
    """pairs = [(iso_date, close), ...]"""
    p = root.joinpath(*MS.GLOBAL_DIR) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    idx = pd.to_datetime([d for d, _ in pairs])
    df = pd.DataFrame({"close": [c for _, c in pairs]}, index=idx)
    df.index.name = "Date"
    df.to_parquet(p)
    return p


def _bdays(end: str, n: int, start_val=100.0, step=0.1):
    days = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    return [(d.date().isoformat(), start_val + i * step)
            for i, d in enumerate(days)]


# ───────────────────────────────── the known DXY transformation

class TestKnownDxyTransformation:
    def test_the_raw_close_is_carried_through_unchanged(self, tmp_path):
        """No scaling, no percentage conversion · identity on the level."""
        _write(tmp_path, "DXY.parquet",
               [("2026-10-30", 101.879997), ("2026-11-02", 101.75),
                ("2026-11-03", 101.727997)])
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2026, 11, 3))
        assert r.status == MS.STATUS_VALID
        assert r.value == pytest.approx(101.728, abs=1e-3)
        assert r.transformation == "identity"
        assert r.unit == MS.UNIT_INDEX_LEVEL
        assert r.observation_date == "2026-11-03"
        assert r.age_days == 0

    def test_a_uup_priced_value_cannot_pass_as_a_dxy_level(self, tmp_path):
        """THE REGRESSION. 28.96 is the ETF, not the index.

        The domain floor is 50, and the check never looks at which symbol
        supplied the number - so remapping a source cannot reintroduce
        this, which is exactly how 29.0 survived before.
        """
        _write(tmp_path, "DXY.parquet",
               [("2026-11-02", 29.040001), ("2026-11-03", 28.959999)])
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2026, 11, 3))
        assert r.status == MS.STATUS_INVALID
        assert r.value is None, "an invalid level must not reach a column"
        assert "OUTSIDE_DOMAIN" in r.reason
        assert "28.96" in r.reason

    def test_uup_is_recorded_as_a_refused_source(self):
        assert "UUP" in MS.NOT_AN_INDEX_LEVEL
        feature, why = MS.NOT_AN_INDEX_LEVEL["UUP"]
        assert feature == "macro_dxy"
        assert "ETF" in why

    def test_the_retired_symbol_table_is_gone(self):
        assert not hasattr(MF, "MACRO_SYMBOL_MAP")
        assert MF.MACRO_SYMBOL_MAP_RETIRED is True


# ───────────────────────────────── units and domains, every series

class TestUnitsAndDomains:
    def test_every_series_declares_a_unit_and_a_domain(self):
        for name, spec in MS.SERIES.items():
            assert spec.unit, name
            assert isinstance(spec.domain, tuple) and len(spec.domain) == 2, name
            assert spec.domain[0] < spec.domain[1], name
            assert spec.note, "%s must say what it is" % name

    @pytest.mark.parametrize("feature,value,ok", [
        ("macro_dxy", 101.73, True), ("macro_dxy", 28.96, False),
        ("macro_dxy", 49.9, False), ("macro_dxy", 250.0, False),
        ("macro_10y", 4.89, True), ("macro_10y", 489.0, False),
        ("macro_vix", 21.15, True), ("macro_vix", 0.5, False),
        ("macro_gold", 3934.9, True), ("macro_gold", 3.9, False),
        ("macro_wti_oil", 97.49, True), ("macro_wti_oil", 900.0, False),
    ])
    def test_domain_accepts_real_values_and_rejects_impostors(self, feature,
                                                              value, ok):
        assert MS._in_domain(MS.SERIES[feature], value) is ok

    def test_wti_may_be_negative_because_it_once_was(self):
        """WTI settled at -37.63 on 2020-04-20."""
        assert MS._in_domain(MS.SERIES["macro_wti_oil"], -37.63) is True

    def test_a_yield_is_in_percent_not_basis_points(self):
        spec = MS.SERIES["macro_10y"]
        assert spec.unit == MS.UNIT_PERCENT
        assert MS._in_domain(spec, 4.89) is True
        assert MS._in_domain(spec, 489.0) is False

    def test_nan_is_never_in_domain(self):
        assert MS._in_domain(MS.SERIES["macro_dxy"], float("nan")) is False


# ───────────────────────────────── point in time

class TestPointInTime:
    def test_a_later_observation_is_never_visible(self, tmp_path):
        _write(tmp_path, "DXY.parquet",
               [("2026-11-02", 101.75), ("2026-11-03", 101.73),
                ("2026-11-04", 999.0)])
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2026, 11, 3))
        assert r.observation_date == "2026-11-03"
        assert r.value == pytest.approx(101.73)

    def test_a_historical_asof_gets_the_historical_value(self, tmp_path):
        _write(tmp_path, "DXY.parquet",
               [("2019-03-01", 96.53), ("2026-11-03", 101.73)])
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2019, 3, 1))
        assert r.value == pytest.approx(96.53)
        assert r.normalized_asof == "2019-03-01"

    def test_an_asof_before_the_series_starts_is_missing(self, tmp_path):
        _write(tmp_path, "DXY.parquet", [("2026-11-03", 101.73)])
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2018, 1, 1))
        assert r.status == MS.STATUS_MISSING
        assert r.reason == "NO_OBSERVATION_ON_OR_BEFORE_ASOF"
        assert r.value is None

    def test_a_change_feature_uses_only_visible_bars(self, tmp_path):
        """21 bars back from asof, not from the end of the file."""
        pairs = _bdays("2026-11-03", 60, start_val=4.0, step=0.01)
        pairs.append(("2026-12-31", 99.0))          # future, must be unseen
        _write(tmp_path, "US10Y.parquet", pairs)
        r = MS.resolve_change(tmp_path, MS.SERIES["macro_10y_chg_1m_pct"],
                              date(2026, 11, 3))
        assert r.status == MS.STATUS_VALID
        assert r.observation_date == "2026-11-03"
        assert r.value == pytest.approx(100 * (4.59 / 4.38 - 1), abs=0.02)

    def test_the_undated_summary_refuses_a_historical_asof(self):
        """Today's level wearing a past date is lookahead."""
        rows = [{"symbol": "^MOVE", "last": 100.36}]
        r = MS.resolve_from_summary(MS.SERIES["macro_move"],
                                    date.today() - timedelta(days=1),
                                    rows, "^MOVE")
        assert r.status == MS.STATUS_MISSING
        assert "UNDATED_SOURCE_CANNOT_SERVE_HISTORICAL_ASOF" in r.reason

    def test_the_undated_summary_serves_today(self):
        rows = [{"symbol": "^MOVE", "last": 100.36}]
        r = MS.resolve_from_summary(MS.SERIES["macro_move"], date.today(),
                                    rows, "^MOVE")
        assert r.status == MS.STATUS_VALID
        assert r.value == pytest.approx(100.36)

    def test_the_summary_also_domain_checks(self):
        rows = [{"symbol": "^MOVE", "last": 2.0}]      # below the 10 floor
        r = MS.resolve_from_summary(MS.SERIES["macro_move"], date.today(),
                                    rows, "^MOVE")
        assert r.status == MS.STATUS_INVALID


# ───────────────────────────────── staleness and bounded ffill

class TestStalenessAndBoundedForwardFill:
    def test_a_weekend_gap_is_carried_within_budget(self, tmp_path):
        """Friday's level stands on Monday · 3 days, budget is 3."""
        _write(tmp_path, "DXY.parquet", [("2026-10-30", 101.88)])
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2026, 11, 2))
        assert r.status == MS.STATUS_VALID
        assert r.age_days == 3 and r.ffilled_days == 3

    def test_beyond_the_ffill_budget_it_is_stale_not_valid(self, tmp_path):
        _write(tmp_path, "DXY.parquet", [("2026-10-30", 101.88)])
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2026, 11, 3))
        assert r.status == MS.STATUS_STALE
        assert r.value is None, "a stale level must not reach a column"
        assert "CARRY_OVER" in r.reason

    def test_well_past_max_age_is_stale_with_the_age_named(self, tmp_path):
        _write(tmp_path, "DXY.parquet", [("2026-09-01", 98.0)])
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2026, 11, 3))
        assert r.status == MS.STATUS_STALE
        assert "63d_OLD" in r.reason or "63d" in r.reason

    def test_change_features_do_not_forward_fill(self):
        for n in ("macro_10y_chg_1m_pct", "macro_vix_chg_1m_pct"):
            assert MS.SERIES[n].ffill_days == 0, (
                "%s must not be carried over · a one-month change cannot "
                "be invented for a day with no observation" % n)

    def test_a_stale_parent_makes_the_change_stale(self, tmp_path):
        pairs = _bdays("2026-09-01", 40, start_val=4.0, step=0.01)
        _write(tmp_path, "US10Y.parquet", pairs)
        r = MS.resolve_change(tmp_path, MS.SERIES["macro_10y_chg_1m_pct"],
                              date(2026, 11, 3))
        assert r.status == MS.STATUS_STALE
        assert r.value is None


# ───────────────────────────────── source hygiene

class TestSourceHygiene:
    def test_duplicate_observation_timestamps_keep_the_last(self, tmp_path):
        """A later revision of the same session wins over the first print."""
        _write(tmp_path, "DXY.parquet",
               [("2026-11-03", 100.0), ("2026-11-03", 101.73)])
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2026, 11, 3))
        assert r.value == pytest.approx(101.73)

    def test_a_duplicated_date_does_not_multiply_rows(self, tmp_path):
        _write(tmp_path, "DXY.parquet",
               [("2026-11-02", 101.0), ("2026-11-02", 101.5),
                ("2026-11-03", 101.73)])
        s = MS.load_series(tmp_path, "DXY.parquet")
        assert len(s) == 2, "join cardinality must stay one row per date"
        assert s.index.is_unique

    def test_an_unsorted_source_is_sorted(self, tmp_path):
        _write(tmp_path, "DXY.parquet",
               [("2026-11-03", 101.73), ("2026-11-02", 101.75)])
        s = MS.load_series(tmp_path, "DXY.parquet")
        assert s.index.is_monotonic_increasing

    def test_a_missing_source_file_is_missing_not_an_exception(self, tmp_path):
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2026, 11, 3))
        assert r.status == MS.STATUS_MISSING
        assert r.reason == "SOURCE_MISSING_OR_UNREADABLE"

    def test_a_corrupt_source_file_is_missing_not_an_exception(self, tmp_path):
        p = tmp_path.joinpath(*MS.GLOBAL_DIR) / "DXY.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"not a parquet")
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2026, 11, 3))
        assert r.status == MS.STATUS_MISSING

    def test_a_tz_aware_index_is_normalised(self, tmp_path):
        p = tmp_path.joinpath(*MS.GLOBAL_DIR) / "DXY.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        idx = pd.to_datetime(["2026-11-03"]).tz_localize("UTC")
        pd.DataFrame({"close": [101.73]}, index=idx).to_parquet(p)
        s = MS.load_series(tmp_path, "DXY.parquet")
        assert s is not None and getattr(s.index, "tz", None) is None

    def test_nan_closes_are_dropped(self, tmp_path):
        _write(tmp_path, "DXY.parquet",
               [("2026-11-02", 101.75), ("2026-11-03", float("nan"))])
        r = MS.resolve_level(tmp_path, MS.SERIES["macro_dxy"],
                             date(2026, 11, 3))
        assert r.observation_date == "2026-11-02"


# ───────────────────────────────── no fabrication

class TestNothingIsFabricated:
    def test_only_valid_values_reach_a_feature_column(self):
        res = {
            "a": MS.Resolved("a", 1.0, MS.STATUS_VALID, "x"),
            "b": MS.Resolved("b", 2.0, MS.STATUS_STALE, "x"),
            "c": MS.Resolved("c", 3.0, MS.STATUS_INVALID, "x"),
            "d": MS.Resolved("d", None, MS.STATUS_MISSING, "x"),
        }
        v = MS.feature_values(res)
        assert v == {"a": 1.0, "b": None, "c": None, "d": None}

    @staticmethod
    def _code_numbers(mod) -> set:
        """Numeric literals in EXECUTABLE code · not docstrings, not comments.

        My first version grepped the source text and failed on the module
        docstring, which quotes 101.73 and 28.96 precisely in order to
        explain the defect. That is the grep-the-prose trap this repository
        has hit repeatedly, so the check parses instead: ast yields only
        real constants, and a docstring is an expression statement that is
        skipped.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(mod))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
                d = ast.get_docstring(node, clean=False)
                if d is not None:
                    docstrings.add(d)
        out = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                if isinstance(node.value, str) and node.value in docstrings:
                    continue
                if isinstance(node.value, (int, float)) and not isinstance(
                        node.value, bool):
                    out.add(float(node.value))
        return out

    def test_the_corrected_dxy_value_is_not_hardcoded(self):
        """A default macro level is indistinguishable from a real one."""
        for mod in (MS, MF):
            nums = self._code_numbers(mod)
            assert not any(abs(n - 101.73) < 0.5 for n in nums), (
                "%s hardcodes a DXY-looking level" % mod.__name__)
            assert not any(abs(n - 28.96) < 0.1 for n in nums), (
                "%s hardcodes a UUP-looking price" % mod.__name__)

    def test_the_dxy_domain_bounds_are_bounds_not_values(self):
        assert MS.SERIES["macro_dxy"].domain == (50.0, 200.0)

    def test_no_zero_filling_or_default_coalescing_in_the_resolver(self):
        import inspect
        code = "\n".join(
            l.split("#", 1)[0] for l in inspect.getsource(MS).splitlines()
            if not l.strip().startswith("#"))
        for bad in ("fillna(0", "or 0.0", ".fillna(0)"):
            assert bad not in code, "fallback-looking construct: %r" % bad

    def test_compute_without_a_root_returns_nothing_rather_than_guessing(self):
        out = MF.compute({}, ["AAA", "BBB"], date.today(), "india", root=None)
        assert out == {"AAA": {}, "BBB": {}}


# ───────────────────────────────── both market joins

class TestBothMarketJoins:
    @staticmethod
    def _full(tmp_path, end="2026-11-03"):
        _write(tmp_path, "DXY.parquet", _bdays(end, 40, 101.0, 0.01))
        _write(tmp_path, "US10Y.parquet", _bdays(end, 40, 4.0, 0.01))
        _write(tmp_path, "GOLD.parquet", _bdays(end, 40, 3900.0, 1.0))
        _write(tmp_path, "OIL.parquet", _bdays(end, 40, 95.0, 0.05))
        _write(tmp_path, "USVIX.parquet", _bdays(end, 40, 20.0, 0.02))
        return tmp_path

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_both_markets_resolve_the_same_global_series(self, tmp_path,
                                                         market):
        root = self._full(tmp_path)
        out = MF.compute({}, ["AAA", "BBB"], date(2026, 11, 3), market,
                         root=root)
        for f in ("macro_dxy", "macro_10y", "macro_gold", "macro_wti_oil",
                  "macro_vix"):
            assert out["AAA"].get(f) is not None, "%s/%s" % (market, f)

    def test_the_value_is_identical_across_every_ticker(self, tmp_path):
        root = self._full(tmp_path)
        out = MF.compute({}, ["A", "B", "C", "D"], date(2026, 11, 3),
                         "india", root=root)
        assert out["A"] == out["B"] == out["C"] == out["D"]

    def test_india_and_usa_agree_on_a_global_series(self, tmp_path):
        """DXY is not market-specific · a divergence would be a defect."""
        root = self._full(tmp_path)
        i = MF.compute({}, ["A"], date(2026, 11, 3), "india", root=root)["A"]
        u = MF.compute({}, ["A"], date(2026, 11, 3), "usa", root=root)["A"]
        assert i["macro_dxy"] == u["macro_dxy"]

    def test_an_absent_series_leaves_its_column_out_entirely(self, tmp_path):
        root = self._full(tmp_path)
        (root.joinpath(*MS.GLOBAL_DIR) / "GOLD.parquet").unlink()
        out = MF.compute({}, ["A"], date(2026, 11, 3), "india", root=root)
        assert "macro_gold" not in out["A"]
        assert out["A"].get("macro_dxy") is not None, "others unaffected"

    def test_determinism(self, tmp_path):
        root = self._full(tmp_path)
        a = MF.compute({}, ["A"], date(2026, 11, 3), "india", root=root)
        b = MF.compute({}, ["A"], date(2026, 11, 3), "india", root=root)
        assert a == b


# ───────────────────────────────── the quality report

class TestQualityReport:
    def test_statuses_are_counted_apart_never_blended(self, tmp_path):
        _write(tmp_path, "DXY.parquet", [("2026-11-03", 28.96)])   # INVALID
        _write(tmp_path, "USVIX.parquet", [("2026-09-01", 20.0)])  # STALE
        res = MS.resolve_all(tmp_path, date(2026, 11, 3))
        rep = MS.quality_report(tmp_path, date(2026, 11, 3), "india", res,
                                n_universe=228)
        assert rep["by_status"][MS.STATUS_INVALID] == ["macro_dxy"]
        assert MS.STATUS_STALE in rep["by_status"]
        assert rep["n_valid"] < rep["n_features"]
        assert rep["universe_rows"] == 228

    def test_an_invalid_value_is_not_counted_as_coverage(self, tmp_path):
        _write(tmp_path, "DXY.parquet", [("2026-11-03", 28.96)])
        res = MS.resolve_all(tmp_path, date(2026, 11, 3))
        rep = MS.quality_report(tmp_path, date(2026, 11, 3), "usa", res)
        assert "macro_dxy" not in rep["by_status"].get(MS.STATUS_VALID, [])

    def test_the_report_names_the_known_gap_and_the_refused_symbol(self,
                                                                   tmp_path):
        res = MS.resolve_all(tmp_path, date(2026, 11, 3))
        rep = MS.quality_report(tmp_path, date(2026, 11, 3), "india", res)
        assert "macro_move" in rep["known_gaps"]
        assert "UUP" in rep["refused_symbols"]

    def test_the_report_states_that_macro_cannot_rank_cross_sectionally(self,
                                                                        tmp_path):
        res = MS.resolve_all(tmp_path, date(2026, 11, 3))
        rep = MS.quality_report(tmp_path, date(2026, 11, 3), "india", res)
        assert "cross-sectional" in rep["market_wide_note"]

    def test_compute_writes_the_report(self, tmp_path):
        _write(tmp_path, "DXY.parquet", [("2026-11-03", 101.73)])
        MF.compute({}, ["A"], date(2026, 11, 3), "india", root=tmp_path)
        p = MS.report_path(tmp_path, "india", date(2026, 11, 3))
        assert p.exists()
        q = json.loads(p.read_text(encoding="utf-8"))
        assert q["market"] == "india" and q["asof"] == "2026-11-03"

    def test_every_feature_carries_full_provenance(self, tmp_path):
        _write(tmp_path, "DXY.parquet", [("2026-11-03", 101.73)])
        res = MS.resolve_all(tmp_path, date(2026, 11, 3))
        d = res["macro_dxy"].as_dict()
        for k in ("source", "observation_date", "normalized_asof",
                  "age_days", "transformation", "unit", "status"):
            assert k in d, k
        assert d["source"].endswith("DXY.parquet")


# ───────────────────────────────── live repository sanity

class TestLiveRepositorySeries:
    """Reads the tracked global series · skips if absent."""

    def test_the_live_dxy_resolves_to_an_index_level(self):
        p = _REPO.joinpath(*MS.GLOBAL_DIR) / "DXY.parquet"
        if not p.exists():
            pytest.skip("no tracked DXY series in this checkout")
        r = MS.resolve_level(_REPO, MS.SERIES["macro_dxy"], date.today())
        assert r.status == MS.STATUS_VALID, r.reason
        assert 50.0 <= r.value <= 200.0
        assert r.value > 50, "an ETF-priced ~29 would fail here"

    def test_the_tracked_sources_exist_for_seven_of_eight_features(self):
        missing = []
        for name, spec in MS.SERIES.items():
            if spec.source_file is None:
                continue
            if not (_REPO.joinpath(*MS.GLOBAL_DIR) / spec.source_file).exists():
                missing.append(name)
        assert missing == [], missing

    def test_macro_move_is_the_only_untracked_gap(self):
        gaps = [n for n, s in MS.SERIES.items()
                if s.source_file is None and not s.derived_from]
        assert gaps == ["macro_move"]
