"""Adaptive Rec v2.0 · feature engineering.

Reads DEV025 learning.parquet, produces the (X, y) matrix the v2.0
signal model consumes. Handles missing values deterministically
(median imputation for numerics, most-frequent for categoricals) so
identical inputs produce identical outputs (ADR-006)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
LEARNING = _ROOT / "reports" / "learning.parquet"


NUMERIC_FEATURES = [
    "dim_momentum",
    "dim_trend",
    "dim_rs_nifty",
    "dim_volatility",
    "dim_drawdown",
    "dim_position_52w",
    "score_at_entry",
    "confidence",
]

CATEGORICAL_FEATURES = ["sector", "industry"]


def load_learning() -> pd.DataFrame:
    if not LEARNING.exists():
        return pd.DataFrame()
    df = pd.read_parquet(LEARNING).sort_values("entry_date").reset_index(drop=True)
    return df


def build_feature_matrix(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Return (X, y, feature_names). Deterministic — same df in, same out."""
    if df.empty:
        return np.array([]).reshape(0, 0), np.array([]), []

    # One-hot categorical (drop_first=False so every category is a column)
    X_num = df[NUMERIC_FEATURES].astype(float).copy()
    X_cat_raw = df[CATEGORICAL_FEATURES].astype(str).copy()
    X_cat = pd.get_dummies(X_cat_raw, drop_first=False)
    # Sort columns for determinism
    X_cat = X_cat.reindex(sorted(X_cat.columns), axis=1)

    X = pd.concat([X_num, X_cat], axis=1)
    feature_names = list(X.columns)
    y = df["is_winner"].astype(int).values
    return X.values.astype(float), y, feature_names


def impute(X: np.ndarray, feature_names: list[str]) -> tuple[np.ndarray, dict[str, float]]:
    """Median imputation for numerics. Returns imputed X + per-feature medians."""
    if X.size == 0:
        return X, {}
    medians = {}
    X_out = X.copy()
    for i, name in enumerate(feature_names):
        col = X_out[:, i]
        median = float(np.nanmedian(col)) if np.any(~np.isnan(col)) else 0.0
        medians[name] = median
        mask = np.isnan(col)
        if mask.any():
            X_out[mask, i] = median
    return X_out, medians


def time_train_test_split(df: pd.DataFrame, train_frac: float = 0.7) -> tuple[np.ndarray, np.ndarray]:
    """Return (train_idx, test_idx) as boolean masks preserving time order."""
    n = len(df)
    split = int(n * train_frac)
    train_mask = np.zeros(n, dtype=bool)
    train_mask[:split] = True
    test_mask = ~train_mask
    return train_mask, test_mask
