# india/ai_lab/LAB007_Dynamic_Exposure/exposure_lab.py
"""
LAB007 SCAFFOLD — exposure-aware cycle simulator + candidate policies.

Extends LAB006 exit_lab with:
  * exp_series_pit()          — reconstruct the PRODUCTION exposure series exactly as
                                confidence_engine.current_regime() would compute it, per date.
                                Fully PIT-safe: rolling windows use only trailing data + ffill.
  * candidate_policy_*()      — the 4 sealed candidates (A, B, C, D) — each returns exp series.
  * simulate_lab007_cycle()   — cycle-level portfolio walk with per-cycle exp + cash return leg
                                + |Δexp|-based transaction cost between cycles.
  * cycle_returns_matrix()    — T×N returns matrix for full-matrix PBO across N0 + candidates.

Every exposure calculation uses ONLY trailing data. Rolling windows, ffill, no future look-ahead.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from india.feature_engine import load_panels


# ================================================================
# EXPOSURE SERIES — reconstruct production + candidates (all PIT)
# ================================================================

def _global_exposure_series():
    """Rebuild global_exposure() exactly as india/global_risk.py does — PIT-safe multiplicative."""
    try:
        from india.global_risk import global_exposure
        g = global_exposure()
        return g
    except Exception:
        return None


def _india_signals():
    """Return (closes_idx, vix_hi_series, nifty_below_series) — the two India PIT signals."""
    closes, _, _, _, idx, vix, _ = load_panels()
    below = (idx < idx.rolling(200).mean()).reindex(closes.index).fillna(False)
    vix_hi = None
    vix_pctile = None
    if vix is not None:
        q80 = vix.rolling(120, min_periods=30).quantile(0.80)
        vix_hi = (vix > q80).reindex(closes.index).fillna(False)
        # pctile for smooth taper: use rolling rank over trailing 120 days
        vix_r = vix.rolling(120, min_periods=30).apply(
            lambda w: (w.iloc[-1] > w).mean(), raw=False)
        vix_pctile = vix_r.reindex(closes.index).ffill().fillna(0.5)
    return closes, vix_hi, below, vix_pctile


def exp_series_pit_production():
    """PRODUCTION EXPOSURE — the null (N0). Reconstruct current_regime() logic per-date, over all
    dates in the price panel. Returns pd.Series indexed by closes.index."""
    closes, vix_hi, below, _ = _india_signals()
    scale = pd.Series(1.0, index=closes.index)
    # G1: India VIX gate (0.6 when in top-20%)
    if vix_hi is not None:
        scale *= vix_hi.map({True: 0.6, False: 1.0})
    # G2: Nifty 200-DMA gate (0.6 when below)
    scale *= below.map({True: 0.6, False: 1.0})
    # G3, G4, G5: global exposure multiplier
    g = _global_exposure_series()
    if g is not None:
        scale *= g.reindex(closes.index).ffill().fillna(1.0)
    return scale


def exp_series_candidate_A():
    """A — MILDER INDIA GATES: G1 + G2 replace 0.6 with 0.75. Global gates unchanged."""
    closes, vix_hi, below, _ = _india_signals()
    scale = pd.Series(1.0, index=closes.index)
    if vix_hi is not None:
        scale *= vix_hi.map({True: 0.75, False: 1.0})   # G1 milder
    scale *= below.map({True: 0.75, False: 1.0})        # G2 milder
    g = _global_exposure_series()
    if g is not None:
        scale *= g.reindex(closes.index).ffill().fillna(1.0)
    return scale


def exp_series_candidate_B():
    """B — STRONGER INDIA GATES: G1 + G2 replace 0.6 with 0.45. Global gates unchanged."""
    closes, vix_hi, below, _ = _india_signals()
    scale = pd.Series(1.0, index=closes.index)
    if vix_hi is not None:
        scale *= vix_hi.map({True: 0.45, False: 1.0})   # G1 stronger
    scale *= below.map({True: 0.45, False: 1.0})        # G2 stronger
    g = _global_exposure_series()
    if g is not None:
        scale *= g.reindex(closes.index).ffill().fillna(1.0)
    return scale


def exp_series_candidate_C():
    """C — SMOOTH INDIA-VIX TAPER: G1 replaced with linear taper 1.0 → 0.60 as VIX pctile crosses
    60th → 90th over trailing 120 days. Below 60th pctile → 1.0. Above 90th pctile → 0.60.
    G2 unchanged (still discrete 0.60 when below 200-DMA). Global gates unchanged."""
    closes, _, below, vix_pctile = _india_signals()
    scale = pd.Series(1.0, index=closes.index)
    # G1: smooth taper
    if vix_pctile is not None:
        # linear from (0.60, 1.0) to (0.90, 0.60), clipped outside
        vix_g = 1.0 - 0.40 * ((vix_pctile - 0.60) / 0.30).clip(lower=0.0, upper=1.0)
        scale *= vix_g.reindex(closes.index).fillna(1.0)
    # G2: unchanged discrete
    scale *= below.map({True: 0.6, False: 1.0})
    g = _global_exposure_series()
    if g is not None:
        scale *= g.reindex(closes.index).ffill().fillna(1.0)
    return scale


def exp_series_candidate_D():
    """D — FIXED 0.85 CONSTANT. No regime input."""
    closes, _, _, _ = _india_signals()
    return pd.Series(0.85, index=closes.index)


CANDIDATES = {
    "N0": ("Production dynamic exposure (control)", exp_series_pit_production),
    "A":  ("Milder India gates (0.75)",              exp_series_candidate_A),
    "B":  ("Stronger India gates (0.45)",            exp_series_candidate_B),
    "C":  ("Smooth India-VIX taper",                 exp_series_candidate_C),
    "D":  ("Fixed 0.85 constant",                    exp_series_candidate_D),
}


# ================================================================
# SIMULATION — cycle-level portfolio with exposure + cash + costs
# ================================================================

def simulate_lab007(exp_series, reg_df, closes, initial_capital=100_000,
                   cash_return_annual=0.0, cost_bps=15):
    """Run the full backtest for ONE exposure policy.

    Portfolio evolution across the 19 chronological cycles:
      value_end_of_cycle = value_start * [ exp * stock_weighted_gross_return
                                          + (1 - exp) * cash_gross_return ]
      Then rebalance cost applied between cycles: cost_bps * |exp_next - exp_current|.

    Returns:
      equity_series: pd.Series (daily bars from cycle 1 asof through last cycle mature),
                     equity value compounded across cycles.
      cycles_meta: list of per-cycle dict with {rec_id, asof, mature, exp, stock_ret_pct,
                   cycle_ret_pct, weak/strong/neutral, ...}
    """
    cycles = reg_df[(reg_df["source"] == "historical") & (reg_df["scored"] == 1)].sort_values("asof")
    if cycles.empty:
        raise RuntimeError("No historical cycles in registry")

    daily_cash_return = (1 + cash_return_annual) ** (1/252) - 1     # per trading day
    equity = pd.Series(dtype=float)
    metas = []
    current_val = float(initial_capital)
    prev_exp = None

    for rec_id, grp in cycles.groupby("rec_id", sort=False):
        asof = pd.Timestamp(grp["asof"].iloc[0])
        mature = pd.Timestamp(grp["mature_date"].iloc[0])
        # exposure at asof (PIT-safe: ffill within the series that was built with rolling windows)
        exp_at_asof = float(exp_series.reindex([asof], method="ffill").iloc[0])

        # Apply |Δexp|-based transaction cost between cycles (on the CHANGED fraction of capital)
        if prev_exp is not None:
            delta_exp = abs(exp_at_asof - prev_exp)
            transaction_cost = current_val * delta_exp * (cost_bps / 10000.0)
            current_val -= transaction_cost

        # Stock-weighted daily returns within cycle
        weights = pd.to_numeric(grp["weight"], errors="coerce").fillna(0.0)
        weights = weights / weights.sum() if weights.sum() > 0 else weights
        syms = [s for s in grp["symbol"] if s in closes.columns]
        wts = weights.set_axis(grp["symbol"]).reindex(syms).fillna(0)
        wts = wts / wts.sum() if wts.sum() > 0 else wts

        prices = closes[syms].loc[asof:mature].dropna(how="all")
        if len(prices) < 2 or wts.sum() == 0:
            prev_exp = exp_at_asof
            continue
        # Portfolio price index (weighted, rebased to 1.0 at asof)
        norm = prices / prices.iloc[0]
        stock_curve = (norm * wts).sum(axis=1)  # gross portfolio return
        # Cash leg: compounds at daily_cash_return
        n_bars = len(stock_curve)
        cash_curve = pd.Series(
            [(1 + daily_cash_return) ** i for i in range(n_bars)],
            index=stock_curve.index,
        )
        # Combined portfolio value path within cycle
        combined = exp_at_asof * stock_curve + (1 - exp_at_asof) * cash_curve
        # Scale to current capital
        cycle_equity = combined * current_val

        # Stitch (avoid duplicate boundary date)
        if not equity.empty:
            cycle_equity = cycle_equity[cycle_equity.index > equity.index[-1]]
        equity = pd.concat([equity, cycle_equity])
        cycle_end_val = float(cycle_equity.iloc[-1]) if not cycle_equity.empty else current_val

        stock_ret_pct = 100 * (stock_curve.iloc[-1] - 1)
        cash_ret_pct = 100 * (cash_curve.iloc[-1] - 1)
        cycle_ret_pct = 100 * (cycle_end_val / current_val - 1) if current_val > 0 else 0.0

        metas.append({
            "rec_id": rec_id, "asof": asof, "mature": mature,
            "exp": exp_at_asof, "delta_exp": abs(exp_at_asof - (prev_exp if prev_exp is not None else exp_at_asof)),
            "stock_ret_pct": stock_ret_pct, "cash_ret_pct": cash_ret_pct,
            "cycle_ret_pct": cycle_ret_pct,
            "regime": "Strong" if exp_at_asof >= 0.9 else ("Neutral" if exp_at_asof >= 0.65 else "Weak"),
        })
        current_val = cycle_end_val
        prev_exp = exp_at_asof

    return equity.sort_index(), metas


# ================================================================
# METRICS
# ================================================================

def metric_suite(equity, cycles_meta=None, trading_days=252):
    """Same shape as LAB006 metric_suite, minimal exposure-relevant additions."""
    r = equity.pct_change().dropna()
    if len(r) < 30:
        return {k: np.nan for k in ("cagr", "sharpe", "sortino", "max_dd", "cvar5", "ulcer",
                                    "recovery_days", "avg_exp", "min_exp", "n_exp_changes",
                                    "total_ret", "years")}
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

    avg_exp = min_exp = n_exp_changes = np.nan
    if cycles_meta:
        cm = pd.DataFrame(cycles_meta)
        if "exp" in cm:
            avg_exp = float(cm["exp"].mean())
            min_exp = float(cm["exp"].min())
        if "delta_exp" in cm:
            n_exp_changes = int((cm["delta_exp"] > 1e-6).sum())

    return {"cagr": cagr, "sharpe": sharpe, "sortino": sortino, "max_dd": max_dd,
            "cvar5": cvar5, "ulcer": ulcer, "recovery_days": recovery_days,
            "avg_exp": avg_exp, "min_exp": min_exp, "n_exp_changes": n_exp_changes,
            "total_ret": total_ret, "years": years}


def period_metrics(equity, cycles_meta, cycle_asofs_in_period, trading_days=252):
    """Slice equity to cycles whose asof is in the given set, compute metrics on the concat."""
    if not cycle_asofs_in_period:
        return {k: np.nan for k in ("cagr", "sharpe", "sortino", "max_dd", "cvar5", "ulcer",
                                    "recovery_days", "avg_exp", "min_exp", "n_exp_changes",
                                    "total_ret", "years")}
    date_windows = [(m["asof"], m["mature"]) for m in cycles_meta
                    if pd.Timestamp(m["asof"]) in cycle_asofs_in_period]
    if not date_windows:
        return metric_suite(pd.Series(dtype=float), None)
    slices, running = [], 1.0
    for start, end in date_windows:
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
    return metric_suite(period_eq, period_meta)


# ================================================================
# FOLD-LEVEL Sharpe rank stability (used when PBO is uninterpretable at low N)
# ================================================================

def sharpe_rank_stability(equity_by_config, n_folds=4):
    """Split full equity index into n_folds; compute per-fold Sharpe rank for each config.
    Returns DataFrame (folds × configs) of ranks (1 = best in fold).
    Also returns a summary: for each config, fraction of folds where it ranked in top-2."""
    common = None
    for eq in equity_by_config.values():
        common = eq.index if common is None else common.intersection(eq.index)
    if common is None or len(common) < 30:
        return pd.DataFrame(), {}
    common = sorted(common)
    fold_size = len(common) // n_folds
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
                sharpes[name] = float(r.mean() / (r.std(ddof=1) + 1e-12) * np.sqrt(252))
        s_series = pd.Series(sharpes).sort_values(ascending=False)
        # rank 1 = best
        ranks[f"fold_{i+1}"] = pd.Series({name: rank + 1 for rank, name in enumerate(s_series.index)})
    ranks_df = pd.DataFrame(ranks).T
    top2 = {name: float((ranks_df[name] <= 2).mean()) for name in ranks_df.columns}
    return ranks_df, top2
