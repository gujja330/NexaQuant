"""Pipeline heartbeat guard · detect silent pipeline misses.

2026-08-08 · Root cause of Aug-3 gap: pipeline didn't run on Mon 2026-08-03 ·
no XLSX rows generated for that trading day · nobody noticed until 5 days
later. Operator directive after CEO-level P&L audit: "stop the bleeding,
don't just backfill."

This guard runs at every Telegram send:
    1. Compute the expected last trading day (skips weekends)
    2. Compare against last recorded successful run per market
    3. If gap > 0 trading days → emit CRITICAL alert prepended to
       Command Center message so operator sees it BEFORE reading the XLSX

Storage: reports/heartbeat/pipeline_heartbeat.json (append-only per-market)

Silent when no gap.  Idempotent.  Zero R1/R2 code touches.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


HEARTBEAT_PATH = "reports/heartbeat/pipeline_heartbeat.json"


def _expected_last_trading_day(today: date) -> date:
    """Return the most recent weekday <= today. Skips Sat/Sun."""
    d = today
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _trading_days_between(start: date, end: date) -> int:
    """Count weekday-trading-days strictly between start and end (excl. both)."""
    if start >= end:
        return 0
    d = start + timedelta(days=1)
    n = 0
    while d < end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def _load(root: Path) -> dict:
    p = root / HEARTBEAT_PATH
    if not p.exists():
        return {"engine": "pipeline_heartbeat.v1", "markets": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"engine": "pipeline_heartbeat.v1", "markets": {}}


def _save(root: Path, data: dict) -> None:
    p = root / HEARTBEAT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, default=str),
                     encoding="utf-8")


def record_run(root: Path, market: str, asof: str) -> None:
    """Record a successful pipeline run. Called after Telegram send succeeds."""
    data = _load(root)
    data.setdefault("markets", {})[market] = {
        "last_asof":    asof[:10],
        "last_run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _save(root, data)


def check(root: Path, market: str, today_iso: str | None = None) -> dict:
    """Check for pipeline gap. Returns:
        {status: "OK"|"WARNING"|"CRITICAL",
         last_asof: str | None,
         expected_asof: str,
         missed_trading_days: int,
         message: str}
    """
    today = date.fromisoformat(today_iso[:10]) if today_iso else date.today()
    expected = _expected_last_trading_day(today)

    data = _load(root)
    market_data = (data.get("markets") or {}).get(market)
    if not market_data:
        return {
            "status": "WARNING",
            "last_asof": None,
            "expected_asof": expected.isoformat(),
            "missed_trading_days": 0,
            "message": f"⚠️ heartbeat: no prior {market} run recorded (first-time)",
        }

    try:
        last = date.fromisoformat(market_data["last_asof"])
    except (KeyError, ValueError):
        return {
            "status": "WARNING",
            "last_asof": market_data.get("last_asof"),
            "expected_asof": expected.isoformat(),
            "missed_trading_days": 0,
            "message": f"⚠️ heartbeat: {market} last_asof unparseable",
        }

    if last >= expected:
        return {
            "status": "OK",
            "last_asof": last.isoformat(),
            "expected_asof": expected.isoformat(),
            "missed_trading_days": 0,
            "message": f"🟢 heartbeat {market}: current (last run {last.isoformat()})",
        }

    missed = _trading_days_between(last, expected) + 1   # +1 = expected day itself also missed
    sev = "CRITICAL" if missed >= 2 else "WARNING"
    icon = "🔴" if sev == "CRITICAL" else "🟡"
    return {
        "status": sev,
        "last_asof": last.isoformat(),
        "expected_asof": expected.isoformat(),
        "missed_trading_days": missed,
        "message": (f"{icon} PIPELINE GAP · {market.upper()} · "
                        f"missed {missed} trading day{'s' if missed>1 else ''} · "
                        f"last run {last.isoformat()} · expected {expected.isoformat()}"),
    }


def render(check_result: dict) -> str:
    """One-liner for the ops dashboard."""
    return check_result.get("message", "heartbeat unknown")
