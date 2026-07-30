"""VWAP Pullback · operator's proven strategy #2.

Methodology (from operator's spec):
  · VWAP = volume-weighted average price · institutional true-price line
  · In uptrend, wait for pullback TO VWAP · buy on bounce
  · Stop-Loss just below VWAP line
  · Active in STABLE_TREND slot (10:15-14:30 IST) where institutional flow dominates
"""
from __future__ import annotations

from .base import SignalBase, SignalScore, register
from ..session_clock import SessionWindow, TradingSlot


@register
class VWAPPullback(SignalBase):
    signal_id      = "vwap_pullback"
    display_name   = "VWAP Pullback"
    active_slots   = [TradingSlot.STABLE_TREND]
    active_windows = [SessionWindow.MORNING, SessionWindow.MIDDAY,
                        SessionWindow.AFTERNOON]

    TOUCH_TOLERANCE_PCT = 0.002   # within 0.2% of VWAP counts as "touch"
    UPTREND_LOOKBACK    = 10       # bars to confirm uptrend
    UPTREND_MIN_PCT     = 0.005    # 0.5% up over lookback

    def compute(self, bars, meta: dict) -> SignalScore | None:
        if bars is None or len(bars) < self.UPTREND_LOOKBACK + 2:
            return None
        ticker = meta.get("ticker") or "?"
        try:
            ordered = bars.sort_index()
            # Session VWAP = cumulative(price × volume) / cumulative(volume)
            pv = ordered["close"] * ordered.get("volume", 1)
            vol = ordered.get("volume", 1)
            if hasattr(vol, "cumsum"):
                vwap = pv.cumsum() / vol.cumsum().replace(0, 1e-9)
            else:
                return None
            last = ordered.iloc[-1]
            prev = ordered.iloc[-2]
            last_vwap = float(vwap.iloc[-1])
            close = float(last["close"])
            prev_close = float(prev["close"])

            # Uptrend check
            lookback_start = float(ordered["close"].iloc[-self.UPTREND_LOOKBACK])
            trend = (close / lookback_start - 1) if lookback_start > 0 else 0
            if trend < self.UPTREND_MIN_PCT:
                return None

            # Touch + bounce: prev bar hit VWAP zone · current bounces up
            dist_prev = abs(prev_close - last_vwap) / last_vwap
            if dist_prev > self.TOUCH_TOLERANCE_PCT:
                return None
            if close <= prev_close:
                return None

            ts = ordered.index[-1]
            entry = close
            stop = last_vwap * 0.997        # just below VWAP
            t1 = entry * 1.007              # +0.7% typical intraday VWAP-bounce target
            t2 = entry * 1.014
            return SignalScore(
                signal_id=self.signal_id,
                ticker=ticker,
                direction="LONG",
                score=+min(1.0, trend / 0.02),   # scaled to trend strength
                entry=entry,
                stop=stop,
                target_1=t1,
                target_2=t2,
                at_ts_utc=str(ts),
                window=SessionWindow.MORNING.value,
                slot=TradingSlot.STABLE_TREND.value,
                reasoning=f"Uptrend +{trend*100:.2f}% · pullback to VWAP {last_vwap:.2f} · bouncing to {close:.2f}",
                metadata={"vwap": last_vwap, "trend_pct": trend * 100},
            )
        except Exception:
            return None
