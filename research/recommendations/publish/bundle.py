"""DEV023 publish — 5 JSON outputs."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
PUBLISH_DIR = _ROOT / "reports"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat() + "Z"


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.integer, np.floating)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    return obj


def build_and_publish(engine_result: dict) -> dict:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)

    recs = engine_result.get("recommendations", [])
    now = _now()

    # ── recommendations.json ── full detail every ticker ────────────────────
    with (PUBLISH_DIR / "recommendations.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize(engine_result), f, indent=2, default=str)

    # ── recommendations.parquet ── flat table ───────────────────────────────
    parquet_rows = []
    for r in recs:
        ee = r.get("entry_exit") or {}
        parquet_rows.append({
            "ticker":            r["ticker"],
            "recommendation":    r["recommendation"],
            "action":            r["action"],
            "composite_decision_score": r["composite_decision_score"],
            "conviction_pct":    r["conviction_pct"],
            "score":             r["score"],
            "classification":    r["classification"],
            "confidence":        r["confidence"],
            "sector":            r["sector"],
            "industry":          r["industry"],
            "sector_score":      r["sector_score"],
            "industry_score":    r["industry_score"],
            "overall_rank":      r["overall_rank"],
            "in_target_portfolios_count": len(r.get("in_target_portfolios", [])),
            "currently_held":    r["currently_held"],
            "unrealised_pnl_pct": r.get("unrealised_pnl_pct"),
            "latest_close":      ee.get("latest_close"),
            "ideal_entry_low":   ee.get("ideal_entry_low"),
            "ideal_entry_high":  ee.get("ideal_entry_high"),
            "target_1":          ee.get("target_1"),
            "target_2":          ee.get("target_2"),
            "stop_loss":         ee.get("stop_loss"),
            "stop_loss_pct":     ee.get("stop_loss_pct"),
            "expected_hold_days": ee.get("expected_holding_days"),
        })
    pd.DataFrame(parquet_rows).to_parquet(PUBLISH_DIR / "recommendations.parquet", index=False)

    # ── watchlist.json ── near-Buy / near-Strong-Buy candidates ─────────────
    watchlist = [r for r in recs if r["recommendation"] == "Watchlist"]
    with (PUBLISH_DIR / "watchlist.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({"run_utc": now,
                                "n_watchlist": len(watchlist),
                                "watchlist": watchlist}),
                    f, indent=2, default=str)

    # ── trade_summary.json ── ordered action plan ───────────────────────────
    actions = defaultdict(list)
    for r in recs:
        actions[r["recommendation"]].append(r)

    trade_summary = {
        "run_utc": now,
        "counts": {k: len(v) for k, v in actions.items()},
        "buys":         _condensed_rows(actions.get("Strong-Buy", []) + actions.get("Buy", [])),
        "accumulates":  _condensed_rows(actions.get("Accumulate", [])),
        "holds":        _condensed_rows(actions.get("Hold", [])),
        "reduces":      _condensed_rows(actions.get("Reduce", [])),
        "sells":        _condensed_rows(actions.get("Sell", [])),
        "watchlist":    _condensed_rows(actions.get("Watchlist", []), n=20),
        "avoid":        _condensed_rows(actions.get("Avoid", []), n=20),
    }
    with (PUBLISH_DIR / "trade_summary.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize(trade_summary), f, indent=2, default=str)

    # ── execution_plan.json ── ordered by conviction ───────────────────────
    execution_order = []
    for action_type in ("Strong-Buy", "Buy", "Accumulate", "Reduce", "Sell"):
        block = actions.get(action_type, [])
        # Sort by conviction descending
        block_sorted = sorted(block, key=lambda x: x["conviction_pct"], reverse=True)
        for r in block_sorted:
            ee = r.get("entry_exit") or {}
            execution_order.append({
                "step":              len(execution_order) + 1,
                "ticker":            r["ticker"],
                "action":            r["action"],
                "recommendation":    r["recommendation"],
                "conviction_pct":    r["conviction_pct"],
                "composite_decision_score": r["composite_decision_score"],
                "sector":            r["sector"],
                "industry":          r["industry"],
                "latest_close":      ee.get("latest_close"),
                "ideal_entry":       f"{ee.get('ideal_entry_low')} - {ee.get('ideal_entry_high')}"
                                     if ee.get("ideal_entry_low") else None,
                "target_1":          ee.get("target_1"),
                "target_2":          ee.get("target_2"),
                "stop_loss":         ee.get("stop_loss"),
                "expected_hold":     ee.get("expected_holding_days"),
                "reasoning":         r["reasons_for"][:3],
            })

    with (PUBLISH_DIR / "execution_plan.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc": now,
            "n_action_items": len(execution_order),
            "governance_note": ("Advisory only. Operator must review and execute manually. "
                                    "No broker integration in v0.1 (ARCH011 deferred)."),
            "execution_order": execution_order,
        }), f, indent=2, default=str)

    return {
        "recommendations":   recs,
        "trade_summary":     trade_summary,
        "watchlist_count":   len(watchlist),
        "execution_count":   len(execution_order),
    }


def _condensed_rows(rows: list[dict], n: int = 30) -> list[dict]:
    """Compact per-recommendation summary."""
    out = []
    for r in rows[:n]:
        ee = r.get("entry_exit") or {}
        out.append({
            "ticker":            r["ticker"],
            "conviction_pct":    r["conviction_pct"],
            "composite_score":   r["composite_decision_score"],
            "score":             r["score"],
            "sector":            r["sector"],
            "industry":          r["industry"],
            "latest_close":      ee.get("latest_close"),
            "target_1":          ee.get("target_1"),
            "stop_loss":         ee.get("stop_loss"),
            "top_reasons":       r["reasons_for"][:2],
        })
    return out
