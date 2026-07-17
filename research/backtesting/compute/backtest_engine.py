"""DEV021 walk-forward backtest engine.

For each rebalance date:
  1. Load PIT price series for each ticker
  2. Score each ticker (point-in-time — NO look-ahead)
  3. Build portfolio per strategy
  4. Hold until next rebalance
  5. Compute realised return
  6. Rebalance

Aggregates a daily equity curve, per-trade P&L, sector-level attribution,
regime-conditional stats, and failure logs.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from backtesting.lib.pit_scorer import score_ticker_at                              # noqa: E402
from backtesting.lib.strategies import STRATEGIES, Portfolio                          # noqa: E402
from backtesting.lib import metrics                                                    # noqa: E402
from company_intelligence.lib import company_catalog                                   # noqa: E402


CONSTITUENT_PARQ_DIR = _ROOT / "data" / "raw" / "india"
RAW_MI_DIR = _ROOT / "data" / "market_intelligence" / "raw"


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


# ── Data loading (all PIT-safe: slice on read; never fetch newer bars) ───────

def load_all_universe() -> dict[str, pd.DataFrame]:
    """Load every AEGIS company parquet keyed by ticker."""
    out: dict[str, pd.DataFrame] = {}
    for c in company_catalog.COMPANIES:
        if not c.parquet_path.exists():
            continue
        try:
            df = pd.read_parquet(c.parquet_path)
            if df.empty or "close" not in df.columns:
                continue
            df.attrs["ticker"] = c.ticker
            out[c.ticker] = df
        except Exception:
            continue
    return out


def load_nifty_series() -> pd.Series:
    """Nifty 50 from the shared raw store (DEV017 fetched it)."""
    frames = []
    if not RAW_MI_DIR.exists():
        return pd.Series(dtype=float)
    for partition in sorted(RAW_MI_DIR.glob("*/")):
        for f in partition.glob("*.parquet"):
            try:
                frames.append(pd.read_parquet(f))
            except Exception:
                continue
    if not frames:
        return pd.Series(dtype=float)
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["checksum"], keep="last")
    df = df[df["variable_key"] == "equity_index.india.nifty50.close"]
    if df.empty:
        return pd.Series(dtype=float)
    df["asof_utc"] = pd.to_datetime(df["asof_utc"])
    df = df.sort_values("asof_utc")
    return pd.Series(df["value"].values.astype(float),
                      index=df["asof_utc"].values, name="nifty50")


# ── Rebalance-date generation ────────────────────────────────────────────────

def month_ends(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    """Business-month-end rebalance dates."""
    dates = pd.date_range(start, end, freq="BME")                        # business month-end
    return [pd.Timestamp(d) for d in dates]


# ── Portfolio return computation ─────────────────────────────────────────────

def portfolio_return_series(portfolio: Portfolio,
                              price_data: dict[str, pd.DataFrame],
                              start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Daily portfolio return from `start` to `end`, given a fixed-weight portfolio.

    Slippage-adjusted: 10 bps applied to each rebalance turnover (v0.1).
    """
    if not portfolio.weights or start >= end:
        return pd.Series(dtype=float)

    all_returns = []
    for ticker, weight in portfolio.weights.items():
        df = price_data.get(ticker)
        if df is None:
            continue
        window = df.loc[(df.index >= start) & (df.index <= end), "close"].dropna()
        if len(window) < 2:
            continue
        r = window.pct_change().dropna()
        weighted = r * weight
        all_returns.append(weighted)

    if not all_returns:
        return pd.Series(dtype=float)

    port_df = pd.concat(all_returns, axis=1).fillna(0.0)
    return port_df.sum(axis=1)


# ── Backtest loop ────────────────────────────────────────────────────────────

def run_backtest(
    strategies: dict[str, callable] | None = None,
    start_date: str = "2022-01-01",
    end_date: str = "2026-06-30",
    verbose: bool = True,
) -> dict:
    """Walk-forward backtest across all strategies. Monthly rebalance."""
    strategies = strategies or STRATEGIES

    if verbose:
        print(f"  loading universe...")
    price_data = load_all_universe()
    nifty = load_nifty_series()

    if verbose:
        print(f"  universe: {len(price_data)} tickers")
        print(f"  nifty history: {len(nifty)} bars "
                f"({nifty.index.min().date() if len(nifty) else 'n/a'} -> "
                f"{nifty.index.max().date() if len(nifty) else 'n/a'})")

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    rebal_dates = month_ends(start, end)
    if verbose:
        print(f"  rebalance dates: {len(rebal_dates)} months from {start.date()} to {end.date()}")

    # State per strategy
    strat_state: dict[str, dict] = {}
    for name in strategies:
        strat_state[name] = {
            "daily_returns": [],
            "trade_log": [],           # per-position (ticker, entry_dt, exit_dt, weight, ret)
            "rebal_log": [],           # per-rebal (dt, portfolio_size, avg_score, turnover)
            "prev_portfolio": None,
        }

    # Iterate over rebalance dates
    for i, rebal_dt in enumerate(rebal_dates):
        if i + 1 >= len(rebal_dates):
            break                                                        # need a next-date for the return window

        next_dt = rebal_dates[i + 1]

        # Score every ticker as of rebal_dt (PIT-safe)
        scored: list[tuple[str, float]] = []
        for ticker, df in price_data.items():
            ps = score_ticker_at(df, rebal_dt, nifty_series=nifty)
            if ps is not None:
                scored.append((ticker, ps.score))

        if not scored:
            if verbose and i % 6 == 0:
                print(f"    {rebal_dt.date()}: no scored tickers, skip")
            continue

        # For each strategy, build portfolio + measure return
        for name, strat_fn in strategies.items():
            state = strat_state[name]
            portfolio = strat_fn(scored)

            # Turnover computation
            prev = state["prev_portfolio"]
            turnover = 0.0
            if prev is not None:
                all_tks = set(prev.weights) | set(portfolio.weights)
                turnover = sum(abs(portfolio.weights.get(t, 0.0) - prev.weights.get(t, 0.0))
                                 for t in all_tks) / 2.0                       # standard turnover def

            # Realised returns over the holding period
            daily = portfolio_return_series(portfolio, price_data, rebal_dt, next_dt)
            # Apply slippage on turnover — 10 bps per unit turnover
            slippage = 0.0010 * turnover
            if not daily.empty:
                daily.iloc[0] -= slippage                                    # charge at rebalance day
            state["daily_returns"].append(daily)

            # Per-position trade log
            avg_score = np.mean([s for t, s in scored if t in portfolio.weights])
            state["rebal_log"].append({
                "rebal_date":    rebal_dt.strftime("%Y-%m-%d"),
                "next_date":     next_dt.strftime("%Y-%m-%d"),
                "n_positions":   len(portfolio.weights),
                "avg_score":     float(avg_score) if not np.isnan(avg_score) else None,
                "turnover":      float(turnover),
                "slippage_bps":  float(slippage * 10000),
            })

            for ticker, weight in portfolio.weights.items():
                df = price_data.get(ticker)
                if df is None:
                    continue
                w = df.loc[(df.index >= rebal_dt) & (df.index <= next_dt), "close"].dropna()
                if len(w) < 2:
                    continue
                trade_ret = float((w.iloc[-1] / w.iloc[0] - 1) * 100)
                state["trade_log"].append({
                    "rebal_date": rebal_dt.strftime("%Y-%m-%d"),
                    "next_date":  next_dt.strftime("%Y-%m-%d"),
                    "ticker":     ticker,
                    "weight":     weight,
                    "entry_px":   float(w.iloc[0]),
                    "exit_px":    float(w.iloc[-1]),
                    "return_pct": trade_ret,
                })

            state["prev_portfolio"] = portfolio

        if verbose and (i % 6 == 0 or i == len(rebal_dates) - 2):
            print(f"    {rebal_dt.date()}: scored={len(scored)}   "
                    f"first strat portfolio size={len(list(strategies.values())[0](scored).weights)}")

    # Concatenate daily returns per strategy, de-duplicating overlap dates.
    # Consecutive rebalance periods can share their endpoint (period[i].end ==
    # period[i+1].start), which produces a duplicate index. Keep the *first*
    # value at each date (the one from the earlier period, which represents
    # the actual daily return of the prior portfolio).
    for name in strategies:
        state = strat_state[name]
        if state["daily_returns"]:
            concat = pd.concat(state["daily_returns"]).sort_index()
            concat = concat[~concat.index.duplicated(keep="first")]
            state["daily_returns"] = concat
        else:
            state["daily_returns"] = pd.Series(dtype=float)

    return {
        "strat_state":  strat_state,
        "nifty_series": nifty,
        "rebal_dates":  [d.strftime("%Y-%m-%d") for d in rebal_dates],
        "universe_size": len(price_data),
        "code_sha":     _git_sha(),
        "run_utc":      datetime.now(timezone.utc).isoformat() + "Z",
    }
