"""AEGIS · Delivery · Portfolio Source (Registry-ACTIVE canonical).

CEO 2026-08-28 · Path A directive:
> "Fix Portfolio to source from Registry ACTIVE (stable current holdings).
>  Fix from source, no interim patches."

Root defect · prior Portfolio row emit iterated source-XLSX rows filtered
by today's status. When R1/R2 didn't fire for a currently-held position
on a given day, it dropped out of Portfolio · reappeared the next day
when the signal re-fired. Registry ACTIVE stayed stable at 18 while
Portfolio display bounced 3 → 6 → 7 across CI runs on the same day.

## Canonical rule

Portfolio ACTIVE row set = Registry ACTIVE (latest per pid) for market.
Every position ever opened by Registry that has not been CLOSED /
REJECTED appears in Portfolio · deterministically · every run.

## Field derivation (in priority order)

  ticker         Registry.ticker
  runner         Registry.runner (R1 / R2 / R3)
  entry_date     canonical snapshot ledger · fallback Registry.created_date
  entry_price    canonical snapshot ledger · fallback parquet close on
                 entry_date (via backend.delivery.canonical_entry.resolve)
  current_price  parquet close on asof (or nearest prior)
  pnl_pct        (current_price - entry_price) / entry_price · %
  days_held      asof - entry_date · calendar days
  sector         backend.delivery.sector lookup
  today_move_pct (current - prev_close) / prev_close · %
  status         "HOLD" (Registry ACTIVE ⇒ position being held)

Nothing here reads from source aegis_history.xlsx · that source is
consulted by the existing Portfolio row emit loop as an ENRICHMENT
(Health / Confidence / Rank / etc.). Positions not in today's source
XLSX still appear in Portfolio · they just have the today-signal
fields blank.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional


def _load_registry_active(root: Path, market: str) -> list:
    """Return latest-event-per-pid where status == ACTIVE."""
    from backend.research import opportunity_registry as oreg
    reg = oreg.load_all(root)
    active = []
    seen = set()
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            if o.opportunity_id in seen: continue
            seen.add(o.opportunity_id)
            if o.is_active():
                active.append(o)
    return active


def _parquet_close(root: Path, market: str, ticker: str,
                    iso_date: str) -> Optional[float]:
    """Read-only close · matches xlsx_validator._parquet_close_lookup
    for consistency with I26/I27/I28 · 5-day nearby lookback."""
    try:
        import pandas as pd
    except Exception:
        return None
    clean = ticker.upper().replace(".NS", "").replace(".BO", "")
    base = ("usa/data/raw/us" if market.lower() == "usa"
             else "data/raw/india")
    p = root / base / f"{clean}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        if iso_date in df.index:
            return float(df.loc[iso_date, col])
        for lookback in range(1, 6):
            prior = (date.fromisoformat(iso_date) - timedelta(days=lookback)).isoformat()
            if prior in df.index:
                return float(df.loc[prior, col])
        return None
    except Exception:
        return None


def _sector_lookup(root: Path, market: str, ticker: str) -> str:
    """Best-effort sector lookup · returns empty string if unknown.

    CEO 2026-09-01 · Path-A rows were showing Sector=— because this
    function only checked configs/sector_map.json which does not
    exist. The sender's `_sector_for` uses reports/sector_cache.json
    (auto-populated by yfinance across the daily pipeline · 226+
    tickers for India). Read that same cache so Path-A rows get the
    real sector without duplicating the yfinance auto-fetch here.
    """
    tk = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
    # 1 · sector_cache.json · shared with sender's _sector_for
    try:
        p = root / "reports" / "sector_cache.json"
        if p.exists():
            import json
            d = json.loads(p.read_text(encoding="utf-8"))
            bucket = d.get((market or "").lower(), {})
            v = bucket.get(tk) or bucket.get(str(ticker).upper())
            if v: return v
    except Exception:
        pass
    # 2 · optional sector_map.json (legacy fallback)
    try:
        p = root / "configs" / "sector_map.json"
        if p.exists():
            import json
            d = json.loads(p.read_text(encoding="utf-8"))
            v = d.get(tk) or d.get(str(ticker).upper())
            if v: return v
    except Exception:
        pass
    return ""


def build_active_positions(root: Path, market: str,
                             asof: str) -> list[dict]:
    """CANONICAL current-portfolio · one dict per Registry ACTIVE.

    Deterministic pure function of (Registry state, snapshot ledger,
    parquet closes, asof). Rerunning against unchanged inputs produces
    byte-identical output · verified by regression test.
    """
    from backend.delivery.canonical_entry import resolve as _canon_resolve
    out = []
    for opp in _load_registry_active(root, market):
        canonical = _canon_resolve(
            root, market=market, ticker=opp.ticker,
            runner=opp.runner, entry_date=str(opp.created_date)[:10],
            backfill_snapshot=False)   # read-only during Portfolio build
        entry_date = canonical.entry_date or str(opp.created_date)[:10]
        entry_price = (canonical.entry_price
                        if canonical.entry_price and canonical.entry_price > 0
                        else _parquet_close(root, market, opp.ticker, entry_date))
        if entry_price is None or entry_price <= 0:
            continue    # cannot compute canonical row · skip
        current = _parquet_close(root, market, opp.ticker, asof)
        if current is None or current <= 0:
            current = entry_price   # position exists but no live price yet
        pnl_pct = round((current - entry_price) / entry_price * 100, 2)
        try:
            days_held = max(0,
                             (date.fromisoformat(asof)
                              - date.fromisoformat(entry_date)).days)
        except Exception:
            days_held = 0
        out.append({
            "ticker":          opp.ticker.upper(),
            "runner":          opp.runner.upper(),
            "entry_date":      entry_date,
            "entry_price":     round(float(entry_price), 2),
            "current_price":   round(float(current), 2),
            "pnl_pct":         pnl_pct,
            "days_held":       days_held,
            "sector":          _sector_lookup(root, market, opp.ticker),
            "status":          "HOLD",
            "opportunity_id":  opp.opportunity_id,
            "created_date":    str(opp.created_date)[:10],
            "initial_signal":  opp.initial_signal or "BUY",
        })
    # Stable sort · deterministic across reruns
    out.sort(key=lambda p: (p["runner"], p["ticker"]))
    return out


def missing_tickers(root: Path, market: str, asof: str,
                     displayed: set) -> list[dict]:
    """Return Registry-ACTIVE positions NOT already in `displayed`
    (a set of (runner, ticker) tuples already written to Portfolio
    by the main row-emit loop)."""
    canonical = build_active_positions(root, market, asof)
    return [p for p in canonical
             if (p["runner"], p["ticker"]) not in displayed]
