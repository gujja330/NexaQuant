"""T2 negative-P&L trajectory classification + T6 MFE/MAE + T5 recovery."""
from __future__ import annotations

from collections import Counter


def classify_trajectory(pos: dict) -> str:
    """Assign one of {IMMEDIATE_LOSER · TEMPORARY_LOSER · DEEP_LOSER ·
    LATE_DETERIORATION · WINNER · FLAT}."""
    worst = pos.get("worst_pct")
    eventual = pos.get("eventual_pct")
    first_neg = pos.get("first_negative_day")
    n_days = pos.get("n_daily_snapshots") or 0

    if worst is None or eventual is None: return "UNKNOWN"

    if worst <= -0.10:
        return "DEEP_LOSER"
    if worst < 0 and eventual > 0:
        return "TEMPORARY_LOSER"       # went red but recovered to profit
    if worst < 0 and eventual > worst + 0.02 and eventual < 0:
        return "TEMPORARY_LOSER"       # bounced but still red
    if first_neg is not None and first_neg > (n_days * 0.5) and worst < -0.03:
        return "LATE_DETERIORATION"
    if worst < 0 and eventual <= worst + 0.01:
        return "IMMEDIATE_LOSER"       # kept falling
    if eventual > 0: return "WINNER"
    return "FLAT"


def mfe_mae_bucket(pos: dict) -> str:
    """T6 · classify by MFE/MAE combination."""
    mfe = pos.get("mfe_pct"); mae = pos.get("mae_pct")
    if mfe is None or mae is None: return "UNKNOWN"
    hi_mfe = mfe >= 0.05
    hi_mae = mae <= -0.05
    if not hi_mae and hi_mfe:  return "LOW_MAE_HIGH_MFE"
    if hi_mae and hi_mfe:      return "HIGH_MAE_HIGH_MFE"
    if hi_mae and not hi_mfe:  return "HIGH_MAE_LOW_MFE"    # <- key intervention group
    return "LOW_MAE_LOW_MFE"


def analyze_trajectories(dataset: dict) -> dict:
    """Runs T2 + T5 + T6 across the dataset positions.

    Returns aggregated distributions + per-position tags added inline
    (dataset is modified in place — key `class` and `mfe_mae_bucket`)."""
    trajs = dataset.get("trajectories", [])
    class_counts = Counter()
    mfe_mae_counts = Counter()
    recover_by_class = Counter()
    n_became_profitable_by_class = Counter()

    for pos in trajs:
        cls = classify_trajectory(pos)
        bucket = mfe_mae_bucket(pos)
        pos["class"] = cls
        pos["mfe_mae_bucket"] = bucket
        class_counts[cls] += 1
        mfe_mae_counts[bucket] += 1
        if pos.get("recovered_from_worst"): recover_by_class[cls] += 1
        if pos.get("became_profitable"): n_became_profitable_by_class[cls] += 1

    # Depth cohorts · positions crossing thresholds
    depth_cohorts = {
        "n_crossed_-2": sum(1 for p in trajs if p.get("first_neg2_day") is not None),
        "n_crossed_-3": sum(1 for p in trajs if p.get("first_neg3_day") is not None),
        "n_crossed_-5": sum(1 for p in trajs if p.get("first_neg5_day") is not None),
        "n_crossed_-7": sum(1 for p in trajs if p.get("first_neg7_day") is not None),
    }

    return {
        "n_positions": len(trajs),
        "class_distribution": dict(class_counts),
        "mfe_mae_bucket_distribution": dict(mfe_mae_counts),
        "n_recovered_by_class": dict(recover_by_class),
        "n_became_profitable_by_class": dict(n_became_profitable_by_class),
        "depth_cohorts": depth_cohorts,
    }
