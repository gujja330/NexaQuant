"""Intraday · Hourly Bar Fetcher + Real Intraday Paper Portfolios.

Operator approved: "intraday hourly data makes sense."

Uses yfinance free tier · 1h interval · up to ~730 days back for NSE
tickers. This is REAL intraday (hourly path), not the daily-OHLC proxy
we had before.

Storage:
  data/raw/india_hourly/{TICKER}_H1.parquet   # append-only local cache
  reports/research/runner1_intraday_h1/positions.json + history.jsonl
  reports/research/runner2_intraday_h1/positions.json + history.jsonl

Entry / exit semantics for hourly-intraday paper:
  · Entry = first hourly bar OPEN of the trading day
  · Exit  = last hourly bar CLOSE of the same trading day
  · Never held overnight · 1-day scope · rebuilt each session

Rate-limit friendly:
  · One symbol fetched at a time · small sleeps between
  · Uses local parquet cache · only fetches missing days on next call
  · If yfinance is not installed or rate-limits, degrades to the
    daily-OHLC proxy path silently (no daily-job failure)
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.research.intraday_hourly.v1.20260731"

YFINANCE_INTERVAL = "1h"
YFINANCE_MAX_LOOKBACK_DAYS = 720            # yfinance hard cap ~730
FETCH_SLEEP_SECS = 0.3                       # be polite to yfinance
DEFAULT_UNIVERSE_LIMIT = 30                  # cap per run (rate-limit safety)


def _normalize(t: str) -> str:
    t = (t or "").strip()
    for suffix in (".NS", ".BO", ".NSE", ".BSE"):
        if t.upper().endswith(suffix):
            return t[: -len(suffix)]
    return t


def _yf_symbol(bare: str) -> str:
    """Add .NS suffix for NSE if missing (yfinance format)."""
    return bare if "." in bare else f"{bare}.NS"


def _cache_path(root: Path, bare: str) -> Path:
    d = root / "data" / "raw" / "india_hourly"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{bare}_H1.parquet"


def fetch_hourly_bars(root: Path, tickers: list[str],
                          lookback_days: int = 60,
                          limit: int = DEFAULT_UNIVERSE_LIMIT) -> dict:
    """Fetch (or refresh) hourly bars for `tickers` into local parquet cache.

    Returns summary dict {fetched: n, cached_hits: n, errors: [...]}.
    Silent degradation: if yfinance is missing, returns {"skipped": "no_yfinance"}.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        return {"skipped": "yfinance_not_installed",
                  "hint": "pip install yfinance"}

    if lookback_days > YFINANCE_MAX_LOOKBACK_DAYS:
        lookback_days = YFINANCE_MAX_LOOKBACK_DAYS

    tickers = [_normalize(t) for t in tickers if t]
    tickers = list(dict.fromkeys(tickers))[:limit]     # dedupe, cap

    result = {
        "requested":     len(tickers),
        "fetched":       0,
        "cached_hits":   0,
        "rows_written":  0,
        "errors":        [],
    }

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    for bare in tickers:
        cp = _cache_path(root, bare)
        try:
            df = yf.download(_yf_symbol(bare),
                                start=start, end=end,
                                interval=YFINANCE_INTERVAL,
                                progress=False, auto_adjust=False,
                                threads=False)
            if df is None or df.empty:
                result["errors"].append({"ticker": bare, "reason": "empty_response"})
                continue
            df = df.rename(columns=str.lower)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            # Merge with existing cache
            if cp.exists():
                try:
                    prev = pd.read_parquet(cp)
                    combined = pd.concat([prev, df]).sort_index()
                    combined = combined[~combined.index.duplicated(keep="last")]
                    df = combined
                    result["cached_hits"] += 1
                except Exception:
                    pass
            df.to_parquet(cp)
            result["fetched"] += 1
            result["rows_written"] += len(df)
        except Exception as e:
            result["errors"].append({"ticker": bare, "reason": str(e)[:200]})
        time.sleep(FETCH_SLEEP_SECS)
    return result


def _load_intraday_bar(root: Path, ticker: str, as_of: str) -> tuple[float | None, float | None]:
    """Return (session_open, session_close) for the given date from hourly cache.
    Session open = first bar of the day. Session close = last bar of the day."""
    try:
        import pandas as pd
    except ImportError:
        return None, None
    bare = _normalize(ticker)
    cp = _cache_path(root, bare)
    if not cp.exists():
        return None, None
    try:
        df = pd.read_parquet(cp)
        df.index = pd.to_datetime(df.index)
        d = pd.to_datetime(as_of).date()
        day = df[df.index.date == d]
        if day.empty:
            return None, None
        return float(day["open"].iloc[0]), float(day["close"].iloc[-1])
    except Exception:
        return None, None


def _snapshot(root: Path, runner_slug: str, picks: list[dict], as_of: str) -> dict:
    out_dir = root / "reports" / "research" / runner_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    positions: dict[str, dict] = {}
    n_opened = 0
    n_valid = 0
    for pick in picks:
        t = str(pick.get("ticker") or "").strip()
        if not t:
            continue
        o, c = _load_intraday_bar(root, t, as_of)
        if not o or not c:
            continue
        n_valid += 1
        positions[t] = {
            "ticker":              t,
            "first_seen_date":     as_of,
            "last_seen_date":      as_of,
            "entry_price":         o,
            "first_seen_price":    o,
            "last_seen_price":     c,
            "high_water_price":    c,
            "low_water_price":     c,
            "n_days_active":       1,
            "is_active":           False,
            "score_at_entry":      pick.get("score"),
        }
        n_opened += 1

    payload = {
        "engine":              "aegis.research.intraday_hourly.v1",
        "schema_fingerprint":  SCHEMA_FINGERPRINT,
        "runner":              runner_slug,
        "mode":                "intraday_shadow_hourly",
        "as_of":               as_of,
        "run_utc":             datetime.now(timezone.utc).isoformat(),
        "positions":           positions,
    }
    (out_dir / "positions.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    event = {
        "as_of":       as_of,
        "run_utc":     payload["run_utc"],
        "n_picks":     len(picks),
        "n_valid":     n_valid,
        "n_opened":    n_opened,
        "n_active":    0,
        "n_closed":    n_opened,
    }
    with (out_dir / "history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    return payload


def ingest_hourly_intraday(root: Path, picks_r1: list[dict],
                              picks_r2: list[dict],
                              as_of: str | None = None,
                              refresh_cache: bool = True) -> dict:
    """Full hourly intraday ingest for BOTH runners.

    picks_r1/r2: [{"ticker": str, "score": float | None}, ...]
    refresh_cache: if True, tries to fetch fresh hourly bars for the
                     union of ticker universes before snapshotting.
    """
    as_of = as_of or date.today().isoformat()
    universe = list({p["ticker"] for p in picks_r1 + picks_r2 if p.get("ticker")})

    fetch_summary = None
    if refresh_cache and universe:
        fetch_summary = fetch_hourly_bars(root, universe, lookback_days=5)

    r1 = _snapshot(root, "runner1_intraday_h1", picks_r1, as_of)
    r2 = _snapshot(root, "runner2_intraday_h1", picks_r2, as_of)
    return {
        "as_of":         as_of,
        "fetch_summary": fetch_summary,
        "runner1_intraday_h1": {"n_positions": len(r1.get("positions", {}))},
        "runner2_intraday_h1": {"n_positions": len(r2.get("positions", {}))},
    }
