"""Feature Drift Engine — PSI, Jensen-Shannon divergence, KS statistic.

Compares TODAY's snapshot to a REFERENCE (the last-good snapshot, or a
rolling window average). Emits per-feature drift scores + a rolled-up
verdict. Deterministic — no random state.

Thresholds (conventional):
  PSI  < 0.1        stable
  PSI  0.1..0.25    minor drift
  PSI  > 0.25       major drift
  JS   > 0.1        drift
  KS   > 0.15       distribution shift
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


N_BINS = 10
PSI_MINOR = 0.10
PSI_MAJOR = 0.25
JS_ALERT  = 0.10
KS_ALERT  = 0.15


@dataclass
class DriftReport:
    market:           str
    asof:             date
    reference_asof:   date | None
    n_features_scored: int
    per_feature:      list[dict] = field(default_factory=list)
    n_stable:         int = 0
    n_minor_drift:    int = 0
    n_major_drift:    int = 0
    verdict:          str = "PASS"


# ── Metric implementations ──────────────────────────────────────
def psi(current: pd.Series, reference: pd.Series, n_bins: int = N_BINS) -> float | None:
    """Population Stability Index. Bins the reference distribution,
    compares current vs reference bin fractions."""
    c = current.dropna(); r = reference.dropna()
    if len(c) < 20 or len(r) < 20: return None
    if r.nunique() < 3: return None
    # Use reference quantiles as bin edges — invariant to current outliers
    try:
        edges = np.unique(np.quantile(r, np.linspace(0, 1, n_bins + 1)))
    except Exception:
        return None
    if len(edges) < 3: return None
    # Force endpoints to include all data
    edges[0]  = min(edges[0], float(c.min()), float(r.min())) - 1e-9
    edges[-1] = max(edges[-1], float(c.max()), float(r.max())) + 1e-9
    r_bins = pd.cut(r, bins=edges, include_lowest=True)
    c_bins = pd.cut(c, bins=edges, include_lowest=True)
    r_pct = (r_bins.value_counts(normalize=True, sort=False) + 1e-6).sort_index()
    c_pct = (c_bins.value_counts(normalize=True, sort=False) + 1e-6).reindex(r_pct.index, fill_value=1e-6)
    return float(np.sum((c_pct - r_pct) * np.log(c_pct / r_pct)))


def js_divergence(current: pd.Series, reference: pd.Series, n_bins: int = N_BINS) -> float | None:
    """Jensen-Shannon divergence (base-2 log · 0..1)."""
    c = current.dropna(); r = reference.dropna()
    if len(c) < 20 or len(r) < 20: return None
    try:
        edges = np.linspace(min(c.min(), r.min()), max(c.max(), r.max()) + 1e-9, n_bins + 1)
    except Exception:
        return None
    p, _ = np.histogram(c, bins=edges, density=False)
    q, _ = np.histogram(r, bins=edges, density=False)
    if p.sum() == 0 or q.sum() == 0: return None
    p = p / p.sum() + 1e-12
    q = q / q.sum() + 1e-12
    m = 0.5 * (p + q)
    def _kl(a, b): return float(np.sum(a * np.log2(a / b)))
    return 0.5 * _kl(p, m) + 0.5 * _kl(q, m)


def ks_statistic(current: pd.Series, reference: pd.Series) -> float | None:
    """Kolmogorov-Smirnov statistic — max absolute difference of ECDFs."""
    c = current.dropna().sort_values(); r = reference.dropna().sort_values()
    if len(c) < 20 or len(r) < 20: return None
    # Merge sorted → ECDFs
    all_pts = np.sort(np.concatenate([c.values, r.values]))
    c_ecdf = np.searchsorted(c.values, all_pts, side="right") / len(c)
    r_ecdf = np.searchsorted(r.values, all_pts, side="right") / len(r)
    return float(np.max(np.abs(c_ecdf - r_ecdf)))


# ── Detector ───────────────────────────────────────────────────
def detect_drift(current: pd.DataFrame, reference: pd.DataFrame,
                   current_asof: date, reference_asof: date | None = None) -> DriftReport:
    r = DriftReport(
        market=str(current["market"].iloc[0]) if "market" in current.columns and len(current) else "?",
        asof=current_asof,
        reference_asof=reference_asof,
        n_features_scored=0,
    )
    if reference is None or reference.empty:
        r.verdict = "NO_REFERENCE"
        return r

    IDENTITY = {"market", "ticker", "asof", "sector", "currency", "mi_regime"}
    for col in current.columns:
        if col in IDENTITY: continue
        if col not in reference.columns: continue
        if not pd.api.types.is_numeric_dtype(current[col]): continue

        p = psi(current[col], reference[col])
        j = js_divergence(current[col], reference[col])
        k = ks_statistic(current[col], reference[col])
        if p is None and j is None and k is None: continue

        # Classify
        label = "stable"
        if (p is not None and p > PSI_MAJOR) or (k is not None and k > 0.30):
            label = "major_drift"
            r.n_major_drift += 1
        elif (p is not None and p > PSI_MINOR) or (j is not None and j > JS_ALERT) or (k is not None and k > KS_ALERT):
            label = "minor_drift"
            r.n_minor_drift += 1
        else:
            r.n_stable += 1

        r.per_feature.append({
            "feature": col, "psi": p, "js": j, "ks": k, "label": label,
        })

    r.n_features_scored = len(r.per_feature)
    if r.n_features_scored == 0:
        r.verdict = "NO_REFERENCE"
    elif r.n_major_drift > 5:
        r.verdict = "FAIL"
    elif r.n_major_drift > 0 or r.n_minor_drift > (r.n_features_scored * 0.30):
        r.verdict = "WARNING"
    else:
        r.verdict = "PASS"
    return r


def _round_or_none(v) -> float | None:
    return round(float(v), 5) if v is not None else None
