"""DEV022 historical stress-test replays.

For a candidate portfolio, replay actual constituent returns over historical
stress windows and report worst-day / worst-week / cumulative return / vol.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


# Historical stress windows for India equity markets. Where the window is
# before AEGIS parquet coverage, the test reports partial coverage transparently.
STRESS_WINDOWS = {
    "COVID_crash_2020":       ("2020-02-15", "2020-04-15",
                                "COVID pandemic crash, Feb-Apr 2020"),
    "Bear_2022_Q2Q3":         ("2022-04-01", "2022-10-15",
                                "2022 mid-year global bear market"),
    "Vol_spike_2025":         ("2025-01-01", "2025-03-31",
                                "Volatility spike Q1 2025"),
    "Rate_hike_2022_H1":      ("2022-01-01", "2022-06-30",
                                "Fed rate hike cycle H1 2022"),
    "Adani_shock_2023":       ("2023-01-24", "2023-03-15",
                                "Hindenburg Adani short-report shock"),
}


def stress_test_portfolio(weights: dict[str, float],
                            price_data: dict[str, pd.Series]) -> dict:
    """Replay portfolio through every historical stress window."""
    results = []

    for window_key, (start, end, description) in STRESS_WINDOWS.items():
        window_result = _replay_one(weights, price_data,
                                       pd.Timestamp(start), pd.Timestamp(end))
        window_result["window_key"] = window_key
        window_result["start_date"] = start
        window_result["end_date"] = end
        window_result["description"] = description
        results.append(window_result)

    return {"stress_windows": results}


def _replay_one(weights: dict[str, float], price_data: dict[str, pd.Series],
                 start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Compute portfolio behaviour over a single window."""
    daily_returns = []
    n_valid_tickers = 0

    for ticker, w in weights.items():
        series = price_data.get(ticker)
        if series is None:
            continue
        window = series.loc[(series.index >= start) & (series.index <= end)].dropna()
        if len(window) < 2:
            continue
        r = window.pct_change().dropna() * w
        daily_returns.append(r)
        n_valid_tickers += 1

    if not daily_returns:
        return {"status": "no_data_in_window",
                "n_valid_tickers": 0,
                "cumulative_return_pct": None,
                "max_drawdown_pct": None,
                "worst_day_pct": None,
                "annualised_vol_pct": None,
                "n_days_covered": 0}

    port_ret = pd.concat(daily_returns, axis=1).fillna(0.0).sum(axis=1)
    if port_ret.empty:
        return {"status": "empty_returns",
                "n_valid_tickers": n_valid_tickers,
                "cumulative_return_pct": None,
                "max_drawdown_pct": None,
                "worst_day_pct": None,
                "annualised_vol_pct": None,
                "n_days_covered": 0}

    cum_ret = float((1 + port_ret).prod() - 1) * 100
    equity = (1 + port_ret).cumprod()
    dd = float((equity / equity.cummax() - 1).min()) * 100
    worst_day = float(port_ret.min()) * 100
    vol = float(port_ret.std() * math.sqrt(252)) * 100 if len(port_ret) > 1 else None

    coverage_pct = n_valid_tickers / len(weights) * 100 if weights else 0.0

    return {
        "status":                   "computed",
        "n_valid_tickers":          n_valid_tickers,
        "n_expected_tickers":       len(weights),
        "coverage_pct":             round(coverage_pct, 1),
        "cumulative_return_pct":    round(cum_ret, 2),
        "max_drawdown_pct":         round(dd, 2),
        "worst_day_pct":            round(worst_day, 2),
        "annualised_vol_pct":       round(vol, 2) if vol is not None else None,
        "n_days_covered":           len(port_ret),
    }
