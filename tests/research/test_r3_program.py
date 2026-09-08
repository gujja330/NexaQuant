"""R3 programme gates.

These tests defend the properties that make the freeze trustworthy. Most
of them assert that the code REFUSES things - a research harness earns
trust by what it declines to conclude, not by what it reports.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.research.r3_program import core, freeze, master_status

ROOT = Path(__file__).resolve().parents[2]


# ── units of evidence ───────────────────────────────────────────────────

def test_effective_units_uses_floor_not_ceil():
    rows = [{"ticker": "A", "date": "2026-08-01"},
            {"ticker": "A", "date": "2026-08-09"}]      # 8-day span < 10
    assert core.effective_units(rows, 10) == 1          # ceil would give 1 too
    rows2 = [{"ticker": "A", "date": "2026-08-01"},
             {"ticker": "A", "date": "2026-08-26"}]     # 25 days -> 2, not 3
    assert core.effective_units(rows2, 10) == 2


def test_ticker_units_and_date_units_are_reported_separately():
    rows = [{"ticker": "T%d" % i, "date": "2026-08-11"} for i in range(400)]
    a = core.substrate_assessment(rows)
    assert a["effective_ticker_units"] == 400
    assert a["effective_date_units"] == 1
    assert a["binding_constraint"] == "dates"


def test_evidence_tier_is_driven_by_units_not_rows():
    assert core.evidence_tier(1) == "OBSERVATION"
    assert core.evidence_tier(50) == "VALIDATION_CANDIDATE"


# ── the single-episode gate · the decisive discovery ────────────────────

def test_single_episode_is_detected():
    rows = ([{"ticker": "T%d" % i, "date": "2026-08-11"} for i in range(486)]
            + [{"ticker": "T%d" % i, "date": "2026-08-12"} for i in range(486)]
            + [{"ticker": "T%d" % i, "date": "2026-08-20"} for i in range(20)])
    d = core.date_concentration(rows)
    assert d["single_episode"] is True
    assert d["top_2_dates_share_pct"] >= 90


def test_well_spread_cohort_is_not_flagged_single_episode():
    rows = [{"ticker": "T%d" % i, "date": "2026-08-%02d" % (1 + i % 15)}
            for i in range(300)]
    assert core.date_concentration(rows)["single_episode"] is False


def test_usa_cohort_is_actually_a_single_episode():
    """The finding that blocked every USA supervised branch."""
    rows = core.load_pop(ROOT, "usa", features=["confidence_pct"])
    if len(rows) < 100:
        pytest.skip("usa cohort unavailable")
    assert core.date_concentration(rows)["single_episode"] is True


# ── sector is not a sector ──────────────────────────────────────────────

def test_cap_bucket_is_not_accepted_as_sector():
    rows = [{"ticker": "T%d" % i, "sector": "Large-Cap"} for i in range(97)] \
        + [{"ticker": "X%d" % i, "sector": "Other"} for i in range(3)]
    v = core.sector_validity(rows)
    assert v["usable_as_sector"] is False


def test_real_sector_labels_are_accepted():
    secs = ["Financials", "Energy", "Health", "Tech", "Utilities"]
    rows = [{"ticker": "T%d" % i, "sector": secs[i % 5]} for i in range(200)]
    assert core.sector_validity(rows)["usable_as_sector"] is True


# ── decision value is not AUC ───────────────────────────────────────────

def test_policy_that_changes_nothing_has_no_value():
    rows = [{"ticker": "T%d" % (i % 20), "fwd": (i % 7) - 3.0}
            for i in range(200)]
    dv = core.decision_value(rows, lambda r: "TAKE")
    assert dv["delta_mean_pp"] == 0.0


def test_cost_is_charged_to_both_sides():
    rows = [{"ticker": "T%d" % (i % 20), "fwd": 1.0} for i in range(100)]
    dv = core.decision_value(rows, lambda r: "TAKE", cost_pct=0.25)
    assert dv["baseline_take_all"]["mean_pct"] == 0.75
    assert dv["policy"]["mean_pct"] == 0.75


def test_bootstrap_resamples_names_not_rows():
    src = Path(core.__file__).read_text(encoding="utf-8")
    assert "by.setdefault(r[\"ticker\"], []).append(i)" in src
    assert "rng.choice(len(names)" in src


# ── refusals ────────────────────────────────────────────────────────────

def test_decision_models_refuse_on_single_episode():
    from backend.research.r3_program import decision_models
    rep = decision_models.load(ROOT, "usa")
    if not rep:
        pytest.skip("usa decision report not generated")
    for t, r in rep["by_target"].items():
        assert r["disposition"] == "INSUFFICIENT_SUBSTRATE"
        assert "SINGLE EPISODE" in r["reason"]


def test_no_branch_reaches_validated_without_date_evidence():
    st = master_status.load(ROOT) or master_status.build(ROOT)
    for k, c in st["classes"].items():
        assert c["disposition"] != "VALIDATED", (
            "%s claims VALIDATED · no class may on 1-2 date units" % k)


def test_abstain_band_is_fixed_in_advance():
    from backend.research.r3_program import decision_models
    assert decision_models.ABSTAIN_BAND == (0.4, 0.6)
    src = Path(decision_models.__file__).read_text(encoding="utf-8")
    assert "never tuned on results" in src


# ── preservation of negative results ────────────────────────────────────

def test_wave1d_remains_invalidated():
    st = master_status.load(ROOT) or master_status.build(ROOT)
    p = st["preserved_historical_results"]
    assert p["II.1-GBM · Wave 1D headline"]["disposition"] == "INVALIDATED"


def test_sequence_models_remain_rejected():
    st = master_status.load(ROOT) or master_status.build(ROOT)
    p = st["preserved_historical_results"]
    assert p["R3-C-TEMP · Wave 1C sequence models"]["disposition"] == "REJECTED"


def test_r3g_remains_frozen():
    st = master_status.load(ROOT) or master_status.build(ROOT)
    assert st["classes"]["R3-G"]["disposition"] == "FROZEN"


def test_registry_still_carries_the_invalidation():
    src = (ROOT / "backend" / "research" / "research_registry.py").read_text(
        encoding="utf-8")
    assert "WAVE 1D RESULT INVALIDATED" in src
    assert "BRANCH FROZEN" in src


# ── isolation · enforced, not promised ──────────────────────────────────

def test_r3_imports_no_production_module():
    assert freeze._check_isolation(ROOT)["pass"] is True


def test_r3_asserts_no_production_impact():
    assert freeze._check_no_validated_promoted(ROOT)["pass"] is True


def test_decision_contract_is_defined_but_not_active():
    c = freeze.R3_DECISION_CONTRACT
    assert "NOT ACTIVE" in c["status"]
    assert set(c["allowed_actions"]) == {"TAKE", "AVOID", "ABSTAIN"}
    for banned in ("write R2", "alter R2 exits"):
        assert any(banned in f for f in c["forbidden_actions"])


# ── completeness ────────────────────────────────────────────────────────

def test_every_class_has_a_disposition():
    st = master_status.load(ROOT) or master_status.build(ROOT)
    assert st["classes_resolved"] == st["classes_defined"] == 11
    for k in master_status.CLASSES:
        assert st["classes"][k]["disposition"] in core.DISPOSITIONS + ("FROZEN",)


def test_blocked_classes_document_what_would_unblock_them():
    st = master_status.load(ROOT) or master_status.build(ROOT)
    for k, c in st["classes"].items():
        if c["disposition"] in ("BLOCKED", "INSUFFICIENT_SUBSTRATE"):
            assert c.get("what_would_unblock") or c.get("reason")


def test_unsupervised_never_emits_outcome_trajectory_as_a_feature():
    from backend.research.r3_program import unsupervised
    src = Path(unsupervised.__file__).read_text(encoding="utf-8")
    assert "DELIBERATELY NOT EMITTED AS A" in src
    for m in ("india", "usa"):
        rep = unsupervised.load(ROOT, m)
        if rep:
            assert "trajectory_clusters_note" in rep
            assert "D_trajectory" not in (rep.get("lanes") or {})
