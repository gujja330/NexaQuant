"""Institutional Memory · per-ticker recommendation history + accuracy.

For every ticker in the current universe:
  1. Walk the archive and build a day-by-day recommendation timeline
     (action / intel / cmp / targets on each archived day).
  2. Join with closed trades from `reports/learning.parquet` — every
     closed trade IS a past AEGIS recommendation, so we can compute
     per-stock prediction accuracy today (before we have long archive
     coverage).
  3. Derive prediction accuracy: n_recommendations, n_correct, accuracy.
     Correct = is_winner (from learning.parquet) at the recommendation.

Output: reports/recommendation_history.json — one entry per ticker,
consumed by the Admin/Validation Lab stock-search page.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import archive as _archive


_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


def _derive_action_from_score(score: float, confidence: float | None = None) -> str:
    """Reverse-map score_at_entry → action pill (approximate, since the
    exact original recommendation pill wasn't stored in learning.parquet)."""
    if score is None:
        return "Buy"
    if score >= 82:  return "Strong-Buy"
    if score >= 72:  return "Buy"
    if score >= 60:  return "Accumulate"
    if score >= 45:  return "Watchlist"
    return "Hold"


def _archived_timeline_for(ticker: str, all_days: list[str]) -> list[dict]:
    """Recommendation snapshots for `ticker` across every archived day."""
    out: list[dict] = []
    for d in all_days:
        recs = _archive.read_archive_bundle(d, "recommendations.json") or {}
        found = None
        for r in (recs.get("recommendations") or []):
            if str(r.get("ticker")) == ticker:
                found = r; break

        intel = None
        ii = _archive.read_archive_bundle(d, "investment_intelligence.json") or {}
        for r in (ii.get("reports") or []):
            if str(r.get("ticker")) == ticker:
                intel = r.get("intelligence_score"); break

        pc = _archive.read_archive_bundle(d, "price_context.json") or {}
        price = (pc.get("tickers") or {}).get(ticker) or {}
        cmp_val = price.get("cmp") if price.get("available") else None

        if found:
            ee = found.get("entry_exit") or {}
            out.append({
                "date":       d,
                "action":     found.get("recommendation"),
                "score":      found.get("composite_decision_score"),
                "confidence": found.get("confidence"),
                "intel":      intel,
                "cmp":        cmp_val,
                "target_1":   ee.get("target_1"),
                "stop_loss":  ee.get("stop_loss"),
                "in_universe": True,
            })
        elif cmp_val is not None or intel is not None:
            out.append({
                "date": d, "action": None, "score": None,
                "confidence": None, "intel": intel,
                "cmp": cmp_val, "target_1": None, "stop_loss": None,
                "in_universe": False,
            })
    return out


def _closed_trades_for(ticker: str, trades_df: pd.DataFrame) -> list[dict]:
    """All historical closed trades for `ticker` from learning.parquet,
    with the reverse-derived action pill."""
    if trades_df.empty:
        return []
    rows = trades_df[trades_df["ticker"] == ticker]
    if rows.empty:
        return []
    out: list[dict] = []
    for _, r in rows.iterrows():
        # learning.parquet stores percent
        ret = r["return_pct"] if pd.notna(r.get("return_pct")) else None
        if ret is not None and abs(ret) > 1.5:
            ret = ret / 100.0
        mfe = r.get("mfe_pct")
        if mfe is not None and pd.notna(mfe) and abs(mfe) > 1.5:
            mfe = float(mfe) / 100.0
        mae = r.get("mae_pct")
        if mae is not None and pd.notna(mae) and abs(mae) > 1.5:
            mae = float(mae) / 100.0

        out.append({
            "entry_date":   str(r["entry_date"])[:10],
            "exit_date":    str(r["exit_date"])[:10],
            "entry_price":  round(float(r["entry_px"]), 2) if pd.notna(r.get("entry_px")) else None,
            "exit_price":   round(float(r["exit_px"]), 2)  if pd.notna(r.get("exit_px"))  else None,
            "return_pct":   round(float(ret), 4) if ret is not None else None,
            "mfe_pct":      round(float(mfe), 4) if mfe is not None and pd.notna(mfe) else None,
            "mae_pct":      round(float(mae), 4) if mae is not None and pd.notna(mae) else None,
            "n_bars_held":  int(r["n_bars_held"]) if pd.notna(r.get("n_bars_held")) else None,
            "is_winner":    bool(r["is_winner"]) if pd.notna(r.get("is_winner")) else None,
            "score_at_entry": round(float(r["score_at_entry"]), 2) if pd.notna(r.get("score_at_entry")) else None,
            "recommended_action": _derive_action_from_score(
                float(r["score_at_entry"]) if pd.notna(r.get("score_at_entry")) else None,
                float(r["confidence"])     if pd.notna(r.get("confidence"))     else None,
            ),
            "correct":      bool(r["is_winner"]) if pd.notna(r.get("is_winner")) else None,
        })
    # Newest first
    out.sort(key=lambda t: (t["entry_date"] or "", t["exit_date"] or ""), reverse=True)
    return out


def _accuracy(closed: list[dict]) -> dict:
    if not closed:
        return {"n_recommendations": 0, "n_correct": 0, "n_incorrect": 0,
                "accuracy": None,
                "avg_return_pct": None, "median_return_pct": None,
                "best_return_pct": None, "worst_return_pct": None}
    scored = [t for t in closed if t.get("correct") is not None]
    n_total = len(scored)
    n_correct = sum(1 for t in scored if t["correct"])
    returns = [t["return_pct"] for t in closed if t.get("return_pct") is not None]
    return {
        "n_recommendations": n_total,
        "n_correct":         n_correct,
        "n_incorrect":       n_total - n_correct,
        "accuracy":          round(n_correct / n_total, 4) if n_total else None,
        "avg_return_pct":    round(sum(returns) / len(returns), 4) if returns else None,
        "median_return_pct": round(sorted(returns)[len(returns) // 2], 4) if returns else None,
        "best_return_pct":   round(max(returns), 4) if returns else None,
        "worst_return_pct":  round(min(returns), 4) if returns else None,
    }


def build_recommendation_history() -> dict:
    """Full per-ticker recommendation history + accuracy."""
    all_days = _archive.list_archive_days()

    # Pull the current universe from today's recommendations (fallback: learning.parquet tickers)
    current_recs_p = REPORTS / "recommendations.json"
    universe: set[str] = set()
    if current_recs_p.exists():
        import json
        j = json.loads(current_recs_p.read_text(encoding="utf-8"))
        for r in (j.get("recommendations") or []):
            if r.get("ticker"): universe.add(str(r["ticker"]))

    learning_p = REPORTS / "learning.parquet"
    trades_df = pd.DataFrame()
    if learning_p.exists():
        try:
            trades_df = pd.read_parquet(learning_p)
            universe |= set(trades_df["ticker"].astype(str).unique())
        except Exception:
            pass

    tickers_out: dict[str, dict] = {}
    for t in sorted(universe):
        timeline = _archived_timeline_for(t, all_days)
        closed   = _closed_trades_for(t, trades_df)
        acc      = _accuracy(closed)
        tickers_out[t] = {
            "ticker":      t,
            "n_days_seen": sum(1 for x in timeline if x.get("in_universe")),
            "timeline":    timeline,
            "closed_trades": closed,
            "accuracy":    acc,
            "n_closed":    len(closed),
        }

    # Global stats
    all_acc = [v["accuracy"]["accuracy"]
                 for v in tickers_out.values()
                 if v["accuracy"]["accuracy"] is not None]
    global_acc = round(sum(all_acc) / len(all_acc), 4) if all_acc else None

    return {
        "n_tickers":       len(tickers_out),
        "n_days_archived": len(all_days),
        "coverage_days":   all_days,
        "tickers":         tickers_out,
        "global_avg_accuracy": global_acc,
        "n_tickers_with_history": sum(1 for v in tickers_out.values() if v["n_closed"] > 0),
    }
