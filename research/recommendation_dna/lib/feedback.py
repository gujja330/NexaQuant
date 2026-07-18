"""DEV028 · v1.5 · DNA feedback loop.

The DNA store recorded 208 immutable recommendations but no downstream
engine reads them (per DESIGN_DECISIONS.md ADR-009 · notes on latent value).

This module realises the latent value:

1. Joins DEV025 learning.parquet outcomes into the DNA records by
   ticker (matching on ticker + rec_type window).
2. Extracts feature-patterns (sector · industry · classification tier ·
   score band) and computes historical win rate + expectancy per pattern.
3. Emits per-current-recommendation prior — "based on DNA history for
   this pattern, expect win rate X, expectancy Y."
4. Emits pattern leaderboard — which patterns win, which lose.

Advisory. Does NOT mutate DEV028's immutable store. Does NOT
auto-rewrite recommendations. Feeds Adaptive Rec Engine as an
optional evidence input."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]


# ────────────────────────────────────────────────────────────────
# LOADERS
# ────────────────────────────────────────────────────────────────
def _load_dna() -> pd.DataFrame:
    p = _ROOT / "reports" / "recommendation_dna.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()


def _load_learning() -> pd.DataFrame:
    p = _ROOT / "reports" / "learning.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()


def _load_current_recommendations() -> list[dict]:
    p = _ROOT / "reports" / "recommendations.json"
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text(encoding="utf-8")).get("recommendations") or [])
    except Exception:
        return []


# ────────────────────────────────────────────────────────────────
# JOIN
# ────────────────────────────────────────────────────────────────
def join_outcomes(dna: pd.DataFrame, learning: pd.DataFrame) -> pd.DataFrame:
    """Aggregate learning outcomes per ticker and left-join into DNA rows.

    DNA records a single point-in-time recommendation. Learning may hold
    multiple prior trades per ticker. We aggregate learning to per-ticker
    win_rate + avg return + n_trades and attach that as historical context
    to the DNA row (never overwrites the immutable DNA fields)."""
    if dna.empty:
        return dna
    if learning.empty:
        # Add empty columns for consistent downstream schema
        for c in ["hist_n_trades", "hist_win_rate", "hist_avg_return",
                    "hist_avg_win", "hist_avg_loss"]:
            dna[c] = None
        return dna

    per_ticker = learning.groupby("ticker").apply(lambda g: pd.Series({
        "hist_n_trades":    int(len(g)),
        "hist_win_rate":    float(g["is_winner"].mean()),
        "hist_avg_return":  float(g["return_pct"].mean()),
        "hist_avg_win":     float(g[g["return_pct"] > 0]["return_pct"].mean())
                              if (g["return_pct"] > 0).any() else 0.0,
        "hist_avg_loss":    float(g[g["return_pct"] <= 0]["return_pct"].mean())
                              if (g["return_pct"] <= 0).any() else 0.0,
    }), include_groups=False).reset_index()

    merged = dna.merge(per_ticker, on="ticker", how="left")
    return merged


# ────────────────────────────────────────────────────────────────
# PATTERN EXTRACTION
# ────────────────────────────────────────────────────────────────
def _score_band(score: float | None) -> str:
    if score is None:
        return "unknown"
    try:
        s = float(score)
    except Exception:
        return "unknown"
    if s >= 80: return "top_decile"
    if s >= 70: return "top_quartile"
    if s >= 60: return "median_plus"
    if s >= 50: return "median_minus"
    return "bottom_half"


def _pattern_row(row) -> dict:
    return {
        "sector":         row.get("sector") or "unknown",
        "industry":       row.get("industry") or "unknown",
        "classification": row.get("classification") or "unknown",
        "score_band":     _score_band(row.get("company_score")),
    }


def _pattern_key(p: dict) -> str:
    return f"{p['sector']}::{p['classification']}::{p['score_band']}"


def compute_pattern_stats(dna_with_outcomes: pd.DataFrame) -> list[dict]:
    """Aggregate historical outcomes per (sector, classification, score_band)."""
    if dna_with_outcomes.empty:
        return []
    df = dna_with_outcomes.copy()
    df["pattern"] = df.apply(lambda r: _pattern_key(_pattern_row(r)), axis=1)

    # Only patterns with historical n_trades > 0 are useful
    df = df[df["hist_n_trades"].fillna(0) > 0]
    if df.empty:
        return []

    grouped = df.groupby("pattern").agg(
        n_dna=("dna_id", "count"),
        hist_n_trades=("hist_n_trades", "sum"),
        hist_win_rate=("hist_win_rate", "mean"),
        hist_avg_return=("hist_avg_return", "mean"),
    ).reset_index()

    grouped = grouped.sort_values("hist_win_rate", ascending=False)
    return grouped.to_dict(orient="records")


def compute_per_rec_priors(current_recs: list[dict],
                              dna_with_outcomes: pd.DataFrame) -> list[dict]:
    """For each current recommendation, compute a DNA-based prior:
    win rate + expectancy from historical trades in the SAME pattern."""
    if dna_with_outcomes.empty:
        return []

    df = dna_with_outcomes.copy()
    df["pattern"] = df.apply(lambda r: _pattern_key(_pattern_row(r)), axis=1)
    df = df[df["hist_n_trades"].fillna(0) > 0]

    # Build pattern -> aggregated stats
    pat_stats = {}
    for pat, group in df.groupby("pattern"):
        pat_stats[pat] = {
            "n_dna":            int(len(group)),
            "hist_total_trades": int(group["hist_n_trades"].sum()),
            "hist_win_rate":    float(group["hist_win_rate"].mean()),
            "hist_avg_return":  float(group["hist_avg_return"].mean()),
        }

    priors = []
    for r in current_recs:
        pat_key = _pattern_key(_pattern_row(r))
        stats = pat_stats.get(pat_key)
        if stats is None:
            # No historical evidence for this exact pattern
            priors.append({
                "ticker":           r.get("ticker"),
                "recommendation":   r.get("recommendation"),
                "pattern":          pat_key,
                "hist_evidence":    False,
                "n_historical":     0,
                "prior_win_rate":   None,
                "prior_expectancy": None,
                "note":             "no historical DNA evidence for this pattern",
            })
        else:
            priors.append({
                "ticker":           r.get("ticker"),
                "recommendation":   r.get("recommendation"),
                "pattern":          pat_key,
                "hist_evidence":    True,
                "n_historical":     stats["hist_total_trades"],
                "prior_win_rate":   round(stats["hist_win_rate"], 4),
                "prior_expectancy": round(stats["hist_avg_return"], 4),
                "n_similar_dna":    stats["n_dna"],
            })
    return priors


# ────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ────────────────────────────────────────────────────────────────
def build_feedback() -> dict:
    dna = _load_dna()
    learning = _load_learning()
    current = _load_current_recommendations()

    if dna.empty:
        return {"error": "reports/recommendation_dna.parquet missing — run DEV028 first"}

    joined = join_outcomes(dna, learning)
    pattern_stats = compute_pattern_stats(joined)
    priors = compute_per_rec_priors(current, joined)

    # Summary aggregates
    n_with_evidence = sum(1 for p in priors if p.get("hist_evidence"))
    n_without = sum(1 for p in priors if not p.get("hist_evidence"))
    winners = [p for p in priors
                if p.get("prior_win_rate") is not None and p["prior_win_rate"] >= 0.65]
    losers  = [p for p in priors
                if p.get("prior_win_rate") is not None and p["prior_win_rate"] <= 0.35]

    return {
        "n_dna_records":       int(len(dna)),
        "n_learning_records":  int(len(learning)),
        "n_current_recs":      len(current),
        "n_with_evidence":     n_with_evidence,
        "n_without_evidence":  n_without,
        "n_patterns":          len(pattern_stats),
        "n_high_prior":        len(winners),
        "n_low_prior":         len(losers),
        "pattern_leaderboard": pattern_stats[:20],
        "pattern_bottom":      pattern_stats[-10:] if len(pattern_stats) >= 10 else [],
        "priors_high":         sorted(winners, key=lambda p: -(p.get("prior_expectancy") or 0))[:20],
        "priors_low":          sorted(losers, key=lambda p: (p.get("prior_expectancy") or 0))[:20],
        "priors_all":          priors,
    }
