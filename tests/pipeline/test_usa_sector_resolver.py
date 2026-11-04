"""USA sector resolution from SEC SIC, with provenance. CEO 2026-11-04 · §1B.

WHAT THIS REPLACES
------------------
`usa/reports/universe.json` carries `sector: "Unknown"` for all 516
names - not partially populated, entirely absent. So USA's four
`sector_*` features are 0% and every sector-relative comparison the
planned Top-300 selector needs has nothing underneath it.

SEC publishes a SIC code per registrant, free and public: 504 of 516
universe symbols resolve to a CIK and 503 carry a SIC.

WHAT IS DELIBERATELY NOT CLAIMED
--------------------------------
SIC is not GICS. One code per registrant, no segments, and some codes
name a legal structure rather than a business. Measured on this
universe, the refusals are:

    6798  Real Estate Investment Trusts   26   legal structure · an
          equity REIT is GICS Real Estate, a mortgage REIT is GICS
          Financials, and the SEC record cannot separate them
    7389  Services-Business Services NEC  16   ambiguous by definition
    (no SIC)                              13   12 non-registrants + NXP

55 of 516 unclassified, and that is the price of not guessing. A
classification nobody can defend is worse than an absent one, because a
selector will rank on it.

HISTORY
-------
SEC exposes no `sicHistory`. `formerNames` dates name changes, not
reclassifications. So `effective_from` equals `first_observed_date`
with `effective_from_basis = FIRST_OBSERVED`, and a query before that
date returns UNAVAILABLE rather than today's answer backdated.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from backend.shared.usa_sector_resolver import (BASIS_FIRST_OBSERVED,
                                                CLASSIFIED, EXACT, MAPPED,
                                                REVIEW_REQUIRED, UNAVAILABLE,
                                                UNCLASSIFIED, UNKNOWN,
                                                VALIDATED,
                                                SectorMapConfigError,
                                                classify_sic, coverage_report,
                                                load_config, resolve,
                                                resolve_asof)

_ROOT = Path(__file__).resolve().parents[2]
CFG = load_config(_ROOT)


def _store(ticker="AAPL", sic="3571", desc="Electronic Computers",
           first="2026-11-04"):
    return {ticker: {"ticker": ticker, "cik": 320193,
                     "source": "SEC:submissions", "sic_code": sic,
                     "sic_description": desc,
                     "retrieved_at_utc": "2026-11-04T08:00:00+00:00",
                     "first_observed_date": first}}


class TestTheConfigIsValidated:
    def test_every_mapping_names_a_declared_sector(self):
        """A typo inventing a twelfth sector must raise, not resolve."""
        assert len(CFG["sectors"]) == 11

    def test_a_sector_outside_the_taxonomy_is_refused(self, tmp_path):
        (tmp_path / "configs").mkdir()
        (tmp_path / "configs" / "usa_sic_sector_map.yaml").write_text(
            yaml.safe_dump({"sectors": ["Technology"],
                            "exact": {"7372": {"sector": "Softwarez"}}}),
            encoding="utf-8")
        with pytest.raises(SectorMapConfigError) as e:
            load_config(tmp_path)
        assert "outside the declared taxonomy" in str(e.value)

    def test_a_missing_config_raises_rather_than_returning_empty(self, tmp_path):
        with pytest.raises(SectorMapConfigError):
            load_config(tmp_path)

    def test_the_taxonomy_matches_the_feature_consumer(self):
        """The resolver must emit what sector_* can actually price."""
        from backend.feature_store.features.sector import _USA_SECTOR_TO_ETF
        assert set(CFG["sectors"]) == set(_USA_SECTOR_TO_ETF)


class TestMappingMethodIsNeverOverstated:
    def test_a_four_digit_override_is_EXACT(self):
        sector, method, conf, review, _ = classify_sic("7372", "software", CFG)
        assert (sector, method, review) == ("Technology", EXACT, VALIDATED)
        assert conf == pytest.approx(0.9)

    def test_a_major_group_rule_is_MAPPED_and_less_confident(self):
        sector, method, conf, review, reason = classify_sic(
            "2043", "Cereal Breakfast Foods", CFG)
        assert (sector, method, review) == ("Consumer Staples", MAPPED,
                                            VALIDATED)
        assert conf == pytest.approx(0.6)
        assert "major group 20" in reason

    def test_exact_and_mapped_are_reported_separately(self):
        """Counting them together would overstate what is known."""
        uni = sorted({t["symbol"] for t in json.loads(
            (_ROOT / "usa" / "reports" / "universe.json")
            .read_text(encoding="utf-8")).get("tickers", [])
            if t.get("symbol")})
        rep = coverage_report(_ROOT, uni)
        assert EXACT in rep["by_mapping_method"]
        assert MAPPED in rep["by_mapping_method"]
        assert rep["by_mapping_method"][EXACT] > 0
        assert rep["by_mapping_method"][MAPPED] > 0

    def test_no_proxy_rule_is_enabled_today(self):
        uni = ["AAPL", "JPM", "XOM"]
        rep = coverage_report(_ROOT, uni)
        assert rep["by_mapping_method"].get("PROXY", 0) == 0


class TestAmbiguousCodesAbstain:
    def test_a_REIT_is_refused_because_SIC_names_a_structure(self):
        sector, method, conf, review, reason = classify_sic(
            "6798", "Real Estate Investment Trusts", CFG)
        assert sector is None
        assert method == UNKNOWN
        assert review == REVIEW_REQUIRED
        assert "mortgage" in reason.lower() or "structure" in reason.lower()

    def test_not_elsewhere_classified_is_refused(self):
        sector, _, _, review, _ = classify_sic(
            "7389", "Services-Business Services, NEC", CFG)
        assert sector is None and review == REVIEW_REQUIRED

    def test_an_unknown_code_is_refused_not_guessed(self):
        sector, method, _, review, reason = classify_sic("9999", "???", CFG)
        assert sector is None and method == UNKNOWN
        assert review == REVIEW_REQUIRED
        assert "no exact or major-group rule" in reason

    def test_a_missing_sic_is_refused_with_a_reason(self):
        sector, method, conf, review, reason = classify_sic(None, None, CFG)
        assert sector is None and method == UNKNOWN and conf == 0.0
        assert "no SIC code" in reason

    def test_coverage_is_not_improved_by_guessing(self):
        """The refusals must stay refused · a regression guard."""
        for code in ("6798", "7389"):
            assert code in (CFG.get("review_required") or {}), (
                "%s was moved out of review_required · if that was "
                "deliberate it needs evidence in the config note" % code)


class TestTheContractIsComplete:
    def test_every_required_field_is_present(self, tmp_path):
        r = resolve(_ROOT, "AAPL", CFG, _store())
        d = r.as_dict()
        for f in ("ticker", "source", "sic_code", "sic_description", "sector",
                  "mapping_method", "confidence", "first_observed_date",
                  "effective_from", "effective_from_basis",
                  "retrieved_at_utc", "review_status",
                  "classification_status"):
            assert f in d, "missing contract field %s" % f

    def test_a_classified_ticker_reports_CLASSIFIED(self):
        r = resolve(_ROOT, "AAPL", CFG, _store())
        assert r.sector == "Technology"
        assert r.classification_status == CLASSIFIED

    def test_an_unresolvable_ticker_reports_UNCLASSIFIED(self):
        r = resolve(_ROOT, "SOMEREIT", CFG,
                    _store("SOMEREIT", "6798", "Real Estate Investment Trusts"))
        assert r.sector is None
        assert r.classification_status == UNCLASSIFIED
        assert r.review_status == REVIEW_REQUIRED

    def test_a_ticker_absent_from_the_store_is_unclassified(self):
        r = resolve(_ROOT, "NOTHERE", CFG, {})
        assert r.sector is None
        assert r.sic_code is None
        assert r.classification_status == UNCLASSIFIED


class TestHistoricalResolutionDoesNotLookAhead:
    def test_effective_from_equals_first_observed_and_says_so(self):
        r = resolve(_ROOT, "AAPL", CFG, _store(first="2026-11-04"))
        assert r.first_observed_date == "2026-11-04"
        assert r.effective_from == "2026-11-04"
        assert r.effective_from_basis == BASIS_FIRST_OBSERVED, (
            "the basis must say the date is an observation, not an "
            "effective date SEC never published")

    def test_a_date_before_first_observation_is_UNAVAILABLE(self):
        r = resolve_asof(_ROOT, "AAPL", date(2020, 1, 2), CFG,
                         _store(first="2026-11-04"))
        assert r.classification_status == UNAVAILABLE
        assert r.sector is None, (
            "backdating today's classification is the lookahead this "
            "whole contract exists to prevent")
        assert "no SIC history" in r.reason

    def test_the_first_observation_date_itself_resolves(self):
        r = resolve_asof(_ROOT, "AAPL", date(2026, 11, 4), CFG,
                         _store(first="2026-11-04"))
        assert r.classification_status == CLASSIFIED
        assert r.sector == "Technology"

    def test_a_later_date_resolves(self):
        r = resolve_asof(_ROOT, "AAPL", date(2026, 12, 31), CFG,
                         _store(first="2026-11-04"))
        assert r.sector == "Technology"

    def test_a_never_observed_ticker_is_unavailable_at_every_date(self):
        r = resolve_asof(_ROOT, "GHOST", date(2026, 11, 4), CFG, {})
        assert r.classification_status == UNAVAILABLE
        assert r.sector is None

    def test_a_reclassification_does_not_rewrite_history(self):
        """Store the EARLIER first_observed_date · a later SIC change
        must not claim to have been true all along."""
        old = _store("ACME", "3571", "Electronic Computers", "2026-06-01")
        r_then = resolve_asof(_ROOT, "ACME", date(2026, 5, 1), CFG, old)
        assert r_then.classification_status == UNAVAILABLE
        r_now = resolve_asof(_ROOT, "ACME", date(2026, 6, 1), CFG, old)
        assert r_now.sector == "Technology"


class TestLiveUniverseCoverage:
    """Read-only · the measured state, so a regression is visible."""

    @staticmethod
    def _uni():
        return sorted({t["symbol"] for t in json.loads(
            (_ROOT / "usa" / "reports" / "universe.json")
            .read_text(encoding="utf-8")).get("tickers", [])
            if t.get("symbol")})

    def test_the_bulk_of_the_universe_is_classified(self):
        rep = coverage_report(_ROOT, self._uni())
        assert rep["n_universe"] == 516
        assert rep["n_classified"] >= 450, rep["n_classified"]
        assert rep["classified_pct"] >= 85.0

    def test_every_classified_sector_is_in_the_taxonomy(self):
        rep = coverage_report(_ROOT, self._uni())
        assert set(rep["by_sector"]) <= set(CFG["sectors"])

    def test_the_unclassified_are_only_the_declared_refusals(self):
        """55 = 26 REITs + 16 NEC + 13 without a SIC."""
        from backend.shared.usa_sector_resolver import resolve_many
        res = resolve_many(_ROOT, self._uni())
        bad = [r for r in res.values() if not r.sector]
        codes = {(r.sic_code or "NO_SIC") for r in bad}
        assert codes <= {"6798", "7389", "6792", "NO_SIC"}, sorted(codes)
        assert all(r.review_status == REVIEW_REQUIRED for r in bad)

    def test_no_classified_ticker_is_left_review_required(self):
        from backend.shared.usa_sector_resolver import resolve_many
        res = resolve_many(_ROOT, self._uni())
        wrong = [t for t, r in res.items()
                 if r.sector and r.review_status == REVIEW_REQUIRED]
        assert wrong == [], wrong


class TestIndiaIsUntouched:
    def test_the_usa_resolver_has_no_india_path(self):
        import backend.shared.usa_sector_resolver as M
        src = Path(M.__file__).read_text(encoding="utf-8")
        for token in ("india", "NSE", ".NS"):
            assert token not in src, (
                "the USA resolver references %r · India must not change as "
                "a side effect of USA-only work" % token)
