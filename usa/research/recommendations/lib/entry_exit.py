"""AEGIS USA · Entry / Target / Stop level generator.

Computes the price levels every USA recommendation exposes. All in USD.
Deterministic: ATR-based sizing, no random state.
"""
from __future__ import annotations

import pandas as pd


def atr(close: pd.Series, window: int = 14) -> float | None:
    """Simplified ATR from daily close (true range approximated as
    abs day-over-day change since intraday high/low may not be loaded)."""
    if close is None or len(close) < window + 1: return None
    tr = close.diff().abs().tail(window)
    if tr.empty: return None
    return float(tr.mean())


def compute_levels(close: pd.Series, score: float | None,
                     action: str | None) -> dict:
    """Return entry_exit block matching India's schema shape.

    All in USD. Wider stop / target for lower-scored ideas (they need
    room to breathe); tighter for high-conviction ideas.
    """
    if close is None or close.empty:
        return {}

    latest = float(close.iloc[-1])
    atr14 = atr(close, 14) or (latest * 0.02)   # fallback: 2% of price

    # Level widths scale with ATR
    if score is None or score < 55:
        target_frac = 0.10; stop_frac = 0.08
    elif score < 70:
        target_frac = 0.10; stop_frac = 0.06
    elif score < 80:
        target_frac = 0.12; stop_frac = 0.05
    else:  # Strong-Buy
        target_frac = 0.14; stop_frac = 0.05

    # But cap by ATR — don't set targets tighter than 2×ATR or wider than 8×ATR
    atr_target_min = latest + 2 * atr14
    atr_target_max = latest + 8 * atr14
    target_1 = max(atr_target_min, min(atr_target_max, latest * (1 + target_frac)))
    target_2 = target_1 + (target_1 - latest) * 0.7      # secondary ~1.7x the first upside

    stop_loss = max(latest - 5 * atr14, latest * (1 - stop_frac))

    # Buy zone: current price ± 1.5% (tight; USA large-caps move less than India mid-caps)
    ideal_low  = latest * 0.985
    ideal_high = latest * 1.005

    # Annualised vol from 20 day pct_change (already available in tech dims;
    # we recompute here to keep this module pure)
    vol_pct = None
    if len(close) >= 21:
        vol_pct = float(close.pct_change().tail(20).std() * (252 ** 0.5) * 100)

    return {
        "latest_close":           round(latest, 2),
        "ideal_entry_low":        round(ideal_low, 2),
        "ideal_entry_high":       round(ideal_high, 2),
        "breakout_entry":         round(latest * 1.02, 2),
        "pullback_entry":         round(latest * 0.97, 2),
        "support_entry":          round(latest * 0.94, 2),
        "momentum_entry":         round(latest * 1.005, 2),
        "target_1":               round(target_1, 2),
        "target_2":               round(target_2, 2),
        "stop_loss":              round(stop_loss, 2),
        "stop_loss_pct":          round((stop_loss - latest) / latest * 100, 2),
        "trailing_stop_initial":  round(stop_loss * 1.02, 2),
        "trailing_stop_pct":      round((stop_loss * 1.02 - latest) / latest * 100, 2),
        "expected_holding_days":  45 if score and score >= 70 else 60,
        "maximum_holding_days":   90,
        "annualised_vol_pct":     round(vol_pct, 2) if vol_pct is not None else None,
        "atr_14":                 round(atr14, 2),
    }
