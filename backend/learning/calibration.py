"""Confidence calibration — empirical winrate per confidence bin.

Sprint 6 baseline: 10-bin isotonic-style monotone calibration (deterministic,
no random state). Given a corpus of closed recs with (calibrated_confidence,
is_winner), bins them by confidence and computes empirical win-rate per bin.
Monotone-corrected via pool-adjacent-violators (PAV) so higher-confidence
bins never have lower empirical win-rates than lower-confidence bins.

Sprint 3's calibration module can read this curve and populate the
historical_precision input on the next run — closing the feedback loop.
"""
from __future__ import annotations

import pandas as pd

from backend.learning.types import CalibrationCurve


DEFAULT_N_BINS = 10


def _pool_adjacent_violators(rates: list[float]) -> list[float]:
    """PAV algorithm: monotone increasing regression.

    Deterministic O(n) sweep — no random tiebreak. Returns a monotone
    non-decreasing series minimizing squared error.
    """
    if not rates:
        return []
    out = list(rates)
    # Iterate until no violations remain
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(out) - 1:
            if out[i] > out[i + 1] + 1e-12:
                # Pool i and i+1
                pool_mean = (out[i] + out[i + 1]) / 2.0
                out[i] = pool_mean
                out[i + 1] = pool_mean
                changed = True
            i += 1
    return out


def fit_calibration_curve(corpus: pd.DataFrame,
                            n_bins: int = DEFAULT_N_BINS) -> CalibrationCurve:
    """Fit a monotone calibration curve to the closed-rec corpus.

    Empty corpus → identity mapping (no calibration adjustment).
    """
    if corpus is None or corpus.empty:
        return _identity_curve(n_bins, 0)
    if "calibrated_confidence" not in corpus.columns or "is_winner" not in corpus.columns:
        return _identity_curve(n_bins, 0)
    if len(corpus) < 20:
        # Too few observations for meaningful calibration
        return _identity_curve(n_bins, int(len(corpus)))

    edges = [i / n_bins for i in range(n_bins + 1)]
    empirical: list[float] = []
    for i in range(n_bins):
        low, high = edges[i], edges[i + 1]
        mask = (corpus["calibrated_confidence"] >= low) & (corpus["calibrated_confidence"] <= high)
        bin_rows = corpus[mask]
        if len(bin_rows) == 0:
            # Interpolate as the bin midpoint — a fair identity guess
            empirical.append((low + high) / 2.0)
        else:
            empirical.append(float(bin_rows["is_winner"].astype(bool).mean()))

    fitted = _pool_adjacent_violators(empirical)
    # RMS calibration error vs bin-midpoint identity
    midpoints = [(edges[i] + edges[i + 1]) / 2.0 for i in range(n_bins)]
    err = (sum((f - m) ** 2 for f, m in zip(fitted, midpoints)) / n_bins) ** 0.5

    return CalibrationCurve(
        method="isotonic_pav",
        n_observations=int(len(corpus)),
        bin_edges=edges,
        empirical_win_rates=[round(v, 4) for v in empirical],
        fitted_win_rates=[round(v, 4) for v in fitted],
        calibration_error=round(err, 5),
    )


def _identity_curve(n_bins: int, n_observations: int) -> CalibrationCurve:
    edges = [i / n_bins for i in range(n_bins + 1)]
    midpoints = [(edges[i] + edges[i + 1]) / 2.0 for i in range(n_bins)]
    return CalibrationCurve(
        method="identity",
        n_observations=n_observations,
        bin_edges=edges,
        empirical_win_rates=[round(m, 4) for m in midpoints],
        fitted_win_rates=[round(m, 4) for m in midpoints],
        calibration_error=0.0,
    )
