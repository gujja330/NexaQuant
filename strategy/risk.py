# strategy/risk.py
"""
Risk & position sizing -- ATR-based stops/targets and volatility-targeted sizing.

Why: our findings show profit comes from RISK CONTROL (cutting drawdown), not from
win rate. Two tools here:
  * vol_target_size() : scale position INVERSELY to volatility so each trade risks a
                        similar amount -- calm market = bigger size, wild market = smaller.
                        This is what halves drawdown vs a fixed-size long.
  * atr_stop_target() : ATR-based stop and take-profit levels for a given entry/side
                        (used when we move from positional backtests to trade-by-trade).
"""
import numpy as np
import pandas as pd


def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def vol_target_size(df, atr_n=14, ref_window=200, cap=3.0, floor=0.25):
    """Multiplier in [floor, cap]: typical_ATR / current_ATR (causal).
    >1 when calmer than usual, <1 when more volatile. Multiply onto a {-1,0,1} signal."""
    a = atr(df, atr_n)
    ref = a.rolling(ref_window, min_periods=atr_n).median()
    size = (ref / a).clip(floor, cap)
    return size.fillna(1.0)


def atr_stop_target(entry_price, side, atr_value, stop_mult=1.5, rr=2.0):
    """Return (stop, target) for a trade. side=+1 long, -1 short.
    rr = reward:risk multiple (target distance = rr * stop distance)."""
    risk = stop_mult * atr_value
    stop = entry_price - side * risk
    target = entry_price + side * rr * risk
    return stop, target


def kelly_fraction(win_rate, payoff, cap=0.5):
    """Fractional Kelly: f* = W - (1-W)/R, capped (never full Kelly -> too volatile)."""
    if payoff <= 0:
        return 0.0
    f = win_rate - (1 - win_rate) / payoff
    return float(np.clip(f, 0.0, cap))


def proba_to_size(proba, payoff=2.0, p_threshold=0.5, kelly_cap=0.5, max_mult=2.0):
    """Convert a CALIBRATED meta-label P(win) into a position-size multiplier — the
    bridge that lets the AI SIZE the rules edge (not just filter it).
      proba <= p_threshold  -> 0   (skip: no conviction)
      else                  -> fractional-Kelly(proba, payoff), scaled to [0, max_mult]
    Calibration matters: Kelly is only valid if P(win) is trustworthy (see calibrate=
    option in strategy/meta_label.make_model)."""
    proba = np.asarray(proba, dtype=float)
    f = np.clip(proba - (1 - proba) / payoff, 0.0, kelly_cap)   # vectorised Kelly
    size = (f / kelly_cap) * max_mult                            # 0..max_mult
    return np.where(proba <= p_threshold, 0.0, size)
