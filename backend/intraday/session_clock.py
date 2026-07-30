"""Session clock + time-of-day window classification.

Operator directive: "intraday majorly plays a key role in morning opening
hrs. If we can capture such levels. Also check different times through
a day."

Design: every minute of the trading session belongs to exactly one named
window. Each signal factory + risk rule declares which windows it is
active in · metrics are broken out per window so we can see WHERE in
the day the engine makes or loses money.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
from enum import Enum


class SessionWindow(str, Enum):
    """Fine-grained 7-window classification for per-window metrics."""
    PRE_OPEN     = "pre_open"      # before session start (no signals · pure setup)
    OPENING      = "opening"       # first ~45 min after session start (highest alpha)
    MORNING      = "morning"       # 10:00-12:00 IST / 10:15-12:00 ET
    MIDDAY       = "midday"        # 12:00-13:30 both markets (quiet lunch)
    AFTERNOON    = "afternoon"     # 13:30-15:00 both markets
    POWER_HOUR   = "power_hour"    # last hour before close (institutional flow)
    POST_CLOSE   = "post_close"    # after session close


class TradingSlot(str, Enum):
    """Operator's 3-slot trader framework (India-first · same for USA scaled).

    Coarser than SessionWindow · used for STRATEGY SELECTION and RISK
    POSTURE at the slot level. Signal factories declare which slots they
    are active in.
    """
    HIGH_VOL     = "high_volatility"   # 09:15-10:15 IST · momentum + breakout only
    STABLE_TREND = "stable_trend"      # 10:15-14:30 IST · mean-rev + pullback + trend
    SQUARE_OFF   = "square_off"        # 14:30-15:30 IST · exits only · no new entries
    OFF_SESSION  = "off_session"       # pre-open / post-close


WINDOW_ORDER = [
    SessionWindow.PRE_OPEN,
    SessionWindow.OPENING,
    SessionWindow.MORNING,
    SessionWindow.MIDDAY,
    SessionWindow.AFTERNOON,
    SessionWindow.POWER_HOUR,
    SessionWindow.POST_CLOSE,
]

SLOT_ORDER = [
    TradingSlot.OFF_SESSION,
    TradingSlot.HIGH_VOL,
    TradingSlot.STABLE_TREND,
    TradingSlot.SQUARE_OFF,
]


# ═══ Session boundaries per market (local trading time) ═══════════════
# India NSE: 09:15 - 15:30 IST · no premarket
# USA: pre-market 04:00-09:30 ET (not used for entries) · session 09:30-16:00 ET
_INDIA_SESSION = {
    "open":            time(9, 15),
    "opening_end":     time(10, 0),      # 45 min opening window
    "morning_end":     time(12, 0),
    "midday_end":      time(13, 30),
    "afternoon_end":   time(15, 0),
    "power_hour_end":  time(15, 15),     # time-stop before close
    "close":           time(15, 30),
    "no_new_entries_after": time(13, 0),
    # Operator's 3-slot boundaries (India-first)
    "high_vol_end":    time(10, 15),
    "stable_trend_end": time(14, 30),
    "square_off_end":  time(15, 30),
}

_USA_SESSION = {
    "open":            time(9, 30),
    "opening_end":     time(10, 15),
    "morning_end":     time(12, 0),
    "midday_end":      time(13, 30),
    "afternoon_end":   time(15, 0),
    "power_hour_end":  time(15, 55),
    "close":           time(16, 0),
    "no_new_entries_after": time(15, 0),
    # 3-slot boundaries scaled for USA session
    "high_vol_end":    time(10, 30),
    "stable_trend_end": time(15, 0),
    "square_off_end":  time(16, 0),
}

_MARKET_SESSIONS = {"india": _INDIA_SESSION, "usa": _USA_SESSION}


def _market_local_time(market: str, t_utc: datetime) -> time:
    """Convert UTC → market local trading time."""
    if t_utc.tzinfo is None:
        t_utc = t_utc.replace(tzinfo=timezone.utc)
    if market == "india":
        local = t_utc.astimezone(timezone(timedelta(hours=5, minutes=30)))
    else:
        # USA · ET auto-DST
        try:
            from zoneinfo import ZoneInfo
            local = t_utc.astimezone(ZoneInfo("America/New_York"))
        except Exception:
            # Fallback fixed EDT (loses DST correctness · flag in caller)
            local = t_utc.astimezone(timezone(timedelta(hours=-4)))
    return local.time()


def window_for_time(market: str, t_utc: datetime) -> SessionWindow:
    """Classify a UTC timestamp into its session window for `market`."""
    s = _MARKET_SESSIONS.get(market)
    if s is None:
        return SessionWindow.PRE_OPEN
    lt = _market_local_time(market, t_utc)
    if lt < s["open"]:
        return SessionWindow.PRE_OPEN
    if lt < s["opening_end"]:
        return SessionWindow.OPENING
    if lt < s["morning_end"]:
        return SessionWindow.MORNING
    if lt < s["midday_end"]:
        return SessionWindow.MIDDAY
    if lt < s["afternoon_end"]:
        return SessionWindow.AFTERNOON
    if lt < s["power_hour_end"]:
        return SessionWindow.POWER_HOUR
    return SessionWindow.POST_CLOSE


def current_window(market: str) -> SessionWindow:
    """Classify NOW (UTC) for `market`."""
    return window_for_time(market, datetime.now(timezone.utc))


def slot_for_time(market: str, t_utc: datetime) -> TradingSlot:
    """Operator's 3-slot classification (coarser than SessionWindow · used
    for strategy selection + risk posture at slot level)."""
    s = _MARKET_SESSIONS.get(market)
    if s is None:
        return TradingSlot.OFF_SESSION
    lt = _market_local_time(market, t_utc)
    if lt < s["open"]:
        return TradingSlot.OFF_SESSION
    if lt < s["high_vol_end"]:
        return TradingSlot.HIGH_VOL
    if lt < s["stable_trend_end"]:
        return TradingSlot.STABLE_TREND
    if lt < s["square_off_end"]:
        return TradingSlot.SQUARE_OFF
    return TradingSlot.OFF_SESSION


def current_slot(market: str) -> TradingSlot:
    return slot_for_time(market, datetime.now(timezone.utc))


def is_entry_allowed(market: str, t_utc: datetime | None = None) -> bool:
    """Per §6.1 · no new entries after `no_new_entries_after` cutoff."""
    if t_utc is None:
        t_utc = datetime.now(timezone.utc)
    s = _MARKET_SESSIONS.get(market)
    if s is None:
        return False
    w = window_for_time(market, t_utc)
    if w in (SessionWindow.PRE_OPEN, SessionWindow.POST_CLOSE):
        return False
    lt = _market_local_time(market, t_utc)
    return lt < s["no_new_entries_after"]


def is_force_close(market: str, t_utc: datetime | None = None) -> bool:
    """Per §6.3 · after `power_hour_end` all positions force-closed."""
    if t_utc is None:
        t_utc = datetime.now(timezone.utc)
    s = _MARKET_SESSIONS.get(market)
    if s is None:
        return False
    lt = _market_local_time(market, t_utc)
    return lt >= s["power_hour_end"]


@dataclass
class SessionBounds:
    market:              str
    session_open:        time
    opening_end:         time
    morning_end:         time
    midday_end:          time
    afternoon_end:       time
    power_hour_end:      time
    session_close:       time
    no_new_entries_after: time


def session_bounds(market: str) -> SessionBounds:
    s = _MARKET_SESSIONS[market]
    return SessionBounds(
        market=market,
        session_open=s["open"],
        opening_end=s["opening_end"],
        morning_end=s["morning_end"],
        midday_end=s["midday_end"],
        afternoon_end=s["afternoon_end"],
        power_hour_end=s["power_hour_end"],
        session_close=s["close"],
        no_new_entries_after=s["no_new_entries_after"],
    )
