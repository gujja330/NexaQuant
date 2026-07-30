"""Intraday signal factories.

Operator's 4 proven strategies + AEGIS's 3 additions = 7 total.

Every factory implements:
  · signal_id       : unique identifier
  · display_name    : human-readable
  · active_slots    : list of TradingSlot values where this signal fires
  · active_windows  : list of SessionWindow values (finer-grained)
  · compute(bars, meta) → SignalScore  or None (no signal)

Zero coupling to delivery engine. Zero imports from backend/recommendation/.
"""
from .base import SignalScore, SignalBase, SIGNAL_REGISTRY
from .orb import OpeningRangeBreakout
from .vwap_pullback import VWAPPullback
from .bollinger_reversion import BollingerReversion
from .ema_crossover import EMACrossover
from .gap_and_go import GapAndGo
from .sector_momentum import SectorMomentum
from .news_impact import NewsImpact
from .smart_money import SmartMoneyConcepts

__all__ = [
    "SignalScore",
    "SignalBase",
    "SIGNAL_REGISTRY",
    "OpeningRangeBreakout",
    "VWAPPullback",
    "BollingerReversion",
    "EMACrossover",
    "GapAndGo",
    "SectorMomentum",
    "NewsImpact",
    "SmartMoneyConcepts",
]
