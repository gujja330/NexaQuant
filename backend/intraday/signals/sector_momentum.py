"""Sector Momentum Follow · AEGIS technique #6.

Methodology:
  · If a stock's intraday move tracks its sector-ETF closely (correlation
    > 0.4 rolling 30-min), follow the sector-ETF direction
  · Enter when sector-ETF is +0.3% or more intraday · stock hasn't moved yet
  · Active in STABLE_TREND (10:15-14:30) when institutional sector flows dominate
"""
from __future__ import annotations

from .base import SignalBase, SignalScore, register
from ..session_clock import SessionWindow, TradingSlot


@register
class SectorMomentum(SignalBase):
    signal_id      = "sector_momentum"
    display_name   = "Sector Momentum Follow"
    active_slots   = [TradingSlot.STABLE_TREND]
    active_windows = [SessionWindow.MORNING, SessionWindow.MIDDAY,
                        SessionWindow.AFTERNOON]

    MIN_CORR       = 0.4
    MIN_SECTOR_MOVE = 0.003    # 0.3%
    LOOKBACK_BARS  = 6           # ~30 min on 5-min bars

    def compute(self, bars, meta: dict) -> SignalScore | None:
        if bars is None or len(bars) < self.LOOKBACK_BARS + 2:
            return None
        sector_bars = meta.get("sector_bars")
        if sector_bars is None or len(sector_bars) < self.LOOKBACK_BARS + 2:
            return None
        ticker = meta.get("ticker") or "?"
        try:
            ordered = bars.sort_index()
            sector = sector_bars.sort_index()
            stock_rets = ordered["close"].astype(float).pct_change().tail(self.LOOKBACK_BARS)
            sector_rets = sector["close"].astype(float).pct_change().tail(self.LOOKBACK_BARS)
            if len(stock_rets) < self.LOOKBACK_BARS or len(sector_rets) < self.LOOKBACK_BARS:
                return None
            corr = float(stock_rets.corr(sector_rets))
            if corr != corr or corr < self.MIN_CORR:
                return None

            session_open_sector = float(sector["close"].iloc[0])
            last_sector = float(sector["close"].iloc[-1])
            sector_move = (last_sector / session_open_sector - 1)
            if abs(sector_move) < self.MIN_SECTOR_MOVE:
                return None

            last_close = float(ordered["close"].iloc[-1])
            session_open_stock = float(ordered["open"].iloc[0])
            stock_move = (last_close / session_open_stock - 1)
            # Enter only when stock LAGGING sector (has room to catch up)
            if abs(stock_move) >= abs(sector_move):
                return None

            direction = "LONG" if sector_move > 0 else "SHORT"
            ts = ordered.index[-1]
            stop = last_close * (0.997 if direction == "LONG" else 1.003)
            t1 = last_close * (1.005 if direction == "LONG" else 0.995)
            t2 = last_close * (1.010 if direction == "LONG" else 0.990)
            return SignalScore(
                signal_id=self.signal_id, ticker=ticker, direction=direction,
                score=(1 if direction == "LONG" else -1) * min(1.0, corr),
                entry=last_close, stop=stop,
                target_1=t1, target_2=t2,
                at_ts_utc=str(ts),
                window=SessionWindow.MORNING.value,
                slot=TradingSlot.STABLE_TREND.value,
                reasoning=f"Sector move {sector_move*100:+.2f}% · corr {corr:.2f} · stock lagging",
                metadata={"correlation": corr, "sector_move_pct": sector_move * 100,
                          "stock_move_pct": stock_move * 100},
            )
        except Exception:
            return None
