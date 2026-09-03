"""T13 protection+damage panel · T14 recent vs historical baseline · T15/16
false-positive / false-negative accounting.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _q(xs, p):
    if not xs: return None
    ys = sorted(xs)
    k = int(p * (len(ys) - 1))
    return ys[k]


def _load_historical_baseline(root: Path, market: str) -> dict:
    """T14 · full Outcome Dataset baseline metrics for comparison."""
    import pandas as pd
    p = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if not p.exists(): return {}
    df = pd.read_parquet(p)
    if df.empty: return {}
    closed = df[(df["is_administrative_exit"] != True) &
                df["realized_return_pct"].notna()]
    if closed.empty: return {}
    rets = closed["realized_return_pct"].astype(float).tolist()
    negs = [r for r in rets if r < 0]
    return {
        "n": int(len(rets)),
        "mean": _mean(rets),
        "median": _q(rets, 0.5),
        "p95_loss": _q(negs, 0.05) if negs else None,
        "max_loss": min(rets) if rets else None,
        "loss_rate": (len([r for r in rets if r < 0]) / len(rets)) if rets else 0.0,
    }


def build_panel(root: Path, market: str, dataset: dict,
                trajectory_summary: dict, counterfactual: dict) -> dict:
    """Assemble T13 + T14 + T15 + T16 panel."""
    trajs = dataset.get("trajectories", [])
    rets = [p.get("eventual_pct", 0.0) for p in trajs]
    negs = [r for r in rets if r < 0]

    protection_recent = {
        "n": len(rets),
        "sum_negative_pnl": sum(negs),
        "mean_loss": _mean(negs),
        "median_loss": _q(negs, 0.5),
        "p95_loss": _q(negs, 0.05),
        "max_loss": min(rets) if rets else None,
        "loss_count": len(negs),
        "loss_rate": (len(negs) / len(rets)) if rets else 0.0,
    }

    # T15 · winner-sacrifice per variant
    winner_sacrifice = [{
        "variant": (f"static_pct@{v['threshold_pct']}"
                    if v.get("doctrine") == "static_pct"
                    else f"static_time@{v['timing_days']}d"),
        "n_exited_early": v["n_exited_early"],
        "n_winners_sacrificed": v["damage"]["n_winners_sacrificed"],
        "n_recovered_sacrificed": v["damage"]["n_recovered_sacrificed"],
        "winner_sacrifice_rate": v["damage"]["winner_sacrifice_rate"],
        "forfeited_upside_sum": v["damage"]["forfeited_upside_sum"],
    } for v in counterfactual.get("variants", [])]

    # T16 · false-negatives · deep losers that would still not have been caught
    def _still_deep_after_variant(v):
        # For static_pct threshold t, deep losers whose min <= -0.10 but
        # trajectory never crossed t before falling deeper.
        # Approximation with the trajectory summary: any DEEP_LOSER whose
        # first_negN_day is None for the variant's threshold.
        if v.get("doctrine") == "static_pct":
            t = v["threshold_pct"]
            key = ("first_neg2_day" if t == -0.02 else
                   "first_neg3_day" if t == -0.03 else
                   "first_neg5_day" if t == -0.05 else
                   "first_neg7_day" if t == -0.07 else None)
            if key is None: return None
            deep = [p for p in trajs if (p.get("class") == "DEEP_LOSER")]
            missed = [p for p in deep if p.get(key) is None]
            return {"n_deep": len(deep), "n_missed_by_variant": len(missed)}
        return None

    false_negatives = [{
        "variant": (f"static_pct@{v['threshold_pct']}"
                    if v.get("doctrine") == "static_pct"
                    else f"static_time@{v['timing_days']}d"),
        "false_negative_analysis": _still_deep_after_variant(v),
    } for v in counterfactual.get("variants", [])]

    historical = _load_historical_baseline(root, market)

    panel = {
        "market": market,
        "asof_today": dataset.get("asof_today"),
        "window_start": dataset.get("window_start"),
        "protection_recent_60d": protection_recent,
        "historical_baseline_full_dataset": historical,
        "recent_vs_historical_mean_delta": (
            _mean(rets) - historical.get("mean", 0.0)
        ) if historical else None,
        "trajectory_classification": trajectory_summary.get("class_distribution"),
        "mfe_mae_buckets": trajectory_summary.get("mfe_mae_bucket_distribution"),
        "depth_cohorts": trajectory_summary.get("depth_cohorts"),
        "counterfactual_variants": counterfactual.get("variants"),
        "trial_count_family": counterfactual.get("trial_count"),
        "winner_sacrifice_table": winner_sacrifice,
        "false_negative_table": false_negatives,
        "governance_reminder": (
            "This panel is DIAGNOSTIC only. No variant here is a production "
            "proposal. Any tightening based on this panel must go through "
            "the PDF walk-forward validation (252/63/21/5) with Deflated "
            "Sharpe using n_trials from `trial_count_family`. Original P0 "
            "result (E-001) preserved unchanged."
        ),
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    out = root / "reports" / "research" / "neg_pnl_control_60d"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"panel_{market}.json").write_text(
        json.dumps(panel, indent=2, default=str), encoding="utf-8"
    )
    return panel
