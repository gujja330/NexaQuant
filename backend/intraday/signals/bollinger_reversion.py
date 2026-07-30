"""Bollinger Bands Reversion · operator's proven strategy #3.

Methodology (from operator's spec):
  · 20-period SMA · 2 standard deviations · 3-min or 5-min chart
  · Price ABOVE upper band = overextended · SHORT toward middle band
  · Price BELOW lower band = oversold · LONG toward middle band
  · Stop-Loss just outside the extreme wick that breached the band
"""
from __future__ import annotations

from .base import SignalBase, SignalScore, register
from ..session_clock import SessionWindow, TradingSlot


@register
class BollingerReversion(SignalBase):
    signal_id      = "bollinger_reversion"
    display_name   = "Bollinger Bands Reversion"
    active_slots   = [TradingSlot.STABLE_TREND]
    active_windows = [SessionWindow.MORNING, SessionWindow.MIDDAY,
                        SessionWindow.AFTERNOON]

    PERIOD  = 20
    STDDEV  = 2.0

    def compute(self, bars, meta: dict) -> SignalScore | None:
        if bars is None or len(bars) < self.PERIOD + 2:
            return None
        ticker = meta.get("ticker") or "?"
        try:
            ordered = bars.sort_index()
            close = ordered["close"].astype(float)
            sma = close.rolling(self.PERIOD).mean()
            std = close.rolling(self.PERIOD).std()
            upper = sma + self.STDDEV * std
            lower = sma - self.STDDEV * std

            last_close = float(close.iloc[-1])
            last_high = float(ordered["high"].iloc[-1])
            last_low = float(ordered["low"].iloc[-1])
            last_sma = float(sma.iloc[-1])
            last_upper = float(upper.iloc[-1])
            last_lower = float(lower.iloc[-1])
            ts = ordered.index[-1]

            if last_high > last_upper:
                # SHORT · target middle band
                stop = last_high * 1.002
                return SignalScore(
                    signal_id=self.signal_id, ticker=ticker, direction="SHORT",
                    score=-min(1.0, (last_high - last_upper) / max(1e-9, last_upper - last_sma)),
                    entry=last_close, stop=stop,
                    target_1=last_sma,
                    target_2=last_lower,
                    at_ts_utc=str(ts),
                    window=SessionWindow.MORNING.value,
                    slot=TradingSlot.STABLE_TREND.value,
                    reasoning=f"High {last_high:.2f} pierced upper band {last_upper:.2f} · mean-revert to SMA {last_sma:.2f}",
                    metadata={"upper": last_upper, "sma": last_sma, "lower": last_lower},
                )
            if last_low < last_lower:
                # LONG · target middle band
                stop = last_low * 0.998
                return SignalScore(
                    signal_id=self.signal_id, ticker=ticker, direction="LONG",
                    score=+min(1.0, (last_lower - last_low) / max(1e-9, last_sma - last_lower)),
                    entry=last_close, stop=stop,
                    target_1=last_sma,
                    target_2=last_upper,
                    at_ts_utc=str(ts),
                    window=SessionWindow.MORNING.value,
                    slot=TradingSlot.STABLE_TREND.value,
                    reasoning=f"Low {last_low:.2f} pierced lower band {last_lower:.2f} · mean-revert to SMA {last_sma:.2f}",
                    metadata={"upper": last_upper, "sma": last_sma, "lower": last_lower},
                )
            return None
        except Exception:
            return None
