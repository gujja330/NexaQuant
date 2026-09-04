"""Section E · Three-Way Comparison.

Compare candidate against R2 production AND standing comparator · never
candidate-only against itself.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ThreeWayResult:
    n_paired: int
    candidate_mean_ret: float
    r2_mean_ret: float
    comparator_mean_ret: float
    delta_candidate_vs_r2: float
    delta_candidate_vs_comparator: float
    delta_r2_vs_comparator: float
    bootstrap_candidate_vs_r2: Optional[dict] = None
    bootstrap_candidate_vs_comparator: Optional[dict] = None
    n_bootstrap_resamples: int = 10_000

    def to_dict(self) -> dict:
        return asdict(self)


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2: return 0.0
    mu = sum(returns) / len(returns)
    var = sum((r - mu)**2 for r in returns) / (len(returns) - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    return mu / sd if sd > 0 else 0.0


def _max_dd(returns: list[float]) -> float:
    """Max drawdown from cumulative product of (1 + return_pct/100)."""
    if not returns: return 0.0
    equity = 1.0; peak = 1.0; max_dd = 0.0
    for r in returns:
        equity *= (1.0 + r / 100.0)
        peak = max(peak, equity)
        dd = (equity - peak) / peak
        if dd < max_dd: max_dd = dd
    return max_dd * 100.0    # in percent


def three_way_compare(candidate_rets: list[float],
                       r2_rets: list[float],
                       comparator_rets: list[float],
                       bootstrap_seed: int = 42) -> ThreeWayResult:
    """Compare three return series paired by index. All three lists MUST be
    aligned position-by-position · shorter series truncates to shortest."""
    n = min(len(candidate_rets), len(r2_rets), len(comparator_rets))
    if n < 3:
        return ThreeWayResult(n_paired=n, candidate_mean_ret=0.0,
                                r2_mean_ret=0.0, comparator_mean_ret=0.0,
                                delta_candidate_vs_r2=0.0,
                                delta_candidate_vs_comparator=0.0,
                                delta_r2_vs_comparator=0.0)
    c = candidate_rets[:n]; r = r2_rets[:n]; k = comparator_rets[:n]
    cm = sum(c)/n; rm = sum(r)/n; km = sum(k)/n
    from backend.research.evidence.statistical_gates import paired_bootstrap
    bs_cr = paired_bootstrap([c[i] - r[i] for i in range(n)], seed=bootstrap_seed)
    bs_ck = paired_bootstrap([c[i] - k[i] for i in range(n)], seed=bootstrap_seed)
    return ThreeWayResult(
        n_paired=n,
        candidate_mean_ret=round(cm, 4),
        r2_mean_ret=round(rm, 4),
        comparator_mean_ret=round(km, 4),
        delta_candidate_vs_r2=round(cm - rm, 4),
        delta_candidate_vs_comparator=round(cm - km, 4),
        delta_r2_vs_comparator=round(rm - km, 4),
        bootstrap_candidate_vs_r2={"mean_delta": round(bs_cr.mean_delta,4),
                                     "ci_low": round(bs_cr.ci_low,4),
                                     "ci_high": round(bs_cr.ci_high,4),
                                     "p_value": round(bs_cr.p_value_two_sided,4)},
        bootstrap_candidate_vs_comparator={"mean_delta": round(bs_ck.mean_delta,4),
                                             "ci_low": round(bs_ck.ci_low,4),
                                             "ci_high": round(bs_ck.ci_high,4),
                                             "p_value": round(bs_ck.p_value_two_sided,4)},
    )
