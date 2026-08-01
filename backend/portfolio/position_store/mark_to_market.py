"""Non-destructive mark-to-market pass for the position store.

Post-mortem 2026-07-31: Max Gain and Max DD showing 0.00% for LUPIN /
HEROMOTOCO / CHAMBLFERT / TRV / etc. Root cause: position_store's
high_water_price and low_water_price were never re-priced after the
opening ingest. Upsert has an idempotent early-return when
`last_seen_date == asof` which prevents same-day updates from the
main pipeline; and the pipeline itself was passing the entry price
(from position_plan) rather than today's actual close price.

This module is a STANDALONE re-pricer:
  · Reads the daily close from data/raw/{market}/{TICKER}_D1.parquet
  · Updates every active position's last_seen_price · high_water_price
    · low_water_price for today
  · Never touches first_seen_* fields (respects position identity)
  · Idempotent per (ticker, asof, price) · re-running is safe
  · No enricher · no snapshot archiver · no recommendation regen

Call sites:
  · scripts/mark_to_market.py --market {india|usa|both}
  · scripts/telegram_command_center_send.py (auto-runs before send)

This mark-to-market pass is what makes Max Gain / Max DD reflect
reality instead of showing stale zeros.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from .store import (  # noqa: E402
    load_all_positions,
    _save_all_positions,
    _append_history,
)


def _bar_path(root: Path, ticker: str, market: str) -> Path:
    """Locate the daily bar parquet · same convention as backend/research/paper_portfolio.py."""
    if market == "usa":
        return root / "data" / "raw" / "us" / f"{ticker}_D1.parquet"
    return root / "data" / "raw" / "india" / f"{ticker}_D1.parquet"


def _normalize_ticker(t: str) -> str:
    """Strip exchange suffix (.NS · .BO) for filename lookup."""
    if not t:
        return ""
    t = t.strip()
    for suffix in (".NS", ".BO", ".NSE", ".BSE"):
        if t.upper().endswith(suffix):
            return t[: -len(suffix)]
    return t


def _latest_close(root: Path, ticker: str, market: str) -> float | None:
    """Read the most recent close price from the daily bar cache.
    Falls back to yfinance on-demand for USA (no local cache typical)."""
    try:
        import pandas as pd
    except ImportError:
        return None
    bare = _normalize_ticker(ticker)
    p = _bar_path(root, bare, market)
    if p.exists():
        try:
            df = pd.read_parquet(p)
            if len(df) > 0:
                return float(df["close"].iloc[-1])
        except Exception:
            pass
    # USA fallback: yfinance on-demand
    if market == "usa":
        try:
            import yfinance as yf
            df = yf.download(bare, period="5d", interval="1d",
                                progress=False, auto_adjust=False, threads=False)
            if df is not None and len(df) > 0:
                close_col = df["Close"] if "Close" in df.columns else df.iloc[:, 3]
                return float(close_col.iloc[-1])
        except Exception:
            pass
    return None


def _reports_root(root: Path, market: str) -> Path:
    return (root / "usa" / "reports") if market == "usa" else (root / "reports")


def mark_to_market(root: Path, market: str, asof: str | None = None,
                      force: bool = False) -> dict:
    """Re-price every active position in the position store to today's close.

    Non-destructive:
      · first_seen_date and first_seen_price are NEVER modified
      · Only last_seen_date · last_seen_price · high_water · low_water update
      · High-water only rises · low-water only falls (monotonic tracking)

    Idempotent:
      · Re-running with same asof + same price is a no-op
      · Records an MTM history event with delta from last mark

    Returns summary dict for the sender/validator to log.
    """
    asof = asof or date.today().isoformat()
    reports = _reports_root(root, market)
    positions = load_all_positions(reports, market)
    if not positions:
        return {"market": market, "asof": asof, "n_positions": 0,
                  "n_repriced": 0, "n_missing_price": 0, "errors": []}

    n_repriced = 0
    n_missing = 0
    errors: list[str] = []
    now_utc = datetime.now(timezone.utc).isoformat()

    for ticker, rec in positions.items():
        if not rec.is_active and not force:
            continue
        current_close = _latest_close(root, ticker, market)
        if current_close is None or current_close <= 0:
            n_missing += 1
            errors.append(f"{ticker}: no close price available")
            continue

        # Always update — this is a mark-to-market pass, not an ingest.
        # Even if last_seen_date == asof, we may have gotten a stale price
        # earlier and want to correct it.
        prior_last = rec.last_seen_price
        prior_high = rec.high_water_price
        prior_low = rec.low_water_price

        rec.last_seen_date = asof
        rec.last_seen_price = float(current_close)
        if float(current_close) > rec.high_water_price:
            rec.high_water_price = float(current_close)
        if float(current_close) < rec.low_water_price:
            rec.low_water_price = float(current_close)

        # Only count as "repriced" if the value actually changed
        if prior_last != rec.last_seen_price or \
             prior_high != rec.high_water_price or \
             prior_low != rec.low_water_price:
            n_repriced += 1
            _append_history(reports, market, {
                "ts_utc":      now_utc,
                "asof":        asof,
                "ticker":      ticker,
                "event":       "MARK_TO_MARKET",
                "price":       float(current_close),
                "prior_price": prior_last,
                "high_water":  rec.high_water_price,
                "low_water":   rec.low_water_price,
                "delta_pct":   round((current_close / rec.first_seen_price - 1) * 100, 3)
                                    if rec.first_seen_price else 0,
            })

    _save_all_positions(reports, market, positions)

    return {
        "market":            market,
        "asof":              asof,
        "n_positions":       len(positions),
        "n_repriced":        n_repriced,
        "n_missing_price":   n_missing,
        "errors":            errors[:10],       # cap error list
    }


def validate_position_freshness(root: Path, market: str,
                                    asof: str | None = None,
                                    max_stale_days: int = 1) -> dict:
    """Precaution: check every active position has a fresh last_seen_date.

    Called by the Telegram sender BEFORE any send. If any active position
    has last_seen_date more than `max_stale_days` behind asof, the sender
    can refuse to ship (operator directive: don't repeat 2026-07-31 zeros).

    Returns:
        {
          "market": str,
          "asof": str,
          "n_active": int,
          "n_stale": int,
          "stale_tickers": [{"ticker": ..., "last_seen": ..., "days_behind": int}],
          "verdict": "OK" | "STALE" | "NO_POSITIONS",
        }
    """
    asof = asof or date.today().isoformat()
    reports = _reports_root(root, market)
    positions = load_all_positions(reports, market)
    active = {t: p for t, p in positions.items() if p.is_active}

    if not active:
        return {"market": market, "asof": asof, "n_active": 0,
                  "n_stale": 0, "stale_tickers": [], "verdict": "NO_POSITIONS"}

    try:
        asof_dt = date.fromisoformat(asof)
    except ValueError:
        return {"market": market, "asof": asof, "n_active": len(active),
                  "n_stale": 0, "stale_tickers": [], "verdict": "INVALID_ASOF"}

    stale: list[dict] = []
    for ticker, rec in active.items():
        try:
            last_dt = date.fromisoformat(rec.last_seen_date)
        except (ValueError, TypeError):
            stale.append({"ticker": ticker, "last_seen": rec.last_seen_date,
                            "days_behind": -1})
            continue
        days_behind = (asof_dt - last_dt).days
        if days_behind > max_stale_days:
            stale.append({"ticker": ticker, "last_seen": rec.last_seen_date,
                            "days_behind": days_behind})

    return {
        "market":         market,
        "asof":           asof,
        "n_active":       len(active),
        "n_stale":        len(stale),
        "stale_tickers":  stale[:20],
        "verdict":        "OK" if not stale else "STALE",
    }
