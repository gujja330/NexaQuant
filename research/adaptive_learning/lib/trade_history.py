"""DEV025 trade history reconstruction.

DEV021 already runs a walk-forward backtest but only publishes aggregate stats.
For learning, we need per-trade rows with (ticker, entry_date, exit_date,
score_at_entry, confidence, sector, industry, return_pct, hit_target, hit_stop).

This module re-runs the walk-forward loop with point-in-time scoring and
emits a per-trade dataframe for statistical analysis.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from backtesting.compute.backtest_engine import (                                    # noqa: E402
    load_all_universe, load_nifty_series, month_ends,
)
from backtesting.lib.pit_scorer import score_ticker_at                                # noqa: E402
from company_intelligence.lib import company_catalog                                    # noqa: E402


def _sector_industry_lookup(ticker: str) -> tuple[str, str]:
    try:
        c = company_catalog.by_ticker(ticker)
        return c.parent_sector_display, c.industry_display
    except KeyError:
        return "Unknown", "Unknown"


def build_trade_history(top_n: int = 20,
                          start_date: str = "2022-01-01",
                          end_date: str = "2026-06-30",
                          verbose: bool = True) -> pd.DataFrame:
    """Walk-forward: at each month-end, pick top-N by PIT score, record next-month return."""
    price_data = load_all_universe()
    nifty = load_nifty_series()
    if verbose:
        print(f"  loaded {len(price_data)} tickers")

    rebal_dates = month_ends(pd.Timestamp(start_date), pd.Timestamp(end_date))
    if verbose:
        print(f"  rebalance dates: {len(rebal_dates)}")

    trades = []
    for i, rebal_dt in enumerate(rebal_dates):
        if i + 1 >= len(rebal_dates):
            break
        next_dt = rebal_dates[i + 1]

        scored = []
        for ticker, df in price_data.items():
            ps = score_ticker_at(df, rebal_dt, nifty_series=nifty)
            if ps is not None:
                scored.append((ticker, ps.score, ps.confidence, ps.dimension_values))

        if not scored:
            continue

        # Take top-N by score
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:top_n]

        for ticker, score, conf, dims in top:
            df = price_data.get(ticker)
            if df is None:
                continue
            window = df.loc[(df.index >= rebal_dt) & (df.index <= next_dt), "close"].dropna()
            if len(window) < 2:
                continue
            entry_px = float(window.iloc[0])
            exit_px = float(window.iloc[-1])
            ret_pct = (exit_px / entry_px - 1) * 100

            # Path metrics
            path_min = float(window.min())
            path_max = float(window.max())
            max_favourable = (path_max / entry_px - 1) * 100
            max_adverse = (path_min / entry_px - 1) * 100

            # Classify win/loss
            hit_5pct_target = max_favourable >= 5.0
            hit_10pct_target = max_favourable >= 10.0
            hit_5pct_stop = max_adverse <= -5.0
            hit_10pct_stop = max_adverse <= -10.0

            sec, ind = _sector_industry_lookup(ticker)

            trades.append({
                "entry_date":     rebal_dt.strftime("%Y-%m-%d"),
                "exit_date":      next_dt.strftime("%Y-%m-%d"),
                "ticker":         ticker,
                "sector":         sec,
                "industry":       ind,
                "score_at_entry": round(float(score), 2),
                "confidence":     round(float(conf), 3),
                "entry_px":       round(entry_px, 2),
                "exit_px":        round(exit_px, 2),
                "return_pct":     round(ret_pct, 3),
                "mfe_pct":        round(max_favourable, 3),
                "mae_pct":        round(max_adverse, 3),
                "hit_5pct_target": hit_5pct_target,
                "hit_10pct_target": hit_10pct_target,
                "hit_5pct_stop":   hit_5pct_stop,
                "hit_10pct_stop":  hit_10pct_stop,
                "is_winner":      ret_pct > 0,
                "n_bars_held":    len(window) - 1,
                # dimension snapshots at entry
                "dim_momentum":       round(float(dims.get("momentum", 0)), 2)
                                        if "momentum" in dims else None,
                "dim_trend":          round(float(dims.get("trend", 0)), 2)
                                        if "trend" in dims else None,
                "dim_rs_nifty":       round(float(dims.get("rs_nifty", 0)), 2)
                                        if "rs_nifty" in dims else None,
                "dim_volatility":     round(float(dims.get("volatility", 0)), 2)
                                        if "volatility" in dims else None,
                "dim_drawdown":       round(float(dims.get("drawdown", 0)), 2)
                                        if "drawdown" in dims else None,
                "dim_position_52w":   round(float(dims.get("position_52w", 0)), 2)
                                        if "position_52w" in dims else None,
            })

        if verbose and i % 12 == 0:
            print(f"    {rebal_dt.date()}: {len(top)} trades recorded")

    df = pd.DataFrame(trades)
    if verbose:
        print(f"  total trades: {len(df)}")
    return df
