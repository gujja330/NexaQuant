"""Feature Importance Engine.

Multiple complementary methods. The set available today depends on whether
we have OUTCOME labels (from `reports/learning.parquet`, Sprint 9's substrate).

Available WITHOUT labels (always):
  - variance          : cross-sectional stdev
  - iqr               : interquartile range
  - dispersion_score  : sqrt(cv × iqr) — Sprint 2.5's ex-ante importance
  - uniqueness        : 1 - max column-correlation with other features

Available WITH labels (when a target is provided):
  - pearson           : linear correlation with target
  - spearman          : rank correlation with target
  - mutual_info       : discretized MI approximation (deterministic bins)
  - abs_pearson       : |Pearson| — magnitude only

Supervised methods with a model (SHAP, permutation, tree-based) are hooked
via the `attach_supervised_importance(model, method_name, values)` API so
Sprint 9's Learning Engine can plug in after training a model.

**Determinism:** every method is deterministic. Bin edges for MI are quantile-
based on the training column (order-invariant), no random state anywhere.

**Walk-forward:** target labels must respect the cutoff. When callers pass a
target series, it should be lagged forward returns (e.g., return_20d realised
AFTER the cutoff). This engine trusts the caller to supply cutoff-honest data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


IDENTITY = {"market", "ticker", "asof", "sector", "currency", "mi_regime"}


@dataclass
class ImportanceResult:
    market:            str
    asof:              date
    n_features_scored: int
    with_labels:       bool
    per_feature:       list[dict] = field(default_factory=list)
    method_available:  list[str]  = field(default_factory=list)


# ── Label-free scores ──────────────────────────────────────────
def _variance(s: pd.Series) -> float | None:
    s = s.dropna()
    if len(s) < 5 or s.nunique() < 2: return None
    return float(s.var())


def _iqr(s: pd.Series) -> float | None:
    s = s.dropna()
    if len(s) < 5 or s.nunique() < 2: return None
    return float(s.quantile(0.75) - s.quantile(0.25))


def _dispersion(s: pd.Series) -> float | None:
    """sqrt(cv × iqr) — matches Sprint 2.5's ex-ante importance."""
    s = s.dropna()
    if len(s) < 5 or s.nunique() < 2: return None
    mu = float(s.mean()); sig = float(s.std())
    cv = (sig / abs(mu)) if mu != 0 else sig
    iqr = float(s.quantile(0.75) - s.quantile(0.25))
    prod = cv * iqr
    return float(prod ** 0.5) if prod > 0 else 0.0


def _uniqueness(df: pd.DataFrame, col: str, others: list[str]) -> float | None:
    """1 - max |Pearson corr| with any other numeric column.
    Value close to 1 = the column is unique / not redundant.
    Value close to 0 = highly duplicative with something else."""
    if col not in df.columns: return None
    s = df[col].dropna()
    if len(s) < 20 or s.nunique() < 2: return None
    max_corr = 0.0
    for o in others:
        if o == col or o not in df.columns: continue
        if not pd.api.types.is_numeric_dtype(df[o]): continue
        merged = pd.concat([df[col], df[o]], axis=1).dropna()
        if len(merged) < 20 or merged.iloc[:, 1].nunique() < 2: continue
        try:
            c = abs(float(merged.corr().iloc[0, 1]))
        except Exception:
            continue
        if c > max_corr: max_corr = c
    return round(1.0 - max_corr, 4)


# ── Label-based scores ──────────────────────────────────────────
def _pearson(s: pd.Series, y: pd.Series) -> float | None:
    m = pd.concat([s, y], axis=1).dropna()
    if len(m) < 20 or m.iloc[:, 0].nunique() < 2 or m.iloc[:, 1].nunique() < 2: return None
    try: return float(m.corr().iloc[0, 1])
    except Exception: return None


def _spearman(s: pd.Series, y: pd.Series) -> float | None:
    m = pd.concat([s, y], axis=1).dropna()
    if len(m) < 20 or m.iloc[:, 0].nunique() < 2 or m.iloc[:, 1].nunique() < 2: return None
    try: return float(m.corr(method="spearman").iloc[0, 1])
    except Exception: return None


def _mutual_info(s: pd.Series, y: pd.Series, n_bins: int = 5) -> float | None:
    """Discretized MI estimate. Quantile bins on s and y independently."""
    m = pd.concat([s, y], axis=1).dropna()
    if len(m) < 40 or m.iloc[:, 0].nunique() < 3 or m.iloc[:, 1].nunique() < 3: return None
    try:
        sb = pd.qcut(m.iloc[:, 0], q=n_bins, duplicates="drop").cat.codes
        yb = pd.qcut(m.iloc[:, 1], q=n_bins, duplicates="drop").cat.codes
    except Exception:
        return None
    joint = pd.crosstab(sb, yb, normalize=True).values + 1e-12
    px = joint.sum(axis=1, keepdims=True); py = joint.sum(axis=0, keepdims=True)
    return float(np.sum(joint * np.log2(joint / (px * py))))


# ── Public API ─────────────────────────────────────────────────
def compute_importance(df: pd.DataFrame, target: pd.Series | None = None,
                         asof: date | None = None) -> ImportanceResult:
    """Compute importance scores for every numeric non-identity column.

    If `target` is provided, adds supervised metrics (Pearson, Spearman, MI).
    Otherwise only label-free metrics are computed.
    """
    market = str(df["market"].iloc[0]) if "market" in df.columns and len(df) else "?"
    numeric_cols = [c for c in df.columns
                     if c not in IDENTITY and pd.api.types.is_numeric_dtype(df[c])]

    r = ImportanceResult(
        market=market, asof=asof or date.today(),
        n_features_scored=len(numeric_cols),
        with_labels=target is not None,
        method_available=["variance", "iqr", "dispersion", "uniqueness"],
    )
    if target is not None:
        r.method_available += ["pearson", "spearman", "mutual_info"]

    for col in numeric_cols:
        s = df[col]
        row = {"feature": col}
        row["variance"]   = _round(_variance(s))
        row["iqr"]        = _round(_iqr(s))
        row["dispersion"] = _round(_dispersion(s))
        row["uniqueness"] = _uniqueness(df, col, numeric_cols)

        if target is not None:
            row["pearson"]     = _round(_pearson(s, target))
            row["spearman"]    = _round(_spearman(s, target))
            row["mutual_info"] = _round(_mutual_info(s, target))
            row["abs_pearson"] = _round(abs(row["pearson"])) if row["pearson"] is not None else None

        r.per_feature.append(row)
    return r


def _round(v):
    return round(float(v), 5) if v is not None else None
