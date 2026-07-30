"""Gap-and-Go · AEGIS technique #5 (overnight gap continuation).

Methodology:
  · Detect overnight gap ≥ 0.5% (open vs prev_close)
  · Confirm with opening 5-min volume ≥ 1.5× session average
  · LONG on positive gaps that continue after first 5 min
  · Active only in HIGH_VOL slot (opening 45 min)
"""
from __future__ import annotations

from .base import SignalBase, SignalScore, register
from ..session_clock import SessionWindow, TradingSlot


@register
class GapAndGo(SignalBase):
    signal_id      = "gap_and_go"
    display_name   = "Gap and Go"
    active_slots   = [TradingSlot.HIGH_VOL]
    active_windows = [SessionWindow.OPENING]

    MIN_GAP_PCT = 0.5
    MIN_VOL_MULT = 1.5

    def compute(self, bars, meta: dict) -> SignalScore | None:
        if bars is None or len(bars) < 3:
            return None
        ticker = meta.get("ticker") or "?"
        prev_close = meta.get("prev_close")
        if not prev_close or prev_close <= 0:
            return None
        try:
            ordered = bars.sort_index()
            session_open = float(ordered["open"].iloc[0])
            gap_pct = (session_open - prev_close) / prev_close * 100
            if abs(gap_pct) < self.MIN_GAP_PCT:
                return None

            first5 = ordered.iloc[0]
            vol_first5 = float(first5.get("volume", 0))
            avg_vol = float(ordered["volume"].mean()) if "volume" in ordered.columns else 0
            if avg_vol > 0 and vol_first5 < self.MIN_VOL_MULT * avg_vol:
                return None

            second_bar = ordered.iloc[1]
            close2 = float(second_bar["close"])
            ts = ordered.index[1]

            if gap_pct > 0 and close2 > session_open:
                stop = session_open * 0.995
                target_1 = close2 * 1.007
                target_2 = close2 * 1.015
                return SignalScore(
                    signal_id=self.signal_id, ticker=ticker, direction="LONG",
                    score=+min(1.0, gap_pct / 3.0),
                    entry=close2, stop=stop,
                    target_1=target_1, target_2=target_2,
                    at_ts_utc=str(ts),
                    window=SessionWindow.OPENING.value,
                    slot=TradingSlot.HIGH_VOL.value,
                    reasoning=f"Gap-up {gap_pct:+.2f}% · volume {vol_first5/max(1,avg_vol):.1f}x avg · continuation",
                    metadata={"gap_pct": gap_pct, "session_open": session_open,
                              "prev_close": prev_close},
                )
            if gap_pct < 0 and close2 < session_open:
                stop = session_open * 1.005
                target_1 = close2 * 0.993
                target_2 = close2 * 0.985
                return SignalScore(
                    signal_id=self.signal_id, ticker=ticker, direction="SHORT",
                    score=-min(1.0, abs(gap_pct) / 3.0),
                    entry=close2, stop=stop,
                    target_1=target_1, target_2=target_2,
                    at_ts_utc=str(ts),
                    window=SessionWindow.OPENING.value,
                    slot=TradingSlot.HIGH_VOL.value,
                    reasoning=f"Gap-down {gap_pct:+.2f}% · continuation",
                    metadata={"gap_pct": gap_pct, "session_open": session_open,
                              "prev_close": prev_close},
                )
            return None
        except Exception:
            return None
