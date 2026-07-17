"""DEV023 entry/exit level calculation from historical OHLCV.

For each recommended ticker:
  - Ideal entry zone (near 20-DMA)
  - Breakout entry (above recent high)
  - Pullback entry (near 50-DMA)
  - Support entry (near recent low + cushion)
  - Momentum entry (5% above current if strong)
  - Target 1 / Target 2 (volatility-scaled)
  - Stop loss (volatility-scaled, floored at -6%)
  - Trailing stop (below rolling high)
  - Expected + max holding periods
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class EntryExitLevels:
    latest_close: float
    ideal_entry_low: float
    ideal_entry_high: float
    breakout_entry: float
    pullback_entry: float | None
    support_entry: float | None
    momentum_entry: float
    target_1: float                            # conservative
    target_2: float                            # aggressive
    stop_loss: float
    stop_loss_pct: float                       # negative %
    trailing_stop_initial: float
    trailing_stop_pct: float
    expected_holding_days: int
    maximum_holding_days: int
    annualised_vol_pct: float


def compute(close: pd.Series,
             recommendation_type: str,
             base_stop_pct: float = 6.0,
             expected_hold_days: int = 60,
             max_hold_days: int = 90) -> EntryExitLevels | None:
    """Compute entry/exit levels for one ticker.

    `recommendation_type` biases risk parameters:
      - Strong-Buy / Buy    → wider targets, closer trailing
      - Accumulate          → moderate targets
      - Watchlist           → indicative levels only
    """
    close = close.dropna()
    if len(close) < 30:
        return None

    latest = float(close.iloc[-1])
    ma_20 = float(close.tail(20).mean()) if len(close) >= 20 else None
    ma_50 = float(close.tail(50).mean()) if len(close) >= 50 else None
    ma_200 = float(close.tail(200).mean()) if len(close) >= 200 else None

    # 20-day realised vol (annualised)
    r = close.pct_change().dropna().tail(20)
    if len(r) < 5:
        return None
    vol_20d_daily = float(r.std())
    vol_annual = vol_20d_daily * math.sqrt(252) * 100

    # 20-day range for support/resistance
    high_20 = float(close.tail(20).max())
    low_20 = float(close.tail(20).min())
    high_60 = float(close.tail(min(60, len(close))).max())

    # ── Entry levels ────────────────────────────────────────────────────────
    ideal_entry_center = ma_20 or latest
    ideal_low = ideal_entry_center * 0.985                                # -1.5%
    ideal_high = ideal_entry_center * 1.015                                # +1.5%

    breakout = high_20 * 1.005                                              # +0.5% above recent high
    pullback = ma_50 * 0.99 if ma_50 else None                              # 1% below 50-DMA
    support = low_20 * 1.02 if low_20 > 0 else None                         # +2% above recent low

    # Momentum entry: only meaningful if we're breaking out
    momentum = latest * 1.005 if latest >= high_20 * 0.98 else breakout

    # ── Targets ─────────────────────────────────────────────────────────────
    # Scale by 20d vol
    daily_move = vol_20d_daily * math.sqrt(20)                              # 20-trading-day sigma
    if recommendation_type in ("Strong-Buy", "Buy"):
        t1_pct = max(0.06, min(0.12, daily_move * 1.5))
        t2_pct = max(0.12, min(0.25, daily_move * 3.0))
    elif recommendation_type == "Accumulate":
        t1_pct = max(0.04, min(0.10, daily_move * 1.2))
        t2_pct = max(0.08, min(0.18, daily_move * 2.5))
    else:
        t1_pct = max(0.05, min(0.10, daily_move * 1.5))
        t2_pct = max(0.10, min(0.20, daily_move * 3.0))

    target_1 = latest * (1 + t1_pct)
    target_2 = latest * (1 + t2_pct)

    # ── Stop loss ───────────────────────────────────────────────────────────
    vol_scaled_stop_pct = max(base_stop_pct, min(10.0, daily_move * 100 * 1.2))
    stop_pct = -vol_scaled_stop_pct
    stop_price = latest * (1 + stop_pct / 100)

    # ── Trailing stop ───────────────────────────────────────────────────────
    trailing_pct = max(6.0, min(10.0, daily_move * 100 * 1.0))
    trailing_initial = latest * (1 - trailing_pct / 100)

    # ── Holding periods ─────────────────────────────────────────────────────
    if recommendation_type == "Strong-Buy":
        expected_hd = expected_hold_days
        max_hd = max_hold_days
    elif recommendation_type == "Buy":
        expected_hd = expected_hold_days
        max_hd = max_hold_days
    elif recommendation_type == "Accumulate":
        expected_hd = int(expected_hold_days * 1.5)
        max_hd = int(max_hold_days * 1.5)
    else:
        expected_hd = expected_hold_days
        max_hd = max_hold_days

    return EntryExitLevels(
        latest_close=round(latest, 2),
        ideal_entry_low=round(ideal_low, 2),
        ideal_entry_high=round(ideal_high, 2),
        breakout_entry=round(breakout, 2),
        pullback_entry=round(pullback, 2) if pullback else None,
        support_entry=round(support, 2) if support else None,
        momentum_entry=round(momentum, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        stop_loss=round(stop_price, 2),
        stop_loss_pct=round(stop_pct, 2),
        trailing_stop_initial=round(trailing_initial, 2),
        trailing_stop_pct=round(-trailing_pct, 2),
        expected_holding_days=expected_hd,
        maximum_holding_days=max_hd,
        annualised_vol_pct=round(vol_annual, 2),
    )
