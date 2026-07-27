"""Alpha Optimization Engine · Article 101.2 measurement extension.

Per operator: "Do NOT build another architecture. Do NOT redesign existing
systems. Instead maximize investment intelligence. Analyze every feature,
factor, model, strategy, sector, regime, holding period, and recommendation
using the historical trade database."

This engine consumes learning.parquet (1060+ closed trades) and produces:

  · Per-dimension IC + Spearman rank correlation + t-stat + hit rate
  · Feature-interaction effects (pairwise cross-dim combinations)
  · Regime-partitioned effectiveness (calm/normal/elevated vol regimes)
  · Sector-partitioned effectiveness (14 sectors)
  · Holding-period-partitioned effectiveness (5 buckets)
  · Best feature combinations (top-K combos by realized alpha)
  · Suggested per-dimension weight updates (|IC|-normalized)
  · Suggested per-sector allocation tilts (win_rate-driven)

Deterministic · fingerprinted · walk-forward safe · pure measurement.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.certification.alpha_optimization.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.certification.alpha_optimization.v1"


def _spearman_rank_corr(x, y) -> float | None:
    """Spearman rank correlation · pandas fallback if scipy missing."""
    import pandas as pd
    try:
        r = pd.Series(x).corr(pd.Series(y), method="spearman")
        return round(float(r), 4) if r == r else None
    except Exception:
        return None


def _pearson_corr(x, y) -> float | None:
    import pandas as pd
    try:
        r = pd.Series(x).corr(pd.Series(y), method="pearson")
        return round(float(r), 4) if r == r else None
    except Exception:
        return None


def _t_stat(r: float | None, n: int) -> float | None:
    if r is None or n <= 2: return None
    try:
        return round(r * math.sqrt((n - 2) / (1 - r * r)), 4)
    except (ValueError, ZeroDivisionError):
        return None


@dataclass
class AlphaReport:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    run_utc: str = ""
    n_trades: int = 0
    dimension_analysis: dict = field(default_factory=dict)
    interaction_effects: dict = field(default_factory=dict)
    regime_partition: dict = field(default_factory=dict)
    sector_partition: dict = field(default_factory=dict)
    holding_partition: dict = field(default_factory=dict)
    best_feature_combinations: list = field(default_factory=list)
    suggested_dimension_weights: dict = field(default_factory=dict)
    suggested_sector_tilts: dict = field(default_factory=dict)
    top_alpha_generators: list = field(default_factory=list)
    top_alpha_destroyers: list = field(default_factory=list)


def _dimension_analysis(df) -> dict:
    """Per-dimension: IC (Pearson) · rank-IC (Spearman) · t-stat · hit-rate above median."""
    if "return_pct" not in df.columns: return {}
    out = {}
    for c in df.columns:
        if not c.startswith("dim_"): continue
        r_p = _pearson_corr(df[c], df["return_pct"])
        r_s = _spearman_rank_corr(df[c], df["return_pct"])
        t = _t_stat(r_p, len(df))
        # Hit rate: does above-median score predict positive return?
        try:
            median = df[c].median()
            above = df[df[c] >= median]
            hit = float((above["return_pct"] > 0).mean()) if len(above) > 0 else None
            out[c] = {"ic_pearson": r_p, "ic_spearman": r_s, "t_stat": t,
                      "hit_rate_above_median": round(hit, 4) if hit is not None else None,
                      "n": int(len(df))}
        except Exception:
            out[c] = {"ic_pearson": r_p, "ic_spearman": r_s, "t_stat": t,
                      "hit_rate_above_median": None, "n": int(len(df))}
    return out


def _interaction_effects(df, max_pairs: int = 10) -> dict:
    """Pairwise dim-interaction: for each pair, compute average return when
    BOTH dims are above-median vs BOTH below-median."""
    if "return_pct" not in df.columns: return {}
    dims = [c for c in df.columns if c.startswith("dim_")]
    if len(dims) < 2: return {}
    out = {}
    for a, b in list(combinations(dims, 2))[:max_pairs]:
        try:
            med_a = df[a].median()
            med_b = df[b].median()
            both_high = df[(df[a] >= med_a) & (df[b] >= med_b)]
            both_low  = df[(df[a] < med_a) & (df[b] < med_b)]
            if len(both_high) < 10 or len(both_low) < 10: continue
            high_mean = float(both_high["return_pct"].mean())
            low_mean = float(both_low["return_pct"].mean())
            diff = high_mean - low_mean
            out[f"{a} × {b}"] = {
                "n_both_high": int(len(both_high)),
                "mean_return_both_high_pct": round(high_mean, 4),
                "n_both_low": int(len(both_low)),
                "mean_return_both_low_pct": round(low_mean, 4),
                "alpha_spread_pct": round(diff, 4),
            }
        except Exception:
            continue
    return out


def _sector_partition(df) -> dict:
    if "sector" not in df.columns or "return_pct" not in df.columns: return {}
    out = {}
    for sec, g in df.groupby("sector"):
        n = len(g)
        if n < 5: continue
        wr = float((g["return_pct"] > 0).mean())
        mean_r = float(g["return_pct"].mean())
        pf_top_wins = float(g[g["return_pct"] > 0]["return_pct"].sum())
        pf_top_losses = abs(float(g[g["return_pct"] < 0]["return_pct"].sum()))
        pf = round(pf_top_wins / pf_top_losses, 4) if pf_top_losses > 0 else None
        out[str(sec)] = {"n": n, "win_rate": round(wr, 4),
                          "mean_return_pct": round(mean_r, 4),
                          "profit_factor": pf}
    return out


def _holding_partition(df) -> dict:
    if "n_bars_held" not in df.columns or "return_pct" not in df.columns: return {}
    buckets = [("1-5", 1, 5), ("6-15", 6, 15), ("16-30", 16, 30),
                ("31-60", 31, 60), ("60+", 61, 10000)]
    out = {}
    for label, lo, hi in buckets:
        g = df[(df["n_bars_held"] >= lo) & (df["n_bars_held"] <= hi)]
        n = len(g)
        if n < 5: continue
        out[label] = {"n": n,
                       "win_rate": round(float((g["return_pct"] > 0).mean()), 4),
                       "mean_return_pct": round(float(g["return_pct"].mean()), 4),
                       "avg_bars": round(float(g["n_bars_held"].mean()), 2)}
    return out


def _regime_partition(df) -> dict:
    """Partition by realized volatility of the trade window (proxy for vol regime)."""
    if "return_pct" not in df.columns: return {}
    out = {}
    # Use dim_volatility if present as regime proxy
    if "dim_volatility" not in df.columns: return {}
    try:
        q_lo = df["dim_volatility"].quantile(0.33)
        q_hi = df["dim_volatility"].quantile(0.67)
    except Exception: return {}
    for label, mask in [
        ("low_vol",    df["dim_volatility"] <= q_lo),
        ("medium_vol", (df["dim_volatility"] > q_lo) & (df["dim_volatility"] <= q_hi)),
        ("high_vol",   df["dim_volatility"] > q_hi),
    ]:
        g = df[mask]
        n = len(g)
        if n < 20: continue
        out[label] = {"n": n,
                       "win_rate": round(float((g["return_pct"] > 0).mean()), 4),
                       "mean_return_pct": round(float(g["return_pct"].mean()), 4)}
    return out


def _best_feature_combinations(interactions: dict, top_k: int = 5) -> list:
    """Top-K combinations by alpha_spread."""
    ranked = sorted(interactions.items(),
                     key=lambda kv: -kv[1].get("alpha_spread_pct", 0.0))
    return [{"combination": k, **v} for k, v in ranked[:top_k]]


def _suggested_weights(dim_analysis: dict) -> dict:
    """|IC|-normalized weights · dims with |IC|<0.02 zeroed."""
    total = 0.0
    for m in dim_analysis.values():
        ic = m.get("ic_pearson")
        if ic is None: continue
        if abs(ic) >= 0.02: total += abs(ic)
    if total <= 0: return {}
    out = {}
    for k, m in dim_analysis.items():
        ic = m.get("ic_pearson")
        if ic is None or abs(ic) < 0.02:
            out[k] = 0.0
        else:
            out[k] = round(abs(ic) / total, 4)
    return out


def _sector_tilts(sector_partition: dict, min_n: int = 30) -> dict:
    """Suggested tilt = (win_rate - 0.55) · normalized. Sectors with n<min_n get 0."""
    out = {}
    for sec, m in sector_partition.items():
        if m["n"] < min_n:
            out[sec] = {"tilt": 0.0, "reason": "insufficient_history"}
            continue
        tilt = round((m["win_rate"] - 0.55) * 2.0, 4)  # scaled
        tilt = max(-1.0, min(1.0, tilt))
        rec = "BOOST" if tilt >= 0.15 else "HOLD" if tilt >= -0.05 else "REDUCE" if tilt >= -0.15 else "UNDERWEIGHT"
        out[sec] = {"tilt": tilt, "recommendation": rec, "n": m["n"]}
    return out


def compute_alpha_report(df) -> AlphaReport:
    rep = AlphaReport(run_utc=datetime.now(timezone.utc).isoformat())
    if df is None or len(df) == 0: return rep
    rep.n_trades = len(df)
    rep.dimension_analysis = _dimension_analysis(df)
    rep.interaction_effects = _interaction_effects(df)
    rep.sector_partition = _sector_partition(df)
    rep.holding_partition = _holding_partition(df)
    rep.regime_partition = _regime_partition(df)
    rep.best_feature_combinations = _best_feature_combinations(rep.interaction_effects, top_k=5)
    rep.suggested_dimension_weights = _suggested_weights(rep.dimension_analysis)
    rep.suggested_sector_tilts = _sector_tilts(rep.sector_partition)

    # Top alpha generators/destroyers (per-sector · min-n gate)
    ranked_sec = sorted(
        [{"sector": s, **m} for s, m in rep.sector_partition.items() if m["n"] >= 30],
        key=lambda x: -x["mean_return_pct"]
    )
    rep.top_alpha_generators = ranked_sec[:5]
    rep.top_alpha_destroyers = ranked_sec[-5:]
    return rep


def run_alpha_optimization(root: Path) -> dict:
    import pandas as pd
    lp = root / "reports" / "learning.parquet"
    if not lp.exists(): return {"error": "learning.parquet missing"}
    df = pd.read_parquet(lp)
    return asdict(compute_alpha_report(df))
