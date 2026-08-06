"""CIL adapters · one per context engine.

Ships 2026-08-05 with 8 real adapters after operator's "think wider" call.
"""
from .macro_adapter import MacroAdapter
from .sector_adapter import SectorAdapter
from .vol_adapter import VolAdapter
from .news_adapter import NewsAdapter
from .overnight_adapter import OvernightAdapter
from .breadth_adapter import BreadthAdapter
from .earnings_adapter import EarningsAdapter
from .macro_event_adapter import MacroEventAdapter
# Sprint G · consumes Sprint F ingests
from .bond_adapter import BondAdapter
from .risk_off_adapter import RiskOffAdapter
from .insider_adapter import InsiderAdapter
from .turnover_adapter import TurnoverAdapter
from .correlation_adapter import CorrelationAdapter
from .sustained_news_adapter import SustainedNewsAdapter

DEFAULT_ADAPTERS = [
    MacroAdapter(),
    SectorAdapter(),
    VolAdapter(),
    NewsAdapter(),
    OvernightAdapter(),
    BreadthAdapter(),
    EarningsAdapter(),
    MacroEventAdapter(),
    # Sprint G (6 new)
    BondAdapter(),                # G-A · reads FRED yield curve
    RiskOffAdapter(),             # G-B · reads FRED VIX+crude+USD composite
    InsiderAdapter(),             # G-C · reads EDGAR Form 4
    TurnoverAdapter(),            # G-D · reads NSE bhavcopy
    CorrelationAdapter(),         # G-E · reads correlation_matrix
    SustainedNewsAdapter(),       # G-F · rolling sector news
]
