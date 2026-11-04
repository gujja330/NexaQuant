"""Semantic feature quality: completeness is not validity. CEO 2026-11-04.

Every Phase 1 defect passed `notna()`:

  macro_dxy   29.0 on all 516 USA rows   — the UUP ETF price, not the index
  sector      'Unknown' on all 516 rows  — 100% complete, zero information
  fii_net_5d  one national aggregate     — correct, and not cross-sectional
  sma_200     0% in both markets         — a 200-bar feature in a 90-bar window

The hard case is that a legitimately shared constant and a broken
ticker-level fan-out are IDENTICAL to `nunique() == 1`. Only the
registry's granularity declaration separates them, so the tests below
check both sides of that line explicitly.

tmp_path-isolated. No live snapshot or report is written.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from backend.feature_store import feature_quality as FQ
from backend.feature_store.feature_registry import (FEATURE_REGISTRY,
                                                    FeatureGranularity,
                                                    feature_by_name,
                                                    granularity_of,
                                                    unclassified_features)

ASOF = date(2026, 11, 3)


def _feat(name):
    f = feature_by_name(name)
    assert f is not None, name
    return f


def _df(n=10, **cols):
    d = {"market": ["india"] * n, "ticker": ["T%02d" % i for i in range(n)],
         "asof": [ASOF.isoformat()] * n, "currency": ["INR"] * n}
    d.update({k: (v if isinstance(v, list) else [v] * n)
              for k, v in cols.items()})
    return pd.DataFrame(d)


# ── the registry declarations themselves ────────────────────────────
class TestDeclarations:
    def test_every_feature_is_classified(self):
        assert unclassified_features() == [], (
            "an UNKNOWN granularity is a blind spot the validator refuses "
            "to judge")

    def test_all_81_features_carry_a_granularity(self):
        assert len(FEATURE_REGISTRY) == 81
        assert all(isinstance(f.granularity, FeatureGranularity)
                   for f in FEATURE_REGISTRY)

    @pytest.mark.parametrize("name,expected", [
        ("macro_dxy", FeatureGranularity.GLOBAL),
        ("macro_move", FeatureGranularity.GLOBAL),
        ("mi_regime", FeatureGranularity.MARKET),
        ("mi_composite_score", FeatureGranularity.MARKET),
        ("fii_net_5d", FeatureGranularity.MARKET),
        ("dii_net_5d", FeatureGranularity.MARKET),
        ("sector", FeatureGranularity.TICKER),
        ("sma_200", FeatureGranularity.TICKER),
        ("price_above_sma200", FeatureGranularity.TICKER),
        ("sector_rank", FeatureGranularity.SECTOR),
        ("sector_return_1m_pct", FeatureGranularity.SECTOR),
    ])
    def test_the_investigated_classifications(self, name, expected):
        assert granularity_of(name) == expected

    def test_constant_is_legitimate_follows_granularity(self):
        assert _feat("mi_regime").constant_is_legitimate is True
        assert _feat("macro_dxy").constant_is_legitimate is True
        assert _feat("sector_rank").constant_is_legitimate is True
        assert _feat("sma_200").constant_is_legitimate is False
        assert _feat("sector").constant_is_legitimate is False

    def test_fii_dii_are_not_classified_from_their_names(self):
        """They read as per-ticker and are one national aggregate."""
        f = _feat("fii_net_5d")
        assert f.granularity == FeatureGranularity.MARKET
        assert "aggregate" in f.provenance

    def test_every_feature_declares_a_provenance(self):
        missing = [f.name for f in FEATURE_REGISTRY if not f.provenance]
        assert missing == []


# ── legitimate shared constants must NOT be flagged ─────────────────
class TestLegitimateSharedConstants:
    @pytest.mark.parametrize("name,value", [
        ("mi_regime", "neutral"),
        ("mi_composite_score", 58.28),
        ("macro_dxy", 101.728),
        ("macro_vix", 21.15),
        ("fii_net_5d", -1234.5),
    ])
    def test_one_value_on_every_row_is_valid_at_shared_granularity(self, name,
                                                                   value):
        q = FQ.check_column(_df(**{name: value}), _feat(name))
        assert q.status == FQ.VALID, q.reason
        assert "SHARED_CONSTANT_AS_DECLARED" in q.codes

    def test_a_sector_level_feature_may_repeat_within_a_sector(self):
        """4 sectors across 12 rows · values repeat and differ."""
        vals = [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4]
        q = FQ.check_column(_df(12, sector_rank=vals), _feat("sector_rank"))
        assert q.status == FQ.VALID, q.reason

    def test_a_sector_level_feature_constant_everywhere_is_still_valid(self):
        """A one-sector universe is legitimate, not a defect."""
        q = FQ.check_column(_df(sector_rank=3), _feat("sector_rank"))
        assert q.status == FQ.VALID


# ── broken ticker-level values MUST be flagged ──────────────────────
class TestBrokenTickerLevelValues:
    def test_a_constant_ticker_feature_is_CONSTANT_not_valid(self):
        """news_n_headlines = 8 on all 516 USA rows, measured."""
        q = FQ.check_column(_df(516, news_n_headlines=8),
                            _feat("news_n_headlines"))
        assert q.status == FQ.CONSTANT
        assert "CONSTANT_AT_TICKER_LEVEL" in q.codes
        assert q.n_present == 516, "it IS fully populated · that is the point"

    def test_the_reason_says_it_carries_no_cross_sectional_information(self):
        q = FQ.check_column(_df(516, news_n_headlines=8),
                            _feat("news_n_headlines"))
        assert "cross-sectional" in q.reason

    def test_a_varying_ticker_feature_is_valid(self):
        q = FQ.check_column(_df(10, sma_200=list(range(100, 110))),
                            _feat("sma_200"))
        assert q.status == FQ.VALID

    def test_a_market_feature_that_varies_is_suspect_fan_out(self):
        q = FQ.check_column(_df(10, mi_composite_score=list(range(10))),
                            _feat("mi_composite_score"))
        assert q.status == FQ.INVALID
        assert "UNEXPECTED_VARIATION" in q.codes


# ── placeholders are not observations ───────────────────────────────
class TestPlaceholders:
    def test_unknown_on_every_row_is_missing_not_complete(self):
        """The live USA case: sector = 'Unknown' x 516."""
        q = FQ.check_column(_df(516, sector="Unknown"), _feat("sector"))
        assert q.status == FQ.MISSING
        assert "PLACEHOLDER_ONLY" in q.codes
        assert q.n_present == 0, "a placeholder must not count as present"
        assert q.n_placeholder == 516

    @pytest.mark.parametrize("ph", ["Unknown", "N/A", "", " ", "none", "-",
                                    "null", "TBD"])
    def test_the_placeholder_vocabulary(self, ph):
        q = FQ.check_column(_df(5, sector=ph), _feat("sector"))
        assert q.n_present == 0

    def test_an_absent_column_is_distinguished_from_a_placeholder(self):
        """India's sector is ABSENT; USA's is the string 'Unknown'.

        Different failures, different fixes, so they must not collapse
        into one status message.
        """
        absent = FQ.check_column(_df(228, sector=None), _feat("sector"))
        placeheld = FQ.check_column(_df(516, sector="Unknown"),
                                     _feat("sector"))
        assert absent.status == placeheld.status == FQ.MISSING
        assert "EMPTY" in absent.codes
        assert "PLACEHOLDER_ONLY" in placeheld.codes
        assert "carry a value" in absent.reason
        assert "placeholder" in placeheld.reason

    def test_a_real_value_beside_placeholders_is_counted_honestly(self):
        vals = ["Pharma"] * 3 + ["Unknown"] * 7
        q = FQ.check_column(_df(10, sector=vals), _feat("sector"))
        assert q.n_present == 3
        assert q.n_placeholder == 7


# ── domains, nulls and coverage ─────────────────────────────────────
class TestDomainsAndCoverage:
    def test_the_uup_substitution_is_a_domain_violation(self):
        """29.0 cannot be a DXY index level. The defect that started this."""
        q = FQ.check_column(_df(516, macro_dxy=29.0), _feat("macro_dxy"))
        assert q.status == FQ.INVALID
        assert "DOMAIN_VIOLATION" in q.codes

    def test_the_corrected_dxy_passes(self):
        q = FQ.check_column(_df(516, macro_dxy=101.728), _feat("macro_dxy"))
        assert q.status == FQ.VALID

    def test_an_all_null_column_is_missing_with_a_count(self):
        q = FQ.check_column(_df(228, sma_200=None), _feat("sma_200"))
        assert q.status == FQ.MISSING
        assert "0 of 228" in q.reason

    def test_coverage_below_the_declared_expectation_is_missing(self):
        vals = [100.0] * 2 + [None] * 98          # 2% against a declared 95%
        q = FQ.check_column(_df(100, sma_200=vals), _feat("sma_200"))
        assert q.status == FQ.MISSING
        assert "COVERAGE_BELOW_DECLARED" in q.codes

    def test_nothing_is_coerced_to_zero(self):
        """A null must never be reported as an observed 0."""
        q = FQ.check_column(_df(10, fund_roe=None), _feat("fund_roe"))
        assert q.status == FQ.MISSING
        assert q.n_present == 0
        assert q.sample is None


# ── point-in-time ───────────────────────────────────────────────────
class TestPointInTime:
    def test_a_clean_snapshot_passes(self):
        rep = FQ.check_snapshot(_df(10, sma_200=list(range(10))), "india",
                                ASOF)
        assert rep["point_in_time"]["ok"] is True

    def test_two_asofs_in_one_snapshot_is_leakage(self):
        df = _df(4)
        df.loc[0, "asof"] = "2026-11-04"
        rep = FQ.check_snapshot(df, "india", ASOF)
        assert rep["point_in_time"]["ok"] is False
        assert "MULTIPLE_ASOF_IN_ONE_SNAPSHOT" in rep["point_in_time"]["codes"]

    def test_an_asof_after_the_requested_date_is_leakage(self):
        df = _df(4)
        df["asof"] = "2026-11-05"
        rep = FQ.check_snapshot(df, "india", date(2026, 11, 3))
        assert rep["point_in_time"]["ok"] is False
        assert "ASOF_AFTER_REQUESTED_DATE" in rep["point_in_time"]["codes"]

    def test_a_missing_asof_column_is_not_point_in_time(self):
        df = _df(4).drop(columns=["asof"])
        rep = FQ.check_snapshot(df, "india", ASOF)
        assert "NO_ASOF_COLUMN" in rep["point_in_time"]["codes"]

    def test_an_undated_value_under_a_historical_asof_is_flagged(self):
        """macro_move resolved from an undated snapshot."""
        past = date.today() - timedelta(days=30)
        df = _df(4, macro_move=100.36)
        df["asof"] = past.isoformat()
        rep = FQ.check_snapshot(df, "india", past)
        assert rep["point_in_time"]["ok"] is False
        assert "UNDATED_VALUE_UNDER_HISTORICAL_ASOF" in \
            rep["point_in_time"]["codes"]
        assert "macro_move" in rep["point_in_time"]["undated_features"]

    def test_the_same_undated_value_is_fine_when_the_asof_is_today(self):
        df = _df(4, macro_move=100.36)
        df["asof"] = date.today().isoformat()
        rep = FQ.check_snapshot(df, "india", date.today())
        assert "UNDATED_VALUE_UNDER_HISTORICAL_ASOF" not in \
            rep["point_in_time"]["codes"]


# ── the report ──────────────────────────────────────────────────────
class TestReport:
    def test_the_report_is_json_serialisable_and_keyed_by_feature(self,
                                                                  tmp_path):
        rep = FQ.check_snapshot(_df(10, sma_200=list(range(10))), "india",
                                ASOF)
        p = FQ.write_report(tmp_path, "india", ASOF, rep)
        back = json.loads(p.read_text(encoding="utf-8"))
        assert back["n_features"] == 81
        assert "sma_200" in back["features"]
        assert back["features"]["sma_200"]["granularity"] == "ticker"

    def test_the_report_carries_counts_percentages_and_reason_codes(self):
        rep = FQ.check_snapshot(_df(516, news_n_headlines=8), "usa", ASOF)
        f = rep["features"]["news_n_headlines"]
        assert f["n_present"] == 516
        assert f["coverage_pct"] == 100.0
        # asdict keeps the tuple in memory; JSON renders it as an array
        assert list(f["codes"]) == ["CONSTANT_AT_TICKER_LEVEL"]
        assert f["reason"]

    def test_usable_features_excludes_every_non_valid_status(self):
        rep = FQ.check_snapshot(_df(516, sector="Unknown",
                                    news_n_headlines=8), "usa", ASOF)
        usable = FQ.usable_features(rep)
        assert "sector" not in usable
        assert "news_n_headlines" not in usable

    def test_a_per_granularity_rollup_is_present(self):
        rep = FQ.check_snapshot(_df(10), "india", ASOF)
        assert set(rep["by_granularity"]) <= {"ticker", "market", "sector",
                                              "global", "unknown"}
        assert rep["by_granularity"]["market"]["n"] == 12

    def test_the_default_status_is_not_valid(self):
        """A forgotten branch must not read as a pass."""
        q = FQ.FeatureQuality(feature="x", granularity="ticker")
        assert q.status == FQ.UNVERIFIABLE
        assert q.usable is False
