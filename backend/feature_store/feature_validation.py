"""Feature Store validation — completeness + null pct + distribution sanity."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class FeatureValidationResult:
    n_rows:            int
    n_columns:         int
    n_features:        int                    # excluding identity cols
    null_pct_per_col:  dict = field(default_factory=dict)
    null_pct_overall:  float = 0.0
    coverage_per_category: dict = field(default_factory=dict)     # cat -> avg non-null pct
    outliers_flagged:  list = field(default_factory=list)
    verdict:           str = "PASS"           # PASS | WARNING | FAIL


IDENTITY_COLS = {"market", "ticker", "asof", "sector", "currency"}


def _pct_non_null(s: pd.Series) -> float:
    if len(s) == 0: return 0.0
    return float(s.notna().sum()) / float(len(s))


def validate_snapshot(df: pd.DataFrame, registry) -> FeatureValidationResult:
    """`registry` is FEATURE_REGISTRY. Returns a FeatureValidationResult."""
    if df is None or df.empty:
        return FeatureValidationResult(n_rows=0, n_columns=0, n_features=0,
                                          verdict="FAIL")

    r = FeatureValidationResult(
        n_rows=int(len(df)),
        n_columns=int(len(df.columns)),
        n_features=int(len(df.columns) - len(IDENTITY_COLS.intersection(df.columns))),
    )

    # ── Per-column null pct
    total_nulls = 0
    total_cells = 0
    for col in df.columns:
        if col in IDENTITY_COLS: continue
        n_null = int(df[col].isna().sum())
        pct = round(n_null / len(df), 4) if len(df) else 0.0
        r.null_pct_per_col[col] = pct
        total_nulls += n_null
        total_cells += len(df)
    r.null_pct_overall = round(total_nulls / total_cells, 4) if total_cells else 0.0

    # ── Coverage per category (avg NON-null across category's cols)
    cat_cols: dict = {}
    for f in registry:
        cat_cols.setdefault(f.category.value, []).append(f.name)
    for cat, cols in cat_cols.items():
        cols_present = [c for c in cols if c in df.columns]
        if not cols_present:
            r.coverage_per_category[cat] = 0.0
            continue
        pcts = [_pct_non_null(df[c]) for c in cols_present]
        r.coverage_per_category[cat] = round(sum(pcts) / len(pcts), 4)

    # ── Outliers — flag any numeric column with |z| > 8 anywhere
    from statistics import mean, pstdev
    for col in df.columns:
        if col in IDENTITY_COLS: continue
        if not pd.api.types.is_numeric_dtype(df[col]): continue
        s = df[col].dropna()
        if len(s) < 10: continue
        mu = float(s.mean()); sig = float(s.std())
        if sig == 0: continue
        z = ((s - mu).abs() / sig).max()
        if z > 8:
            r.outliers_flagged.append({"col": col, "max_abs_z": round(float(z), 2)})

    # ── Verdict
    if r.null_pct_overall > 0.60:  r.verdict = "FAIL"
    elif r.null_pct_overall > 0.35:  r.verdict = "WARNING"
    else:                             r.verdict = "PASS"
    return r
