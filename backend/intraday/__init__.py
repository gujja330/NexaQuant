"""AEGIS Intraday Engine · fully isolated from daily pipelines.

Ticket R004 · architecture in docs/AEGIS_INTRADAY_ARCHITECTURE.md.

ISOLATION GUARANTEE:
    Zero imports from backend/recommendation/, backend/research/,
    or backend/delivery/telegram/. This module has its own storage
    (reports/intraday/), own configs (configs/intraday_*), own scripts
    (scripts/intraday_*.py), and own Telegram sender. Nothing in the
    delivery daily pipeline can be broken by changes here.

TIME-OF-DAY WINDOWS (per operator directive · morning is critical):
    OPENING     · India 09:15-10:00 IST · USA 09:30-10:15 ET  (highest alpha window)
    MORNING     · India 10:00-12:00 IST · USA 10:15-12:00 ET
    MIDDAY      · India 12:00-13:30 IST · USA 12:00-13:30 ET
    AFTERNOON   · India 13:30-15:00 IST · USA 13:30-15:00 ET
    POWER_HOUR  · India 15:00-15:15 IST · USA 15:00-15:55 ET
    NO_ENTRY    · after 13:00 IST (§6.1) · no new entries but exits allowed
    TIME_STOP   · India 15:15 IST · USA 15:55 ET · all positions force-closed
"""
from .session_clock import (
    SessionWindow,
    TradingSlot,
    current_window,
    current_slot,
    window_for_time,
    slot_for_time,
    session_bounds,
    is_entry_allowed,
    is_force_close,
    WINDOW_ORDER,
    SLOT_ORDER,
)

SCHEMA_FINGERPRINT = "aegis.intraday.v1.20260731"
ENGINE_ID = "aegis.intraday.v1"

__all__ = [
    "SessionWindow",
    "TradingSlot",
    "current_window",
    "current_slot",
    "window_for_time",
    "slot_for_time",
    "session_bounds",
    "is_entry_allowed",
    "is_force_close",
    "WINDOW_ORDER",
    "SLOT_ORDER",
    "SCHEMA_FINGERPRINT",
    "ENGINE_ID",
]
