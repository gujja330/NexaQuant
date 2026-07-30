"""News Impact · AEGIS technique #7.

Methodology:
  · Real-time headline scraped from Google News RSS · ticker-specific
  · FinBERT sentiment → bullish/bearish score
  · Recency decay: exp(-minutes_ago / 30)
  · Only reacts to headlines within the last 30 minutes
  · Active across all in-session windows (news can hit any time)
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .base import SignalBase, SignalScore, register
from ..session_clock import SessionWindow, TradingSlot


@register
class NewsImpact(SignalBase):
    signal_id      = "news_impact"
    display_name   = "News Impact"
    active_slots   = [TradingSlot.HIGH_VOL, TradingSlot.STABLE_TREND]
    active_windows = [SessionWindow.OPENING, SessionWindow.MORNING,
                        SessionWindow.MIDDAY, SessionWindow.AFTERNOON]

    RECENCY_MIN     = 30       # only news within last 30 min
    MIN_SENTIMENT   = 0.4      # FinBERT confidence threshold

    def compute(self, bars, meta: dict) -> SignalScore | None:
        if bars is None or len(bars) < 2:
            return None
        news = meta.get("news_items") or []   # list of {headline, sentiment, published_ts_utc}
        if not news:
            return None
        ticker = meta.get("ticker") or "?"
        try:
            now = datetime.now(timezone.utc)
            # Find most impactful recent news
            best = None
            best_impact = 0.0
            for item in news:
                pub = item.get("published_ts_utc")
                if not pub:
                    continue
                try:
                    pub_dt = datetime.fromisoformat(str(pub).replace("Z", "+00:00"))
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                mins_ago = (now - pub_dt).total_seconds() / 60
                if mins_ago > self.RECENCY_MIN or mins_ago < 0:
                    continue
                sentiment = float(item.get("sentiment", 0))
                if abs(sentiment) < self.MIN_SENTIMENT:
                    continue
                decay = math.exp(-mins_ago / 30)
                impact = sentiment * decay
                if abs(impact) > abs(best_impact):
                    best_impact = impact
                    best = item
            if best is None:
                return None

            ordered = bars.sort_index()
            last_close = float(ordered["close"].iloc[-1])
            ts = ordered.index[-1]

            if best_impact > 0:
                stop = last_close * 0.995
                return SignalScore(
                    signal_id=self.signal_id, ticker=ticker, direction="LONG",
                    score=+min(1.0, best_impact), entry=last_close, stop=stop,
                    target_1=last_close * 1.008, target_2=last_close * 1.015,
                    at_ts_utc=str(ts),
                    window=SessionWindow.MORNING.value,
                    slot=TradingSlot.STABLE_TREND.value,
                    reasoning=f"Bullish news · sentiment {best.get('sentiment'):.2f} · headline: {(best.get('headline') or '')[:80]}",
                    metadata={"impact": best_impact, "headline": best.get("headline")},
                )
            else:
                stop = last_close * 1.005
                return SignalScore(
                    signal_id=self.signal_id, ticker=ticker, direction="SHORT",
                    score=-min(1.0, abs(best_impact)), entry=last_close, stop=stop,
                    target_1=last_close * 0.992, target_2=last_close * 0.985,
                    at_ts_utc=str(ts),
                    window=SessionWindow.MORNING.value,
                    slot=TradingSlot.STABLE_TREND.value,
                    reasoning=f"Bearish news · sentiment {best.get('sentiment'):.2f}",
                    metadata={"impact": best_impact, "headline": best.get("headline")},
                )
        except Exception:
            return None
