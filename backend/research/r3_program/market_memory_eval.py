"""R3 MARKET MEMORY v1 — outcome memory, separation and date-aware validation.

The order here is deliberate and is the whole discipline of the module:

  1. twin stability decides whether a twin is a real object at all
  2. outcome memory describes what happened to twins, in full, not as a win rate
  3. separation asks what differentiates failure twins from success twins
     BEFORE the outcome
  4. validation asks whether any of it survives removing a date, a ticker, or a
     block of time

A separation statistic computed on unstable twins is a statement about the
distance metric. A separation statistic that dies under leave-date-out was one
week wearing a thousand rows.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

SEVERE = -5.0
MEANINGFUL_MFE = 2.0


# ── §6 OUTCOME MEMORY ─────────────────────────────────────────────────
def outcome_memory(panel: pd.DataFrame, idx: list) -> dict:
    """The full outcome picture for a twin set. Not reduced to a win rate."""
    if not len(idx):
        return {"n": 0}
    s = panel.iloc[idx]
    out: dict = {"n": int(len(s)),
                 "n_tickers": int(s["ticker"].nunique()),
                 "n_dates": int(s["date"].nunique())}
    for h in (1, 5, 10, 20):
        c = "fwd_%dd" % h
        if c in s.columns:
            v = s[c].dropna()
            out["fwd_%dd_mean" % h] = round(float(v.mean()), 4) if len(v) else None
    for c, name in (("fwd_mae_20", "mae"), ("fwd_mfe_20", "mfe")):
        if c in s.columns:
            v = s[c].dropna()
            out["%s_mean" % name] = round(float(v.mean()), 4) if len(v) else None
    f20 = s.get("fwd_20d")
    mfe = s.get("fwd_mfe_20")
    if f20 is not None:
        v = f20.dropna()
        out["win_rate_pct"] = round(100.0 * float((v > 0).mean()), 2) if len(v) else None
        out["severe_loss_rate_pct"] = round(100.0 * float((v <= SEVERE).mean()), 2) if len(v) else None
    if mfe is not None and f20 is not None:
        both = s[["fwd_mfe_20", "fwd_20d"]].dropna()
        if len(both):
            never = (both["fwd_mfe_20"] < MEANINGFUL_MFE)
            rev = (both["fwd_mfe_20"] >= MEANINGFUL_MFE) & (both["fwd_20d"] <= SEVERE)
            out["never_profitable_pct"] = round(100.0 * float(never.mean()), 2)
            out["profit_then_reversed_pct"] = round(100.0 * float(rev.mean()), 2)
    return out


# ── §7/§8 FAILURE AND SUCCESS TWINS ───────────────────────────────────
def twin_populations(panel: pd.DataFrame, query_idx: np.ndarray,
                     consensus: list, outcome: str = "fwd_20d") -> dict:
    """For each query, what fraction of its twins subsequently failed?

    The research question is whether that fraction is knowable at entry - i.e.
    whether it differs between queries that later failed and queries that later
    succeeded.
    """
    oc = panel[outcome].to_numpy(dtype=float)
    rows = []
    for i, qi in enumerate(query_idx):
        tw = consensus[i]
        if len(tw) < 10:
            continue
        v = pd.Series(oc[tw]).dropna()
        if len(v) < 10:
            continue
        q = oc[qi]
        rows.append({
            "query_index": int(qi),
            "ticker": str(panel["ticker"].iloc[qi]),
            "date": str(pd.Timestamp(panel["date"].iloc[qi]).date()),
            "n_twins": int(len(v)),
            "twin_fail_frac": round(float((v <= SEVERE).mean()), 4),
            "twin_win_frac": round(float((v > 0).mean()), 4),
            "twin_mean": round(float(v.mean()), 4),
            "twin_sd": round(float(v.std()), 4),
            "query_outcome": None if not np.isfinite(q) else round(float(q), 4),
        })
    if not rows:
        return {"status": "NO_CONSENSUS_TWINS",
                "reason": ("No query had enough twins agreed on by multiple "
                           "methods, which is a direct consequence of the "
                           "stability result.")}
    d = pd.DataFrame(rows).dropna(subset=["query_outcome"])
    if d.empty:
        return {"status": "NO_SCORED_QUERIES"}
    failed = d[d["query_outcome"] <= SEVERE]
    ok = d[d["query_outcome"] > 0]
    return {"status": "OK", "n_queries": int(len(d)),
            "n_dates": int(pd.Series(d["date"]).nunique()),
            "n_tickers": int(pd.Series(d["ticker"]).nunique()),
            "failed_queries": {
                "n": int(len(failed)),
                "mean_twin_fail_frac": round(float(failed["twin_fail_frac"].mean()), 4) if len(failed) else None,
                "mean_twin_mean": round(float(failed["twin_mean"].mean()), 4) if len(failed) else None},
            "successful_queries": {
                "n": int(len(ok)),
                "mean_twin_fail_frac": round(float(ok["twin_fail_frac"].mean()), 4) if len(ok) else None,
                "mean_twin_mean": round(float(ok["twin_mean"].mean()), 4) if len(ok) else None},
            "separation_twin_fail_frac": (
                round(float(failed["twin_fail_frac"].mean() - ok["twin_fail_frac"].mean()), 4)
                if len(failed) and len(ok) else None),
            "rank_corr_twinmean_vs_actual": round(float(
                d["twin_mean"].corr(d["query_outcome"], method="spearman")), 4),
            # THE CONFOUND SPLIT. twin_mean averages EARLIER outcomes, so it can
            # track the market state of the query DATE rather than anything
            # about the stock. Removing the date mean isolates the
            # cross-sectional claim; the date-level correlation isolates the
            # market-timing one. India and USA come out opposite here.
            **_demean_split(d),
            "detail": rows}


def _demean_split(d: pd.DataFrame) -> dict:
    """Separate the cross-sectional claim from the date-level one."""
    t = d.copy()
    if t["date"].nunique() < 5 or len(t) < 30:
        return {"demean_split": {"status": "TOO_FEW"}}
    t["tm_dm"] = t["twin_mean"] - t.groupby("date")["twin_mean"].transform("mean")
    t["qo_dm"] = t["query_outcome"] - t.groupby("date")["query_outcome"].transform("mean")
    within = t["tm_dm"].corr(t["qo_dm"], method="spearman")
    ss_tot = float(((t["twin_mean"] - t["twin_mean"].mean()) ** 2).sum())
    ss_in = float((t["tm_dm"] ** 2).sum())
    g = t.groupby("date").agg(tm=("twin_mean", "mean"),
                              qo=("query_outcome", "mean"),
                              n=("ticker", "size"))
    g = g[g["n"] >= 3]
    dlev = (g["tm"].corr(g["qo"], method="spearman") if len(g) >= 10 else None)
    return {"demean_split": {
        "within_date_rho": None if pd.isna(within) else round(float(within), 4),
        "date_level_rho": None if (dlev is None or pd.isna(dlev)) else round(float(dlev), 4),
        "n_dates_for_date_level": int(len(g)),
        "variance_of_twin_mean_due_to_date_pct": (
            round(100.0 * (1 - ss_in / ss_tot), 1) if ss_tot > 0 else None),
        "interpretation": ("within_date_rho is the cross-sectional claim; "
                           "date_level_rho is market timing. A result that only "
                           "survives at date level is the already-rejected "
                           "latent-state finding under another name.")}}


def within_date_frame(d: pd.DataFrame) -> pd.DataFrame:
    """Rows with the date mean removed from both sides, for validation."""
    t = d.copy()
    t["tm_dm"] = t["twin_mean"] - t.groupby("date")["twin_mean"].transform("mean")
    t["qo_dm"] = t["query_outcome"] - t.groupby("date")["query_outcome"].transform("mean")
    return t


# ── §15 DATE-AWARE VALIDATION ─────────────────────────────────────────
def leave_one_out(d: pd.DataFrame, value: str, group: str,
                  outcome: str = "query_outcome") -> dict:
    """Recompute the rank correlation with each group removed in turn.

    If one date or one ticker carries the result, this is where it shows.
    """
    if d.empty or d[group].nunique() < 3:
        return {"status": "TOO_FEW_GROUPS"}
    base = float(d[value].corr(d[outcome], method="spearman"))
    vals = []
    for g in d[group].unique():
        sub = d[d[group] != g]
        if len(sub) < 30:
            continue
        r = sub[value].corr(sub[outcome], method="spearman")
        if pd.notna(r):
            vals.append({"removed": str(g), "rho": round(float(r), 4)})
    if not vals:
        return {"status": "TOO_FEW_ROWS"}
    arr = np.array([v["rho"] for v in vals])
    flips = bool((arr.min() < 0 < arr.max()) or
                 (np.sign(arr).min() != np.sign(base) and base != 0))
    return {"status": "OK", "baseline_rho": round(base, 4),
            "n_groups": int(len(vals)),
            "rho_min": round(float(arr.min()), 4),
            "rho_max": round(float(arr.max()), 4),
            "rho_mean": round(float(arr.mean()), 4),
            "sign_flips_when_a_group_is_removed": flips,
            "worst_case_group": min(vals, key=lambda v: abs(v["rho"]))["removed"],
            "verdict": "FRAGILE" if flips else "STABLE"}


def date_block_bootstrap(d: pd.DataFrame, value: str,
                         outcome: str = "query_outcome",
                         block: int = 5, n_boot: int = 400,
                         seed: int = 20260916) -> dict:
    """Resample whole blocks of DATES, never individual rows.

    Rows on the same date are not independent - hundreds of names share one
    morning - so a row bootstrap would produce a confidence interval far too
    narrow to mean anything.
    """
    if d.empty:
        return {"status": "EMPTY"}
    dates = np.sort(pd.Series(d["date"]).unique())
    if len(dates) < block * 3:
        return {"status": "INSUFFICIENT_DATES", "n_dates": int(len(dates))}
    blocks = [dates[i:i + block] for i in range(0, len(dates), block)]
    rng = np.random.default_rng(seed)
    obs = float(d[value].corr(d[outcome], method="spearman"))
    stats = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(blocks), size=len(blocks))
        keep = np.concatenate([blocks[i] for i in pick])
        sub = d[d["date"].isin(set(keep))]
        if len(sub) < 30:
            continue
        r = sub[value].corr(sub[outcome], method="spearman")
        if pd.notna(r):
            stats.append(float(r))
    if len(stats) < 50:
        return {"status": "TOO_FEW_RESAMPLES", "n": len(stats)}
    arr = np.array(stats)
    lo, hi = np.percentile(arr, [2.5, 97.5])
    return {"status": "OK", "observed_rho": round(obs, 4),
            "block_size_dates": block, "n_resamples": len(stats),
            "ci95_low": round(float(lo), 4), "ci95_high": round(float(hi), 4),
            "ci_excludes_zero": bool(lo > 0 or hi < 0),
            "n_dates": int(len(dates)),
            "note": ("Blocks of whole dates are resampled. A row-level bootstrap "
                     "would treat one morning of several hundred names as several "
                     "hundred independent observations.")}


# ── §17 DECISION UTILITY ──────────────────────────────────────────────
def decision_utility(d: pd.DataFrame, value: str,
                     outcome: str = "query_outcome",
                     quantile: float = 0.2) -> dict:
    """R2 baseline vs R2 + memory: would avoiding the worst-twin cohort help?

    Measured on the same cohort, so the comparison is like-for-like.
    """
    if d.empty or len(d) < 50:
        return {"status": "INSUFFICIENT_SAMPLE", "n": int(len(d))}
    thr = d[value].quantile(quantile)
    avoid = d[value] <= thr
    base, kept = d[outcome], d.loc[~avoid, outcome]
    sev_base = float((base <= SEVERE).mean())
    sev_kept = float((kept <= SEVERE).mean()) if len(kept) else np.nan
    win_base = float((base > 0).mean())
    win_kept = float((kept > 0).mean()) if len(kept) else np.nan
    avoided = d.loc[avoid, outcome]
    return {
        "status": "OK", "rule": "avoid the worst %.0f%% by %s" % (quantile * 100, value),
        "n_total": int(len(d)), "n_avoided": int(avoid.sum()),
        "n_dates": int(pd.Series(d["date"]).nunique()),
        "severe_rate_baseline_pct": round(100.0 * sev_base, 2),
        "severe_rate_after_pct": round(100.0 * sev_kept, 2),
        "severe_losses_avoided": int((avoided <= SEVERE).sum()),
        "winners_sacrificed": int((avoided > 0).sum()),
        "false_avoidance_rate_pct": round(100.0 * float((avoided > 0).mean()), 2) if len(avoided) else None,
        "expectancy_baseline_pct": round(float(base.mean()), 4),
        "expectancy_after_pct": round(float(kept.mean()), 4) if len(kept) else None,
        "expectancy_delta_pct": round(float(kept.mean() - base.mean()), 4) if len(kept) else None,
        "win_rate_baseline_pct": round(100.0 * win_base, 2),
        "win_rate_after_pct": round(100.0 * win_kept, 2),
        "turnover_impact": "%d of %d candidates removed" % (int(avoid.sum()), len(d)),
        "verdict": ("NO INCREMENTAL DECISION VALUE"
                    if not (len(kept) and kept.mean() > base.mean() and sev_kept < sev_base)
                    else "POSITIVE ON THIS COHORT - requires frozen confirmation"),
    }
