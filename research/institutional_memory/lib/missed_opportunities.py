"""Institutional Memory · Missed Opportunity Miner.

For every ticker in the universe (`data/raw/india/*.parquet`), compare
today's price vs the price N days ago. If the forward return exceeds a
threshold and the ticker was NOT in the recommendation set N days ago,
log it as a "missed alpha" event.

Also identifies the blocking reason from the archived state N days ago:
- below_intelligence_threshold
- sizing_block
- sector_regime_bearish
- not_in_universe_at_time
- unknown

This builds the training set for "what should we have caught?"
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import archive as _archive


_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = _ROOT / "data" / "raw" / "india"


# ── Thresholds (deterministic, tenant-generic)
DEFAULT_LOOKBACKS = [5, 20, 60]     # trading days
DEFAULT_THRESHOLD_PCT = 0.08         # forward return above 8% is "notable"


def _load_price_series(ticker: str) -> pd.Series | None:
    p = RAW_DIR / f"{ticker}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
    except Exception:
        return None
    if df.empty: return None
    close_col = next((c for c in df.columns if c.lower() in ("close", "adj close", "adj_close")), None)
    if not close_col: return None
    date_col = next((c for c in df.columns if c.lower() in ("date", "dt", "timestamp")), None)
    if date_col and date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col]).sort_values(date_col).set_index(date_col)
    else:
        try:
            df.index = pd.to_datetime(df.index, errors="coerce")
        except Exception:
            return None
        df = df.sort_index()
    return df[close_col].dropna().astype(float)


def _recommended_tickers_on(day: str) -> set[str]:
    j = _archive.read_archive_bundle(day, "recommendations.json") or {}
    return {str(r["ticker"]) for r in (j.get("recommendations") or []) if r.get("ticker")}


def _intel_on(day: str) -> dict[str, float]:
    j = _archive.read_archive_bundle(day, "investment_intelligence.json") or {}
    return {str(r["ticker"]): r.get("intelligence_score")
            for r in (j.get("reports") or []) if r.get("ticker")}


def _blocking_reason(ticker: str, day: str) -> str:
    """Best-effort reason the ticker was NOT in the rec set on `day`."""
    intel = _intel_on(day).get(ticker)
    if intel is None:
        return "not_in_universe_at_time"
    if intel < 50:
        return "intelligence_score_below_threshold"
    if intel < 65:
        return "intelligence_score_moderate"
    # Was scored high but still rejected — check sizing / risk block from the
    # archived risk_capital_v2 snapshot.
    j = _archive.read_archive_bundle(day, "risk_capital_v2_latest.json") or {}
    for s in (j.get("sizing") or []):
        if str(s.get("ticker")) == ticker:
            if s.get("verdict") == "BLOCK":
                return "risk_sizing_block"
            if s.get("verdict") == "WARNING":
                return "risk_sizing_warning"
    return "unknown_reject"


def mine_missed(
    lookbacks: list[int] | None = None,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
    max_missed_per_day: int = 50,
) -> dict:
    """Scan the archive for missed alpha events.

    For each archive day (going back through history), and for each lookback
    window, find tickers whose forward return exceeded the threshold but were
    not in the recommendation set on the anchor day.
    """
    if lookbacks is None:
        lookbacks = list(DEFAULT_LOOKBACKS)
    days = _archive.list_archive_days()
    if not days:
        return {"n_days_scanned": 0, "n_events": 0, "events": [],
                "note": "no archive yet — first archive run establishes baseline"}

    # Universe from disk
    universe = sorted([p.stem.replace("_D1", "") for p in RAW_DIR.glob("*_D1.parquet")])
    price_cache: dict[str, pd.Series] = {}

    events: list[dict] = []
    for anchor_day in days:
        anchor_dt = pd.to_datetime(anchor_day)
        recommended = _recommended_tickers_on(anchor_day)

        for N in lookbacks:
            # Skip lookback windows that extend into the future
            # (we can only compute forward-N if N days of price data exist AFTER anchor_day)
            for ticker in universe:
                if ticker in recommended:
                    continue
                s = price_cache.get(ticker)
                if s is None:
                    s = _load_price_series(ticker)
                    if s is None:
                        continue
                    price_cache[ticker] = s

                # Find price at anchor date (nearest ≤ anchor_dt)
                s_anchor = s[s.index <= anchor_dt]
                if s_anchor.empty:
                    continue
                p_anchor = float(s_anchor.iloc[-1])

                # Forward N trading days
                s_forward = s[s.index > anchor_dt]
                if len(s_forward) < N:
                    continue
                p_forward = float(s_forward.iloc[N - 1])
                fwd_ret = (p_forward - p_anchor) / p_anchor if p_anchor > 0 else 0.0

                if fwd_ret >= threshold_pct:
                    events.append({
                        "ticker":         ticker,
                        "anchor_date":    anchor_day,
                        "forward_days":   N,
                        "forward_return": round(fwd_ret, 4),
                        "anchor_price":   round(p_anchor, 2),
                        "forward_price":  round(p_forward, 2),
                        "blocking_reason": _blocking_reason(ticker, anchor_day),
                        "intel_at_anchor":  _intel_on(anchor_day).get(ticker),
                    })

    # Deterministic sort: biggest missed alpha first, then earliest anchor date, then ticker
    events.sort(key=lambda e: (-e["forward_return"], e["anchor_date"], e["ticker"]))

    # Optional cap per day to keep the report readable
    if max_missed_per_day:
        capped: list[dict] = []
        per_day_counts: dict[str, int] = {}
        for e in events:
            k = e["anchor_date"]
            if per_day_counts.get(k, 0) < max_missed_per_day:
                capped.append(e)
                per_day_counts[k] = per_day_counts.get(k, 0) + 1
        events = capped

    # Blocking-reason breakdown
    reasons: dict[str, int] = {}
    for e in events:
        reasons[e["blocking_reason"]] = reasons.get(e["blocking_reason"], 0) + 1

    return {
        "n_days_scanned":   len(days),
        "lookbacks":        lookbacks,
        "threshold_pct":    threshold_pct,
        "n_events":         len(events),
        "reason_breakdown": dict(sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))),
        "top_missed":       events[:100],  # biggest 100 by forward return
        "all_events":       events,        # full list (still deterministic order)
    }
