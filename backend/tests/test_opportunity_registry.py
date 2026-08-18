"""Operator 2026-08-18 · Wave 1 · Opportunity Registry tests.

Covers the invariants that make Zydus/ONGC/Hindunilvr/INDIGO/LUPIN cases
resolve correctly:
  · created_date is immutable
  · same-day get_or_create returns existing (idempotent)
  · lifecycle_state fires NEW exactly once
  · re-entry after CLOSE creates new id
  · REJECTED same-day never gets ACTIVE lifecycle
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.research.opportunity_registry import (   # noqa: E402
    Opportunity, make_opportunity_id, get_or_create, close, reject, touch,
    load_all, lifecycle_state, opportunity_age_days,
    opportunities_created_on, active_opportunities, count_by_status,
)


# ─────────────────────────────────────────────────────────────
# Deterministic id
# ─────────────────────────────────────────────────────────────
def test_opportunity_id_deterministic():
    a = make_opportunity_id("india", "R1", "ZYDUSLIFE", "2026-08-11")
    b = make_opportunity_id("india", "R1", "ZYDUSLIFE", "2026-08-11")
    assert a == b
    assert a.startswith("IND-R1-ZYDUSLIFE-20260811-")


def test_opportunity_id_diverges_across_runner():
    r1 = make_opportunity_id("india", "R1", "LUPIN", "2026-07-31")
    r2 = make_opportunity_id("india", "R2", "LUPIN", "2026-07-31")
    assert r1 != r2
    assert r1.startswith("IND-R1-LUPIN-")
    assert r2.startswith("IND-R2-LUPIN-")


def test_opportunity_id_diverges_across_market():
    ind = make_opportunity_id("india", "R2", "TCS", "2026-08-11")
    usa = make_opportunity_id("usa",   "R2", "TCS", "2026-08-11")
    assert ind != usa


# ─────────────────────────────────────────────────────────────
# ZYDUSLIFE bug · NEW fires exactly once
# ─────────────────────────────────────────────────────────────
def test_zydus_new_only_on_created_date(tmp_path: Path):
    (tmp_path / "reports" / "research").mkdir(parents=True)
    # Day 1 · fresh registry · create
    opp = get_or_create(tmp_path, "india", "R1", "ZYDUSLIFE", "2026-08-11",
                                  initial_signal="STRONG BUY", initial_rank=3)
    assert opp.created_date == "2026-08-11"
    assert lifecycle_state(opp, "2026-08-11") == "NEW"
    # Days 2, 3, 4, ..., 7 · same call must return SAME id + ACTIVE lifecycle
    for day in ("2026-08-12", "2026-08-13", "2026-08-14", "2026-08-15",
                    "2026-08-18"):
        opp2 = get_or_create(tmp_path, "india", "R1", "ZYDUSLIFE", day)
        assert opp2.opportunity_id == opp.opportunity_id, f"day {day} · id changed"
        assert opp2.created_date == "2026-08-11", f"day {day} · created_date restamped"
        assert lifecycle_state(opp2, day) == "ACTIVE", f"day {day} · still NEW · BUG"


# ─────────────────────────────────────────────────────────────
# ONGC / HINDUNILVR bug · created_date never changes
# ─────────────────────────────────────────────────────────────
def test_ongc_created_date_immutable(tmp_path: Path):
    (tmp_path / "reports" / "research").mkdir(parents=True)
    opp = get_or_create(tmp_path, "india", "R1", "ONGC", "2026-08-12")
    original = opp.created_date
    # Simulate 6 more daily runs · each MUST return the same created_date
    for day in ("2026-08-13", "2026-08-14", "2026-08-15", "2026-08-17",
                    "2026-08-18", "2026-08-19"):
        opp2 = get_or_create(tmp_path, "india", "R1", "ONGC", day)
        assert opp2.created_date == original, f"{day}: created_date changed to {opp2.created_date}"


# ─────────────────────────────────────────────────────────────
# LUPIN bug · re-entry after CLOSE creates NEW id
# ─────────────────────────────────────────────────────────────
def test_lupin_reentry_creates_new_id(tmp_path: Path):
    (tmp_path / "reports" / "research").mkdir(parents=True)
    # First opportunity · Jul 31 · closed Aug 12
    op1 = get_or_create(tmp_path, "india", "R1", "LUPIN", "2026-07-31")
    close(tmp_path, op1.opportunity_id, "2026-08-12", "STOP_LOSS_HIT")
    # Registry now has one CLOSED entry
    reg = load_all(tmp_path)
    assert reg[("india","R1","LUPIN")][0].status == "CLOSED"
    # Aug 20 · attractive again · get_or_create should build a NEW opportunity
    op2 = get_or_create(tmp_path, "india", "R1", "LUPIN", "2026-08-20")
    assert op2.opportunity_id != op1.opportunity_id
    assert op2.created_date == "2026-08-20"
    assert op2.status == "ACTIVE"
    # First opportunity stays CLOSED · doesn't revert
    reg = load_all(tmp_path)
    lupin_opps = reg[("india","R1","LUPIN")]
    assert len(lupin_opps) == 2
    assert lupin_opps[0].status == "CLOSED"
    assert lupin_opps[1].status == "ACTIVE"


# ─────────────────────────────────────────────────────────────
# INDIGO bug · same-day CLOSED must be REJECTED, not shown as active NEW
# ─────────────────────────────────────────────────────────────
def test_indigo_same_day_rejected_never_active(tmp_path: Path):
    (tmp_path / "reports" / "research").mkdir(parents=True)
    op = get_or_create(tmp_path, "india", "R1", "INDIGO", "2026-08-18",
                            initial_signal="BUY")
    reject(tmp_path, op.opportunity_id, "2026-08-18", "SAME_DAY_ROTATION")
    reg = load_all(tmp_path)
    assert reg[("india","R1","INDIGO")][-1].status == "REJECTED"
    # get_or_create on subsequent days does NOT resurrect · it either
    # returns nothing active or creates a fresh re-entry.
    op2 = get_or_create(tmp_path, "india", "R1", "INDIGO", "2026-08-19")
    # Fresh opportunity for the re-appearance
    assert op2.opportunity_id != op.opportunity_id
    assert op2.status == "ACTIVE"
    # Old REJECTED is untouched
    reg2 = load_all(tmp_path)
    rejected_still = [o for o in reg2[("india","R1","INDIGO")] if o.status == "REJECTED"]
    assert len(rejected_still) == 1


# ─────────────────────────────────────────────────────────────
# Lifecycle state buckets
# ─────────────────────────────────────────────────────────────
def test_lifecycle_state_variants():
    o = Opportunity(created_date="2026-08-11", status="ACTIVE")
    assert lifecycle_state(o, "2026-08-11") == "NEW"
    assert lifecycle_state(o, "2026-08-12") == "ACTIVE"
    o.status = "CLOSED"
    assert lifecycle_state(o, "2026-08-15") == "CLOSED"
    o.status = "REJECTED"
    assert lifecycle_state(o, "2026-08-15") == "REJECTED"


def test_opportunity_age():
    o = Opportunity(created_date="2026-08-11", status="ACTIVE")
    assert opportunity_age_days(o, "2026-08-11") == 0
    assert opportunity_age_days(o, "2026-08-12") == 1
    assert opportunity_age_days(o, "2026-08-18") == 7


# ─────────────────────────────────────────────────────────────
# Terminal states cannot revert (constitutional invariant)
# ─────────────────────────────────────────────────────────────
def test_closed_cannot_revert_to_active(tmp_path: Path):
    (tmp_path / "reports" / "research").mkdir(parents=True)
    op = get_or_create(tmp_path, "india", "R2", "TCS", "2026-08-01")
    close(tmp_path, op.opportunity_id, "2026-08-10", "TARGET_REACHED")
    # Attempting get_or_create AGAIN with the CLOSED opportunity's context
    # · must NOT return the closed one · must create a NEW re-entry id.
    op2 = get_or_create(tmp_path, "india", "R2", "TCS", "2026-08-18")
    assert op2.opportunity_id != op.opportunity_id
    assert op2.status == "ACTIVE"
    # Original closed record intact
    reg = load_all(tmp_path)
    orig = [o for o in reg[("india","R2","TCS")] if o.opportunity_id == op.opportunity_id][0]
    assert orig.status == "CLOSED"
    assert orig.closed_date == "2026-08-10"


# ─────────────────────────────────────────────────────────────
# Bulk helpers
# ─────────────────────────────────────────────────────────────
def test_bulk_helpers(tmp_path: Path):
    (tmp_path / "reports" / "research").mkdir(parents=True)
    get_or_create(tmp_path, "india", "R2", "A", "2026-08-11")
    get_or_create(tmp_path, "india", "R2", "B", "2026-08-12")
    get_or_create(tmp_path, "india", "R2", "C", "2026-08-12")
    op_c = load_all(tmp_path)[("india","R2","C")][0]
    close(tmp_path, op_c.opportunity_id, "2026-08-12", "SAME_DAY")
    reg = load_all(tmp_path)
    created_today = opportunities_created_on(reg, "2026-08-12")
    assert len(created_today) == 2   # B and C both created on 08-12
    active = active_opportunities(reg)
    assert len(active) == 2          # A and B (C is closed)
    counts = count_by_status(reg)
    assert counts["ACTIVE"] == 2
    assert counts["CLOSED"] == 1
