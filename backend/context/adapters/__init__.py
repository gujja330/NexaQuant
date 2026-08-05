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

DEFAULT_ADAPTERS = [
    MacroAdapter(),
    SectorAdapter(),
    VolAdapter(),
    NewsAdapter(),
    OvernightAdapter(),           # NEW · answers IT-down question
    BreadthAdapter(),             # NEW · sector A/D from existing bars
    EarningsAdapter(),            # NEW · ticker earnings pre-event penalty
    MacroEventAdapter(),          # NEW · Fed/RBI/CPI pre-event penalty
]
