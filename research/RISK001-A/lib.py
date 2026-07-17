"""RISK001-A shared library — loading, measurement, policies, simulation.

Research code only. NOT importable by production; lives under `research/`
by design so it can never accidentally be wired into the daily pipeline.

Reads (read-only):
  data/aegis_registry.csv
  data/raw/india/*.parquet

Writes:
  research/RISK001-A/outputs/*
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PARQ_DIR = ROOT / "data" / "raw" / "india"
REGISTRY = ROOT / "data" / "aegis_registry.csv"

# Slippage and cost assumptions applied identically to every policy.
SLIPPAGE_BPS = 5                                                       # 5 bps per side
BROKERAGE_BPS = 3                                                      # 3 bps per side
COST_ROUNDTRIP_BPS = 2 * (SLIPPAGE_BPS + BROKERAGE_BPS)                # 16 bps round-trip
COST_ROUNDTRIP_PCT_POINTS = COST_ROUNDTRIP_BPS * 0.01                  # 0.16 percentage points%


@dataclass
class Position:
    rec_id: str
    symbol: str
    entry_date: pd.Timestamp
    mature_date: pd.Timestamp
    entry_price: float
    mature_price: float
    baseline_return_pct: float
    weight: float
    regime: str
    path: pd.DataFrame            # daily OHLC over [entry_date, mature_date]

    @property
    def n_bars(self) -> int:
        return len(self.path)


# ─── LOADER ─────────────────────────────────────────────────────────────

def load_universe() -> list[Position]:
    """Load every scored=1 registry row and attach its OHLC path."""
    reg = pd.read_csv(REGISTRY)
    reg = reg[reg["scored"] == 1].copy()
    reg["asof"] = pd.to_datetime(reg["asof"])
    reg["mature_date"] = pd.to_datetime(reg["mature_date"])
    positions: list[Position] = []
    dropped: list[str] = []
    for _, row in reg.iterrows():
        pq = PARQ_DIR / f"{row['symbol']}_D1.parquet"
        if not pq.exists():
            dropped.append(f"{row['rec_id']} missing parquet {row['symbol']}")
            continue
        df = pd.read_parquet(pq)
        # Slice inclusive of entry and mature bars
        mask = (df.index >= row["asof"]) & (df.index <= row["mature_date"])
        path = df.loc[mask, ["open", "high", "low", "close"]].copy()
        if len(path) < 5:
            dropped.append(f"{row['rec_id']} thin path ({len(path)} bars)")
            continue
        positions.append(Position(
            rec_id=row["fingerprint"],       # unique per position (was: row["rec_id"] which is the cohort ID)
            symbol=row["symbol"],
            entry_date=row["asof"], mature_date=row["mature_date"],
            entry_price=float(row["buy_price"]),
            mature_price=float(row["exit_price"]),
            baseline_return_pct=float(row["actual_ret"]),
            weight=float(row["weight"]),
            regime=str(row["regime"]),
            path=path,
        ))
    # Sanity: rec_id must be unique across the universe (otherwise merge in report
    # cross-multiplies and produces nonsense counts).
    seen = {p.rec_id for p in positions}
    assert len(seen) == len(positions), (
        f"rec_id not unique: {len(positions)} positions, {len(seen)} unique ids")
    return positions, dropped


# ─── MEASUREMENT ─────────────────────────────────────────────────────────

def measure(p: Position) -> dict:
    """Path-level metrics for a single position."""
    if p.path.empty:
        return {}
    entry = p.entry_price
    highs = p.path["high"].values
    lows = p.path["low"].values
    closes = p.path["close"].values

    mfe_pct = float((highs.max() - entry) / entry * 100)
    mae_pct = float((lows.min() - entry) / entry * 100)

    # Time underwater = bars where close < entry
    underwater_bars = int(((closes < entry).sum()))
    # Max intraday drawdown from entry
    max_dd_from_entry_pct = float((lows.min() - entry) / entry * 100)

    # Recovery days after MAE bar (if underwater ever)
    if (lows < entry).any():
        mae_bar_idx = int(lows.argmin())
        rebound = closes[mae_bar_idx:]
        recovered_after = None
        for i, c in enumerate(rebound):
            if c >= entry:
                recovered_after = i
                break
        recovery_days = int(recovered_after) if recovered_after is not None else -1
    else:
        recovery_days = 0

    # Profit given back = MFE − final return
    profit_given_back_pct = float(mfe_pct - p.baseline_return_pct)

    return {
        "rec_id": p.rec_id,
        "symbol": p.symbol,
        "sector_regime": p.regime,
        "entry_date": p.entry_date.strftime("%Y-%m-%d"),
        "mature_date": p.mature_date.strftime("%Y-%m-%d"),
        "entry_price": entry,
        "mature_price": p.mature_price,
        "n_bars": p.n_bars,
        "baseline_return_pct": p.baseline_return_pct,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "underwater_bars": underwater_bars,
        "max_dd_from_entry_pct": max_dd_from_entry_pct,
        "recovery_days_after_mae": recovery_days,
        "profit_given_back_pct": profit_given_back_pct,
    }


def compute_entry_atr(p: Position, window: int = 20) -> float:
    """20-day ATR observed at the bar immediately BEFORE entry_date.

    No look-ahead: uses parquet bars up to (but not including) entry."""
    pq = PARQ_DIR / f"{p.symbol}_D1.parquet"
    df = pd.read_parquet(pq)
    hist = df.loc[df.index < p.entry_date].tail(window + 1)
    if len(hist) < window:
        # fallback: use first `window` bars of the position path itself as a rough estimate
        hist = p.path.head(window)
    high = hist["high"].values
    low = hist["low"].values
    close = hist["close"].values
    tr = np.maximum(high[1:] - low[1:],
                     np.maximum(np.abs(high[1:] - close[:-1]),
                                 np.abs(low[1:] - close[:-1])))
    return float(tr[-window:].mean()) if len(tr) else float(high.max() - low.min()) / max(1, len(hist))


# ─── POLICIES ─────────────────────────────────────────────────────────────

# Policy signature:
#   (position, atr_at_entry) -> (sim_exit_bar_idx, sim_exit_price)
# sim_exit_bar_idx=-1 means "held to maturity" (natural exit at mature_price).


def policy_A_baseline(p: Position, atr: float) -> tuple[int, float]:
    """Policy A — Current production behaviour: hold to mature_date, no stop."""
    return (-1, p.mature_price)


def _apply_fixed_stop(p: Position, stop_pct: float) -> tuple[int, float]:
    """Shared helper for fixed hard-stop policies (B, C).

    If any bar's low crosses the stop, exit at max(open_next, stop) — i.e. use
    the next-bar open if it gapped through, otherwise the stop price itself.
    """
    stop = p.entry_price * (1.0 - stop_pct)
    lows = p.path["low"].values
    opens = p.path["open"].values
    closes = p.path["close"].values
    for i, low in enumerate(lows):
        if low <= stop:
            # Same-bar close is our best available proxy for a triggered stop-loss fill
            # We use min(open, stop) if the bar opened below the stop (gap-down),
            # else stop itself.
            if opens[i] <= stop:
                # Gap-down: fill at open
                exit_px = float(opens[i])
            else:
                # Intraday breach: fill at stop
                exit_px = float(stop)
            return (i, exit_px)
    return (-1, p.mature_price)


def policy_B_hard5(p: Position, atr: float) -> tuple[int, float]:
    return _apply_fixed_stop(p, 0.05)


def policy_C_hard7(p: Position, atr: float) -> tuple[int, float]:
    return _apply_fixed_stop(p, 0.07)


def policy_D_atr(p: Position, atr: float) -> tuple[int, float]:
    """2 × ATR stop below entry. ATR-aware, no fixed threshold."""
    if atr <= 0 or math.isnan(atr):
        return policy_B_hard5(p, atr)  # fallback if ATR is degenerate
    stop = p.entry_price - 2 * atr
    # Bound: stop must be less than entry, else the position is exited immediately (never happens)
    if stop >= p.entry_price:
        stop = p.entry_price * 0.95
    stop_pct = 1.0 - stop / p.entry_price
    return _apply_fixed_stop(p, stop_pct)


def policy_E_trailing(p: Position, atr: float) -> tuple[int, float]:
    """Initial 6% stop; once high ≥ entry × 1.03, trail 3% below running high."""
    initial_stop = p.entry_price * 0.94
    trail_activation = p.entry_price * 1.03
    trail_pct = 0.03
    highs = p.path["high"].values
    lows = p.path["low"].values
    opens = p.path["open"].values
    running_high = p.entry_price
    activated = False
    for i in range(len(highs)):
        running_high = max(running_high, highs[i])
        if not activated and running_high >= trail_activation:
            activated = True
        stop = running_high * (1 - trail_pct) if activated else initial_stop
        if lows[i] <= stop:
            exit_px = float(opens[i]) if opens[i] <= stop else float(stop)
            return (i, exit_px)
    return (-1, p.mature_price)


def policy_F_breakeven(p: Position, atr: float) -> tuple[int, float]:
    """No stop for first 5 bars; then if close < entry, exit next-bar open."""
    closes = p.path["close"].values
    opens = p.path["open"].values
    for i in range(5, len(closes)):
        if closes[i] < p.entry_price:
            j = min(i + 1, len(opens) - 1)
            return (j, float(opens[j]))
    return (-1, p.mature_price)


POLICIES: dict[str, tuple[str, Callable]] = {
    "A_baseline":  ("Current production (no stop)",   policy_A_baseline),
    "B_hard5":     ("5% hard stop",                    policy_B_hard5),
    "C_hard7":     ("7% hard stop",                    policy_C_hard7),
    "D_atr":       ("2×ATR stop",                      policy_D_atr),
    "E_trailing":  ("Trailing stop (6%/3%)",           policy_E_trailing),
    "F_breakeven": ("Break-even after day 5",          policy_F_breakeven),
}


# ─── SIMULATION ─────────────────────────────────────────────────────────

def simulate_policy(positions: list[Position], policy_name: str) -> pd.DataFrame:
    """Apply one policy to every position; return one row per position."""
    _, fn = POLICIES[policy_name]
    rows = []
    for p in positions:
        atr = compute_entry_atr(p, window=20) if policy_name == "D_atr" else 0.0
        bar_idx, exit_px = fn(p, atr)
        if bar_idx == -1:
            sim_exit_date = p.mature_date
            sim_holding_days = 63
            reason = "MATURED"
        else:
            sim_exit_date = p.path.index[bar_idx]
            sim_holding_days = bar_idx + 1
            reason = "STOP_TRIGGERED"
        raw_ret = (exit_px - p.entry_price) / p.entry_price * 100
        net_ret = raw_ret - COST_ROUNDTRIP_PCT_POINTS
        rows.append({
            "rec_id": p.rec_id,
            "symbol": p.symbol,
            "entry_date": p.entry_date.strftime("%Y-%m-%d"),
            "policy": policy_name,
            "sim_exit_date": pd.Timestamp(sim_exit_date).strftime("%Y-%m-%d"),
            "sim_holding_days": sim_holding_days,
            "sim_exit_reason": reason,
            "sim_exit_price": exit_px,
            "sim_return_pct_gross": raw_ret,
            "sim_return_pct_net": net_ret,
            "baseline_return_pct": p.baseline_return_pct,
            "weight": p.weight,
        })
    return pd.DataFrame(rows)


# ─── PORTFOLIO METRICS ─────────────────────────────────────────────────────

def build_equity_curve(sim: pd.DataFrame) -> pd.DataFrame:
    """Equal-weighted equity curve. Each of N positions contributes 1/N of its
    net return, realised on its sim_exit_date. Portfolio starts at 100."""
    N = len(sim)
    if N == 0:
        return pd.DataFrame()
    df = sim.copy()
    df["sim_exit_date"] = pd.to_datetime(df["sim_exit_date"])
    df["contribution_pct"] = df["sim_return_pct_net"] / N
    daily = df.groupby("sim_exit_date")["contribution_pct"].sum()
    idx = pd.date_range(df["sim_exit_date"].min(), df["sim_exit_date"].max(), freq="D")
    daily = daily.reindex(idx, fill_value=0.0)
    cumulative = 100.0 + daily.cumsum()
    running_peak = cumulative.cummax()
    drawdown_pct = (cumulative / running_peak - 1) * 100
    return pd.DataFrame({
        "date": idx,
        "daily_pnl_pct": daily.values,
        "equity": cumulative.values,
        "drawdown_pct": drawdown_pct.values,
    })


def portfolio_metrics(sim: pd.DataFrame) -> dict:
    """The 11 portfolio-level metrics defined in RISK001-A §7."""
    if sim.empty:
        return {}
    r = sim["sim_return_pct_net"].values
    N = len(r)
    win_rate = float((r > 0).mean() * 100)
    avg_ret = float(r.mean())
    med_ret = float(np.median(r))
    largest_loss = float(r.min())
    largest_gain = float(r.max())
    gains = r[r > 0].sum()
    losses = abs(r[r < 0].sum())
    profit_factor = float(gains / losses) if losses > 0 else float("inf")
    # Sharpe (position-level): annualised assuming avg holding period
    avg_hold = float(sim["sim_holding_days"].mean())
    if r.std() > 0 and avg_hold > 0:
        sharpe = float(r.mean() / r.std() * math.sqrt(252 / avg_hold))
    else:
        sharpe = float("nan")
    eq = build_equity_curve(sim)
    max_dd = float(eq["drawdown_pct"].min()) if not eq.empty else float("nan")
    ulcer = float(math.sqrt((eq["drawdown_pct"] ** 2).mean())) if not eq.empty else float("nan")

    # Turnover: total positions / avg_positions_live per year
    if avg_hold > 0:
        turnover_annual = float(N / (max(1, (sim["sim_exit_date"].nunique()) / 252)) * (avg_hold / 63))
    else:
        turnover_annual = float("nan")

    # Loss-bucket counts (extra deliverable per prompt)
    losses10 = int((r <= -10).sum())
    losses15 = int((r <= -15).sum())
    losses20 = int((r <= -20).sum())

    return {
        "N": N,
        "win_rate_pct": win_rate,
        "avg_return_pct": avg_ret,
        "median_return_pct": med_ret,
        "profit_factor": profit_factor,
        "sharpe_ann": sharpe,
        "max_drawdown_pct": max_dd,
        "avg_holding_days": avg_hold,
        "largest_loss_pct": largest_loss,
        "largest_gain_pct": largest_gain,
        "turnover_proxy_per_yr": turnover_annual,
        "ulcer_index_pct": ulcer,
        "losses_lte_-10pct": losses10,
        "losses_lte_-15pct": losses15,
        "losses_lte_-20pct": losses20,
    }


# ─── COMPARE TO BASELINE ─────────────────────────────────────────────────

def counterfactual_diff(sim_A: pd.DataFrame, sim_X: pd.DataFrame) -> dict:
    """How many winners became losers, how many bad losses disappeared."""
    merged = sim_A[["rec_id", "sim_return_pct_net"]].merge(
        sim_X[["rec_id", "sim_return_pct_net"]],
        on="rec_id", suffixes=("_A", "_X"))
    ret_A = merged["sim_return_pct_net_A"]
    ret_X = merged["sim_return_pct_net_X"]
    winners_became_losers = int(((ret_A > 0) & (ret_X < 0)).sum())
    losers_became_winners = int(((ret_A < 0) & (ret_X > 0)).sum())
    losses10_A_gone = int(((ret_A <= -10) & (ret_X > -10)).sum())
    losses15_A_gone = int(((ret_A <= -15) & (ret_X > -15)).sum())
    losses20_A_gone = int(((ret_A <= -20) & (ret_X > -20)).sum())
    return {
        "winners_became_losers": winners_became_losers,
        "losers_became_winners": losers_became_winners,
        "losses10pct_prevented": losses10_A_gone,
        "losses15pct_prevented": losses15_A_gone,
        "losses20pct_prevented": losses20_A_gone,
    }


def paired_delta_ci(a: np.ndarray, b: np.ndarray, iters: int = 10000, seed: int = 20260717) -> tuple[float, float, float]:
    """Bootstrap 95% CI on mean(b - a)."""
    rng = np.random.default_rng(seed)
    diff = b - a
    if len(diff) == 0:
        return (float("nan"), float("nan"), float("nan"))
    mean_diff = float(diff.mean())
    idx = np.arange(len(diff))
    samples = np.array([diff[rng.choice(idx, len(idx), replace=True)].mean() for _ in range(iters)])
    lo, hi = float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))
    return (mean_diff, lo, hi)
