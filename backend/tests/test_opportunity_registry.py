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
    """CEO 2026-11-03 · the date now clears the cooling window.

    This failed with `get_or_create` returning None, which read like the
    re-entry bug had come back. It had not.

    The cause is RE-ENTRY COOLING, added after this test was written.
    configs/opportunity_registry.yaml sets cooling_period_days 7 plus
    stop_loss_extra_cooling_days 7, so a STOP_LOSS_HIT close on 08-12
    cannot re-enter before 08-26. The original 08-20 is 8 days later and
    is inside the window.

    I first blamed the retired-runner guard as well, and that was wrong:
    `is_retired` reads configs/aegis_retirement.yaml from the root it is
    GIVEN, and in a tmp_path test that file does not exist, so the guard
    returns False and R1 creates normally here. Retirement is real in
    production and is covered by its own test below, with the config
    written into the tmp root so the guard can actually see it.

    The invariant this test exists for - a re-entry after CLOSE gets a NEW
    opportunity_id and never revives the closed one - is unchanged, and is
    now exercised outside the cooling window. Runner R2 rather than R1 so
    the test also holds once a retirement config is present in the tree.
    """
    (tmp_path / "reports" / "research").mkdir(parents=True)
    # First opportunity · Jul 31 · closed Aug 12 on a stop
    op1 = get_or_create(tmp_path, "india", "R2", "LUPIN", "2026-07-31")
    close(tmp_path, op1.opportunity_id, "2026-08-12", "STOP_LOSS_HIT")
    # Registry now has one CLOSED entry
    reg = load_all(tmp_path)
    assert reg[("india","R2","LUPIN")][0].status == "CLOSED"
    # Aug 27 · past the 14-day stop-loss cooling · a NEW opportunity
    op2 = get_or_create(tmp_path, "india", "R2", "LUPIN", "2026-08-27")
    assert op2 is not None, "past cooling, a re-entry must be created"
    assert op2.opportunity_id != op1.opportunity_id
    assert op2.created_date == "2026-08-27"
    assert op2.status == "ACTIVE"
    # First opportunity stays CLOSED · doesn't revert
    reg = load_all(tmp_path)
    lupin_opps = reg[("india","R2","LUPIN")]
    assert len(lupin_opps) == 2
    assert lupin_opps[0].status == "CLOSED"
    assert lupin_opps[1].status == "ACTIVE"


def test_a_retired_runner_cannot_open_a_new_opportunity(tmp_path: Path):
    """Forward-only retirement · a retired runner may not create.

    The retirement config has to be written into the tmp root, because
    `is_retired(root, ...)` reads configs/aegis_retirement.yaml relative
    to the root it is handed. Without it the guard silently returns False,
    which is exactly why my first reading of the LUPIN failure blamed
    retirement when cooling was doing all the work.
    """
    from backend.delivery.canonical import retirement as _ret
    (tmp_path / "reports" / "research").mkdir(parents=True)
    (tmp_path / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "configs" / "aegis_retirement.yaml").write_text(
        "retired_runners: [R1]\nactive_runners: [R2]\n", encoding="utf-8")
    _ret._CACHE["config"] = None          # the loader caches on mtime
    _ret._CACHE["mtime"] = None

    assert _ret.is_retired(tmp_path, "R1") is True
    assert _ret.is_retired(tmp_path, "R2") is False
    assert get_or_create(tmp_path, "india", "R1", "LUPIN", "2026-07-31") is None
    assert get_or_create(tmp_path, "india", "R2", "LUPIN", "2026-07-31") is not None


def test_production_really_does_retire_r1(tmp_path: Path):
    """The live config, read from the repo root · a separate claim."""
    from backend.delivery.canonical.retirement import is_retired
    assert is_retired(_ROOT, "R1") is True
    assert is_retired(_ROOT, "R2") is False


def test_re_entry_inside_the_cooling_window_is_blocked(tmp_path: Path):
    """A closed name must not reappear as NEW just because it still ranks.

    The operator's §10 condition. 8 days after a stop-loss close is inside
    the 14-day window, so it returns None; 15 days clears it.
    """
    (tmp_path / "reports" / "research").mkdir(parents=True)
    op1 = get_or_create(tmp_path, "india", "R2", "LUPIN", "2026-07-31")
    close(tmp_path, op1.opportunity_id, "2026-08-12", "STOP_LOSS_HIT")
    assert get_or_create(tmp_path, "india", "R2", "LUPIN", "2026-08-20") is None
    assert get_or_create(tmp_path, "india", "R2", "LUPIN", "2026-08-27") is not None


def test_cooling_can_be_disabled_explicitly_and_only_explicitly(tmp_path: Path):
    """enforce_cooling=False is the documented escape · it must be opt-in."""
    (tmp_path / "reports" / "research").mkdir(parents=True)
    op1 = get_or_create(tmp_path, "india", "R2", "LUPIN", "2026-07-31")
    close(tmp_path, op1.opportunity_id, "2026-08-12", "STOP_LOSS_HIT")
    assert get_or_create(tmp_path, "india", "R2", "LUPIN", "2026-08-20") is None
    forced = get_or_create(tmp_path, "india", "R2", "LUPIN", "2026-08-20",
                           enforce_cooling=False)
    assert forced is not None and forced.opportunity_id != op1.opportunity_id


# ─────────────────────────────────────────────────────────────
# INDIGO bug · same-day CLOSED must be REJECTED, not shown as active NEW
# ─────────────────────────────────────────────────────────────
def test_indigo_same_day_rejected_never_active(tmp_path: Path):
    """CEO 2026-11-03 · runner R1 -> R2, and 08-19 -> 08-22.

    Same two causes as the LUPIN test above: R1 is retired, and
    rejected_same_day_cooling_days is 3, so a rejection on 08-18 cannot
    re-enter on 08-19. The invariant - a REJECTED record is never revived
    into ACTIVE, and a genuine re-appearance gets a fresh id - is
    unchanged and is what is asserted here.
    """
    (tmp_path / "reports" / "research").mkdir(parents=True)
    op = get_or_create(tmp_path, "india", "R2", "INDIGO", "2026-08-18",
                            initial_signal="BUY")
    reject(tmp_path, op.opportunity_id, "2026-08-18", "SAME_DAY_ROTATION")
    reg = load_all(tmp_path)
    assert reg[("india","R2","INDIGO")][-1].status == "REJECTED"
    # One day later is inside the 3-day rejection cooling window.
    assert get_or_create(tmp_path, "india", "R2", "INDIGO", "2026-08-19") is None
    # get_or_create past the window does NOT resurrect · it creates a
    # fresh re-entry and leaves the REJECTED record alone.
    op2 = get_or_create(tmp_path, "india", "R2", "INDIGO", "2026-08-22")
    assert op2 is not None
    # Fresh opportunity for the re-appearance
    assert op2.opportunity_id != op.opportunity_id
    assert op2.status == "ACTIVE"
    # Old REJECTED is untouched
    reg2 = load_all(tmp_path)
    rejected_still = [o for o in reg2[("india","R2","INDIGO")] if o.status == "REJECTED"]
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
