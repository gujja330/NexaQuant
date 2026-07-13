"""
india/ai_lab/LAB009_Horizon_Phase_Recalibration/horizon_phase_policies.py

LAB009 plugin — per-(horizon × phase) PIT-safe registries + realistic-turnover simulator
+ phase aggregator.

Design:
- For every candidate horizon H, we run 4 phase offsets {0, ⌊H/4⌋, ⌊H/2⌋, ⌊3H/4⌋}.
- Registry per (H, phase) is built in memory from `champion_picks()` at strided asofs.
- Simulator applies REALISTIC turnover cost (Formulation B EXTENDED — effective portfolio
  weights including cash bucket, one-sided cost basis, single term):

    turnover_t = 0.5 * ( Σ_{s ∈ Union} |eff_w_t(s) - eff_w_{t-1}(s)|  +  |Δexp| )
    cost_t     = current_val * turnover_t * cost_bps * 1e-4
    eff_w_t(s) = exp_t * normalized_stock_weight_t(s)

- Applies production dynamic exposure at each cycle asof (same PIT construction as LAB007 N0).
- Common evaluation window derived from scorable-cycle boundaries ACROSS ALL 16 configs.
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


# =============== SHARED CONTEXT ===============

def build_context(rolling_min_periods: int) -> dict:
    if not isinstance(rolling_min_periods, int) or rolling_min_periods <= 0:
        raise ValueError("rolling_min_periods must be a positive int (from config)")
    closes, _, _, _, idx, vix, _ = load_panels()
    rets = closes.pct_change()

    # PIT production exp_series — identical construction to LAB007 N0 / LAB008
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

    return {"closes": closes, "rets": rets, "exp_series": scale}


def phase_offsets_for(horizon_days: int) -> list[int]:
    """Deterministic 4-phase offsets per horizon: [0, ⌊H/4⌋, ⌊H/2⌋, ⌊3H/4⌋]."""
    return [0, horizon_days // 4, horizon_days // 2, (3 * horizon_days) // 4]


# =============== PER-(HORIZON, PHASE) REGISTRY BUILDER ===============

_REG_COLS = [
    "fingerprint", "rec_id", "asof", "strategy_version", "universe", "horizon_d",
    "symbol", "weight", "buy_price", "mature_date", "exit_price", "actual_ret",
    "holding_days", "scored", "source", "phase_offset",
]


def build_registry_for_horizon_phase(horizon_days: int, phase_offset: int,
                                      closes: pd.DataFrame, rets: pd.DataFrame) -> pd.DataFrame:
    """Build a PIT-safe registry at (horizon, phase). Cycles strided by horizon_days starting at
    index `phase_offset` in closes.index. Only cycles with a scorable forward return are kept."""
    if horizon_days <= 0:
        raise ValueError("horizon_days must be > 0")
    if not (0 <= phase_offset < horizon_days):
        raise ValueError(f"phase_offset {phase_offset} must be in [0, {horizon_days})")

    rows = []
    for i in range(phase_offset, len(closes.index), horizon_days):
        if i + horizon_days >= len(closes.index):
            continue
        asof = closes.index[i]
        mature = closes.index[i + horizon_days]

        picks = champion_picks(closes, rets, asof)          # PIT: uses only trailing LOOKBACK
        if not picks:
            continue

        rec_id = f"H{horizon_days}_P{phase_offset:02d}_{asof.date()}"
        for j, (sym, w) in enumerate(picks.items()):
            if sym not in closes.columns:
                continue
            buy_px = float(closes.loc[asof, sym])
            exit_px = float(closes.iloc[i + horizon_days][sym])
            actual_ret = round(100 * (exit_px / buy_px - 1), 4) if buy_px > 0 else np.nan
            rows.append({
                "fingerprint": f"LAB009-H{horizon_days}-P{phase_offset:02d}-{asof.strftime('%Y%m%d')}-{j:04d}",
                "rec_id": rec_id, "asof": asof.date(),
                "strategy_version": f"LAB009-H{horizon_days}-P{phase_offset:02d}",
                "universe": "nifty200", "horizon_d": horizon_days, "phase_offset": phase_offset,
                "symbol": sym, "weight": round(w, 6), "buy_price": round(buy_px, 4),
                "mature_date": mature.date(), "exit_price": round(exit_px, 4),
                "actual_ret": actual_ret,
                "holding_days": horizon_days,
                "scored": 1, "source": "historical",
            })
    if not rows:
        raise RuntimeError(f"No cycles generated for horizon={horizon_days}, phase={phase_offset}")
    return pd.DataFrame(rows, columns=_REG_COLS).sort_values("asof").reset_index(drop=True)


# =============== SIMULATOR — REALISTIC TURNOVER COST ===============

def simulate_horizon_phase(reg_df: pd.DataFrame, closes: pd.DataFrame, exp_series: pd.Series,
                            common_start_asof, common_end_asof, *,
                            initial_capital: float, cash_return_annual: float,
                            cost_bps: float, trading_days_per_year: int) -> tuple[pd.Series, list]:
    """One horizon × phase run under realistic turnover cost model B-EXTENDED.

    Cost per transition (i.e., at each cycle asof after the first):
        eff_w_t(s)     = exp_t * normalized_stock_weight_t(s)
        stock_side_t   = Σ_{s in Union(t-1, t)} |eff_w_t(s) - eff_w_{t-1}(s)|
        cash_side_t    = |exp_t - exp_{t-1}|
        turnover_t     = 0.5 * (stock_side_t + cash_side_t)
        cost_t         = current_val * turnover_t * cost_bps * 1e-4

    ONLY cycles whose asof is within [common_start_asof, common_end_asof] contribute to the
    returned equity curve and meta (i.e. common evaluation window applied here)."""
    if initial_capital <= 0:
        raise ValueError("initial_capital must be > 0")
    if trading_days_per_year <= 0:
        raise ValueError("trading_days_per_year must be > 0")
    if cost_bps < 0:
        raise ValueError("cost_bps must be >= 0")

    reg_df = reg_df.copy()
    reg_df["asof"] = pd.to_datetime(reg_df["asof"]).dt.normalize()
    reg_df["mature_date"] = pd.to_datetime(reg_df["mature_date"]).dt.normalize()
    common_start = pd.Timestamp(common_start_asof).normalize()
    common_end = pd.Timestamp(common_end_asof).normalize()
    # CORRECTED (LAB009 maturity-boundary audit): filter on BOTH asof >= common_start AND
    # mature_date <= common_end. Ensures realized returns lie within the declared window.
    reg_df = reg_df[(reg_df["asof"] >= common_start) & (reg_df["mature_date"] <= common_end)]
    # Hard assertion — no included cycle may mature past common_end.
    assert (reg_df["mature_date"] <= common_end).all(), (
        f"included cycle has mature_date > common_end ({common_end}); "
        f"filter breach on {reg_df[reg_df['mature_date'] > common_end][['rec_id','asof','mature_date']].to_dict('records')}")

    daily_cash_return = (1 + cash_return_annual) ** (1 / trading_days_per_year) - 1
    equity = pd.Series(dtype=float)
    metas = []
    current_val = float(initial_capital)
    prev_eff_w: dict[str, float] | None = None       # {sym: exp * w_norm}
    prev_exp: float | None = None

    for rec_id, grp in reg_df.groupby("rec_id", sort=False):
        asof = pd.Timestamp(grp["asof"].iloc[0])
        mature = pd.Timestamp(grp["mature_date"].iloc[0])
        exp_at_asof = float(exp_series.reindex([asof], method="ffill").iloc[0])

        weights = pd.to_numeric(grp["weight"], errors="coerce").fillna(0.0)
        weights_norm = weights / weights.sum() if weights.sum() > 0 else weights
        stock_w_dict = dict(zip(grp["symbol"], weights_norm))
        eff_w_dict = {s: exp_at_asof * w for s, w in stock_w_dict.items()}

        # --- Realistic turnover cost (Formulation B EXTENDED) ---
        if prev_eff_w is not None:
            all_syms = set(prev_eff_w) | set(eff_w_dict)
            stock_side = sum(abs(eff_w_dict.get(s, 0.0) - prev_eff_w.get(s, 0.0)) for s in all_syms)
            cash_side = abs(exp_at_asof - (prev_exp if prev_exp is not None else exp_at_asof))
            turnover_t = 0.5 * (stock_side + cash_side)
            cost_t = current_val * turnover_t * (cost_bps / 10_000.0)
            current_val -= cost_t
        else:
            turnover_t = 0.0

        # --- In-cycle price path ---
        syms = [s for s in grp["symbol"] if s in closes.columns]
        wts = pd.Series(stock_w_dict).reindex(syms).fillna(0.0)
        wts = wts / wts.sum() if wts.sum() > 0 else wts
        prices = closes[syms].loc[asof:mature].dropna(how="all")
        if len(prices) < 2 or wts.sum() == 0:
            prev_eff_w = eff_w_dict
            prev_exp = exp_at_asof
            continue
        norm = prices / prices.iloc[0]
        stock_curve = (norm * wts).sum(axis=1)
        n_bars = len(stock_curve)
        cash_curve = pd.Series(
            [(1 + daily_cash_return) ** i for i in range(n_bars)], index=stock_curve.index,
        )
        combined = exp_at_asof * stock_curve + (1 - exp_at_asof) * cash_curve
        cycle_equity = combined * current_val

        if not equity.empty:
            cycle_equity = cycle_equity[cycle_equity.index > equity.index[-1]]
        equity = pd.concat([equity, cycle_equity])
        cycle_end_val = float(cycle_equity.iloc[-1]) if not cycle_equity.empty else current_val

        metas.append({
            "rec_id": rec_id, "asof": asof, "mature": mature,
            "horizon_days": int(grp["horizon_d"].iloc[0]),
            "phase_offset": int(grp["phase_offset"].iloc[0]),
            "exp": exp_at_asof, "regime_signal": exp_at_asof,
            "turnover_t": turnover_t,
            "cycle_ret_pct": 100 * (cycle_end_val / current_val - 1) if current_val > 0 else 0.0,
        })
        current_val = cycle_end_val
        prev_eff_w = eff_w_dict
        prev_exp = exp_at_asof

    equity = equity.sort_index()
    # Hard assertion — no equity observation may exceed common_end.
    if len(equity):
        assert equity.index.max() <= common_end, (
            f"equity index max {equity.index.max()} > common_end {common_end}")
    return equity, metas


# =============== COMMON EVALUATION WINDOW ===============

def compute_common_window(all_registries: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    """all_registries: {(horizon, phase): registry_df}

    CORRECTED per LAB009_MATURITY_BOUNDARY_AUDIT.md (sealed 2026-07-13):

    - common_start = MAX over configs of each config's earliest scorable asof (unchanged).
    - common_end   = MIN over configs of each config's LATEST MATURE_DATE (was: last asof).

    The original asof-based common_end allowed cycles' realized-return paths to extend up
    to 122 days past the declared window end. Under the corrected rule, common_end is the
    latest maturity date that ALL configs can reach — ensuring realized returns don't
    escape the declared evaluation interval."""
    firsts, mature_lasts = [], []
    for (h, p), reg in all_registries.items():
        asofs = pd.to_datetime(reg["asof"])
        matures = pd.to_datetime(reg["mature_date"])
        firsts.append(asofs.min())
        mature_lasts.append(matures.max())
    common_start = pd.Timestamp(max(firsts)).normalize()
    common_end = pd.Timestamp(min(mature_lasts)).normalize()
    if common_start > common_end:
        raise RuntimeError(f"Empty common window: start={common_start}, end={common_end}")
    return common_start, common_end
