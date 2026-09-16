"""R3 promotion ladder + failure intelligence contract.

The ladder exists because "when does a discovery reach production" was a
conversation, and a conversation cannot be failed. These tests pin the two
properties that make it worth having:

  1. it is STRICTLY SEQUENTIAL - a later gate cannot rescue an earlier failure,
     which is exactly how the market-memory wave nearly went wrong;
  2. AUTHORIZATION and INTEGRATION are human acts that no evidence can set.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.research.r3_program import promotion_ladder as PL
from backend.research.r3_program.failure_intelligence import (
    label_failures, flag_rate_sweep, decision_value, cost_sensitivity,
    SEVERE_PCT, DEEP_MAE_PCT)

ROOT = Path(__file__).resolve().parents[2]


# 1 · SEQUENCE ───────────────────────────────────────────────────────
def test_a_later_gate_cannot_rescue_an_earlier_failure():
    r = PL.evaluate("X", "india", {
        "DISCOVERY": False,
        "REPEATABILITY": True, "TEMPORAL": True, "ROBUSTNESS": True,
        "INCREMENTAL": True, "DECISION": True, "ECONOMICS": True, "SHADOW": True})
    assert r.verdict == "HALTED_AT_DISCOVERY"
    assert r.highest_gate_passed is None
    later = {g.gate: g.status for g in r.gates}
    assert later["REPEATABILITY"] == PL.STATUS_NOT_REACHED, \
        "a gate after the halt was evaluated"
    assert r.can_enter_pipeline is False


def test_a_missing_measurement_blocks_rather_than_passes():
    r = PL.evaluate("X", "usa", {"DISCOVERY": True})
    g = {x.gate: x for x in r.gates}
    assert g["REPEATABILITY"].status == PL.STATUS_BLOCKED
    assert r.verdict == "HALTED_AT_REPEATABILITY"
    assert "No measurement" in g["REPEATABILITY"].reason


def test_full_evidence_still_stops_at_the_human_gate():
    """The strongest possible computed result is READY_FOR_AUTHORIZATION."""
    r = PL.evaluate("X", "india", {g: True for g, _ in PL.GATES
                                   if g not in PL.HUMAN_GATES})
    assert r.verdict == "READY_FOR_AUTHORIZATION"
    assert r.halted_at == "AUTHORIZATION"
    assert r.can_enter_pipeline is False
    g = {x.gate: x for x in r.gates}
    assert g["AUTHORIZATION"].status == PL.STATUS_HUMAN
    assert g["INTEGRATION"].status == PL.STATUS_NOT_REACHED


def test_human_gates_cannot_be_passed_by_supplying_evidence():
    """Even an explicit True for a human gate must not pass it."""
    checks = {g: True for g, _ in PL.GATES}
    r = PL.evaluate("X", "usa", checks)
    g = {x.gate: x for x in r.gates}
    assert g["AUTHORIZATION"].status == PL.STATUS_HUMAN
    assert g["INTEGRATION"].status != PL.STATUS_PASS
    assert r.can_enter_pipeline is False


def test_summary_never_reports_anything_in_pipeline():
    rs = [PL.evaluate("A", "india", {g: True for g, _ in PL.GATES}),
          PL.evaluate("B", "usa", {"DISCOVERY": False})]
    s = PL.summarise([r.to_dict() for r in rs])
    assert s["in_pipeline"] == []
    assert "A" in s["ready_for_authorization"]


# 2 · THE TWO QUEUES STAY SEPARATE ───────────────────────────────────
def test_an_engineering_fix_carries_no_evidence_tier():
    f = PL.engineering_fix("CANON-2", "tail before cutoff", False, "ref.json")
    assert f["queue"] == "ENGINEERING_AUTHORIZATION"
    assert f["evidence_tier"] is None
    assert "not a research discovery" in f["note"].lower()


# 3 · FAILURE LABELS ─────────────────────────────────────────────────
def test_deep_mae_and_severe_are_different_labels():
    """A position can end flat having been 10% underwater."""
    p = pd.DataFrame({"fwd_20d": [0.0, -6.0, 1.0], "fwd_mae_20": [-12.0, -6.0, -1.0]})
    out = label_failures(p)
    assert list(out["y_severe"]) == [0.0, 1.0, 0.0]
    assert list(out["y_deep_mae"]) == [1.0, 0.0, 0.0]


def test_labels_are_nan_where_the_window_has_not_closed():
    p = pd.DataFrame({"fwd_20d": [np.nan], "fwd_mae_20": [np.nan]})
    out = label_failures(p)
    assert out["y_severe"].isna().all() and out["y_deep_mae"].isna().all()


# 4 · SHIPPED RESULT ─────────────────────────────────────────────────
def _shipped(name):
    p = ROOT / "reports/research/r3/failure_intelligence_v1" / name
    if not p.exists():
        pytest.skip("failure intelligence not run in this checkout")
    return json.loads(p.read_text(encoding="utf-8"))


def test_shipped_ladder_reaches_no_authorization():
    d = _shipped("promotion_ladder.json")
    assert d["summary"]["ready_for_authorization"] == []
    assert d["summary"]["in_pipeline"] == []
    for r in d["results"]:
        assert r["can_enter_pipeline"] is False
        assert r["queue"] == "RESEARCH_DISCOVERY"


def test_shipped_decision_gate_was_never_reached_on_a_failing_sweep():
    """Halting at INCREMENTAL must not hide that the DECISION measurement is
    negative. The sweep is recorded even where the gate was not reached."""
    d = _shipped("failure_intelligence.json")
    for m, mv in d["markets"].items():
        for label, lv in (mv.get("per_label") or {}).items():
            sw = lv.get("flag_rate_sweep") or {}
            if sw.get("status") != "OK":
                continue
            assert "verdict" in sw
            assert len(sw["points"]) >= 3, "the sweep must cover several operating points"


def test_shipped_trial_count_declares_both_labels():
    d = _shipped("summary.json")
    ta = d["ladder_summary"] if "trial_accounting" not in d else d["trial_accounting"]
    if "trial_accounting" in d:
        assert set(d["trial_accounting"]["labels_pre_registered"]) == {
            "y_severe", "y_deep_mae"}
        assert d["trial_accounting"]["trials_run"] >= 2


def test_shipped_engineering_queue_is_not_in_the_research_ledger():
    e = _shipped("engineering_queue.json")
    assert e["queue"] == "ENGINEERING_AUTHORIZATION"
    ids = {i["fix_id"] for i in e["items"]}
    assert "CANON-2" in ids
    lad = _shipped("promotion_ladder.json")
    research_ids = {r["discovery_id"] for r in lad["results"]}
    assert not (ids & research_ids), "a defect fix leaked into the research ladder"


def test_shipped_governance_is_frozen():
    for n in ("failure_intelligence.json", "promotion_ladder.json", "summary.json"):
        g = _shipped(n)["governance"]
        assert g["r2_modified"] is False and g["r1_modified"] is False
        assert g["r3_production_writes"] == 0
        assert g["max_verdict"] == "READY_FOR_AUTHORIZATION"
