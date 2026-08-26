"""AEGIS · Price integrity · weekend entry tolerance regression.

Before fix: `check_entry_alignment` compared quoted entry_price against
parquet close on entry_date. Positions recommended over weekends/
holidays legitimately used the PRIOR trading day close (e.g., Friday's
close for a Monday entry). PI1 flagged those as 2-4% drift and blocked
the delivery.

Fix: PI1 walks back up to 7 calendar days and accepts if quoted matches
any prior trading day close within 0.1%. Position_store remains the
immutable canonical transaction price · PI1 no longer flags legitimate
Friday-close-on-Monday entries.

The tolerance for genuine drift (mid-week entries where quoted doesn't
match ANY nearby close) is preserved.
"""
from __future__ import annotations
import json
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def synthetic_repo(tmp_path):
    """Builds a minimal parquet + report tree the guard understands."""
    root = tmp_path
    (root / "data" / "raw" / "india").mkdir(parents=True)
    # CANBK · Friday 2026-08-07 close 131.95 · Monday 2026-08-10 close 129.00
    df = pd.DataFrame({
        "open":  [125, 127, 129, 130, 131, 132, 129],
        "high":  [126, 128, 129, 130, 132, 132, 130],
        "low":   [125, 126, 128, 128, 130, 128, 128],
        "close": [125.85, 127.8, 128.0, 128.5, 131.95, 129.0, 130.3],
        "tick_volume": [1000]*7, "spread": [0.0]*7,
    }, index=pd.to_datetime([
        "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06",
        "2026-08-07", "2026-08-10", "2026-08-11",
    ]))
    df.index.name = "time"
    df.to_parquet(root / "data" / "raw" / "india" / "CANBK_D1.parquet")
    return root


def test_monday_entry_using_friday_close_is_not_a_drift(synthetic_repo):
    """Position entered Mon with Fri close → PI1 must accept."""
    from backend.context.price_integrity_guard import check_entry_alignment
    positions = [{
        "ticker":     "CANBK",
        "entry_date": "2026-08-10",
        "entry_price": 131.95,           # Friday 2026-08-07 close
    }]
    result = check_entry_alignment(synthetic_repo, "india", positions)
    assert result.status == "PASS", \
        f"Weekend entry should not be a drift · got {result.violations}"


def test_real_drift_is_still_flagged(synthetic_repo):
    """Quoted price matching no nearby close → real drift → FAIL."""
    from backend.context.price_integrity_guard import check_entry_alignment
    positions = [{
        "ticker":     "CANBK",
        "entry_date": "2026-08-10",
        "entry_price": 200.0,            # No parquet close matches
    }]
    result = check_entry_alignment(synthetic_repo, "india", positions)
    assert result.status == "FAIL"
    assert len(result.violations) == 1


def test_matching_same_day_close_is_not_a_drift(synthetic_repo):
    """Quoted == entry_date's close → PASS (baseline)."""
    from backend.context.price_integrity_guard import check_entry_alignment
    positions = [{
        "ticker":     "CANBK",
        "entry_date": "2026-08-10",
        "entry_price": 129.0,            # Matches Monday close exactly
    }]
    result = check_entry_alignment(synthetic_repo, "india", positions)
    assert result.status == "PASS"


def test_exit_using_prior_close_is_not_a_drift(synthetic_repo):
    """Same lookback logic applies to exits."""
    from backend.context.price_integrity_guard import check_exit_alignment
    positions = [{
        "ticker":    "CANBK",
        "exit_date": "2026-08-10",
        "exit_price": 131.95,            # Friday's close
        "status":    "EXIT",
    }]
    result = check_exit_alignment(synthetic_repo, "india", positions)
    assert result.status == "PASS", \
        f"Weekend exit should not be a drift · got {result.violations}"
