"""
india/ai_lab/lab_metrics.py — shared metric suite for AI Lab experiments.

Consolidates helpers previously duplicated in LAB006 exit_lab.py and LAB007 exposure_lab.py.
- metric_suite(equity, cycles_meta): CAGR/Sharpe/Sortino/MaxDD/CVaR/Ulcer/recovery + exposure stats
- period_metrics(equity, meta, asofs): metric_suite restricted to a subset of cycles
- read_trial_manifest_count(path): reads cumulative_strategy_search from central manifest
- pbo_across_configs(config_returns_df, S, min_configs): CSCV with feasibility guard
- sharpe_rank_stability(equity_by_config, n_folds): per-fold Sharpe rankings

All functions PIT-safe (operate on the equity curve you pass; no re-reconstruction of PIT signals).
"""
from __future__ import annotations
from pathlib import Path
import re
import numpy as np
import pandas as pd


# ==================================== METRIC SUITE ====================================

def metric_suite(equity: pd.Series, cycles_meta: list | None = None, trading_days: int = 252) -> dict:
    """Compute the full metric suite from an equity curve + optional per-cycle metadata.

    equity: daily-indexed portfolio value series.
    cycles_meta: optional list of dicts. Recognized keys:
        n_exits, exited, n_false_exits — for exit-style experiments (LAB006)
        exp, delta_exp                  — for exposure-style experiments (LAB007)
    """
    r = equity.pct_change().dropna()
    empty = {
        "cagr": np.nan, "sharpe": np.nan, "sortino": np.nan, "max_dd": np.nan,
        "cvar5": np.nan, "ulcer": np.nan, "recovery_days": np.nan,
        "avg_exp": np.nan, "min_exp": np.nan, "n_exp_changes": np.nan,
        "total_exits": np.nan, "cycles_with_any_exit": np.nan,
        "false_exit_rate": np.nan, "opportunity_cost": np.nan,
        "total_ret": np.nan, "years": np.nan,
    }
    if len(r) < 30:
        return empty

    T = len(r); years = T / trading_days
    total_ret = float(equity.iloc[-1] / equity.iloc[0] - 1)
    cagr = (1 + total_ret) ** (1 / years) - 1 if years > 0 else 0.0
    sr = r.mean() / (r.std(ddof=1) + 1e-12)
    sharpe = sr * np.sqrt(trading_days)
    downside = r[r < 0]
    sortino = (r.mean() / (downside.std(ddof=1) + 1e-12) * np.sqrt(trading_days)) if len(downside) else np.nan
    peak = equity.cummax(); dd = equity / peak - 1
    max_dd = float(dd.min())
    var5 = float(np.percentile(r, 5))
    cvar5 = float(r[r <= var5].mean()) if (r <= var5).any() else var5
    ulcer = float(np.sqrt((dd ** 2).mean()) * 100)
    trough_idx = dd.idxmin(); after = equity.loc[trough_idx:]; peak_val = peak.loc[trough_idx]
    recovered = after[after >= peak_val]
    recovery_days = int((recovered.index[0] - trough_idx).days) if len(recovered) else np.nan

    out = {
        "cagr": cagr, "sharpe": sharpe, "sortino": sortino, "max_dd": max_dd,
        "cvar5": cvar5, "ulcer": ulcer, "recovery_days": recovery_days,
        "avg_exp": np.nan, "min_exp": np.nan, "n_exp_changes": np.nan,
        "total_exits": np.nan, "cycles_with_any_exit": np.nan,
        "false_exit_rate": np.nan, "opportunity_cost": np.nan,
        "total_ret": total_ret, "years": years,
    }

    if cycles_meta:
        cm = pd.DataFrame(cycles_meta)
        if "exp" in cm:
            out["avg_exp"] = float(cm["exp"].mean())
            out["min_exp"] = float(cm["exp"].min())
        if "delta_exp" in cm:
            out["n_exp_changes"] = int((cm["delta_exp"] > 1e-6).sum())
        if "exited" in cm and len(cm):
            out["cycles_with_any_exit"] = float(cm["exited"].mean())
        if "n_exits" in cm:
            out["total_exits"] = int(cm["n_exits"].sum())
        if "n_exits" in cm and "n_false_exits" in cm:
            denom = int(cm["n_exits"].sum())
            if denom > 0:
                out["false_exit_rate"] = float(cm["n_false_exits"].sum() / denom)
        if "opportunity_pct" in cm and "exited" in cm:
            triggered = cm[cm["exited"] == True]
            if len(triggered):
                out["opportunity_cost"] = float(triggered["opportunity_pct"].mean())
    return out


def period_metrics(equity: pd.Series, cycles_meta: list, cycle_asofs_in_period: set,
                   trading_days: int = 252) -> dict:
    """Compute metric_suite restricted to cycles whose asof is in the given set.

    Slices the equity curve to each in-scope cycle's [asof, mature] window and stitches them
    (compounding across gaps). Preserves per-cycle metadata."""
    if not cycle_asofs_in_period:
        return metric_suite(pd.Series(dtype=float), None)
    windows = [(m["asof"], m["mature"]) for m in cycles_meta
               if pd.Timestamp(m["asof"]) in cycle_asofs_in_period]
    if not windows:
        return metric_suite(pd.Series(dtype=float), None)
    slices = []; running = 1.0
    for start, end in windows:
        seg = equity.loc[pd.Timestamp(start):pd.Timestamp(end)]
        if seg.empty:
            continue
        seg_norm = (seg / seg.iloc[0]) * running
        slices.append(seg_norm)
        running = float(seg_norm.iloc[-1])
    if not slices:
        return metric_suite(pd.Series(dtype=float), None)
    period_eq = pd.concat(slices)
    period_eq = period_eq[~period_eq.index.duplicated(keep="last")].sort_index()
    period_meta = [m for m in cycles_meta if pd.Timestamp(m["asof"]) in cycle_asofs_in_period]
    return metric_suite(period_eq, period_meta, trading_days=trading_days)


# ==================================== ROBUSTNESS ====================================

def read_trial_manifest_count(manifest_path: str | Path) -> int:
    """Parse cumulative_strategy_search from a central Lab-wide manifest. Raises on parse-miss."""
    p = Path(manifest_path)
    if not p.exists():
        raise FileNotFoundError(f"Trial manifest not found: {p}")
    text = p.read_text(encoding="utf-8")
    m = re.search(r"cumulative_strategy_search:\s*(\d+)", text)
    if m:
        return int(m.group(1))
    raise LookupError(f"Could not parse cumulative_strategy_search from {p}. "
                      f"Add a 'cumulative_strategy_search: N' line at the top.")


def pbo_across_configs(config_returns_df: pd.DataFrame, S: int = 8,
                       min_configs_for_interpretation: int = 6) -> dict:
    """Bailey-López de Prado CSCV PBO across N distinct strategy configs.

    Returns dict with:
      status: "computed" | "N/A"
      value: float or NaN
      note: human-readable reason
      n_configs: int
      s_folds: int
    """
    from india.validation import pbo as _pbo
    R = config_returns_df.dropna(how="any")
    n_configs = R.shape[1]
    if n_configs < 4:
        return {"status": "N/A", "value": float("nan"),
                "note": f"only {n_configs} configs; CSCV requires ≥4",
                "n_configs": n_configs, "s_folds": S}
    if len(R) < S:
        return {"status": "N/A", "value": float("nan"),
                "note": f"only {len(R)} time obs vs {S} folds",
                "n_configs": n_configs, "s_folds": S}
    val = float(_pbo(R, S=S))
    interp_note = "" if n_configs >= min_configs_for_interpretation else \
        f" · CAUTION: N={n_configs} < min-for-interpretation {min_configs_for_interpretation} — treat with skepticism"
    return {"status": "computed", "value": val,
            "note": f"N={n_configs} configs, S={S} folds{interp_note}",
            "n_configs": n_configs, "s_folds": S}


def sharpe_rank_stability(equity_by_config: dict, n_folds: int = 4,
                          trading_days: int = 252) -> tuple[pd.DataFrame, dict]:
    """Split equity index into n_folds; rank configs by fold Sharpe (1 = best).
    Returns (ranks_df, top_2_fraction)."""
    common = None
    for eq in equity_by_config.values():
        common = eq.index if common is None else common.intersection(eq.index)
    if common is None or len(common) < 30:
        return pd.DataFrame(), {}
    common = sorted(common); fold_size = len(common) // n_folds
    ranks = {}
    for i in range(n_folds):
        s = i * fold_size
        e = (i + 1) * fold_size if i < n_folds - 1 else len(common)
        fold_dates = common[s:e]
        sharpes = {}
        for name, eq in equity_by_config.items():
            r = eq.reindex(fold_dates).pct_change().dropna()
            if len(r) < 5:
                sharpes[name] = -np.inf
            else:
                sharpes[name] = float(r.mean() / (r.std(ddof=1) + 1e-12) * np.sqrt(trading_days))
        srs = pd.Series(sharpes).sort_values(ascending=False)
        ranks[f"fold_{i+1}"] = pd.Series({name: rank + 1 for rank, name in enumerate(srs.index)})
    ranks_df = pd.DataFrame(ranks).T
    top2 = {name: float((ranks_df[name] <= 2).mean()) for name in ranks_df.columns}
    return ranks_df, top2
