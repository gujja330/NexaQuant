"""Feature Selection Engine.

Given a snapshot + importance scores, produce a *selected feature subset*
that downstream engines will consume. Selection pipeline:

  1. STATUS filter        — drop DEPRECATED, drop EXPERIMENTAL (opt-in)
  2. Remove CONSTANTS      — features whose stdev is ~0
  3. Remove DUPLICATES     — features with |corr| > 0.99 with an already-selected
  4. Correlation filter    — features with |corr| > correlation_threshold (default 0.90)
                              are grouped; keep the one with highest importance
  5. Leakage detection     — flag any feature perfectly correlated (|r|=1) with target
  6. Rank by importance    — sort remaining by dispersion + (supervised score if any)
  7. Top-K cap             — optional cap on total selected count

Emits SelectionResult with the selected list + removal reasons + trace.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from backend.feature_store.feature_registry import (
    FEATURE_REGISTRY, FeatureStatus,
)


IDENTITY = {"market", "ticker", "asof", "sector", "currency"}


@dataclass
class SelectionResult:
    market:                str
    asof:                  date
    n_input:               int
    n_selected:            int
    selected:              list[str] = field(default_factory=list)
    removed_constants:     list[str] = field(default_factory=list)
    removed_duplicates:    list[tuple] = field(default_factory=list)   # (kept, dropped)
    removed_correlated:    list[tuple] = field(default_factory=list)
    removed_deprecated:    list[str] = field(default_factory=list)
    removed_experimental:  list[str] = field(default_factory=list)
    leakage_flagged:       list[str] = field(default_factory=list)
    correlation_threshold: float = 0.90


def _feature_status(name: str) -> FeatureStatus | None:
    for f in FEATURE_REGISTRY:
        if f.name == name: return f.status
    return None


def _get_importance(imp_result, feature_name: str) -> float:
    """Return best available importance value; higher = more important."""
    if imp_result is None: return 0.0
    for row in getattr(imp_result, "per_feature", []):
        if row.get("feature") == feature_name:
            # Prefer supervised abs_pearson if available, else dispersion
            v = row.get("abs_pearson")
            if v is None: v = row.get("dispersion")
            return float(v) if v is not None else 0.0
    return 0.0


def select_features(df: pd.DataFrame,
                       importance_result=None,
                       target: pd.Series | None = None,
                       correlation_threshold: float = 0.90,
                       top_k: int | None = None,
                       include_experimental: bool = False) -> SelectionResult:
    market = str(df["market"].iloc[0]) if "market" in df.columns and len(df) else "?"
    asof   = str(df["asof"].iloc[0])   if "asof"   in df.columns and len(df) else "?"

    numeric = [c for c in df.columns
                if c not in IDENTITY and pd.api.types.is_numeric_dtype(df[c])]

    r = SelectionResult(
        market=market, asof=date.fromisoformat(asof) if asof and asof != "?" else date.today(),
        n_input=len(numeric), n_selected=0,
        correlation_threshold=correlation_threshold,
    )

    candidates = list(numeric)

    # Step 1: status filter
    filtered = []
    for c in candidates:
        st = _feature_status(c)
        if st == FeatureStatus.DEPRECATED:
            r.removed_deprecated.append(c); continue
        if st == FeatureStatus.EXPERIMENTAL and not include_experimental:
            r.removed_experimental.append(c); continue
        filtered.append(c)
    candidates = filtered

    # Step 2: constants
    filtered = []
    for c in candidates:
        s = df[c].dropna()
        if len(s) < 5 or s.nunique() < 2:
            r.removed_constants.append(c); continue
        filtered.append(c)
    candidates = filtered

    # Step 3+4: correlation-based dedup — greedy, keep the more important one
    # Sort candidates by importance descending
    candidates.sort(key=lambda c: _get_importance(importance_result, c), reverse=True)

    # Compute pairwise correlation lazily
    kept: list[str] = []
    for c in candidates:
        redundant = False
        for k in kept:
            m = pd.concat([df[c], df[k]], axis=1).dropna()
            if len(m) < 20: continue
            if m.iloc[:, 0].nunique() < 2 or m.iloc[:, 1].nunique() < 2: continue
            try:
                corr = abs(float(m.corr().iloc[0, 1]))
            except Exception:
                continue
            if corr >= 0.99:
                r.removed_duplicates.append((k, c)); redundant = True; break
            if corr >= correlation_threshold:
                r.removed_correlated.append((k, c)); redundant = True; break
        if not redundant:
            kept.append(c)

    # Step 5: leakage
    if target is not None:
        for c in list(kept):
            m = pd.concat([df[c], target], axis=1).dropna()
            if len(m) < 20 or m.iloc[:, 1].nunique() < 2: continue
            try:
                corr = abs(float(m.corr().iloc[0, 1]))
            except Exception:
                continue
            if corr >= 0.999:
                r.leakage_flagged.append(c)

    # Step 7: top-k cap
    if top_k is not None and len(kept) > top_k:
        kept = kept[:top_k]

    r.selected = kept
    r.n_selected = len(kept)
    return r
