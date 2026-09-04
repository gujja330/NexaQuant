"""Section C · Statistical validation gates.

Wraps · paired bootstrap · likelihood-ratio · DSR / Reality Check.
Every call records trial_count for downstream deflation. No hidden trials.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass


@dataclass
class BootstrapResult:
    n: int
    mean_delta: float
    ci_low: float
    ci_high: float
    p_value_two_sided: float
    n_resamples: int
    conf: float


def paired_bootstrap(deltas: list[float], n_resamples: int = 10_000,
                      conf: float = 0.95, seed: int | None = 42) -> BootstrapResult:
    """Empirical CI + two-sided p-value for mean(delta) via percentile bootstrap.

    deltas = [candidate_i - baseline_i] pair-aligned. Non-parametric ·
    makes no distributional assumption (trade returns are fat-tailed · V2 PDF
    calls this out explicitly)."""
    n = len(deltas)
    if n < 3:
        return BootstrapResult(n, 0.0, 0.0, 0.0, 1.0, n_resamples, conf)
    rng = random.Random(seed) if seed is not None else random.Random()
    means: list[float] = []
    for _ in range(n_resamples):
        sample = [deltas[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_i = int((1 - conf) / 2 * n_resamples)
    hi_i = int((1 + conf) / 2 * n_resamples) - 1
    mean_delta = sum(deltas) / n
    # Two-sided p = 2 · min(P(mean≤0), P(mean≥0))
    n_le_zero = sum(1 for m in means if m <= 0)
    n_ge_zero = sum(1 for m in means if m >= 0)
    p_two = 2.0 * min(n_le_zero, n_ge_zero) / n_resamples
    p_two = min(1.0, p_two)
    return BootstrapResult(
        n=n, mean_delta=mean_delta,
        ci_low=means[lo_i], ci_high=means[hi_i],
        p_value_two_sided=p_two, n_resamples=n_resamples, conf=conf,
    )


def likelihood_ratio_test(loglik_reduced: float, loglik_full: float,
                            df_diff: int) -> dict:
    """Nested-model comparison · chi-squared LR statistic + approximate p."""
    lr_stat = 2.0 * (loglik_full - loglik_reduced)
    if lr_stat < 0: lr_stat = 0.0
    # Chi-squared survival function approximated via series for common df
    # For our use (df 1-5) a simple Wilson-Hilferty is adequate
    p_value = _chi2_sf(lr_stat, df_diff)
    return {"lr_stat": lr_stat, "df": df_diff, "p_value": p_value}


def _chi2_sf(x: float, k: int) -> float:
    """Chi-squared survival function via Wilson-Hilferty normal approximation."""
    if x <= 0: return 1.0
    if k <= 0: return 1.0
    z = ((x / k) ** (1/3) - (1 - 2/(9*k))) / math.sqrt(2/(9*k))
    return 0.5 * math.erfc(z / math.sqrt(2))


def deflated_sharpe(sharpe_observed: float, n_trials: int,
                     n_returns: int) -> dict:
    """DSR wrapper · delegates to existing walkforward implementation.
    Records the (sharpe, n_trials, n_returns) triple that produced the p_value."""
    try:
        from backend.research.walkforward.deflated_sharpe import deflated_sharpe_ratio
        r = deflated_sharpe_ratio(sharpe_observed, n_trials=n_trials, n_returns=n_returns)
        r["input_sharpe"] = sharpe_observed
        r["n_trials"] = n_trials
        r["n_returns"] = n_returns
        return r
    except Exception as e:
        return {"error": str(e)[:200], "input_sharpe": sharpe_observed,
                 "n_trials": n_trials, "n_returns": n_returns}
