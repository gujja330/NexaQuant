"""Opening Range Breakout · operator's proven strategy #1.

Methodology (from operator's spec):
  · Take first 15 min of session (India 09:15-09:30) high + low as the range
  · LONG when a subsequent 5-min candle CLOSES decisively above range high
  · SHORT when a subsequent 5-min candle CLOSES below range low
  · Stop-Loss = midpoint of the 15-min opening range
  · Only fires during OPENING + HIGH_VOL slot (§operator's morning strategy)

Applies to India + USA identically (adjusted for session-open time).
"""
from __future__ import annotations

from datetime import datetime, timezone
from .base import SignalBase, SignalScore, register
from ..session_clock import SessionWindow, TradingSlot


@register
class OpeningRangeBreakout(SignalBase):
    signal_id      = "orb"
    display_name   = "Opening Range Breakout"
    active_slots   = [TradingSlot.HIGH_VOL, TradingSlot.STABLE_TREND]
    active_windows = [SessionWindow.OPENING, SessionWindow.MORNING]

    ORB_MINUTES = 15                # opening range = first 15 min
    BREAKOUT_BUFFER_PCT = 0.001     # 0.1% buffer above/below range for "decisive"

    def compute(self, bars, meta: dict) -> SignalScore | None:
        """bars: intraday DataFrame indexed by timestamp with OHLC.
        meta: {'ticker': str, 'market': str, 'session_open_ts': datetime, ...}
        """
        import pandas as pd
        if bars is None or len(bars) < 4:
            return None
        ticker = meta.get("ticker") or "?"
        market = meta.get("market") or "india"

        # Extract opening range · assume 5-min bars · first 3 bars = 15 min
        ordered = bars.sort_index()
        opening = ordered.head(3)
        if len(opening) < 3:
            return None
        orh = float(opening["high"].max())
        orl = float(opening["low"].min())
        orm = (orh + orl) / 2

        # Post-opening bars
        post = ordered.iloc[3:]
        if post.empty:
            return None

        for ts, bar in post.iterrows():
            close = float(bar["close"])
            if close > orh * (1 + self.BREAKOUT_BUFFER_PCT):
                # LONG breakout · stop at midpoint · T1/T2 by symmetric extension
                range_size = orh - orl
                return SignalScore(
                    signal_id=self.signal_id,
                    ticker=ticker,
                    direction="LONG",
                    score=+1.0 * min(1.0, (close - orh) / max(1e-9, range_size)),
                    entry=close,
                    stop=orm,
                    target_1=close + range_size,
                    target_2=close + 2 * range_size,
                    at_ts_utc=(ts.tz_convert("UTC") if ts.tzinfo else ts).isoformat()
                                if hasattr(ts, "tz_convert") else str(ts),
                    window=SessionWindow.OPENING.value,
                    slot=TradingSlot.HIGH_VOL.value,
                    reasoning=f"5-min close {close:.2f} broke opening-range-high {orh:.2f} decisively",
                    metadata={"orh": orh, "orl": orl, "orm": orm, "range_size": range_size},
                )
            if close < orl * (1 - self.BREAKOUT_BUFFER_PCT):
                range_size = orh - orl
                return SignalScore(
                    signal_id=self.signal_id,
                    ticker=ticker,
                    direction="SHORT",
                    score=-1.0 * min(1.0, (orl - close) / max(1e-9, range_size)),
                    entry=close,
                    stop=orm,
                    target_1=close - range_size,
                    target_2=close - 2 * range_size,
                    at_ts_utc=(ts.tz_convert("UTC") if ts.tzinfo else ts).isoformat()
                                if hasattr(ts, "tz_convert") else str(ts),
                    window=SessionWindow.OPENING.value,
                    slot=TradingSlot.HIGH_VOL.value,
                    reasoning=f"5-min close {close:.2f} broke opening-range-low {orl:.2f} decisively",
                    metadata={"orh": orh, "orl": orl, "orm": orm, "range_size": range_size},
                )
        return None
