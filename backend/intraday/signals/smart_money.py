"""Smart Money Concepts (SMC) · institutional-grade signal factory.

Combines multiple SMC techniques into ONE unified score per bar:

  · BOS (Break of Structure)     · trend continuation
  · CHoCH (Change of Character)  · trend reversal
  · Order Blocks (OB)            · institutional zones
  · Fair Value Gaps (FVG)        · 3-candle price imbalance
  · Liquidity Sweeps             · equal-highs/equal-lows hunted before real move
  · Premium/Discount             · buy only in discount, sell only in premium

Emits LONG when confluence points bullish (BOS up + bullish OB + FVG fill
in discount zone), SHORT symmetric. Uses ATR for dynamic stop sizing.
Targets are wide (2-3% intraday) because SMC targets multi-hour moves,
not scalps.
"""
from __future__ import annotations

from .base import SignalBase, SignalScore, register
from ..session_clock import SessionWindow, TradingSlot


@register
class SmartMoneyConcepts(SignalBase):
    signal_id      = "smart_money"
    display_name   = "Smart Money Concepts (BOS + OB + FVG + Sweep)"
    active_slots   = [TradingSlot.HIGH_VOL, TradingSlot.STABLE_TREND]
    active_windows = [SessionWindow.OPENING, SessionWindow.MORNING,
                        SessionWindow.MIDDAY, SessionWindow.AFTERNOON]

    LOOKBACK        = 30           # ~2.5 hours on 5-min bars
    SWING_WINDOW    = 5             # bars for swing high/low pivots
    FVG_MIN_PCT     = 0.002         # 0.2% minimum gap
    ATR_STOP_MULT   = 1.5           # dynamic stop = 1.5×ATR
    ATR_T1_MULT     = 3.0           # target 1 = 3×ATR (~1.5-2% move typically)
    ATR_T2_MULT     = 6.0           # target 2 = 6×ATR (~3-4% move · big intraday)
    MIN_CONFLUENCE  = 3             # need at least 3 aligned · quality over quantity

    def _find_swings(self, high, low):
        """Return lists of swing-high indices + swing-low indices."""
        n = len(high)
        w = self.SWING_WINDOW
        swing_highs, swing_lows = [], []
        for i in range(w, n - w):
            if high.iloc[i] == max(high.iloc[i - w:i + w + 1]):
                swing_highs.append(i)
            if low.iloc[i] == min(low.iloc[i - w:i + w + 1]):
                swing_lows.append(i)
        return swing_highs, swing_lows

    def _detect_bos_or_choch(self, close, swing_highs, swing_lows):
        """Return (direction, kind) · direction in {LONG, SHORT}, kind in {BOS, CHOCH}."""
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return None, None
        last_high = close.iloc[swing_highs[-1]] if swing_highs else None
        last_low = close.iloc[swing_lows[-1]] if swing_lows else None
        last_close = close.iloc[-1]
        # Uptrend: recent higher-highs · BOS UP if breaks above last swing high
        if last_high is not None and last_close > last_high:
            # Determine: is this continuation (BOS) or reversal from a downtrend (CHoCH)?
            # Reversal if last two swings before were making lower-lows
            if len(swing_lows) >= 2 and close.iloc[swing_lows[-1]] < close.iloc[swing_lows[-2]]:
                return "LONG", "CHOCH"
            return "LONG", "BOS"
        if last_low is not None and last_close < last_low:
            if len(swing_highs) >= 2 and close.iloc[swing_highs[-1]] > close.iloc[swing_highs[-2]]:
                return "SHORT", "CHOCH"
            return "SHORT", "BOS"
        return None, None

    def _last_order_block(self, open_, close, high, low, direction: str):
        """Bullish OB = last bearish candle before an up-move · vice versa."""
        n = len(close)
        if direction == "LONG":
            # Look back for last bearish candle before recent strong up-move
            for i in range(n - 3, max(0, n - 15), -1):
                if close.iloc[i] < open_.iloc[i]:      # bearish candle
                    # Confirm strong up-move followed
                    if close.iloc[i + 2] > high.iloc[i]:
                        return low.iloc[i], high.iloc[i]     # OB zone
            return None
        else:
            for i in range(n - 3, max(0, n - 15), -1):
                if close.iloc[i] > open_.iloc[i]:      # bullish candle
                    if close.iloc[i + 2] < low.iloc[i]:
                        return low.iloc[i], high.iloc[i]
            return None

    def _has_fvg(self, high, low, direction: str) -> bool:
        """3-candle price imbalance · bullish FVG when candle1.high < candle3.low."""
        n = len(high)
        for i in range(n - 5, max(0, n - 20), -1):
            if i + 2 >= n:
                continue
            if direction == "LONG":
                gap = low.iloc[i + 2] - high.iloc[i]
                if gap > 0 and gap / max(1e-9, high.iloc[i]) > self.FVG_MIN_PCT:
                    return True
            else:
                gap = low.iloc[i] - high.iloc[i + 2]
                if gap > 0 and gap / max(1e-9, low.iloc[i]) > self.FVG_MIN_PCT:
                    return True
        return False

    def _liquidity_sweep(self, high, low, direction: str) -> bool:
        """Detect sweep of equal highs (bearish setup) or equal lows (bullish)."""
        n = len(high)
        if n < 10:
            return False
        recent_high = high.iloc[-3:].max()
        prior_high = high.iloc[-10:-3].max()
        recent_low = low.iloc[-3:].min()
        prior_low = low.iloc[-10:-3].min()
        # Bullish sweep: recent low pierces prior low then bounces (stops hunted)
        if direction == "LONG":
            return recent_low < prior_low * 0.999 and low.iloc[-1] > recent_low
        else:
            return recent_high > prior_high * 1.001 and high.iloc[-1] < recent_high

    def _in_discount_zone(self, high, low) -> bool:
        """Premium/Discount: is current price in the LOWER half (discount) of the dealing range?"""
        r_high = high.max(); r_low = low.min()
        equilibrium = (r_high + r_low) / 2
        return low.iloc[-1] < equilibrium

    def _atr(self, high, low, close, period: int = 14) -> float:
        import pandas as pd
        h_l = high - low
        h_c = (high - close.shift()).abs()
        l_c = (low - close.shift()).abs()
        tr = pd.concat([h_l, h_c, l_c], axis=1).max(axis=1)
        val = float(tr.rolling(period).mean().iloc[-1])
        return val if val == val and val > 0 else float(close.iloc[-1]) * 0.005

    def compute(self, bars, meta: dict) -> SignalScore | None:
        if bars is None or len(bars) < self.LOOKBACK:
            return None
        ticker = meta.get("ticker") or "?"
        try:
            import pandas as pd
            ordered = bars.sort_index().tail(self.LOOKBACK)
            open_ = ordered["open"].astype(float)
            high = ordered["high"].astype(float)
            low = ordered["low"].astype(float)
            close = ordered["close"].astype(float)

            swing_highs, swing_lows = self._find_swings(high, low)
            direction, structure_kind = self._detect_bos_or_choch(close, swing_highs, swing_lows)
            if direction is None:
                return None

            # Confluence checks
            confluence = 1                # base: structure signal itself
            reasons = [structure_kind]

            ob = self._last_order_block(open_, close, high, low, direction)
            if ob is not None:
                confluence += 1
                reasons.append("OB")

            if self._has_fvg(high, low, direction):
                confluence += 1
                reasons.append("FVG")

            if self._liquidity_sweep(high, low, direction):
                confluence += 1
                reasons.append("Sweep")

            # Premium/Discount filter: LONG only in discount, SHORT only in premium
            in_disc = self._in_discount_zone(high, low)
            if direction == "LONG" and not in_disc:
                return None
            if direction == "SHORT" and in_disc:
                return None
            reasons.append("Disc" if in_disc else "Prem")

            if confluence < self.MIN_CONFLUENCE:
                return None

            # Dynamic stop + wide targets via ATR
            atr = self._atr(high, low, close)
            entry = float(close.iloc[-1])
            if direction == "LONG":
                stop = entry - self.ATR_STOP_MULT * atr
                t1 = entry + self.ATR_T1_MULT * atr
                t2 = entry + self.ATR_T2_MULT * atr
                score = +min(1.0, confluence / 4.0)
            else:
                stop = entry + self.ATR_STOP_MULT * atr
                t1 = entry - self.ATR_T1_MULT * atr
                t2 = entry - self.ATR_T2_MULT * atr
                score = -min(1.0, confluence / 4.0)

            ts = ordered.index[-1]
            return SignalScore(
                signal_id=self.signal_id, ticker=ticker, direction=direction,
                score=score, entry=entry, stop=stop,
                target_1=t1, target_2=t2,
                at_ts_utc=str(ts),
                window=SessionWindow.MORNING.value,
                slot=TradingSlot.STABLE_TREND.value,
                reasoning=f"SMC confluence {confluence} · {' + '.join(reasons)} · ATR-stop {atr:.2f}",
                metadata={"atr": atr, "confluence": confluence, "components": reasons,
                          "structure": structure_kind},
            )
        except Exception as e:
            return None
