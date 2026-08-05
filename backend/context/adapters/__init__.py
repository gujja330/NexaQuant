"""CIL adapters · one per context engine.

Ships 2026-08-05 with 4 real adapters. Rest arrive in Phase 2B/2C.
"""
from .macro_adapter import MacroAdapter
from .sector_adapter import SectorAdapter
from .vol_adapter import VolAdapter
from .news_adapter import NewsAdapter

DEFAULT_ADAPTERS = [
    MacroAdapter(), SectorAdapter(), VolAdapter(), NewsAdapter(),
]
