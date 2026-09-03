"""Paired bootstrap CI for the mean-difference between two same-underlying
strategy return series (e.g., actual vs counterfactual exits on the same
positions). Non-parametric · handles fat-tailed trade returns better than a
paired t-test.
"""
from __future__ import annotations

from typing import Sequence
import math
import random


def paired_bootstrap_ci(actual: Sequence[float], counterfactual: Sequence[float],
                        n_resamples: int = 10_000,
                        conf: float = 0.95, seed: int = 42) -> dict:
    """Bootstrap CI for mean(counterfactual - actual).

    Positive lower bound ⇒ counterfactual is significantly better at conf.
    Returns dict:
      { mean_delta, ci_low, ci_high, p_value_two_sided,
        n_positions, n_resamples }
    """
    if len(actual) != len(counterfactual):
        raise ValueError("actual and counterfactual must be same length")
    n = len(actual)
    if n == 0:
        return {"mean_delta": None, "ci_low": None, "ci_high": None,
                "p_value_two_sided": None, "n_positions": 0,
                "n_resamples": n_resamples}
    deltas = [float(c) - float(a) for a, c in zip(actual, counterfactual)]
    observed_mean = sum(deltas) / n

    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_resamples):
        idxs = [rng.randrange(n) for __ in range(n)]
        s = 0.0
        for i in idxs: s += deltas[i]
        means.append(s / n)
    means.sort()
    alpha = (1.0 - conf) / 2.0
    lo = means[int(alpha * n_resamples)]
    hi = means[int((1.0 - alpha) * n_resamples)]
    # Two-sided p-value · fraction of resample means whose sign contradicts observed
    n_beyond = 0
    for m in means:
        if observed_mean >= 0:
            if m <= 0: n_beyond += 1
        else:
            if m >= 0: n_beyond += 1
    p_two = 2.0 * (n_beyond / n_resamples)
    if p_two > 1.0: p_two = 1.0

    return {
        "mean_delta": observed_mean,
        "ci_low": lo, "ci_high": hi,
        "p_value_two_sided": p_two,
        "n_positions": n,
        "n_resamples": n_resamples,
        "conf": conf,
    }
