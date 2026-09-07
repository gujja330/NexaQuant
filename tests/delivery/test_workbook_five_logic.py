"""AEGIS · five-sheet builder · unit tests for the shared computation.

These test `backend/delivery/sheets/workbook_five.py` directly, with no
workbook and no artifacts, so the rules hold even on a day when the
delivered XLSX happens to contain no interesting rows.

Covered:
  · the loss/stop escalation ladder (R1 loss visibility)
  · momentum producer funnel reconciliation (declared vs evaluated)
  · momentum staleness detection
  · Momentum -> R2 lifecycle reconciliation, including the two mismatch
    conditions that must never be reported silently
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.delivery.sheets import workbook_five as wf
from backend.delivery.sheets.workbook_five import (
    STATE_NORMAL, STATE_WATCH, STATE_BREACH, STATE_DEEP_LOSS,
    escalation_state, FIVE_SHEETS,
)

ROOT = Path(__file__).resolve().parents[2]


# ── Escalation ladder ─────────────────────────────────────────────────


def test_normal_position_is_normal():
    assert escalation_state(pnl_pct=3.2, current_price=110.0, stop=90.0,
                            stop_distance_pct=18.2) == STATE_NORMAL


def test_price_at_or_below_stop_is_a_breach():
    assert escalation_state(-4.0, 90.0, 90.0, 0.0) == STATE_BREACH
    assert escalation_state(-4.0, 89.9, 90.0, -0.1) == STATE_BREACH


def test_deep_loss_outranks_breach():
    """A position both deeply underwater AND through its stop reports the
    more severe state · the operator must see the worse of the two."""
    assert escalation_state(-22.0, 70.0, 90.0, -28.6) == STATE_DEEP_LOSS


def test_watch_on_moderate_loss_and_on_stop_proximity():
    assert escalation_state(-9.0, 91.0, 80.0, 12.1) == STATE_WATCH
    # Healthy P&L but hugging the stop is still WATCH.
    assert escalation_state(2.0, 100.0, 98.0, 2.0) == STATE_WATCH


def test_missing_stop_does_not_manufacture_a_breach():
    """No canonical stop must not be silently rendered as 'safe' via a
    breach test against None · nor as a breach."""
    assert escalation_state(1.0, 100.0, None, None) == STATE_NORMAL
    assert escalation_state(-20.0, 100.0, None, None) == STATE_DEEP_LOSS


def test_thresholds_are_the_documented_values():
    """Pinned · these are display thresholds. Changing them changes what
    the operator is warned about and must be a deliberate edit."""
    assert wf.DEEP_LOSS_PCT == -15.0
    assert wf.WATCH_LOSS_PCT == -8.0
    assert wf.WATCH_STOP_DISTANCE_PCT == 3.0


def test_five_sheet_names_are_pinned():
    assert FIVE_SHEETS == ["R1", "R2", "MOMENTUM", "DAILY RECOMMENDATION",
                           "EXIT"]


# ── Momentum funnel ───────────────────────────────────────────────────


FUNNEL_KEYS = ("n_universe", "n_evaluated", "n_unreadable",
               "n_insufficient_history", "n_ignored_no_momentum")


def test_momentum_report_declares_funnel_counters():
    """CODE contract · the producer must DECLARE every funnel counter.

    This is the hard gate and it always runs. The artifact test below is
    deliberately allowed to skip on a pre-schema file, so this test is what
    guarantees a regression (producer stops emitting counters) is caught
    even on a day when no fresh artifact exists.
    """
    from dataclasses import fields
    from backend.research.short_term_momentum import MomentumReport
    declared = {f.name for f in fields(MomentumReport)}
    missing = [k for k in FUNNEL_KEYS if k not in declared]
    assert not missing, (
        "MomentumReport no longer declares %s · the truthful funnel was "
        "removed, and a total data failure would again be indistinguishable "
        "from a quiet market" % missing)


@pytest.mark.parametrize("market", ["india", "usa"])
def test_producer_funnel_reconciles(market):
    """declared == unreadable + insufficient + evaluated, and
    evaluated == no-signal + candidates.

    A funnel that does not add up means tickers are vanishing silently ·
    exactly the condition that hid the 11-day producer outage.

    SKIPS on an artifact written before the counters existed. That is not
    a code defect: the committed momentum JSON can legitimately predate
    this schema (on CI the delivery-test job runs before the market's own
    producer step, and the other market's file is whatever was last
    committed). The code contract is pinned by
    `test_momentum_report_declares_funnel_counters` above, which never
    skips · so a real regression still fails the suite.
    """
    p = ROOT / "reports" / "research" / ("short_term_momentum_%s.json" % market)
    if not p.exists():
        pytest.skip("producer artifact absent")
    d = json.loads(p.read_text(encoding="utf-8"))
    missing = [k for k in FUNNEL_KEYS if k not in d]
    if missing:
        pytest.skip(
            "artifact asof=%s predates the funnel-counter schema (missing "
            "%s) · rebuild with `python -m "
            "backend.research.short_term_momentum --market %s`"
            % (d.get("asof"), missing, market))
    assert (d["n_unreadable"] + d["n_insufficient_history"]
            + d["n_evaluated"]) == d["n_universe"], (
        "declared universe does not reconcile: %s" % d)
    assert (d["n_ignored_no_momentum"] + len(d.get("candidates") or [])
            == d["n_evaluated"]), (
        "evaluated count does not reconcile against candidates: %s" % d)


@pytest.mark.parametrize("market", ["india", "usa"])
def test_declared_universe_is_not_the_evaluated_count(market):
    """The two numbers must be published separately.

    They may be EQUAL on a clean day · what must never happen is only one
    of them existing, which is how 'declared' got rendered as 'scanned'.
    """
    p = ROOT / "reports" / "research" / ("short_term_momentum_%s.json" % market)
    if not p.exists():
        pytest.skip("producer artifact absent")
    d = json.loads(p.read_text(encoding="utf-8"))
    if "n_evaluated" not in d:
        pytest.skip("artifact asof=%s predates the funnel-counter schema"
                    % d.get("asof"))
    assert d["n_universe"] >= d["n_evaluated"], (
        "evaluated cannot exceed the declared universe")


def test_momentum_view_flags_stale_producer():
    """A producer as-of older than the reporting as-of is STALE.

    This is the 11-day outage detector · without it a frozen producer
    renders as a quiet market.
    """
    ledger = {"producer_asof": "2026-08-27", "producer_funnel": {},
              "by_terminal_state": {}, "entries": []}
    view = wf._momentum_view(ROOT, "india", "2026-09-07", ledger)
    assert view["stale"] is True
    assert view["producer_asof"] == "2026-08-27"
    assert view["reporting_asof"] == "2026-09-07"


def test_momentum_view_fresh_producer_is_not_stale():
    ledger = {"producer_asof": "2026-09-07", "producer_funnel": {},
              "by_terminal_state": {}, "entries": []}
    assert wf._momentum_view(ROOT, "india", "2026-09-07", ledger)["stale"] is False


def test_momentum_view_surfaces_out_of_universe_candidates(tmp_path):
    """A zero in-universe count must be distinguishable from a quiet market.

    India on 2026-09-07 found 2 real momentum candidates, both outside the
    50-name production universe. Reporting only 'candidates: 0' would read
    as 'nothing moved' when in fact something moved and was filtered.
    """
    root = tmp_path
    (root / "reports" / "research").mkdir(parents=True)
    (root / "reports" / "research" / "short_term_momentum_india.json").write_text(
        json.dumps({"asof": "2026-09-07", "n_universe": 230,
                    "candidates": [{"ticker": "FOO", "verdict": "AVOID"},
                                    {"ticker": "BAR", "verdict": "PUMP_RISK"}]}),
        encoding="utf-8")
    ledger = {"producer_asof": "2026-09-07",
              "producer_funnel": {"n_declared_universe": 230,
                                   "n_evaluated": 230, "n_candidates": 2},
              "by_terminal_state": {}, "entries": []}
    view = wf._momentum_view(root, "india", "2026-09-07", ledger)
    assert view["n_in_universe_candidates"] == 0
    assert len(view["out_of_universe"]) == 2, (
        "candidates filtered by the production universe must still be shown")


# ── Momentum -> R2 reconciliation ─────────────────────────────────────


def _views(r2_tickers, asof="2026-09-07"):
    v = wf.Views(market="india", asof=asof)
    for t in r2_tickers:
        v.r2.append(wf.PositionView(
            source="R2", pid="IND-R2-%s" % t, ticker=t, sector="X",
            entry_date=asof, entry_price=100.0, current_price=101.0,
            pnl_pct=1.0, holding_days=0, stop=90.0, stop_type="atr",
            stop_source="dynamic_risk_v2", stop_distance_pct=10.9,
            target=130.0, confidence=70.0,
            confidence_source="recommendations.json:confidence",
            target_distance_pct=28.7, rr=2.63, state=STATE_NORMAL,
            action="HOLD", reason="ok"))
    v.momentum = {"n_declared_universe": 230, "n_evaluated": 230,
                  "n_unreadable": 0, "n_insufficient_history": 0,
                  "n_ignored_no_momentum": 228, "n_candidates": 2,
                  "n_production_universe": 50,
                  "n_out_of_universe_dropped": 0,
                  "n_in_universe_candidates": 2, "n_accepted": 1,
                  "n_watch": 1, "n_rejected": 0, "n_no_evidence": 0,
                  "conservation_ok": True}
    return v


def test_reconciliation_reports_every_stage():
    v = _views([])
    ledger = {"entries": [{"ticker": "AAA", "terminal_state": "ACCEPTED"}]}
    rec = wf._reconcile(ROOT, "india", "2026-09-07", v, ledger)
    labels = [s[0] for s in rec["stages"]]
    assert len(labels) == 7, labels
    assert any("Declared universe" in l for l in labels)
    assert any("Actually evaluated" in l for l in labels)
    assert any("R2 sheet ACTIVE" in l for l in labels)


def test_reconciliation_flags_accepted_but_never_opened():
    """A momentum ACCEPT that produced no R2 entry must be reported ·
    never dropped silently."""
    v = _views([])
    ledger = {"entries": [{"ticker": "AAA", "terminal_state": "ACCEPTED"}]}
    rec = wf._reconcile(ROOT, "india", "2026-09-07", v, ledger)
    assert rec["mismatches"], "accepted-but-not-opened must be reported"
    assert "AAA" in rec["mismatches"][0]
    # And it must NOT be phrased as a defect · R2 eligibility is a real gate.
    assert "R2 eligibility is a separate gate" in rec["mismatches"][0]


def test_reconciliation_flags_r2_entry_with_no_momentum_accept():
    """Guards the 'never bypass R2 eligibility by copying Momentum' rule
    from the other direction · an R2 entry with no upstream accept."""
    v = _views(["ZZZ"])
    ledger = {"entries": [{"ticker": "AAA", "terminal_state": "ACCEPTED"}]}
    rec = wf._reconcile(ROOT, "india", "2026-09-07", v, ledger)
    joined = " ".join(rec["mismatches"])
    assert "ZZZ" in joined, "unexplained R2 entry must be reported"


def test_reconciliation_reports_broken_ledger_conservation():
    v = _views([])
    v.momentum["conservation_ok"] = False
    rec = wf._reconcile(ROOT, "india", "2026-09-07", v, {"entries": []})
    assert any("CONSERVATION BROKEN" in m for m in rec["mismatches"])


def test_reconciliation_is_quiet_when_everything_matches():
    v = _views(["AAA"])
    ledger = {"entries": [{"ticker": "AAA", "terminal_state": "ACCEPTED"}]}
    rec = wf._reconcile(ROOT, "india", "2026-09-07", v, ledger)
    assert rec["mismatches"] == [], rec["mismatches"]


# -- Confidence sourcing + investable daily recommendations ------------


def _write_recs(root, market, recs, asof="2026-09-07"):
    d = (root / "usa" / "reports") if market == "usa" else (root / "reports")
    d.mkdir(parents=True, exist_ok=True)
    (d / "recommendations.json").write_text(
        json.dumps({"asof": asof, "market": market, "recommendations": recs}),
        encoding="utf-8")


def test_daily_recommendations_expose_confidence_and_investables(tmp_path):
    """action == NEW_POSITION is the engine's INVESTABLE verdict."""
    _write_recs(tmp_path, "india", [
        {"ticker": "AAA.NS", "action": "NEW_POSITION", "confidence": 0.82,
         "composite_decision_score": 70.0, "recommendation": "Buy"},
        {"ticker": "BBB.NS", "action": "NO_ACTION", "confidence": 0.55,
         "composite_decision_score": 30.0, "recommendation": "Hold"},
    ])
    out = wf._daily_recommendations(tmp_path, "india")
    assert out["n"] == 2
    assert [r["ticker"] for r in out["new_positions"]] == ["AAA.NS"]
    assert out["by_ticker"]["AAA"]["confidence"] == 0.82
    assert out["asof"] == "2026-09-07"


def test_daily_recommendations_report_missing_artifact_without_crashing(tmp_path):
    out = wf._daily_recommendations(tmp_path, "usa")
    assert out["n"] == 0 and out["new_positions"] == []
    assert out["by_ticker"] == {}


def test_confidence_saturation_is_detected(tmp_path):
    """India's engine returns 1.0 for most names · a Confidence column that
    does not discriminate must be flagged, not presented as conviction."""
    _write_recs(tmp_path, "india", [
        {"ticker": "A", "action": "NO_ACTION", "confidence": 1.0},
        {"ticker": "B", "action": "NO_ACTION", "confidence": 1.0},
        {"ticker": "C", "action": "NO_ACTION", "confidence": 0.9},
    ])
    out = wf._daily_recommendations(tmp_path, "india")
    assert out["confidence_saturated"] is True
    assert out["confidence_stats"]["pct_at_max"] == pytest.approx(66.7, abs=0.1)


def test_confidence_spread_is_not_flagged_as_saturated(tmp_path):
    _write_recs(tmp_path, "usa", [
        {"ticker": "A", "action": "NO_ACTION", "confidence": 0.30},
        {"ticker": "B", "action": "NO_ACTION", "confidence": 0.65},
        {"ticker": "C", "action": "NO_ACTION", "confidence": 0.90},
    ])
    out = wf._daily_recommendations(tmp_path, "usa")
    assert out["confidence_saturated"] is False


def test_new_positions_sorted_by_conviction(tmp_path):
    _write_recs(tmp_path, "usa", [
        {"ticker": "LOW", "action": "NEW_POSITION", "confidence": 0.5,
         "composite_decision_score": 10.0},
        {"ticker": "HIGH", "action": "NEW_POSITION", "confidence": 0.5,
         "composite_decision_score": 95.0},
    ])
    out = wf._daily_recommendations(tmp_path, "usa")
    assert [r["ticker"] for r in out["new_positions"]] == ["HIGH", "LOW"]


def test_investable_recommendations_never_enter_r2():
    """CEO: new daily recommendations go to the sheets they belong to.

    R2 entry requires R2 eligibility · a recommendation may surface as an
    R1/candidate row but must never be written onto the R2 production
    sheet, which is what `build_views` guarantees by only appending to
    `r1_new`.
    """
    import inspect
    src = inspect.getsource(wf.build_views)
    marker = src.index("NEW TODAY")
    tail = src[marker:marker + 2000]
    assert "v.r1_new.append" in tail
    assert "v.r2.append" not in tail, (
        "investable daily recommendations are being written onto the R2 "
        "production sheet · that bypasses R2 eligibility")


def test_r3_ledger_refuses_a_future_asof(tmp_path):
    """A shadow ledger must never hold a record dated after today.

    Demonstrated live: a stray `--asof <tomorrow>` wrote 566 future-dated
    rows. A prospective evidence record cannot predate its own
    observation, so the writer refuses rather than trusting the caller.
    """
    from datetime import date, timedelta
    from backend.research.r3.shadow_ledger import append_shadow_pick
    future = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="future as-of"):
        append_shadow_pick(tmp_path, "usa", "AAPL", future,
                           r3_score=None, r3_calibrated_p=None,
                           action="NO_MODEL", features={})


def test_r3_ledger_accepts_today(tmp_path):
    from datetime import date
    from backend.research.r3.shadow_ledger import append_shadow_pick
    rec = append_shadow_pick(tmp_path, "usa", "AAPL", date.today().isoformat(),
                             r3_score=None, r3_calibrated_p=None,
                             action="NO_MODEL", features={})
    assert rec["runner"] == "R3" and rec["shadow_only"] is True
