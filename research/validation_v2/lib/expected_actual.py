"""Validation Engine v2.0 · expected vs actual reconciliation.

For every closed paper trade, compare the realised outcome against
what DEV023 predicted (entry / target / stop / holding period).
Aggregate divergences into an actionable report."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]


def _load_recommendations() -> dict[str, dict]:
    """Load current DEV023 recommendations keyed by ticker."""
    p = _ROOT / "reports" / "recommendations.json"
    if not p.exists():
        return {}
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(r["ticker"]): r for r in (j.get("recommendations") or [])}


def reconcile(closed_trades: pd.DataFrame) -> dict:
    """Reconcile realised outcomes against DEV023 targets."""
    if closed_trades.empty:
        return {"n": 0, "note": "no closed trades yet"}

    recs = _load_recommendations()

    per_trade = []
    for _, t in closed_trades.iterrows():
        rec = recs.get(str(t["ticker"]), {})
        target1 = rec.get("target_1")
        stop = rec.get("stop_loss")
        expected_hold = rec.get("expected_hold_days")

        exit_price = float(t.get("exit_price") or 0)
        ret = float(t.get("return_pct") or 0)
        hd = int(t.get("holding_days") or 0)

        expected_ret = None
        if target1 is not None and t.get("entry_price"):
            try:
                expected_ret = (float(target1) - float(t["entry_price"])) / float(t["entry_price"])
            except Exception:
                pass

        row = {
            "ticker":              t["ticker"],
            "entry_date":          t["entry_date"],
            "exit_date":           t["exit_date"],
            "rec_type":            t.get("rec_type"),
            "rec_source":          t.get("rec_source"),
            "actual_return_pct":   ret,
            "expected_return_pct": expected_ret,
            "return_delta":        (ret - expected_ret) if expected_ret is not None else None,
            "actual_holding_days": hd,
            "expected_holding_days": expected_hold,
            "holding_delta":       (hd - expected_hold) if expected_hold is not None else None,
            "hit_target":          (exit_price >= float(target1)) if target1 else None,
            "hit_stop":             (exit_price <= float(stop)) if stop else None,
            "reason_close":        t.get("reason_close"),
        }
        per_trade.append(row)

    df = pd.DataFrame(per_trade)

    # Aggregate
    non_null = df["return_delta"].dropna()
    avg_delta = float(non_null.mean()) if len(non_null) else None
    hit_rate_target = float(df["hit_target"].dropna().mean()) if df["hit_target"].notna().any() else None
    hit_rate_stop   = float(df["hit_stop"].dropna().mean())   if df["hit_stop"].notna().any() else None
    within_tolerance = None
    if avg_delta is not None:
        within_tolerance = bool(abs(avg_delta) < 0.05)  # 5pp tolerance

    return {
        "n":                    int(len(df)),
        "avg_return_delta":     round(avg_delta, 4) if avg_delta is not None else None,
        "target_hit_rate":      round(hit_rate_target, 4) if hit_rate_target is not None else None,
        "stop_hit_rate":        round(hit_rate_stop, 4) if hit_rate_stop is not None else None,
        "within_5pp_tolerance": within_tolerance,
        "per_trade":            per_trade,
    }
