"""Date-consistency guardrail across critical pipeline outputs.

The 2026-07-29 operator report: "just now i received july 24th notification"
uncovered a systemic problem — outputs at different pipeline layers were
carrying DIFFERENT dates because upstream engines failed silently and
downstream engines processed stale inputs.

This test enforces the contract:
    If recommendations.json exists and carries `asof = D`, every
    UPSTREAM engine output must also carry `asof = D` (allowing at
    most ±2 business days for legitimate weekend gaps).

Fail early in CI rather than let stale data land in operator's Telegram.

Only checks files that ARE present · missing outputs are not a date bug.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

# Upstream engines whose asof MUST match recommendations.json (±2 biz days).
# Layer numbering documents the dependency chain from raw data to operator.
UPSTREAM_CHAIN = [
    # (label, path relative to reports dir, date field, max_stale_days)
    ("ensemble",         "ensemble.json",              "asof", 3),
    ("recommendations_v3", "recommendations_v3.json",  "asof", 3),
    ("dynamic_holding",  "dynamic_holding.json",       "asof", 3),
    ("lifecycle",        "recommendation_lifecycle.json", "asof", 3),
]


def _parse_date(s) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _load_asof(path: Path, key: str) -> date | None:
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return _parse_date(d.get(key))
    except Exception:
        return None


def _check_market(market: str) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a market."""
    reports = _ROOT / ("usa/reports" if market == "usa" else "reports")
    recs_path = reports / "recommendations.json"
    if not recs_path.exists():
        return [], [f"{market}: recommendations.json missing · skipping"]
    recs_asof = _load_asof(recs_path, "asof")
    if recs_asof is None:
        return [f"{market}: recommendations.json has unparseable asof"], []

    errors: list[str] = []
    warnings: list[str] = []
    for label, rel, key, max_stale in UPSTREAM_CHAIN:
        p = reports / rel
        if not p.exists():
            warnings.append(f"{market}: {label} missing (may be fine)")
            continue
        upstream_asof = _load_asof(p, key)
        if upstream_asof is None:
            warnings.append(f"{market}: {label} has unparseable asof")
            continue
        stale_days = (recs_asof - upstream_asof).days
        if stale_days > max_stale:
            errors.append(
                f"{market}: {label} asof={upstream_asof} is {stale_days}d "
                f"BEHIND recommendations.json asof={recs_asof} "
                f"(threshold {max_stale}d). Upstream engine did not run today."
            )
        elif stale_days < -max_stale:
            errors.append(
                f"{market}: {label} asof={upstream_asof} is FUTURE-DATED "
                f"vs recommendations.json asof={recs_asof}."
            )
    return errors, warnings


def test_india_upstream_dates_are_consistent_with_recommendations():
    errors, warnings = _check_market("india")
    for w in warnings:
        print(f"WARN: {w}")
    assert not errors, "\n".join(errors)


def test_usa_upstream_dates_are_consistent_with_recommendations():
    errors, warnings = _check_market("usa")
    for w in warnings:
        print(f"WARN: {w}")
    assert not errors, "\n".join(errors)


def test_legacy_paper_csv_within_business_week():
    """data/aegis_today.csv freshness — legacy paper portfolio input.

    Rationale: the 2026-07-29 incident traced back to this CSV being 5 days
    stale in git. If it's more than 7 calendar days behind, CI must fail.
    (7 days accounts for long weekends + market holidays.)
    """
    p = _ROOT / "data" / "aegis_today.csv"
    if not p.exists():
        return   # not present = not a bug, this test is guardrail only
    with p.open("r", encoding="utf-8") as f:
        _hdr = f.readline()
        first = f.readline().strip()
    if not first:
        return
    gen_str = first.split(",", 1)[0].strip().strip('"')
    gen = _parse_date(gen_str)
    if gen is None:
        return
    # Use recommendations.json asof as "today" to keep the test deterministic
    # regardless of wall-clock (so it doesn't false-alarm every future day
    # when history is queried).
    recs_asof = _load_asof(_ROOT / "reports" / "recommendations.json", "asof")
    if recs_asof is None:
        # Fall back to system date only when recs missing.
        recs_asof = date.today()
    stale_days = (recs_asof - gen).days
    assert stale_days <= 7, (
        f"data/aegis_today.csv Generated={gen} is {stale_days}d "
        f"behind recommendations.json asof={recs_asof}. Legacy paper "
        f"portfolio CSV has not been regenerated · risk of stale "
        f"Telegram notification (see 2026-07-29 incident)."
    )


def test_snapshot_for_recs_asof_exists():
    """Every recommendations.json.asof must have a matching snapshot on disk."""
    for market in ("india", "usa"):
        reports = _ROOT / ("usa/reports" if market == "usa" else "reports")
        recs_path = reports / "recommendations.json"
        if not recs_path.exists():
            continue
        asof = _load_asof(recs_path, "asof")
        if asof is None:
            continue
        snap = reports / "recommendations_history" / market / f"{asof.isoformat()}.json"
        assert snap.exists(), (
            f"{market}: snapshot missing at {snap.relative_to(_ROOT)} — "
            f"recommendations.json asof {asof} was published without "
            f"archiving to history. Cycle 4 snapshot persistence broke."
        )
