"""
india/ai_lab/LAB008_Horizon_Calibration/horizon_policies.py

LAB008 plugin — per-horizon PIT-safe historical registry builder + simulator.

DESIGN
------
- LAB008 does NOT touch production `HOLD=63` in `india/recommendation_registry.py` or `rebal=63`
  in `india/recommendation_generator.py`. Each candidate horizon (21/42/63/84) builds its OWN
  in-memory registry using the same PIT-safe `champion_picks()` function that production uses.
- The simulator applies PRODUCTION dynamic exposure (`exp_series` from confidence_engine
  reconstruction) at each cycle's asof — identical construction to LAB007's N0.
- Cost at every rebalance boundary after the first: `cost_bps × current_val` (100% stock
  turnover, worst-case assumption). Plus the LAB007-style |Δexp| cost for exposure changes.
- Meta rows write `regime_signal` = PIT production exp at asof; runner assigns regime bucket
  from that key via YAML `regimes.metric_key: regime_signal`.

PIT SAFETY
----------
1. Selection uses only `rets.loc[:asof].tail(LOOKBACK)` — trailing.
2. Regime signal uses the LAB007 exp_series (rolling quantile, ffill) — trailing.
3. Forward closes at `asof + horizon` are used ONLY for cycle scoring (exit price / cycle P&L),
   never for selection.
4. LOOKBACK=120 is independent of the candidate horizon → no horizon-induced look-ahead.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from india.feature_engine import load_panels
from india.recommendation_registry import champion_picks


# ================== SHARED CONTEXT ==================

def build_context(rolling_min_periods: int) -> dict:
    """Load panels + production exp_series ONCE. Cache per-horizon registries here."""
    if not isinstance(rolling_min_periods, int) or rolling_min_periods <= 0:
        raise ValueError("rolling_min_periods must be a positive int (from config)")
    closes, _, _, _, idx, vix, _ = load_panels()
    rets = closes.pct_change()

    # Reconstruct PIT production exp_series (identical formula to LAB007's N0)
    scale = pd.Series(1.0, index=closes.index)
    if vix is not None:
        q80 = vix.rolling(120, min_periods=rolling_min_periods).quantile(0.80)
        hi = (vix > q80).reindex(closes.index).fillna(False)
        scale *= hi.map({True: 0.6, False: 1.0})
    below = (idx < idx.rolling(200).mean()).reindex(closes.index).fillna(False)
    scale *= below.map({True: 0.6, False: 1.0})
    try:
        from india.global_risk import global_exposure
        g = global_exposure()
        if g is not None:
            scale *= g.reindex(closes.index).ffill().fillna(1.0)
    except Exception:
        pass

    return {
        "closes": closes,
        "rets": rets,
        "exp_series": scale,
        "registry_cache": {},          # {horizon_days: DataFrame}
    }


# ================== PER-HORIZON REGISTRY BUILDER (PIT-safe) ==================

_REG_COLS = [
    "fingerprint", "rec_id", "asof", "strategy_version", "universe", "horizon_d",
    "symbol", "weight", "buy_price", "mature_date", "exit_price", "actual_ret",
    "holding_days", "holding_months", "rank", "universe_n", "hit_top25", "regime",
    "scored", "source",
]


def _build_registry_for_horizon(horizon_days: int, closes: pd.DataFrame,
                                 rets: pd.DataFrame) -> pd.DataFrame:
    """Build a per-horizon PIT-safe historical registry entirely in memory.

    Mirrors `recommendation_registry.log_rec` semantics but does NOT touch disk. Iterates
    `closes.index[::horizon_days]` as cycle asofs, calls `champion_picks(closes, rets, asof)`
    (which uses ONLY trailing data), and scores the cycle at `mature = closes.index[i + horizon]`.

    Returns DataFrame with the same schema as data/aegis_registry.csv, sorted by asof.
    """
    if horizon_days <= 0:
        raise ValueError(f"horizon_days must be positive, got {horizon_days}")
    rows = []
    for i in range(0, len(closes.index), horizon_days):
        asof = closes.index[i]
        # Skip if we don't have enough forward bars to score at least once
        if i + horizon_days >= len(closes.index):
            continue
        mature = closes.index[i + horizon_days]

        picks = champion_picks(closes, rets, asof)          # PIT-safe (trailing LOOKBACK only)
        if not picks:
            continue

        # Forward return for scoring — PIT-neutral (post-selection maturity data)
        fwd = (closes.iloc[i + horizon_days] / closes.iloc[i] - 1).dropna()
        pct = fwd.rank(pct=True) if len(fwd) else pd.Series(dtype=float)
        N = len(fwd)

        rec_id = f"{asof.date()}_{horizon_days}"
        for j, (sym, w) in enumerate(picks.items()):
            if sym not in closes.columns:
                continue
            buy_px = float(closes.loc[asof, sym])
            exit_px = float(closes.iloc[i + horizon_days][sym]) if sym in closes.columns else np.nan
            actual_ret = round(100 * (exit_px / buy_px - 1), 4) if buy_px > 0 else np.nan
            rank = int((1 - pct[sym]) * N) + 1 if sym in pct.index else np.nan
            hit = int(pct[sym] >= 0.75) if sym in pct.index else np.nan
            rows.append({
                "fingerprint": f"LAB008-{horizon_days}-{asof.strftime('%Y%m%d')}-{j:04d}",
                "rec_id": rec_id, "asof": asof.date(),
                "strategy_version": f"LAB008-horizon={horizon_days}",
                "universe": "nifty200", "horizon_d": horizon_days,
                "symbol": sym, "weight": round(w, 6), "buy_price": round(buy_px, 2),
                "mature_date": mature.date(), "exit_price": round(exit_px, 2),
                "actual_ret": actual_ret,
                "holding_days": horizon_days, "holding_months": round(horizon_days / 21, 2),
                "rank": rank, "universe_n": N, "hit_top25": hit,
                "regime": "", "scored": 1, "source": "historical",
            })

    if not rows:
        raise RuntimeError(f"No cycles generated for horizon={horizon_days}. Check panel length + asof stride.")
    return pd.DataFrame(rows, columns=_REG_COLS).sort_values("asof").reset_index(drop=True)


# ================== POLICY BUILDER ==================

def build_horizon_policy(candidate_config: dict, context: dict) -> dict:
    """Returns policy input for the simulator: {horizon_days, registry_df, exp_series}."""
    horizon = int(candidate_config["horizon_days"])
    cache = context["registry_cache"]
    if horizon not in cache:
        cache[horizon] = _build_registry_for_horizon(horizon, context["closes"], context["rets"])
    return {
        "horizon_days": horizon,
        "registry_df": cache[horizon],
        "exp_series": context["exp_series"],
    }


# ================== SIMULATOR ==================

def simulate_horizon_cycle(policy_input, registry_df_unused, closes, *,
                            initial_capital: float, cash_return_annual: float,
                            cost_bps: float, trading_days_per_year: int) -> tuple[pd.Series, list]:
    """LAB008 simulator. Ignores `registry_df_unused` — uses `policy_input['registry_df']`
    (per-horizon in-memory registry).

    Applies production dynamic exposure at each cycle asof. Cost at each rebalance boundary
    after the first: `cost_bps × current_val × (1 + |Δexp|)` — combines 100% stock turnover
    (worst-case) with any exposure change between cycles.
    """
    if initial_capital <= 0:
        raise ValueError("initial_capital must be > 0")
    if trading_days_per_year <= 0:
        raise ValueError("trading_days_per_year must be > 0")
    if cost_bps < 0:
        raise ValueError("cost_bps must be >= 0")

    reg = policy_input["registry_df"]
    exp_series = policy_input["exp_series"]

    daily_cash_return = (1 + cash_return_annual) ** (1 / trading_days_per_year) - 1
    equity = pd.Series(dtype=float)
    metas = []
    current_val = float(initial_capital)
    prev_exp = None

    for rec_id, grp in reg.groupby("rec_id", sort=False):
        asof = pd.Timestamp(grp["asof"].iloc[0])
        mature = pd.Timestamp(grp["mature_date"].iloc[0])
        exp_at_asof = float(exp_series.reindex([asof], method="ffill").iloc[0])

        # Rebalance cost — combines stock turnover (100%) + exposure change
        if prev_exp is not None:
            delta_exp = abs(exp_at_asof - prev_exp)
            # Cost applies to: (a) all stock-side capital being churned (100% turnover), plus
            # (b) any change in exposure (which moves capital between stocks and cash).
            # Model: cost = cost_bps * current_val * (1 + delta_exp). At delta_exp=0, still 100%
            # stock turnover; at delta_exp=1, both sides fully churn.
            transaction_cost = current_val * (1.0 + delta_exp) * (cost_bps / 10000.0)
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
            "horizon_days": int(policy_input["horizon_days"]),
            "exp": exp_at_asof,                    # exposure applied by simulator
            "regime_signal": exp_at_asof,          # what runner buckets on (config metric_key)
            "delta_exp": abs(exp_at_asof - (prev_exp if prev_exp is not None else exp_at_asof)),
            "stock_ret_pct": stock_ret_pct,
            "cash_ret_pct": cash_ret_pct,
            "cycle_ret_pct": cycle_ret_pct,
        })
        current_val = cycle_end_val
        prev_exp = exp_at_asof

    return equity.sort_index(), metas
