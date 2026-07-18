"""Validation Engine v2.0 · orchestration.

Every daily run:
1. Pull current DEV023 recommendations.
2. Open paper positions for any new Strong-Buy / Buy that we're not already in.
3. Mark-to-market every open position using latest close prices from data/raw.
4. Close positions where the recommendation flipped to Sell / Reduce, or
   where target / stop was hit.
5. Reconcile closed trades vs DEV023 targets (expected vs actual).
6. Compute drift + edge decay.
7. Compute opportunity cost vs the recommendation history.

The engine writes to `data/market_intelligence/derived/validation_v2/`
and to `reports/validation_v2_*.{json,md}`."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from validation_v2.lib import paper_portfolio, expected_actual, drift, opportunity_cost   # noqa: E402


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _load_recommendations() -> dict:
    p = _ROOT / "reports" / "recommendations.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_learning() -> pd.DataFrame:
    p = _ROOT / "reports" / "learning.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()


def _latest_price_for(ticker: str) -> float | None:
    """Read the last close price for a ticker from data/raw/india/{ticker}_D1.parquet."""
    p = _ROOT / "data" / "raw" / "india" / f"{ticker}_D1.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        close_col = next((c for c in df.columns if c.lower() in ("close", "adj close", "adj_close")), None)
        if close_col is None:
            return None
        return float(df[close_col].iloc[-1])
    except Exception:
        return None


MAX_PAPER_POSITIONS = 20   # cap to keep the paper portfolio realistic


def _new_opens(recs: dict, as_of: str) -> list[dict]:
    """Return list of positions to open — top-N Strong-Buy / Buy / Accumulate
    NOT already in the paper book, ranked by composite_decision_score."""
    strong = {"Strong-Buy", "Buy", "Accumulate"}
    open_pos = paper_portfolio.open_positions()
    open_tickers = set(open_pos["ticker"].astype(str)) if not open_pos.empty else set()
    remaining_slots = max(0, MAX_PAPER_POSITIONS - len(open_tickers))
    if remaining_slots == 0:
        return []

    candidates = [r for r in (recs.get("recommendations") or [])
                    if r.get("recommendation") in strong
                    and str(r.get("ticker")) not in open_tickers]
    candidates.sort(key=lambda r: -float(r.get("composite_decision_score") or 0))

    # Equal weight across the top-N candidates that will fit
    n_to_open = min(len(candidates), remaining_slots)
    if n_to_open == 0:
        return []
    weight = round(1.0 / MAX_PAPER_POSITIONS, 5)   # 5% each; portfolio ~100% when full

    to_open = []
    for r in candidates[:n_to_open]:
        t = str(r.get("ticker"))
        price = _latest_price_for(t)
        if price is None:
            continue
        to_open.append({
            "ticker": t, "entry_price": price, "weight": weight,
            "rec_type": r.get("recommendation"), "entry_date": as_of,
        })
    return to_open


def _to_close(recs: dict) -> list[dict]:
    """Return list of positions to close — held tickers whose current rec
    is Sell / Reduce / Avoid."""
    exit_types = {"Sell", "Reduce", "Avoid"}
    open_pos = paper_portfolio.open_positions()
    if open_pos.empty:
        return []
    rec_by_ticker = {str(r["ticker"]): r for r in (recs.get("recommendations") or [])}
    to_close = []
    for _, pos in open_pos.iterrows():
        rec = rec_by_ticker.get(str(pos["ticker"]))
        if not rec:
            continue
        if rec.get("recommendation") in exit_types:
            price = _latest_price_for(str(pos["ticker"]))
            if price is None:
                continue
            to_close.append({
                "ticker":     str(pos["ticker"]),
                "exit_price": price,
                "reason":     f"rec_flip_to_{rec.get('recommendation')}",
            })
    return to_close


def run(dry_run: bool = False, verbose: bool = True) -> dict:
    as_of = date.today().isoformat()
    recs = _load_recommendations()
    if not recs:
        return {"error": "no reports/recommendations.json — run DEV023 first"}

    learning = _load_learning()

    if verbose:
        print(f"  as_of={as_of}   n_recs={len(recs.get('recommendations') or [])}")

    # Opens
    to_open_list = _new_opens(recs, as_of)
    opened = []
    if not dry_run:
        for op in to_open_list:
            t = paper_portfolio.open_position(**op, rec_source="v1.4")
            opened.append({"ticker": t.ticker, "entry_price": t.entry_price,
                             "weight": t.weight, "rec_type": t.rec_type})
    if verbose:
        print(f"  new opens: {len(opened)} ({'DRY' if dry_run else 'wrote'})")

    # Closes
    to_close_list = _to_close(recs)
    closed_now = []
    if not dry_run:
        for c in to_close_list:
            t = paper_portfolio.close_position(**c)
            if t is not None:
                closed_now.append({"ticker": t.ticker, "return_pct": t.return_pct,
                                       "holding_days": t.holding_days,
                                       "reason": t.reason_close})
    if verbose:
        print(f"  new closes: {len(closed_now)} ({'DRY' if dry_run else 'wrote'})")

    # Mark to market
    open_pos = paper_portfolio.open_positions()
    mtm_rows = pd.DataFrame()
    if not open_pos.empty and not dry_run:
        prices = {}
        for t in open_pos["ticker"].astype(str):
            p = _latest_price_for(t)
            if p is not None:
                prices[t] = p
        mtm_rows = paper_portfolio.mark_to_market(prices, as_of=as_of)
        if verbose:
            print(f"  MTM: {len(mtm_rows)} positions · portfolio pnl={float(mtm_rows['weighted_pnl'].sum() if not mtm_rows.empty else 0):.4f}")

    # Reconciliation
    closed = paper_portfolio.closed_trades()
    reconciliation = expected_actual.reconcile(closed)

    # Drift
    drift_report = drift.metric_drift(closed)
    rolling = drift.rolling_edge(closed, window=20)

    # Opportunity cost
    opp_cost = opportunity_cost.compute_opportunity_cost(recs, learning)

    # Summary
    open_n = int(len(open_pos))
    closed_n = int(len(closed))
    open_pnl = float(mtm_rows["weighted_pnl"].sum()) if not mtm_rows.empty else 0.0

    return {
        "run_utc":              datetime.now(timezone.utc).isoformat() + "Z",
        "code_sha":             _git_sha(),
        "engine":               "Validation Engine",
        "version":              "v2.0",
        "as_of":                as_of,
        "n_new_opens":          len(opened),
        "n_new_closes":         len(closed_now),
        "n_open_positions":     open_n,
        "n_closed_trades":      closed_n,
        "portfolio_pnl_pct":    round(open_pnl, 4),
        "reconciliation":       reconciliation,
        "metric_drift":         drift_report,
        "rolling_edge":         rolling.to_dict(orient="records") if not rolling.empty else [],
        "opportunity_cost":     opp_cost,
        "governance":           "Advisory-only. Paper trades never execute against a broker.",
        "_mtm":                 mtm_rows,
        "_opened":              opened,
        "_closed_now":          closed_now,
    }
