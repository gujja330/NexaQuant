"""Permutation Feature Importance · SHAP-alternative for rule-based models.

Why permutation instead of SHAP:
    SHAP is designed for tree-ensemble models (XGBoost, RandomForest, LightGBM)
    where feature contributions can be decomposed exactly via Shapley values.
    AEGIS's 11 models are rule-based scoring engines (rank_score over
    momentum/trend/value/... indicators). For those, SHAP degenerates —
    each rule's contribution is trivially additive.

    Permutation importance is model-agnostic and proven institutionally:
    shuffle a feature's values across the sample · measure the drop in
    correlation-with-return · higher drop = more predictive feature.

Reference: Breiman 2001 · applied by every major quant desk as the
model-agnostic institutional-grade feature importance measure.

Article 101.2 · pure measurement extension.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

SCHEMA_FINGERPRINT = "aegis.certification.permutation_importance.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.certification.permutation_importance.v1"


@dataclass
class PermutationImportanceReport:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    run_utc: str = ""
    n_trades: int = 0
    n_permutations: int = 0
    baseline_ic: float | None = None
    per_feature_importance: dict = field(default_factory=dict)
    top_features_ranked: list = field(default_factory=list)
    top_negative_features: list = field(default_factory=list)


def _pearson_ic(x, y) -> float | None:
    """Pearson correlation coefficient · handles zero-variance gracefully."""
    import pandas as pd
    try:
        r = pd.Series(x).corr(pd.Series(y), method="pearson")
        return float(r) if r == r else None
    except Exception:
        return None


def compute_permutation_importance(df,
                                      feature_cols: list[str] | None = None,
                                      target_col: str = "return_pct",
                                      n_permutations: int = 20,
                                      seed: int = 42) -> PermutationImportanceReport:
    """Compute per-feature permutation importance.

    For each feature:
      1. Compute baseline IC (Pearson) of feature vs target
      2. Shuffle the feature n_permutations times, compute IC each time
      3. Importance = |baseline_IC| - mean(|shuffled_ICs|)
         Positive importance = feature is predictive (shuffling degrades signal)
    """
    import pandas as pd
    import numpy as np
    rep = PermutationImportanceReport(run_utc=datetime.now(timezone.utc).isoformat())
    if df is None or len(df) == 0 or target_col not in df.columns:
        return rep
    rep.n_trades = len(df)
    rep.n_permutations = n_permutations

    if feature_cols is None:
        feature_cols = [c for c in df.columns if c.startswith("dim_")]
    if not feature_cols:
        return rep

    # Deterministic RNG
    rng = np.random.default_rng(seed)
    y = df[target_col].values

    # Baseline: full-model IC. For per-feature importance, we use the direct
    # feature-to-target correlation as the baseline (not requiring a trained
    # model · works with any signal-producing pipeline).
    for col in feature_cols:
        if col not in df.columns: continue
        x = df[col].values
        # Skip if constant column
        if np.std(x) == 0: continue

        baseline_ic = _pearson_ic(x, y)
        if baseline_ic is None: continue

        # Shuffle n_permutations times and measure IC each time
        shuffled_ics = []
        for _ in range(n_permutations):
            x_shuf = x.copy()
            rng.shuffle(x_shuf)
            ic = _pearson_ic(x_shuf, y)
            if ic is not None: shuffled_ics.append(abs(ic))

        if not shuffled_ics: continue
        mean_shuffled_abs = sum(shuffled_ics) / len(shuffled_ics)
        std_shuffled_abs = math.sqrt(sum((s - mean_shuffled_abs) ** 2 for s in shuffled_ics) / len(shuffled_ics))
        importance = round(abs(baseline_ic) - mean_shuffled_abs, 6)
        # Significance z-score: how many stdevs baseline is above the shuffled distribution
        z = round((abs(baseline_ic) - mean_shuffled_abs) / std_shuffled_abs, 4) if std_shuffled_abs > 0 else None

        rep.per_feature_importance[col] = {
            "baseline_ic": round(baseline_ic, 4),
            "mean_shuffled_abs_ic": round(mean_shuffled_abs, 4),
            "importance": importance,
            "z_score": z,
            "significant": bool(z and z >= 1.96),
        }

    # Rank by importance descending (most predictive first)
    ranked = sorted(rep.per_feature_importance.items(),
                     key=lambda kv: -kv[1]["importance"])
    rep.top_features_ranked = [
        {"feature": f, **m} for f, m in ranked[:10]
    ]
    rep.top_negative_features = [
        {"feature": f, **m} for f, m in ranked[-5:]
    ]
    return rep


def run_permutation_importance(root: Path,
                                   n_permutations: int = 20) -> dict:
    import pandas as pd
    lp = root / "reports" / "learning.parquet"
    if not lp.exists(): return {"error": "learning.parquet missing"}
    df = pd.read_parquet(lp)
    rep = compute_permutation_importance(df, n_permutations=n_permutations)
    return asdict(rep)
