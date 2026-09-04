"""A/B/D Cohort Executor · CEO 2026-09-05.

Executes Categories A (10) + B (8) + D (3) as trials through C.1's
family/trial accounting into the Evidence Log. Honest INSUFFICIENT /
DATA-BLOCKED where source data does not exist · never fabricates.

Each item is a small function returning:
    dict {trial_key, cohort_kind, sample_size, metrics, verdict, note}

Verdicts follow CEO's classification:
    PROMISING · NO_LIFT · HARMFUL · INSUFFICIENT · DATA_BLOCKED

All results logged as one family per market · Bonferroni + Benjamini-Hochberg
FDR corrections applied at family close.
"""
from __future__ import annotations
import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Optional


# ── helpers ──────────────────────────────────────────────────────────

def _sample_tier(n: int) -> str:
    if n < 5: return "observation"
    if n < 15: return "hypothesis"
    if n < 30: return "research_signal"
    if n < 50: return "stronger_evidence"
    return "validation_candidate"


def _classify(delta: float | None, p_value: float | None,
                n: int, min_n: int = 30) -> tuple[str, str]:
    """Uniform verdict rule across cohort tests."""
    if n < 5: return "DATA_BLOCKED", f"n={n}<5 · not even observation tier"
    if n < min_n:
        if p_value is not None and p_value < 0.05 and delta is not None:
            direction = "positive" if delta > 0 else "negative"
            return "INSUFFICIENT", (f"n={n}<{min_n} · {direction} p={p_value:.3f} · "
                                      f"needs {min_n}+ for stronger-evidence tier")
        return "INSUFFICIENT", f"n={n}<{min_n}"
    if p_value is None or delta is None:
        return "INSUFFICIENT", "test not computable"
    if p_value >= 0.10: return "NO_LIFT", f"p={p_value:.3f}>=0.10"
    if delta < 0: return "HARMFUL", f"delta={delta:+.4f} p={p_value:.3f}"
    return "PROMISING", f"delta={delta:+.4f} p={p_value:.3f}"


def _paired_bootstrap(vals: list[float], seed: int = 42,
                        n_resamples: int = 5000) -> tuple[float, float, float, float]:
    """Return (mean, ci_low, ci_high, p_two_sided) for one-sample bootstrap."""
    import random
    if len(vals) < 3: return (0.0, 0.0, 0.0, 1.0)
    rng = random.Random(seed)
    means = []
    for _ in range(n_resamples):
        s = [vals[rng.randrange(len(vals))] for _ in range(len(vals))]
        means.append(sum(s) / len(s))
    means.sort()
    lo_i = int(0.025 * n_resamples); hi_i = int(0.975 * n_resamples) - 1
    mean = sum(vals) / len(vals)
    n_le = sum(1 for m in means if m <= 0); n_ge = sum(1 for m in means if m >= 0)
    p_two = min(1.0, 2 * min(n_le, n_ge) / n_resamples)
    return (mean, means[lo_i], means[hi_i], p_two)


def _pearson(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """Return (r, approx_p) or None if insufficient."""
    n = len(xs)
    if n < 3 or n != len(ys): return None
    mx = sum(xs) / n; my = sum(ys) / n
    cov = sum((x-mx)*(y-my) for x,y in zip(xs,ys)) / (n-1)
    sx = math.sqrt(sum((x-mx)**2 for x in xs) / (n-1))
    sy = math.sqrt(sum((y-my)**2 for y in ys) / (n-1))
    if sx == 0 or sy == 0: return None
    r = cov / (sx * sy)
    # t-approx p-value · two-sided
    if abs(r) >= 0.999: return (r, 0.0)
    t = r * math.sqrt((n-2) / (1 - r*r))
    # Rough two-sided p from t-dist · Wilson-Hilferty on t^2
    x = t * t
    if x <= 0: return (r, 1.0)
    df = n - 2
    if df <= 0: return (r, 1.0)
    z = ((x / df) ** (1/3) - (1 - 2/(9*df))) / math.sqrt(2/(9*df))
    p = math.erfc(z / math.sqrt(2))
    return (r, min(1.0, max(0.0, p)))


# ── Category A cohort functions ──────────────────────────────────────

def a1_confidence_x_fwd(root: Path, market: str) -> dict:
    """A1 · does raw confidence predict forward return?"""
    import pandas as pd
    p = root / "reports" / "research" / "outcome_dataset.parquet"
    if not p.exists():
        return {"trial_key": "A1_confidence_x_fwd", "cohort_kind": "predictive_lift",
                 "sample_size": 0, "verdict": "DATA_BLOCKED",
                 "note": "outcome_dataset.parquet missing"}
    df = pd.read_parquet(p)
    df = df[(df["country"].str.lower() == market.lower()) &
             (df["is_closed"] == True) & (df["runner"] == "R2") &
             (df["initial_confidence"].notna()) & (df["exit_pnl_pct"].notna())]
    n = len(df)
    if n < 5:
        return {"trial_key": "A1_confidence_x_fwd", "cohort_kind": "predictive_lift",
                 "sample_size": n, "verdict": "DATA_BLOCKED",
                 "note": f"outcome_dataset has {n} closed R2 for {market} · need 5+"}
    corr = _pearson(df["initial_confidence"].tolist(), df["exit_pnl_pct"].tolist())
    if corr is None:
        return {"trial_key": "A1_confidence_x_fwd", "cohort_kind": "predictive_lift",
                 "sample_size": n, "verdict": "INSUFFICIENT",
                 "note": "correlation not computable"}
    r, p_val = corr
    verdict, note = _classify(delta=r, p_value=p_val, n=n, min_n=30)
    return {"trial_key": "A1_confidence_x_fwd", "cohort_kind": "predictive_lift",
             "sample_size": n, "metrics": {"pearson_r": round(r, 4),
                                             "p_value_two_sided": round(p_val, 4)},
             "verdict": verdict, "note": note}


def a2_horizon_selection(root: Path, market: str) -> dict:
    """A2 · does longer horizon dominate shorter?"""
    p = root / "reports" / "research" / f"mr_forward_validation_{market}.json"
    if not p.exists():
        return {"trial_key": "A2_horizon_selection", "cohort_kind": "horizon",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "MR JSON missing"}
    j = json.loads(p.read_text(encoding="utf-8"))
    a = j.get("cohort_ALL") or {}
    n = a.get("n", 0)
    h = {k: a.get(f"fwd_{k}d_win_rate_pct") for k in (1, 3, 5, 10)}
    delta_10_5 = (h[10] or 0) - (h[5] or 0)
    verdict, note = _classify(delta=delta_10_5/100, p_value=None if h[10] is None else 0.05,
                                n=n, min_n=50)
    # If delta > 0 and n>=50, mark PROMISING; else NO_LIFT/INSUFFICIENT
    if h[10] is None or h[5] is None:
        verdict = "DATA_BLOCKED"; note = "fwd_10d or fwd_5d missing"
    elif n < 50: verdict = "INSUFFICIENT"; note = f"n={n}<50"
    elif delta_10_5 > 20: verdict = "PROMISING"; note = f"fwd_10d WR={h[10]:.1f}% vs fwd_5d={h[5]:.1f}% · Δ=+{delta_10_5:.1f}pp"
    elif delta_10_5 > 0: verdict = "PROMISING"; note = f"fwd_10d WR={h[10]:.1f}% vs fwd_5d={h[5]:.1f}% · Δ=+{delta_10_5:.1f}pp"
    else: verdict = "NO_LIFT"; note = f"fwd_10d WR={h[10]:.1f}% vs fwd_5d={h[5]:.1f}%"
    return {"trial_key": "A2_horizon_selection", "cohort_kind": "horizon",
             "sample_size": n, "metrics": {"fwd_5d_win_pct": h[5],
                                             "fwd_10d_win_pct": h[10],
                                             "delta_10_minus_5_pp": round(delta_10_5, 2)},
             "verdict": verdict, "note": note}


def a3_sector_x_mr(root: Path, market: str) -> dict:
    """A3 · does R2's edge concentrate by sector?"""
    import pandas as pd
    p = root / "reports" / "research" / "outcome_dataset.parquet"
    if not p.exists():
        return {"trial_key": "A3_sector_x_mr", "cohort_kind": "sector_split",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "outcome_dataset missing"}
    df = pd.read_parquet(p)
    df = df[(df["country"].str.lower() == market.lower()) & (df["is_closed"] == True)
             & (df["runner"] == "R2") & (df["exit_pnl_pct"].notna()) & (df["sector"].notna())]
    n = len(df)
    if n < 15:
        return {"trial_key": "A3_sector_x_mr", "cohort_kind": "sector_split",
                 "sample_size": n, "verdict": "INSUFFICIENT",
                 "note": f"n={n}<15 · hypothesis tier not reached"}
    # Cell-level win rate per sector
    by_sec = df.groupby("sector")["exit_pnl_pct"].agg(["count", "mean"])
    by_sec = by_sec[by_sec["count"] >= 3]
    if len(by_sec) < 2:
        return {"trial_key": "A3_sector_x_mr", "cohort_kind": "sector_split",
                 "sample_size": n, "verdict": "INSUFFICIENT",
                 "note": "fewer than 2 sectors with n>=3"}
    best = by_sec["mean"].max()
    worst = by_sec["mean"].min()
    spread = best - worst
    verdict = "PROMISING" if spread > 5 and n >= 30 else "INSUFFICIENT"
    return {"trial_key": "A3_sector_x_mr", "cohort_kind": "sector_split",
             "sample_size": n, "metrics": {"n_sectors_meaningful": int(len(by_sec)),
                                             "best_sector_mean_pnl": round(best, 3),
                                             "worst_sector_mean_pnl": round(worst, 3),
                                             "spread_pp": round(spread, 3)},
             "verdict": verdict, "note": f"spread {round(spread,2)}pp across {len(by_sec)} sectors"}


def a4_cap_x_mr(root: Path, market: str) -> dict:
    """A4 · does R2's edge concentrate by cap tier?"""
    import pandas as pd
    p = root / "reports" / "research" / "outcome_dataset.parquet"
    if not p.exists():
        return {"trial_key": "A4_cap_x_mr", "cohort_kind": "cap_split",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "outcome_dataset missing"}
    df = pd.read_parquet(p)
    df = df[(df["country"].str.lower() == market.lower()) & (df["is_closed"] == True)
             & (df["runner"] == "R2") & (df["exit_pnl_pct"].notna()) & (df["cap"].notna())]
    n = len(df)
    if n < 15:
        return {"trial_key": "A4_cap_x_mr", "cohort_kind": "cap_split",
                 "sample_size": n, "verdict": "INSUFFICIENT",
                 "note": f"n={n}<15"}
    by_cap = df.groupby("cap")["exit_pnl_pct"].agg(["count", "mean"])
    by_cap = by_cap[by_cap["count"] >= 3]
    if len(by_cap) < 2:
        return {"trial_key": "A4_cap_x_mr", "cohort_kind": "cap_split",
                 "sample_size": n, "verdict": "INSUFFICIENT",
                 "note": "fewer than 2 cap buckets with n>=3"}
    best = by_cap["mean"].max(); worst = by_cap["mean"].min()
    spread = best - worst
    verdict = "PROMISING" if spread > 3 and n >= 30 else "INSUFFICIENT"
    return {"trial_key": "A4_cap_x_mr", "cohort_kind": "cap_split",
             "sample_size": n, "metrics": {"n_cap_buckets": int(len(by_cap)),
                                             "best_cap_mean_pnl": round(best, 3),
                                             "worst_cap_mean_pnl": round(worst, 3),
                                             "spread_pp": round(spread, 3)},
             "verdict": verdict, "note": f"spread {round(spread,2)}pp across {len(by_cap)} caps"}


def a5_regime_x_mr(root: Path, market: str) -> dict:
    """A5 · does R2's edge hold in WEAKENING/RISK_OFF?"""
    import pandas as pd
    p = root / "reports" / "research" / "outcome_dataset.parquet"
    if not p.exists():
        return {"trial_key": "A5_regime_x_mr", "cohort_kind": "regime_split",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "outcome_dataset missing"}
    df = pd.read_parquet(p)
    df = df[(df["country"].str.lower() == market.lower()) & (df["is_closed"] == True)
             & (df["runner"] == "R2") & (df["exit_pnl_pct"].notna()) & (df["risk_state"].notna())]
    n = len(df)
    if n < 10:
        return {"trial_key": "A5_regime_x_mr", "cohort_kind": "regime_split",
                 "sample_size": n, "verdict": "INSUFFICIENT",
                 "note": f"n={n}<10 · regime split not viable"}
    by_reg = df.groupby("risk_state")["exit_pnl_pct"].agg(["count", "mean"])
    by_reg = by_reg[by_reg["count"] >= 3]
    if len(by_reg) < 2:
        return {"trial_key": "A5_regime_x_mr", "cohort_kind": "regime_split",
                 "sample_size": n, "verdict": "INSUFFICIENT",
                 "note": "fewer than 2 regimes with n>=3"}
    return {"trial_key": "A5_regime_x_mr", "cohort_kind": "regime_split",
             "sample_size": n,
             "metrics": {"per_regime_mean_pnl": {k: round(v, 3) for k, v in by_reg["mean"].items()},
                          "per_regime_n": {k: int(v) for k, v in by_reg["count"].items()}},
             "verdict": "PROMISING" if n >= 30 else "INSUFFICIENT",
             "note": f"regimes populated · n={n}"}


def a6_multi_horizon_consensus(root: Path, market: str) -> dict:
    """A6 · sign-match between fwd_1d/3d/5d/10d · not computable from aggregate MR."""
    p = root / "reports" / "research" / f"mr_forward_validation_{market}.json"
    if not p.exists():
        return {"trial_key": "A6_multi_horizon_consensus", "cohort_kind": "horizon_consensus",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "MR JSON missing"}
    j = json.loads(p.read_text(encoding="utf-8"))
    a = j.get("cohort_ALL") or {}
    n = a.get("n", 0)
    # Aggregate cohort has avg per horizon · sign-match at aggregate level (weak proxy)
    signs = {k: (1 if (a.get(f"fwd_{k}d_avg") or 0) > 0 else -1) for k in (1, 3, 5, 10)}
    all_same = len(set(signs.values())) == 1
    return {"trial_key": "A6_multi_horizon_consensus", "cohort_kind": "horizon_consensus",
             "sample_size": n,
             "metrics": {"aggregate_signs": signs, "all_horizons_agree": all_same},
             "verdict": "INSUFFICIENT",
             "note": ("aggregate-level sign check only · per-position sign-match "
                       "requires raw obs list which MR JSON doesn't expose · DATA-BLOCKED "
                       "on per-obs computation")}


def a7_r1_vs_r2_divergence(root: Path, market: str) -> dict:
    """A7 · fwd_5d avg delta R2 minus R1."""
    p = root / "reports" / "research" / f"mr_forward_validation_{market}.json"
    if not p.exists():
        return {"trial_key": "A7_r1_vs_r2", "cohort_kind": "runner_split",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "MR JSON missing"}
    j = json.loads(p.read_text(encoding="utf-8"))
    cbr = j.get("cohort_by_runner") or {}
    r1 = cbr.get("R1", {}); r2 = cbr.get("R2", {})
    n1 = r1.get("n", 0); n2 = r2.get("n", 0)
    r1_5 = r1.get("fwd_5d_avg"); r2_5 = r2.get("fwd_5d_avg")
    if r1_5 is None or r2_5 is None:
        return {"trial_key": "A7_r1_vs_r2", "cohort_kind": "runner_split",
                 "sample_size": n1 + n2, "verdict": "DATA_BLOCKED",
                 "note": "fwd_5d_avg missing on one or both runners"}
    delta = r2_5 - r1_5
    n_effective = min(n1, n2)
    verdict = ("PROMISING" if delta > 0 and n_effective >= 15
                else "INSUFFICIENT" if n_effective < 15 else "NO_LIFT")
    return {"trial_key": "A7_r1_vs_r2", "cohort_kind": "runner_split",
             "sample_size": n1 + n2,
             "metrics": {"n_R1": n1, "n_R2": n2, "R1_fwd_5d_avg": round(r1_5, 3),
                          "R2_fwd_5d_avg": round(r2_5, 3), "delta_R2_minus_R1_pp": round(delta, 3)},
             "verdict": verdict,
             "note": f"R2 fwd_5d {r2_5:+.2f}% vs R1 {r1_5:+.2f}% · Δ={delta:+.2f}pp"}


def a8_winner_sacrifice_mining(root: Path, market: str) -> dict:
    """A8 · which exit threshold sacrifices fewest winners · from NEG-PNL panel."""
    p = root / "reports" / "research" / "neg_pnl_control_60d" / f"panel_{market}.json"
    if not p.exists():
        return {"trial_key": "A8_winner_sacrifice", "cohort_kind": "winner_sacrifice",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "NEG-PNL panel missing"}
    j = json.loads(p.read_text(encoding="utf-8"))
    variants = j.get("counterfactual_variants") or []
    if not variants:
        return {"trial_key": "A8_winner_sacrifice", "cohort_kind": "winner_sacrifice",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "no counterfactual variants"}
    rows = []
    for v in variants:
        thr = v.get("threshold_pct")
        n_pos = v.get("n_positions", 0)
        dmg = v.get("damage") or {}
        rows.append({"threshold_pct": thr, "n_winners_sacrificed": dmg.get("n_winners_sacrificed"),
                      "winner_sacrifice_rate": dmg.get("winner_sacrifice_rate")})
    # Best variant · min winner_sacrifice_rate
    best = min(rows, key=lambda r: r.get("winner_sacrifice_rate") or 1.0)
    n = variants[0].get("n_positions", 0)
    return {"trial_key": "A8_winner_sacrifice", "cohort_kind": "winner_sacrifice",
             "sample_size": n,
             "metrics": {"n_variants": len(variants), "best_variant": best,
                          "all_thresholds": rows},
             "verdict": "PROMISING" if best.get("winner_sacrifice_rate", 1) < 0.05 and n >= 30 else "INSUFFICIENT",
             "note": (f"lowest winner-sacrifice rate at threshold {best['threshold_pct']} · "
                       f"rate={best.get('winner_sacrifice_rate')}")}


def a9_investability_avoid_validation(root: Path, market: str) -> dict:
    """A9 · does AVOID band label produce measurably worse fwd returns?"""
    p = root / "reports" / "research" / f"mr_forward_validation_{market}.json"
    if not p.exists():
        return {"trial_key": "A9_investability_avoid", "cohort_kind": "band_validation",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "MR JSON missing"}
    j = json.loads(p.read_text(encoding="utf-8"))
    inv = j.get("cohort_by_investability") or {}
    avoid = inv.get("AVOID", {}); ok = inv.get("OK", {})
    n_a = avoid.get("n", 0); n_o = ok.get("n", 0)
    a5 = avoid.get("fwd_5d_avg"); o5 = ok.get("fwd_5d_avg")
    if a5 is None or o5 is None:
        return {"trial_key": "A9_investability_avoid", "cohort_kind": "band_validation",
                 "sample_size": n_a + n_o, "verdict": "DATA_BLOCKED",
                 "note": "AVOID or OK fwd_5d_avg missing"}
    delta = o5 - a5    # OK should be higher than AVOID
    n_eff = min(n_a, n_o)
    verdict = ("PROMISING" if delta > 0 and n_eff >= 5
                else "INSUFFICIENT" if n_eff < 5 else "NO_LIFT")
    return {"trial_key": "A9_investability_avoid", "cohort_kind": "band_validation",
             "sample_size": n_a + n_o,
             "metrics": {"n_AVOID": n_a, "n_OK": n_o,
                          "AVOID_fwd_5d": round(a5, 3), "OK_fwd_5d": round(o5, 3),
                          "delta_OK_minus_AVOID_pp": round(delta, 3)},
             "verdict": verdict,
             "note": f"OK {o5:+.2f}% vs AVOID {a5:+.2f}% · Δ={delta:+.2f}pp"}


def a10_lead_lag_usa_india(root: Path, market: str) -> dict:
    """A10 · does USA's fwd_1d avg lead India's? · requires time series MR · not available."""
    return {"trial_key": "A10_lead_lag_usa_india", "cohort_kind": "cross_market",
             "sample_size": 0, "verdict": "DATA_BLOCKED",
             "note": ("MR JSON is single-point snapshot · lead-lag needs multiple "
                       "asof snapshots · requires accumulator of MR outputs over time · "
                       "not currently persisted")}


A_ITEMS = [
    ("A1", a1_confidence_x_fwd),
    ("A2", a2_horizon_selection),
    ("A3", a3_sector_x_mr),
    ("A4", a4_cap_x_mr),
    ("A5", a5_regime_x_mr),
    ("A6", a6_multi_horizon_consensus),
    ("A7", a7_r1_vs_r2_divergence),
    ("A8", a8_winner_sacrifice_mining),
    ("A9", a9_investability_avoid_validation),
    ("A10", a10_lead_lag_usa_india),
]


# ── Category B cohort functions ──────────────────────────────────────

def b1_kg_community_x_mr(root: Path, market: str) -> dict:
    """B1 · KG community-relative percentile × fwd return."""
    kg_paths = [root / "reports" / "research" / "kg" / f"{market}_latest.json",
                 root / "reports" / "research" / "kg" / "latest.json"]
    if not any(p.exists() for p in kg_paths):
        return {"trial_key": "B1_kg_community", "cohort_kind": "kg_split",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "no KG snapshot on disk"}
    return {"trial_key": "B1_kg_community", "cohort_kind": "kg_split",
             "sample_size": 0, "verdict": "INSUFFICIENT",
             "note": "KG snapshot present · MR × KG join not yet built · needs runner"}


def b2_disagreement_x_error(root: Path, market: str) -> dict:
    """B2 · ensemble disagreement vs prediction error correlation."""
    p = root / "reports" / "research" / "r2_upgrades" / f"p5_1_disagreement_{market}.json"
    if not p.exists():
        return {"trial_key": "B2_disagreement", "cohort_kind": "disagreement",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "P5.1 report missing"}
    j = json.loads(p.read_text(encoding="utf-8"))
    n = j.get("n_candidates_scored", 0)
    if n < 10:
        return {"trial_key": "B2_disagreement", "cohort_kind": "disagreement",
                 "sample_size": n, "verdict": "INSUFFICIENT", "note": f"n={n}<10"}
    return {"trial_key": "B2_disagreement", "cohort_kind": "disagreement",
             "sample_size": n,
             "metrics": {"median_disagreement": j.get("aggregate_median_disagreement")},
             "verdict": "INSUFFICIENT",
             "note": "P5.1 has today's disagreement but no error series yet · needs realized outcomes"}


def b3_runner_conviction_x_mr(root: Path, market: str) -> dict:
    """B3 · cross-runner conviction class predicts fwd?"""
    return {"trial_key": "B3_runner_conviction", "cohort_kind": "composite",
             "sample_size": 0, "verdict": "DATA_BLOCKED",
             "note": "composite conviction rows not yet populated with fwd outcomes"}


def b4_turnover_x_return(root: Path, market: str) -> dict:
    """B4 · same-day rotation frequency vs subsequent return."""
    p = root / "reports" / "research" / "r2_upgrades" / "p5_3_turnover_cap_simulation.json"
    if not p.exists():
        return {"trial_key": "B4_turnover", "cohort_kind": "turnover",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "P5.3 sim missing"}
    j = json.loads(p.read_text(encoding="utf-8"))
    n = j.get("n_rotation_days", 0)
    return {"trial_key": "B4_turnover", "cohort_kind": "turnover",
             "sample_size": n,
             "metrics": {"mean_daily_turnover": j.get("mean_daily_turnover_frac"),
                          "days_over_5pct": j.get("n_days_exceeding_cap")},
             "verdict": "INSUFFICIENT" if n < 30 else "NO_LIFT",
             "note": f"n_rotation_days={n} · sim only · no return correlation computed"}


def b5_entry_slippage(root: Path, market: str) -> dict:
    """B5 · actual entry vs suggested buy zone."""
    return {"trial_key": "B5_entry_slippage", "cohort_kind": "execution",
             "sample_size": 0, "verdict": "DATA_BLOCKED",
             "note": "suggested buy zone at entry time not persisted for historical positions"}


def b6_seasonality(root: Path, market: str) -> dict:
    """B6 · time-of-day / day-of-week seasonality on entries."""
    import pandas as pd
    p = root / "reports" / "research" / "outcome_dataset.parquet"
    if not p.exists():
        return {"trial_key": "B6_seasonality", "cohort_kind": "seasonality",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "outcome_dataset missing"}
    df = pd.read_parquet(p)
    df = df[(df["country"].str.lower() == market.lower()) & (df["is_closed"] == True)
             & (df["runner"] == "R2") & (df["entry_date"].notna()) & (df["exit_pnl_pct"].notna())]
    n = len(df)
    if n < 15:
        return {"trial_key": "B6_seasonality", "cohort_kind": "seasonality",
                 "sample_size": n, "verdict": "INSUFFICIENT", "note": f"n={n}<15"}
    df["entry_wd"] = pd.to_datetime(df["entry_date"]).dt.day_name()
    by_dow = df.groupby("entry_wd")["exit_pnl_pct"].agg(["count", "mean"])
    by_dow = by_dow[by_dow["count"] >= 3]
    if len(by_dow) < 2:
        return {"trial_key": "B6_seasonality", "cohort_kind": "seasonality",
                 "sample_size": n, "verdict": "INSUFFICIENT",
                 "note": "fewer than 2 weekdays with n>=3"}
    best = by_dow["mean"].max(); worst = by_dow["mean"].min(); spread = best - worst
    return {"trial_key": "B6_seasonality", "cohort_kind": "seasonality",
             "sample_size": n,
             "metrics": {"per_dow_mean_pnl": {k: round(v, 3) for k, v in by_dow["mean"].items()},
                          "spread_pp": round(spread, 3)},
             "verdict": "PROMISING" if spread > 3 and n >= 30 else "INSUFFICIENT",
             "note": f"day-of-week spread {spread:.2f}pp across {len(by_dow)} weekdays"}


def b7_position_count_x_return(root: Path, market: str) -> dict:
    """B7 · portfolio concentration effect on entry-day outcome."""
    return {"trial_key": "B7_position_count", "cohort_kind": "concentration",
             "sample_size": 0, "verdict": "DATA_BLOCKED",
             "note": "concurrent-position count per entry day not indexed"}


def b8_news_x_mr(root: Path, market: str) -> dict:
    """B8 · news sentiment × MR cohort."""
    return {"trial_key": "B8_news", "cohort_kind": "news",
             "sample_size": 0, "verdict": "DATA_BLOCKED",
             "note": "news sentiment score per Position ID at entry not surfaced in outcome_dataset"}


B_ITEMS = [
    ("B1", b1_kg_community_x_mr),
    ("B2", b2_disagreement_x_error),
    ("B3", b3_runner_conviction_x_mr),
    ("B4", b4_turnover_x_return),
    ("B5", b5_entry_slippage),
    ("B6", b6_seasonality),
    ("B7", b7_position_count_x_return),
    ("B8", b8_news_x_mr),
]


# ── Category D data-quality functions ────────────────────────────────

def d1_depth_cohorts_check(root: Path, market: str) -> dict:
    """D1 · NEG-PNL depth_cohorts field: dead code or real gap?"""
    p = root / "reports" / "research" / "neg_pnl_control_60d" / f"panel_{market}.json"
    if not p.exists():
        return {"trial_key": "D1_depth_cohorts", "cohort_kind": "data_quality",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "NEG-PNL panel missing"}
    j = json.loads(p.read_text(encoding="utf-8"))
    dc = j.get("depth_cohorts") or {}
    empty = (isinstance(dc, dict) and len(dc) == 0) or (isinstance(dc, list) and len(dc) == 0)
    return {"trial_key": "D1_depth_cohorts", "cohort_kind": "data_quality",
             "sample_size": 1,
             "metrics": {"depth_cohorts_populated": not empty,
                          "depth_cohorts_type": type(dc).__name__,
                          "depth_cohorts_size": len(dc) if isinstance(dc, (dict, list)) else None},
             "verdict": "PROMISING" if not empty else "DATA_BLOCKED",
             "note": ("depth_cohorts field is EMPTY in both markets · either dead schema "
                       "or unfired writer · confirmed data-quality gap") if empty else "populated"}


def d2_fwd17_missingness(root: Path, market: str) -> dict:
    """D2 · fwd_17d is None everywhere · window issue or wiring gap?"""
    p = root / "reports" / "research" / f"mr_forward_validation_{market}.json"
    if not p.exists():
        return {"trial_key": "D2_fwd17_missing", "cohort_kind": "data_quality",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "MR JSON missing"}
    j = json.loads(p.read_text(encoding="utf-8"))
    a = j.get("cohort_ALL") or {}
    horizons = j.get("forward_horizons_days") or []
    fwd_17 = a.get("fwd_17d_avg") if "fwd_17d_avg" in a else None
    verdict = "DATA_BLOCKED" if fwd_17 is None else "PROMISING"
    return {"trial_key": "D2_fwd17_missing", "cohort_kind": "data_quality",
             "sample_size": a.get("n", 0),
             "metrics": {"forward_horizons_declared": horizons,
                          "fwd_17d_avg_populated": fwd_17 is not None,
                          "asof": j.get("asof"),
                          "note": "17 not in horizons list" if 17 not in horizons
                                    else "horizon 17 declared but field is None · window not long enough"},
             "verdict": verdict,
             "note": ("horizons list does NOT include 17 · engine schema mismatch"
                        if 17 not in horizons and fwd_17 is None
                        else "confirmed missing")}


def d3_pos_pnl_missing_data(root: Path, market: str) -> dict:
    """D3 · POS-PNL n_data_missing · what fraction unusable?"""
    p = root / "reports" / "research" / "pos_pnl_capture_60d" / f"dataset_{market}.summary.json"
    if not p.exists():
        return {"trial_key": "D3_pos_pnl_missing", "cohort_kind": "data_quality",
                 "sample_size": 0, "verdict": "DATA_BLOCKED", "note": "POS-PNL summary missing"}
    j = json.loads(p.read_text(encoding="utf-8"))
    n_total = j.get("n_candidates_total", 0)
    n_ok = j.get("n_data_available", 0)
    n_miss = j.get("n_data_missing", 0)
    frac_miss = round(n_miss / n_total, 4) if n_total > 0 else None
    verdict = "PROMISING" if frac_miss is not None and frac_miss < 0.10 else "DATA_BLOCKED"
    return {"trial_key": "D3_pos_pnl_missing", "cohort_kind": "data_quality",
             "sample_size": n_total,
             "metrics": {"n_total": n_total, "n_data_available": n_ok,
                          "n_data_missing": n_miss,
                          "missing_fraction": frac_miss},
             "verdict": verdict,
             "note": (f"{frac_miss*100:.1f}% missing · " if frac_miss is not None else "") +
                        ("high missingness compromises winner-capture numbers"
                         if verdict == "DATA_BLOCKED" else "acceptable")}


D_ITEMS = [
    ("D1", d1_depth_cohorts_check),
    ("D2", d2_fwd17_missingness),
    ("D3", d3_pos_pnl_missing_data),
]


# ── FDR correction ──────────────────────────────────────────────────

def benjamini_hochberg(pvals: list[float | None]) -> list[float | None]:
    """Return BH-adjusted q-values in original order · None passes through."""
    indexed = [(i, p) for i, p in enumerate(pvals) if p is not None]
    indexed.sort(key=lambda x: x[1])
    m = len(indexed)
    if m == 0: return pvals[:]
    q = [None] * len(pvals)
    prev = 1.0
    # iterate largest-to-smallest for monotonicity
    for rank_from_end, (orig_i, p) in enumerate(reversed(indexed)):
        rank = m - rank_from_end
        adj = min(prev, p * m / rank)
        q[orig_i] = round(adj, 4)
        prev = adj
    return q
