"""T3 counterfactual intervention points + T4 static vs dynamic + T12 matched-pair.

Every threshold / timing tested becomes a trial in the family. Trial count
recorded for later Deflated Sharpe deflation.
"""
from __future__ import annotations

import math
import random

CONTROL_THRESHOLDS_PCT = [-0.02, -0.03, -0.04, -0.05, -0.06, -0.07]  # 6 variants
CONTROL_TIMINGS_DAYS = [3, 5, 10]                                    # 3 variants
# T4 doctrines
CONTROL_DOCTRINES = ["baseline", "static_pct", "static_time"]        # baseline + 2 doctrines
# Total variant family: 1 baseline + 6 static_pct + 3 static_time = 10 trials


def _apply_static_pct_control(trajectory: list[dict], threshold_pct: float):
    """Simulate exiting on first day trajectory close <= threshold_pct.
    Returns (exit_day, exit_pct, exited_flag)."""
    for i, d in enumerate(trajectory):
        if d["unrealized_pct"] <= threshold_pct:
            return (i, d["unrealized_pct"], True)
    return (None, trajectory[-1]["unrealized_pct"] if trajectory else 0.0, False)


def _apply_static_time_control(trajectory: list[dict], timing_days: int):
    """Simulate exiting on day `timing_days` from entry if position is
    unrealized-negative at that point."""
    if len(trajectory) <= timing_days:
        return (None, trajectory[-1]["unrealized_pct"] if trajectory else 0.0, False)
    d = trajectory[timing_days]
    if d["unrealized_pct"] < 0:
        return (timing_days, d["unrealized_pct"], True)
    return (None, trajectory[-1]["unrealized_pct"], False)


def _paired_bootstrap_mean_delta(deltas: list[float], n_resamples: int = 10_000,
                                  conf: float = 0.95, seed: int = 42) -> dict:
    if not deltas:
        return {"n": 0, "mean_delta": None, "ci_low": None, "ci_high": None, "p_two": None}
    n = len(deltas)
    observed = sum(deltas) / n
    rng = random.Random(seed)
    means = []
    for _ in range(n_resamples):
        s = 0.0
        for _ in range(n):
            s += deltas[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    alpha = (1.0 - conf) / 2.0
    lo = means[int(alpha * n_resamples)]
    hi = means[int((1.0 - alpha) * n_resamples)]
    n_beyond = sum(1 for m in means if (m <= 0 if observed >= 0 else m >= 0))
    p_two = min(2.0 * n_beyond / n_resamples, 1.0)
    return {"n": n, "mean_delta": observed,
            "ci_low": lo, "ci_high": hi, "p_two": p_two,
            "n_resamples": n_resamples}


def run_counterfactual_controls(dataset: dict, n_resamples: int = 10_000) -> dict:
    """Run every control variant against baseline (actual eventual P&L)."""
    trajs = [p for p in dataset.get("trajectories", []) if p.get("daily_trajectory")]
    baseline_pnl = [p["eventual_pct"] for p in trajs]
    baseline_mean = sum(baseline_pnl) / len(baseline_pnl) if baseline_pnl else 0.0

    variants: list[dict] = []
    trial_count = 0

    for threshold in CONTROL_THRESHOLDS_PCT:
        trial_count += 1
        deltas = []
        n_exited_early = 0
        n_winners_sacrificed = 0
        n_recovered_sacrificed = 0
        n_deep_avoided = 0
        forfeited_upside_sum = 0.0
        for p in trajs:
            traj = p["daily_trajectory"]
            actual = p["eventual_pct"]
            _, cf_pct, exited = _apply_static_pct_control(traj, threshold)
            deltas.append(cf_pct - actual)
            if exited:
                n_exited_early += 1
                if actual > 0: n_winners_sacrificed += 1
                if p.get("recovered_from_worst") and actual > cf_pct:
                    n_recovered_sacrificed += 1
                if p.get("mfe_pct") and p["mfe_pct"] > 0:
                    forfeited_upside_sum += max(0.0, p["mfe_pct"] - cf_pct)
                if actual <= -0.10: n_deep_avoided += 1
        cf_mean = baseline_mean + (sum(deltas) / len(deltas) if deltas else 0)
        ci = _paired_bootstrap_mean_delta(deltas, n_resamples=n_resamples)
        variants.append({
            "doctrine": "static_pct",
            "threshold_pct": threshold,
            "n_positions": len(trajs),
            "n_exited_early": n_exited_early,
            "protection": {
                "mean_actual": baseline_mean,
                "mean_counterfactual": cf_mean,
                "delta": cf_mean - baseline_mean,
                "n_deep_losses_avoided": n_deep_avoided,
            },
            "damage": {
                "n_winners_sacrificed": n_winners_sacrificed,
                "n_recovered_sacrificed": n_recovered_sacrificed,
                "forfeited_upside_sum": forfeited_upside_sum,
                "winner_sacrifice_rate": (n_winners_sacrificed / n_exited_early)
                                          if n_exited_early else 0.0,
            },
            "paired_bootstrap": ci,
        })

    for timing in CONTROL_TIMINGS_DAYS:
        trial_count += 1
        deltas = []
        n_exited_early = 0
        n_winners_sacrificed = 0
        n_recovered_sacrificed = 0
        n_deep_avoided = 0
        forfeited_upside_sum = 0.0
        for p in trajs:
            traj = p["daily_trajectory"]
            actual = p["eventual_pct"]
            _, cf_pct, exited = _apply_static_time_control(traj, timing)
            deltas.append(cf_pct - actual)
            if exited:
                n_exited_early += 1
                if actual > 0: n_winners_sacrificed += 1
                if p.get("recovered_from_worst") and actual > cf_pct:
                    n_recovered_sacrificed += 1
                if p.get("mfe_pct") and p["mfe_pct"] > 0:
                    forfeited_upside_sum += max(0.0, p["mfe_pct"] - cf_pct)
                if actual <= -0.10: n_deep_avoided += 1
        cf_mean = baseline_mean + (sum(deltas) / len(deltas) if deltas else 0)
        ci = _paired_bootstrap_mean_delta(deltas, n_resamples=n_resamples)
        variants.append({
            "doctrine": "static_time",
            "timing_days": timing,
            "n_positions": len(trajs),
            "n_exited_early": n_exited_early,
            "protection": {
                "mean_actual": baseline_mean,
                "mean_counterfactual": cf_mean,
                "delta": cf_mean - baseline_mean,
                "n_deep_losses_avoided": n_deep_avoided,
            },
            "damage": {
                "n_winners_sacrificed": n_winners_sacrificed,
                "n_recovered_sacrificed": n_recovered_sacrificed,
                "forfeited_upside_sum": forfeited_upside_sum,
                "winner_sacrifice_rate": (n_winners_sacrificed / n_exited_early)
                                          if n_exited_early else 0.0,
            },
            "paired_bootstrap": ci,
        })

    return {
        "n_positions_analyzed": len(trajs),
        "baseline_mean_pnl": baseline_mean,
        "variants": variants,
        "trial_count": trial_count,
        "deflation_note": (
            f"n_trials={trial_count} · any 'best' variant must apply "
            "Deflated Sharpe with this trial count · never n_trials=1."
        ),
        "governance_note": (
            "NO variant here is a proposed production change. "
            "Every result reports BOTH protection and damage. "
            "Original P0 result (E-001) preserved unchanged."
        ),
    }
