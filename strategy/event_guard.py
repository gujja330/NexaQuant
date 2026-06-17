# strategy/event_guard.py
"""
Event & volatility risk guard — "stay away from volatility" made concrete.

Three layers of protection (the research is clear: stops get blown during vol spikes,
and scheduled news is the most avoidable source of that):

  1. REALIZED-VOL SPIKE   : realized_vol_spike() — ATR_fast/ATR_slow above a threshold
                            (same signal the regime gate uses for the 'volatile' state)
  2. SCHEDULED-NEWS BLACKOUT : event_blackout() — no new entries within +/-window of a
                            HIGH-impact economic event (FOMC, CPI, NFP) from EVENTS.parquet
  3. EVENT-PROXIMITY FEATURE : event_proximity_feature() -> f_event_within_24h for the
                            meta-labeler (so the AI also LEARNS event risk, not just blocks it)

avoid_mask() = (1) OR (2): True where we should NOT open a new trade. Entries are ANDed
with ~avoid_mask in strategy/playbook.entries(avoid_volatility=True).
"""
from pathlib import Path
import numpy as np
import pandas as pd
from strategy.smc import atr

EVENTS = Path(__file__).resolve().parents[1] / "data" / "raw" / "EVENTS.parquet"


def realized_vol_spike(df, fast=14, slow=100, thresh=1.8):
    ratio = atr(df, fast) / atr(df, slow).replace(0, np.nan)
    return (ratio >= thresh).fillna(False)


def _load_events(min_impact="high"):
    """EVENTS.parquet: DatetimeIndex 'time' + column 'impact' in {low,medium,high}."""
    if not EVENTS.exists():
        return None
    ev = pd.read_parquet(EVENTS).sort_index()
    if "impact" in ev.columns and min_impact == "high":
        ev = ev[ev["impact"].str.lower() == "high"]
    return ev


def event_blackout(df, window_hours=12, min_impact="high"):
    """True for bars within +/- window_hours of a high-impact event (no new entries)."""
    ev = _load_events(min_impact)
    mask = pd.Series(False, index=df.index)
    if ev is None or ev.empty:
        return mask                      # no calendar -> no blackout (guard is a no-op)
    w = pd.Timedelta(hours=window_hours)
    et = ev.index.values
    times = df.index.values
    # vectorised: for each bar, is there an event within the window?
    for t0 in et:
        mask |= (df.index >= (pd.Timestamp(t0) - w)) & (df.index <= (pd.Timestamp(t0) + w))
    return mask


def event_proximity_feature(df, window_hours=24, min_impact="high"):
    """1.0 if a high-impact event is within +/- window (else 0) — feeds f_event_within_24h."""
    return event_blackout(df, window_hours, min_impact).astype(float)


def avoid_mask(df, vol_thresh=1.8, blackout_hours=12):
    """Bars where we should NOT open a new position: vol spike OR scheduled-news window."""
    return realized_vol_spike(df, thresh=vol_thresh) | event_blackout(df, blackout_hours)
