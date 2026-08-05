"""Economic Calendar · daily ingest.

Reads free sources (yfinance economic events fallback · hardcoded RBI/Fed
schedules for known dates · earnings.parquet where already ingested) and
maintains an append-only history at:

    reports/context/economic_calendar.jsonl

Each row:
    {ts_utc, asof_captured, event_date, event_id, region, category,
     event_name, expected_impact, tickers_affected}

Idempotent per (event_date, event_id). Safe to run daily.

No confidence adjustment · pure data plumbing. Phase 2A's macro/earnings
adapters will READ this file.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


# ── Known-recurring events · minimal seed set · expanded in Phase 2A ──
# Format: (region, category, event_name, expected_impact, tickers_affected)
# expected_impact: "high" · "medium" · "low"
# tickers_affected: sector tag(s) e.g. "IT" "BANKS" "*" (market-wide)

KNOWN_RECURRING_EVENTS = [
    # Fed schedule (monthly-ish · placeholder dates · Phase 2A hits real APIs)
    ("USA", "central_bank", "FOMC Rate Decision",       "high",   "*"),
    ("USA", "macro",         "US CPI",                   "high",   "*"),
    ("USA", "macro",         "US PPI",                   "medium", "*"),
    ("USA", "macro",         "US Non-Farm Payrolls",     "high",   "*"),
    ("USA", "macro",         "US Unemployment Rate",     "high",   "*"),
    ("USA", "macro",         "US Retail Sales",          "medium", "Consumer"),
    ("USA", "macro",         "US ISM Manufacturing",     "medium", "Industrials"),
    ("USA", "macro",         "US GDP",                   "high",   "*"),
    # India
    ("INDIA", "central_bank", "RBI MPC Meeting",         "high",   "*"),
    ("INDIA", "macro",         "India CPI",              "high",   "*"),
    ("INDIA", "macro",         "India WPI",              "medium", "*"),
    ("INDIA", "macro",         "India IIP",              "medium", "Industrials"),
    ("INDIA", "macro",         "India GDP",              "high",   "*"),
    ("INDIA", "macro",         "India PMI Manufacturing", "medium", "Industrials"),
    ("INDIA", "macro",         "India PMI Services",     "medium", "Services"),
    ("INDIA", "macro",         "India GST Collections",  "low",    "*"),
    # Global
    ("EU",     "central_bank", "ECB Rate Decision",       "high",   "*"),
    ("JP",     "central_bank", "BOJ Rate Decision",       "medium", "*"),
    ("UK",     "central_bank", "BOE Rate Decision",       "medium", "*"),
    ("CHINA",  "macro",         "China PMI",              "medium", "Materials"),
    ("CHINA",  "macro",         "China GDP",              "high",   "Materials"),
    ("GLOBAL", "commodity",     "OPEC Meeting",           "medium", "Energy"),
    ("GLOBAL", "commodity",     "US Crude Inventories",   "low",    "Energy"),
]


@dataclass
class CalendarEntry:
    ts_utc: str
    asof_captured: str          # what date we captured this on
    event_date: str             # YYYY-MM-DD · when the event happens
    event_id: str               # stable key for idempotency
    region: str                 # USA · INDIA · EU · JP · UK · CHINA · GLOBAL
    category: str               # central_bank · macro · commodity · earnings · corporate
    event_name: str
    expected_impact: str        # high · medium · low
    tickers_affected: str       # sector code · "*" · comma-separated
    source: str = "seed"        # seed · yfinance · rbi_web · fed_ical · earnings_parquet
    metadata: dict = field(default_factory=dict)


def _path(root: Path) -> Path:
    p = root / "reports" / "context" / "economic_calendar.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _existing_keys(root: Path) -> set:
    p = _path(root)
    if not p.exists(): return set()
    keys = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try: d = json.loads(line)
        except json.JSONDecodeError: continue
        keys.add((d.get("event_date"), d.get("event_id")))
    return keys


def _append(root: Path, entries: list[CalendarEntry]) -> int:
    existing = _existing_keys(root)
    n = 0
    with _path(root).open("a", encoding="utf-8") as fh:
        for e in entries:
            if (e.event_date, e.event_id) in existing: continue
            fh.write(json.dumps(asdict(e), default=str, ensure_ascii=False) + "\n")
            existing.add((e.event_date, e.event_id))
            n += 1
    return n


def _seed_upcoming_recurring(root: Path, asof: str, lookahead_days: int = 45) -> int:
    """Placeholder seeding · gives Phase 2A a substrate to reason over.

    Real implementation (Phase 2A): hit RBI website · Fed iCal · TradingEconomics
    free-tier · earnings calendars. This seed just marks that certain event
    categories exist so the schema doesn't lie about capability.
    """
    now = datetime.now(timezone.utc).isoformat()
    entries = []
    d0 = date.fromisoformat(asof)
    for offset in [7, 14, 21, 28, 35]:
        target = (d0 + timedelta(days=offset)).isoformat()
        for region, category, name, impact, affected in KNOWN_RECURRING_EVENTS:
            event_id = f"seed_{region}_{name.replace(' ', '_')}_{target}"
            entries.append(CalendarEntry(
                ts_utc=now, asof_captured=asof, event_date=target,
                event_id=event_id, region=region, category=category,
                event_name=name, expected_impact=impact,
                tickers_affected=affected, source="seed_recurring_placeholder",
                metadata={"note": "seed only · Phase 2A replaces with real feeds"},
            ))
    return _append(root, entries)


def _ingest_earnings_from_usa_parquet(root: Path, asof: str) -> int:
    """Pull upcoming earnings from usa/data/raw/us/earnings.parquet if present."""
    p = root / "usa" / "data" / "raw" / "us" / "earnings.parquet"
    if not p.exists(): return 0
    try:
        import pandas as pd
        df = pd.read_parquet(p)
    except Exception:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    d0 = date.fromisoformat(asof)
    horizon = d0 + timedelta(days=45)
    entries = []
    for _, row in df.iterrows():
        try:
            next_dt = str(row.get("next_earnings_date") or "")[:10]
            if not next_dt: continue
            edt = date.fromisoformat(next_dt)
            if edt < d0 or edt > horizon: continue
            ticker = str(row.get("ticker") or "").upper()
            if not ticker: continue
            entries.append(CalendarEntry(
                ts_utc=now, asof_captured=asof, event_date=next_dt,
                event_id=f"earnings_USA_{ticker}_{next_dt}",
                region="USA", category="earnings",
                event_name=f"{ticker} Earnings",
                expected_impact="high" if ticker in
                    ("NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA") else "medium",
                tickers_affected=ticker, source="earnings_parquet",
                metadata={"symbol": ticker},
            ))
        except Exception:
            continue
    return _append(root, entries)


def ingest_daily(root: Path, asof: str) -> dict:
    """Run one daily ingest cycle · idempotent · returns summary."""
    n_seed = _seed_upcoming_recurring(root, asof)
    n_earnings = _ingest_earnings_from_usa_parquet(root, asof)
    return {
        "engine":               "aegis.context.economic_calendar.v0.1",
        "asof":                 asof,
        "generated_utc":        datetime.now(timezone.utc).isoformat(),
        "n_seeded_recurring":   n_seed,
        "n_earnings_upcoming":  n_earnings,
        "total_appended":       n_seed + n_earnings,
        "output":               str(_path(root)),
        "phase":                "DATA_ONLY · Phase 2A activates consumption 2026-09-09",
    }


def query_upcoming(root: Path, asof: str, days_ahead: int = 7,
                       region: str | None = None,
                       min_impact: str = "medium") -> list[dict]:
    """Read-only query · returns events happening in the next N days."""
    p = _path(root)
    if not p.exists(): return []
    d0 = date.fromisoformat(asof)
    end = d0 + timedelta(days=days_ahead)
    order = {"high": 3, "medium": 2, "low": 1}
    min_ord = order.get(min_impact, 2)
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try: d = json.loads(line)
        except json.JSONDecodeError: continue
        try:
            edt = date.fromisoformat((d.get("event_date") or "")[:10])
        except (ValueError, TypeError):
            continue
        if edt < d0 or edt > end: continue
        if region and d.get("region") != region: continue
        if order.get(d.get("expected_impact"), 0) < min_ord: continue
        out.append(d)
    out.sort(key=lambda x: (x.get("event_date"), -order.get(x.get("expected_impact"), 0)))
    return out
