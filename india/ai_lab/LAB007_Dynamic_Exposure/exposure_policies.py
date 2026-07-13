"""
india/ai_lab/LAB007_Dynamic_Exposure/exposure_policies.py — YAML → exp_series builders.

Policy plugins for LAB007. Registered with lab_runner via register_policy(). Interpret the
declarative config in `lab007.yaml` and produce PIT-safe exp_series pd.Series indexed by the
price panel dates.

Two policy types:
- multiplicative_gates: sequential multiplication of configurable India VIX gate + Nifty 200-DMA
                        gate + optional global-exposure series. Each India gate is either DISCRETE
                        (0.6-style on/off at a percentile threshold) or SMOOTH_TAPER (linear).
- constant:             a fixed exp value at every date.

Also registers the exposure simulator (simulate_cycle) which is unchanged from the historical
LAB007 implementation.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from india.feature_engine import load_panels


# ==================================== SHARED CONTEXT ====================================

def build_context(rolling_min_periods: int) -> dict:
    """Load once, share across all candidate builders + simulator invocations.
    `rolling_min_periods` MUST be supplied explicitly (from config.policy_parameters)."""
    if not isinstance(rolling_min_periods, int) or rolling_min_periods <= 0:
        raise ValueError("rolling_min_periods must be a positive int (from config)")
    closes, _, _, _, idx, vix, _ = load_panels()
    ctx = {
        "closes": closes,
        "nifty_idx": idx,
        "india_vix": vix,
        "rolling_min_periods": rolling_min_periods,
    }
    try:
        from india.global_risk import global_exposure
        g = global_exposure()
        ctx["global_exposure"] = g
    except Exception:
        ctx["global_exposure"] = None
    return ctx


# ==================================== POLICY BUILDERS ====================================

def build_multiplicative_gates_series(candidate_config: dict, context: dict) -> pd.Series:
    """
    Notes:
    - `min_periods` for the trailing rolling windows is read from context, which the caller
      seeds from `config.policy_parameters.rolling_min_periods` (no silent Python default).
    """
    """Config-driven reproduction of the production multiplicative-gate exposure formula.

    candidate_config schema (see lab007.yaml candidates):
        type: multiplicative_gates
        gates:
          india_vix:
            mode: discrete | smooth_taper
            window_days: int
            (discrete)     threshold_pctile: float, multiplier_on: float, multiplier_off: float
            (smooth_taper) from_pctile, to_pctile, multiplier_at_from_pctile, multiplier_at_to_pctile
          nifty_200dma:
            mode: discrete
            window_days: int
            multiplier_on: float, multiplier_off: float
          global_exposure:
            enabled: bool
    """
    closes = context["closes"]
    vix = context["india_vix"]
    nifty = context["nifty_idx"]
    if "rolling_min_periods" not in context:
        raise LookupError("build_multiplicative_gates_series: context missing 'rolling_min_periods' "
                          "(seed it from config.policy_parameters.rolling_min_periods)")
    min_periods = int(context["rolling_min_periods"])
    scale = pd.Series(1.0, index=closes.index)

    gates_cfg = candidate_config.get("gates", {})

    # India VIX gate
    vix_cfg = gates_cfg.get("india_vix", {})
    if vix_cfg and vix is not None:
        window = int(vix_cfg["window_days"])
        mode = vix_cfg["mode"]
        if mode == "discrete":
            q = vix.rolling(window, min_periods=min_periods).quantile(vix_cfg["threshold_pctile"])
            hi = (vix > q).reindex(closes.index).fillna(False)
            m_on = float(vix_cfg["multiplier_on"])
            m_off = float(vix_cfg["multiplier_off"])
            scale *= hi.map({True: m_on, False: m_off})
        elif mode == "smooth_taper":
            # Rolling percentile rank of latest VIX value within trailing window
            vix_r = vix.rolling(window, min_periods=min_periods).apply(
                lambda w: (w.iloc[-1] > w).mean(), raw=False)
            pctile = vix_r.reindex(closes.index).ffill().fillna(0.5)
            from_p = float(vix_cfg["from_pctile"])
            to_p = float(vix_cfg["to_pctile"])
            m_from = float(vix_cfg["multiplier_at_from_pctile"])
            m_to = float(vix_cfg["multiplier_at_to_pctile"])
            span = to_p - from_p
            amplitude = m_from - m_to
            # linear from (from_p, m_from) → (to_p, m_to); clipped outside
            taper = m_from - amplitude * ((pctile - from_p) / span).clip(lower=0.0, upper=1.0)
            scale *= taper.reindex(closes.index).fillna(m_from)
        else:
            raise ValueError(f"Unknown india_vix mode: {mode}")

    # Nifty 200-DMA gate
    n_cfg = gates_cfg.get("nifty_200dma", {})
    if n_cfg:
        window = int(n_cfg["window_days"])
        if n_cfg["mode"] != "discrete":
            raise ValueError(f"nifty_200dma only supports discrete mode (got {n_cfg['mode']})")
        below = (nifty < nifty.rolling(window).mean()).reindex(closes.index).fillna(False)
        m_on = float(n_cfg["multiplier_on"])
        m_off = float(n_cfg["multiplier_off"])
        scale *= below.map({True: m_on, False: m_off})

    # Global exposure multiplier
    g_cfg = gates_cfg.get("global_exposure", {})
    if g_cfg.get("enabled", False):
        g = context.get("global_exposure")
        if g is not None:
            scale *= g.reindex(closes.index).ffill().fillna(1.0)

    return scale


def build_constant_series(candidate_config: dict, context: dict) -> pd.Series:
    """Constant exposure policy: exp(t) = value for all t."""
    val = float(candidate_config["value"])
    return pd.Series(val, index=context["closes"].index)


# ==================================== SIMULATOR ====================================

def simulate_cycle(exp_series: pd.Series, reg_df: pd.DataFrame, closes: pd.DataFrame,
                   *, initial_capital: float, cash_return_annual: float, cost_bps: float,
                   trading_days_per_year: int) -> tuple[pd.Series, list]:
    """Cycle-by-cycle portfolio simulation. NO silent defaults — every research-critical parameter
    is keyword-required. Numerically identical to the historical exposure_lab.py implementation
    when the same values are supplied (parity-verified 2026-07-13).

    Returns (equity_series, cycles_meta_list). Meta rows include `exp` (raw exposure at asof);
    regime bucketing is assigned by the runner using config buckets (not by the simulator).
    """
    if initial_capital <= 0:
        raise ValueError("initial_capital must be > 0")
    if trading_days_per_year <= 0:
        raise ValueError("trading_days_per_year must be > 0")
    if cost_bps < 0:
        raise ValueError("cost_bps must be >= 0")
    cycles = reg_df[(reg_df["source"] == "historical") & (reg_df["scored"] == 1)].sort_values("asof")
    if cycles.empty:
        raise RuntimeError("No historical cycles in registry")

    daily_cash_return = (1 + cash_return_annual) ** (1/trading_days_per_year) - 1
    equity = pd.Series(dtype=float)
    metas = []
    current_val = float(initial_capital)
    prev_exp = None

    for rec_id, grp in cycles.groupby("rec_id", sort=False):
        asof = pd.Timestamp(grp["asof"].iloc[0])
        mature = pd.Timestamp(grp["mature_date"].iloc[0])
        exp_at_asof = float(exp_series.reindex([asof], method="ffill").iloc[0])

        if prev_exp is not None:
            delta_exp = abs(exp_at_asof - prev_exp)
            transaction_cost = current_val * delta_exp * (cost_bps / 10000.0)
            current_val -= transaction_cost

        weights = pd.to_numeric(grp["weight"], errors="coerce").fillna(0.0)
        weights = weights / weights.sum() if weights.sum() > 0 else weights
        syms = [s for s in grp["symbol"] if s in closes.columns]
        wts = weights.set_axis(grp["symbol"]).reindex(syms).fillna(0)
        wts = wts / wts.sum() if wts.sum() > 0 else wts

        prices = closes[syms].loc[asof:mature].dropna(how="all")
        if len(prices) < 2 or wts.sum() == 0:
            prev_exp = exp_at_asof
            continue
        norm = prices / prices.iloc[0]
        stock_curve = (norm * wts).sum(axis=1)
        n_bars = len(stock_curve)
        cash_curve = pd.Series(
            [(1 + daily_cash_return) ** i for i in range(n_bars)],
            index=stock_curve.index,
        )
        combined = exp_at_asof * stock_curve + (1 - exp_at_asof) * cash_curve
        cycle_equity = combined * current_val

        if not equity.empty:
            cycle_equity = cycle_equity[cycle_equity.index > equity.index[-1]]
        equity = pd.concat([equity, cycle_equity])
        cycle_end_val = float(cycle_equity.iloc[-1]) if not cycle_equity.empty else current_val

        stock_ret_pct = 100 * (stock_curve.iloc[-1] - 1)
        cash_ret_pct = 100 * (cash_curve.iloc[-1] - 1)
        cycle_ret_pct = 100 * (cycle_end_val / current_val - 1) if current_val > 0 else 0.0

        metas.append({
            "rec_id": rec_id, "asof": asof, "mature": mature,
            "exp": exp_at_asof,           # raw exposure — runner buckets it via config regimes
            "delta_exp": abs(exp_at_asof - (prev_exp if prev_exp is not None else exp_at_asof)),
            "stock_ret_pct": stock_ret_pct, "cash_ret_pct": cash_ret_pct,
            "cycle_ret_pct": cycle_ret_pct,
        })
        current_val = cycle_end_val
        prev_exp = exp_at_asof

    return equity.sort_index(), metas
