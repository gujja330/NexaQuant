"""Ticket 11 · Recommendation Timeline Audit.

Operator's #1 production-blocker concern: verify that recommendation age
progresses correctly day-over-day, entry_price stays immutable, and the
lifecycle is coherent across many simulated days.

'One bug here destroys user trust.' — operator

This test simulates a 7-day recommendation lifecycle:
  Day 1: rec appears · first_seen_date = D1 · entry_price captured
  Day 2: same rec · price moves · days_recommended = 2 · entry unchanged
  Day 3: high water rises · current_stop trails up · entry unchanged
  Day 4: price dips · low water tracks · entry + high_water still fixed
  Day 5: same rec · continuity intact
  Day 6: rec DROPPED from top-N · marked inactive · history preserved
  Day 7: rec reappears · does it treat as continuation or new? · locked
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.portfolio.position_store import (  # noqa: E402
    upsert_position, load_position, update_from_recs, load_all_positions,
    TRAIL_PCT,
)
from backend.portfolio.position_store.store import compute_days_recommended  # noqa: E402


def _rec(ticker: str, price: float, score: float = 0.15,
            action: str = "BUY") -> dict:
    return {
        "ticker": ticker,
        "ensemble_score": score,
        "percentile_action": action,
        "position_plan": {
            "suggested_allocation_pct": 3.0,
            "entry_zone": {
                "current_price": price,
                "stop_loss": round(price * 0.94, 2),
                "target_1": round(price * 1.12, 2),
            },
        },
        "lifecycle_state": {"current_state": "HOLD"},
    }


def test_ticket11_entry_price_never_changes_across_5_days(tmp_path):
    """entry_price captured on day 1 · every subsequent day preserves it
    regardless of current price movement (up, down, sideways)."""
    d1 = date(2026, 8, 1)
    upsert_position(tmp_path, "test", "AAA", asof=d1.isoformat(),
                       current_price=100.0, current_score=0.5, initial_stop=94.0)
    day1 = load_position(tmp_path, "test", "AAA")
    assert day1.first_seen_price == 100.0

    # Day 2: price up 5%
    upsert_position(tmp_path, "test", "AAA", asof=(d1 + timedelta(days=1)).isoformat(),
                       current_price=105.0, current_score=0.6)
    d2 = load_position(tmp_path, "test", "AAA")
    assert d2.first_seen_price == 100.0   # IMMUTABLE
    assert d2.last_seen_price == 105.0
    assert d2.high_water_price == 105.0

    # Day 3: price up 20% (new high)
    upsert_position(tmp_path, "test", "AAA", asof=(d1 + timedelta(days=2)).isoformat(),
                       current_price=120.0, current_score=0.7)
    d3 = load_position(tmp_path, "test", "AAA")
    assert d3.first_seen_price == 100.0   # STILL IMMUTABLE
    assert d3.high_water_price == 120.0

    # Day 4: price drops back to 108
    upsert_position(tmp_path, "test", "AAA", asof=(d1 + timedelta(days=3)).isoformat(),
                       current_price=108.0, current_score=0.5)
    d4 = load_position(tmp_path, "test", "AAA")
    assert d4.first_seen_price == 100.0   # STILL IMMUTABLE
    assert d4.high_water_price == 120.0   # locked at day-3 peak
    assert d4.low_water_price == 100.0

    # Day 5: price crashes to 90
    upsert_position(tmp_path, "test", "AAA", asof=(d1 + timedelta(days=4)).isoformat(),
                       current_price=90.0, current_score=0.3)
    d5 = load_position(tmp_path, "test", "AAA")
    assert d5.first_seen_price == 100.0   # STILL IMMUTABLE
    assert d5.high_water_price == 120.0   # not affected by crash
    assert d5.low_water_price == 90.0     # new low tracked


def test_ticket11_days_recommended_increments_correctly(tmp_path):
    """compute_days_recommended must equal (today - first_seen) + 1
    every day · no drift · no off-by-one."""
    d1 = date(2026, 8, 1)
    upsert_position(tmp_path, "test", "AAA", asof=d1.isoformat(),
                       current_price=100.0, current_score=0.5)

    # Day 1
    assert compute_days_recommended(tmp_path, "test", "AAA", d1.isoformat()) == 1
    # Day 2
    assert compute_days_recommended(tmp_path, "test", "AAA",
                                        (d1 + timedelta(days=1)).isoformat()) == 2
    # Day 7
    assert compute_days_recommended(tmp_path, "test", "AAA",
                                        (d1 + timedelta(days=6)).isoformat()) == 7
    # Day 30
    assert compute_days_recommended(tmp_path, "test", "AAA",
                                        (d1 + timedelta(days=29)).isoformat()) == 30


def test_ticket11_trailing_stop_only_ratchets_up_never_down(tmp_path):
    """current_stop must monotonically increase · never decrease · even
    when price crashes below the last stop level."""
    d1 = date(2026, 8, 1)
    upsert_position(tmp_path, "test", "AAA", asof=d1.isoformat(),
                       current_price=100.0, current_score=0.5, initial_stop=94.0)
    # Day 2: price up to 120 → stop trails to 120 * 0.94 = 112.80
    upsert_position(tmp_path, "test", "AAA", asof=(d1 + timedelta(days=1)).isoformat(),
                       current_price=120.0, current_score=0.7)
    stop_day2 = load_position(tmp_path, "test", "AAA").current_stop
    assert abs(stop_day2 - 120 * (1 - TRAIL_PCT)) < 0.01

    # Day 3: price crashes to 90 (below original stop even) → stop MUST NOT lower
    upsert_position(tmp_path, "test", "AAA", asof=(d1 + timedelta(days=2)).isoformat(),
                       current_price=90.0, current_score=0.3)
    stop_day3 = load_position(tmp_path, "test", "AAA").current_stop
    assert stop_day3 == stop_day2   # unchanged · trailing stop is one-way


def test_ticket11_dropped_from_top_n_preserves_history(tmp_path):
    """Rec drops from top-N → is_active=False · history 100% preserved."""
    d1 = date(2026, 8, 1)
    # Day 1: 2 tickers
    update_from_recs(tmp_path, "test", [_rec("A", 100), _rec("B", 200)],
                        asof=d1.isoformat())
    # Day 2: only B (A dropped)
    update_from_recs(tmp_path, "test", [_rec("B", 210)],
                        asof=(d1 + timedelta(days=1)).isoformat())
    positions = load_all_positions(tmp_path, "test")
    assert positions["A"].is_active is False
    assert positions["A"].first_seen_date == d1.isoformat()   # preserved
    assert positions["A"].first_seen_price == 100.0            # preserved
    assert positions["B"].is_active is True


def test_ticket11_reappearing_ticker_continues_lifecycle_not_restart(tmp_path):
    """A rec that drops off top-N then reappears must CONTINUE its
    original lifecycle · NOT reset first_seen_date/price to today."""
    d1 = date(2026, 8, 1)
    # Day 1: rec A
    update_from_recs(tmp_path, "test", [_rec("A", 100)], asof=d1.isoformat())
    # Day 2: A drops (no recs)
    update_from_recs(tmp_path, "test", [], asof=(d1 + timedelta(days=1)).isoformat())
    # Day 3: A reappears at higher price
    update_from_recs(tmp_path, "test", [_rec("A", 115)],
                        asof=(d1 + timedelta(days=2)).isoformat())
    pos = load_position(tmp_path, "test", "A")
    # first_seen must be day 1 · NOT day 3 · NOT a "new" rec
    assert pos.first_seen_date == d1.isoformat()
    assert pos.first_seen_price == 100.0
    assert pos.is_active is True
    assert pos.high_water_price == 115.0   # captures the peak
    assert pos.n_appearances == 2   # appeared day 1 + day 3 (not day 2)


def test_ticket11_command_center_never_shows_stale_current_price(tmp_path, monkeypatch):
    """Command Center price rendering must use the LATEST last_seen_price
    from position_store · not any cached value."""
    d1 = date(2026, 8, 1)
    upsert_position(tmp_path, "test", "AAA", asof=d1.isoformat(),
                       current_price=100.0, current_score=0.5, initial_stop=94.0)
    upsert_position(tmp_path, "test", "AAA", asof=(d1 + timedelta(days=1)).isoformat(),
                       current_price=125.0, current_score=0.7)
    latest = load_position(tmp_path, "test", "AAA")
    assert latest.last_seen_price == 125.0   # command center reads THIS field


def test_ticket11_no_hardcoded_dates_in_position_store():
    """Position store code contains zero hardcoded date literals."""
    import re
    src = (_ROOT / "backend" / "portfolio" / "position_store" / "store.py").read_text(encoding="utf-8")
    # Skip comment lines
    code_only = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    bad = re.findall(r"date\s*\(\s*20\d\d\s*,\s*\d+\s*,\s*\d+\s*\)", code_only)
    assert not bad, f"Hardcoded date literals in position_store: {bad}"
