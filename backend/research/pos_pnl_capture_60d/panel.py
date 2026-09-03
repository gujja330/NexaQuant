"""T5 selection metrics + T6 joint pos/neg accounting.

Per predeclared winner definition (16 trial family = 4 horizons × 4 thresholds):
  precision · recall · F1 · top-K capture · recoverable missed-winner cost.

Every metric reported both PER winner definition AND aggregated.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path


def _precision_recall_f1(tp: int, fp: int, fn: int) -> dict:
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec  = tp / (tp + fn) if (tp + fn) else 0.0
    f1   = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    return {"precision": prec, "recall": rec, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn}


def build_capture_panel(root: Path, market: str, dataset: dict,
                        confidence_floor: float = 0.55,
                        rank_topn: int = 15) -> dict:
    """Selection quality panel per winner definition.

    Also emits the missed-winner classification distribution per
    (horizon, threshold) so operator can see WHERE the misses cluster.
    """
    from backend.research.pos_pnl_capture_60d.missed_winner_funnel import (
        classify_missed_winner, MISS_CATEGORIES,
    )
    from backend.research.pos_pnl_capture_60d.dataset import (
        WINNER_HORIZONS_DAYS, WINNER_THRESHOLDS_PCT,
    )
    cands = dataset.get("candidates") or []
    per_definition: dict[str, dict] = {}
    total_missed_cost = {"5d": 0.0, "10d": 0.0, "20d": 0.0, "60d": 0.0}
    total_captured = {"5d": 0.0, "10d": 0.0, "20d": 0.0, "60d": 0.0}

    for h in WINNER_HORIZONS_DAYS:
        for t in WINNER_THRESHOLDS_PCT:
            key = f"h{h}_t{int(t*100)}pct"
            label = f"is_winner_{h}d_at_{int(t*100)}pct"
            tp = fp = fn = tn = 0
            miss_dist: Counter = Counter()
            missed_cost_sum = 0.0
            for c in cands:
                is_win = c.get(label)
                if is_win is None: continue
                sel = bool(c.get("was_selected_by_aegis"))
                if is_win and sel: tp += 1
                elif is_win and not sel:
                    fn += 1
                    fwd_val = c.get(f"fwd_{h}d") or 0.0
                    missed_cost_sum += float(fwd_val)
                    # Classify miss
                    cls = classify_missed_winner(
                        root, market, c.get("date"), c.get("ticker"),
                        was_in_universe=True, data_available=bool(c.get("data_available")),
                        confidence_floor=confidence_floor, rank_topn=rank_topn,
                    )
                    miss_dist[cls["category"]] += 1
                elif not is_win and sel: fp += 1
                else: tn += 1
            per_definition[key] = {
                **_precision_recall_f1(tp, fp, fn),
                "tn": tn,
                "winner_recall_at_definition": (tp / (tp + fn) if (tp + fn) else 0.0),
                "missed_winner_cost_sum_pct": missed_cost_sum,
                "miss_category_distribution": dict(miss_dist),
            }
            horizon_key = f"{h}d"
            total_missed_cost[horizon_key] = total_missed_cost.get(horizon_key, 0.0) + missed_cost_sum
            total_captured[horizon_key] = total_captured.get(horizon_key, 0.0) + tp

    panel = {
        "market": market,
        "asof_today": dataset.get("asof_today"),
        "window_start": dataset.get("window_start"),
        "n_candidates_total": len(cands),
        "n_data_available": dataset.get("n_data_available"),
        "n_data_missing": dataset.get("n_data_missing"),
        "winner_definition_trial_count": dataset.get("winner_definition_trial_count"),
        "per_winner_definition": per_definition,
        "aggregate_missed_cost_pct_by_horizon": total_missed_cost,
        "aggregate_captured_count_by_horizon": total_captured,
        "governance_note": (
            "Trial family = 16 (4 horizons × 4 thresholds). "
            "Any 'best' variant claim must apply Deflated Sharpe with "
            "n_trials=16. Missed-winner cost is a research metric · NOT "
            "a production target. Category L (correct risk rejection) is "
            "not currently computable from available substrate; misses "
            "flagged G_RISK_MISS_OR_LATER_UNKNOWN could be L in practice."
        ),
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out = root / "reports" / "research" / "pos_pnl_capture_60d"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"panel_{market}.json").write_text(
        json.dumps(panel, indent=2, default=str), encoding="utf-8"
    )
    return panel
