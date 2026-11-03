"""Risk alerts · advisory, and provably not a second way into the universe.

The test this module exists for is
`test_running_the_alert_pass_does_not_change_the_selection`. Everything
else is detail. An advisory channel that quietly grows the selected set
would be the alias-drift bug class again - a consumer holding its own
private copy of what "selected" means - and the instruction was explicit
that the mechanism must not bypass the main selector.

tmp_path-isolated. No live ledger, registry or report is written.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from backend.universe import risk_alerts as RA
from backend.universe import top_selection as T


def _rec(ticker, action, **kw):
    r = {"ticker": ticker, "action": action, "calibrated_confidence": 0.5,
         "ensemble_score": 0.1}
    r.update(kw)
    return r


def _snapshot(n=40, asof="2026-11-03"):
    return pd.DataFrame([{
        "ticker": "T%02d" % i, "asof": asof, "sector": "Tech",
        "close": 100.0 + i, "volume": 1e6 + i,
        "return_20d_pct": float(i), "return_60d_pct": float(i),
        "adx_14": 20.0, "price_above_sma50": 1, "price_above_sma200": 1,
        "volatility_20d": 20.0, "max_drawdown_60d_pct": -5.0,
        "hist_ticker_win_rate": 50.0, "hist_ticker_n_trades": 5,
    } for i in range(n)])


# ------------------------------------------------- the load-bearing test

class TestAlertsDoNotBypassTheSelector:
    def test_running_the_alert_pass_does_not_change_the_selection(self, tmp_path):
        """The selected set must be identical with and without alerts."""
        snap = _snapshot(40)
        cfg = {"universe_selection_enabled": True, "target_count": 10,
               "preserve_existing_universe": False, "min_completeness": 0.0}
        sel_a, audit_a = T.select(tmp_path, "usa", snap, "2026-11-03", cfg)
        before = json.dumps(audit_a["selected_tickers"], sort_keys=True)

        recs = [_rec("T%02d" % i, "STRONG SELL") for i in range(40)]
        rep = RA.build(tmp_path, "usa", recommendations=recs,
                       selected_tickers=audit_a["selected_tickers"],
                       asof="2026-11-03", held=set())
        assert rep["n_alerts"] > 0, "the fixture must actually raise alerts"

        sel_b, audit_b = T.select(tmp_path, "usa", snap, "2026-11-03", cfg)
        after = json.dumps(audit_b["selected_tickers"], sort_keys=True)
        assert before == after
        assert list(sel_a["ticker"]) == list(sel_b["ticker"])

    def test_the_report_carries_no_selection_of_its_own(self, tmp_path):
        recs = [_rec("AAA", "SELL")]
        rep = RA.build(tmp_path, "usa", recommendations=recs,
                       selected_tickers=["BBB"], asof="2026-11-03", held=set())
        assert "selected_tickers" not in rep
        assert rep["contract"]["alters_selection"] is False
        assert rep["contract"]["enters_r2_lifecycle"] is False

    def test_every_alert_record_declares_itself_advisory(self, tmp_path):
        recs = [_rec("A%d" % i, "SELL") for i in range(5)]
        rep = RA.build(tmp_path, "usa", recommendations=recs,
                       selected_tickers=[], asof="2026-11-03", held=set())
        assert len(rep["alerts"]) == 5
        for a in rep["alerts"]:
            assert a["bypasses_selector"] is False
            assert a["action_taken"] == "NONE"

    def test_the_input_sequence_is_not_mutated(self, tmp_path):
        sel = ["AAA", "BBB"]
        recs = [_rec("CCC", "SELL")]
        RA.build(tmp_path, "usa", recommendations=recs, selected_tickers=sel,
                 asof="2026-11-03", held=set())
        assert sel == ["AAA", "BBB"]


# ------------------------------------------------------------- what alerts

class TestWhatRaisesAnAlert:
    def test_a_selected_name_never_alerts_however_bad_its_signal(self, tmp_path):
        recs = [_rec("AAA", "STRONG SELL")]
        rep = RA.build(tmp_path, "usa", recommendations=recs,
                       selected_tickers=["AAA"], asof="2026-11-03", held=set())
        assert rep["n_alerts"] == 0, "the selector is already watching it"

    def test_an_excluded_sell_alerts(self, tmp_path):
        recs = [_rec("AAA", "SELL")]
        rep = RA.build(tmp_path, "usa", recommendations=recs,
                       selected_tickers=["BBB"], asof="2026-11-03", held=set())
        assert rep["n_alerts"] == 1
        assert rep["alerts"][0]["alert"] == RA.ALERT_EXCLUDED_SELL

    def test_an_excluded_buy_does_not_alert(self, tmp_path):
        """A foregone opportunity is not a risk · conflating them would
        turn this into a second recommendation feed."""
        recs = [_rec("AAA", "STRONG BUY")]
        rep = RA.build(tmp_path, "usa", recommendations=recs,
                       selected_tickers=["BBB"], asof="2026-11-03", held=set())
        assert rep["n_alerts"] == 0
        assert rep["signal_counts"]["buy"] == 1

    def test_an_excluded_hold_does_not_alert(self, tmp_path):
        recs = [_rec("AAA", "HOLD")]
        rep = RA.build(tmp_path, "usa", recommendations=recs,
                       selected_tickers=["BBB"], asof="2026-11-03", held=set())
        assert rep["n_alerts"] == 0

    def test_a_sell_on_a_held_but_excluded_name_is_critical(self, tmp_path):
        """This should be impossible · the open-position exemption covers
        every holding. If it fires, that exemption has failed."""
        recs = [_rec("AAA", "SELL")]
        rep = RA.build(tmp_path, "usa", recommendations=recs,
                       selected_tickers=["BBB"], asof="2026-11-03",
                       held={"AAA"})
        assert rep["n_critical"] == 1
        a = rep["alerts"][0]
        assert a["severity"] == RA.SEV_CRITICAL
        assert a["alert"] == RA.ALERT_EXCLUDED_HELD
        assert a["held"] is True

    def test_critical_alerts_sort_first(self, tmp_path):
        recs = [_rec("ZZZ", "SELL"), _rec("AAA", "SELL")]
        rep = RA.build(tmp_path, "usa", recommendations=recs,
                       selected_tickers=[], asof="2026-11-03", held={"ZZZ"})
        assert rep["alerts"][0]["ticker"] == "ZZZ"


class TestSignalSpellingDrift:
    """India ships "STRONG SELL", the percentile classifier "STRONG_SELL"."""

    @pytest.mark.parametrize("sig", ["SELL", "STRONG SELL", "STRONG_SELL",
                                     "strong sell", " Sell ", "REDUCE", "EXIT"])
    def test_both_spellings_of_every_sell_are_recognised(self, sig):
        assert RA.is_sell(sig) is True

    @pytest.mark.parametrize("sig", ["BUY", "STRONG BUY", "STRONG_BUY",
                                     "strong_buy", "ACCUMULATE"])
    def test_both_spellings_of_every_buy_are_recognised(self, sig):
        assert RA.is_buy(sig) is True and RA.is_sell(sig) is False

    @pytest.mark.parametrize("sig", ["HOLD", "", None, "INSUFFICIENT_DATA"])
    def test_non_actionable_is_neither(self, sig):
        assert RA.is_sell(sig) is False and RA.is_buy(sig) is False

    def test_underscore_and_space_spellings_alert_identically(self, tmp_path):
        a = RA.build(tmp_path, "usa", recommendations=[_rec("X", "STRONG SELL")],
                     selected_tickers=[], asof="2026-11-03", held=set())
        b = RA.build(tmp_path, "usa", recommendations=[_rec("X", "STRONG_SELL")],
                     selected_tickers=[], asof="2026-11-03", held=set())
        assert a["n_alerts"] == b["n_alerts"] == 1


class TestTickerNormalisation:
    def test_an_india_suffix_matches_a_bare_selected_ticker(self, tmp_path):
        """The bug that made the open-position exemption inert on India."""
        recs = [_rec("AARTIIND.NS", "SELL")]
        rep = RA.build(tmp_path, "india", recommendations=recs,
                       selected_tickers=["AARTIIND"], asof="2026-11-03",
                       held=set())
        assert rep["n_alerts"] == 0, "same name · must not alert"

    def test_a_bare_recommendation_matches_a_suffixed_holding(self, tmp_path):
        recs = [_rec("AARTIIND", "SELL")]
        rep = RA.build(tmp_path, "india", recommendations=recs,
                       selected_tickers=[], asof="2026-11-03",
                       held={"AARTIIND.NS"})
        assert rep["n_critical"] == 1

    @pytest.mark.parametrize("t", ["RELIANCE", "RELIANCE.NS", "reliance.ns",
                                   " RELIANCE.BO "])
    def test_every_spelling_collapses_to_one_identity(self, t):
        assert RA.bare_ticker(t) == "RELIANCE"


# -------------------------------------------------------------- coverage

class TestCoverageIsReportedByFamily:
    def test_a_blended_number_would_hide_the_sell_loss(self):
        """The live USA shape: 12 of 12 BUYs, 3 of 6 SELLs.

        Blended that is 83.33%, which reads as a small loss. By family it
        is a 50% miss rate on exactly the signals risk control needs, and
        that is the number that changed the design.
        """
        recs = ([_rec("B%d" % i, "BUY") for i in range(12)]
                + [_rec("S%d" % i, "SELL") for i in range(6)])
        sel = ["B%d" % i for i in range(12)] + ["S0", "S1", "S2"]
        cov = RA.coverage(recs, sel)
        assert cov["BUY"]["coverage_pct"] == 100.0
        assert cov["SELL"]["coverage_pct"] == 50.0
        assert cov["ALL_ACTIONABLE"]["coverage_pct"] == 83.33
        assert cov["SELL"]["missed"] == ["S3", "S4", "S5"]

    def test_missed_names_are_listed_not_just_counted(self):
        recs = [_rec("AAA", "SELL"), _rec("BBB", "SELL")]
        cov = RA.coverage(recs, ["AAA"])
        assert cov["SELL"]["missed"] == ["BBB"]

    def test_full_coverage_reports_an_empty_missed_list(self):
        recs = [_rec("AAA", "SELL"), _rec("BBB", "BUY")]
        cov = RA.coverage(recs, ["AAA", "BBB"])
        assert cov["ALL_ACTIONABLE"]["coverage_pct"] == 100.0
        assert cov["SELL"]["missed"] == [] and cov["BUY"]["missed"] == []

    def test_no_actionable_signals_yields_none_not_zero_percent(self):
        cov = RA.coverage([_rec("AAA", "HOLD")], ["AAA"])
        assert cov["ALL_ACTIONABLE"]["coverage_pct"] is None
        assert cov["SELL"]["coverage_pct"] is None


class TestTheKnownResidualIsRecorded:
    def test_the_three_missed_usa_sells_are_named_in_the_artifact(self, tmp_path):
        """"Do not silently remove the three missed non-held SELL
        candidates" · so they are written into every report."""
        rep = RA.build(tmp_path, "usa", recommendations=[],
                       selected_tickers=[], asof="2026-11-03", held=set())
        assert rep["known_residual"]["tickers"] == ["AKAM", "DAL", "GPC"]

    def test_the_artifact_is_written_under_reports_universe(self, tmp_path):
        rep = RA.build(tmp_path, "usa", recommendations=[_rec("A", "SELL")],
                       selected_tickers=[], asof="2026-11-03", held=set())
        p = RA.write(tmp_path, "usa", rep)
        assert p.parent.name == "universe"
        assert p.name == "risk_alerts_usa_2026-11-03.json"
        assert json.loads(p.read_text(encoding="utf-8"))["n_alerts"] == 1

    def test_building_is_deterministic(self, tmp_path):
        recs = [_rec("A%d" % i, "SELL") for i in range(10)]
        kw = dict(recommendations=recs, selected_tickers=["A1"],
                  asof="2026-11-03", held={"A2"})
        a = RA.build(tmp_path, "usa", **kw)
        b = RA.build(tmp_path, "usa", **kw)
        a.pop("generated_utc"), b.pop("generated_utc")
        assert a == b
