"""EMA Crossover · operator's proven strategy #4 (9/21 EMA on 5-min).

Methodology (from operator's spec):
  · 9-period EMA + 21-period EMA on 5-min chart
  · LONG when 9-EMA crosses ABOVE 21-EMA (bullish acceleration)
  · SHORT when 9-EMA crosses BELOW 21-EMA
  · Exit immediately if crossover reverses
"""
from __future__ import annotations

from .base import SignalBase, SignalScore, register
from ..session_clock import SessionWindow, TradingSlot


@register
class EMACrossover(SignalBase):
    signal_id      = "ema_crossover"
    display_name   = "EMA Crossover 9/21"
    active_slots   = [TradingSlot.HIGH_VOL, TradingSlot.STABLE_TREND]
    active_windows = [SessionWindow.OPENING, SessionWindow.MORNING,
                        SessionWindow.MIDDAY, SessionWindow.AFTERNOON]

    FAST_PERIOD = 9
    SLOW_PERIOD = 21
    STOP_ATR_MULT = 1.5

    def compute(self, bars, meta: dict) -> SignalScore | None:
        if bars is None or len(bars) < self.SLOW_PERIOD + 2:
            return None
        ticker = meta.get("ticker") or "?"
        try:
            ordered = bars.sort_index()
            close = ordered["close"].astype(float)
            fast = close.ewm(span=self.FAST_PERIOD, adjust=False).mean()
            slow = close.ewm(span=self.SLOW_PERIOD, adjust=False).mean()
            # True range for stop sizing
            high = ordered["high"].astype(float)
            low = ordered["low"].astype(float)
            atr = (high - low).rolling(14).mean().iloc[-1]
            if atr != atr:      # NaN guard
                atr = float(close.iloc[-1]) * 0.005

            last_close = float(close.iloc[-1])
            f_now, f_prev = float(fast.iloc[-1]), float(fast.iloc[-2])
            s_now, s_prev = float(slow.iloc[-1]), float(slow.iloc[-2])
            ts = ordered.index[-1]

            # Fresh bullish cross
            if f_prev <= s_prev and f_now > s_now:
                stop = last_close - self.STOP_ATR_MULT * float(atr)
                target_1 = last_close + 2 * self.STOP_ATR_MULT * float(atr)
                target_2 = last_close + 4 * self.STOP_ATR_MULT * float(atr)
                return SignalScore(
                    signal_id=self.signal_id, ticker=ticker, direction="LONG",
                    score=+min(1.0, (f_now - s_now) / max(1e-9, s_now) * 100),
                    entry=last_close, stop=stop,
                    target_1=target_1, target_2=target_2,
                    at_ts_utc=str(ts),
                    window=SessionWindow.MORNING.value,
                    slot=TradingSlot.STABLE_TREND.value,
                    reasoning=f"9-EMA {f_now:.2f} crossed above 21-EMA {s_now:.2f}",
                    metadata={"fast": f_now, "slow": s_now, "atr": float(atr)},
                )
            # Fresh bearish cross
            if f_prev >= s_prev and f_now < s_now:
                stop = last_close + self.STOP_ATR_MULT * float(atr)
                target_1 = last_close - 2 * self.STOP_ATR_MULT * float(atr)
                target_2 = last_close - 4 * self.STOP_ATR_MULT * float(atr)
                return SignalScore(
                    signal_id=self.signal_id, ticker=ticker, direction="SHORT",
                    score=-min(1.0, (s_now - f_now) / max(1e-9, s_now) * 100),
                    entry=last_close, stop=stop,
                    target_1=target_1, target_2=target_2,
                    at_ts_utc=str(ts),
                    window=SessionWindow.MORNING.value,
                    slot=TradingSlot.STABLE_TREND.value,
                    reasoning=f"9-EMA {f_now:.2f} crossed below 21-EMA {s_now:.2f}",
                    metadata={"fast": f_now, "slow": s_now, "atr": float(atr)},
                )
            return None
        except Exception:
            return None
