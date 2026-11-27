"""Market-local completed sessions from reviewed exchange schedules."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.aegis_local_state import contained
from scripts.aegis_shadow.pipeline import _json


@dataclass(frozen=True)
class ExchangeCalendar:
    timezone: ZoneInfo
    start: date
    end: date
    closes: dict

    def completed(self, now):
        if now.utcoffset() is None:
            raise ValueError("exchange calendar requires a timezone-aware clock")
        local = now.astimezone(self.timezone)
        if not self.start <= local.date() <= self.end:
            raise ValueError("current date outside reviewed exchange schedule")
        eligible = (day for day, close in self.closes.items()
                    if day < local.date() or (day == local.date() and local.time() >= close))
        latest = max(eligible, default=None)
        if latest is None:
            raise ValueError("reviewed schedule has no completed session yet")
        return latest

    def missing(self, previous, latest):
        if not self.start <= previous <= latest <= self.end or previous not in self.closes or latest not in self.closes:
            raise ValueError("checkpoint outside reviewed exchange sessions")
        return [day.isoformat() for day in sorted(self.closes) if previous < day < latest]


def exchange_calendar(market, storage=None):
    zone = ZoneInfo({"india": "Asia/Kolkata", "usa": "America/New_York"}[market])
    if storage is not None:
        path = contained(storage, Path("inputs") / market / "exchange_calendar.json")
        if path.is_file():
            evidence = _json(path)
            if (evidence.get("schema") != "aegis.exchange_calendar.v1" or evidence.get("market") != market
                    or evidence.get("timezone") != zone.key or not str(evidence.get("source") or "").strip()):
                raise ValueError("exchange schedule identity or source is invalid")
            start, end = (date.fromisoformat(evidence[key]) for key in ("coverage_start", "coverage_end"))
            closes = {}
            for record in evidence["sessions"]:
                day, close = date.fromisoformat(record["date"]), time.fromisoformat(record["close"])
                if day in closes or not start <= day <= end or close.utcoffset() is not None:
                    raise ValueError("duplicate or invalid exchange session")
                closes[day] = close
            if not closes:
                raise ValueError("reviewed exchange schedule is empty")
            return ExchangeCalendar(zone, start, end, closes)
    from backend.research.evidence.trading_calendars import NYSE_EARLY_CLOSES, NYSE_HOLIDAYS
    from scripts.check_data_freshness import NSE_HOLIDAYS_2026

    start, end = date(2026, 1, 1), date(2026, 12, 31)
    holidays = NSE_HOLIDAYS_2026 if market == "india" else NYSE_HOLIDAYS
    close = time(15, 30) if market == "india" else time(16)
    days = (start + timedelta(days=offset) for offset in range((end - start).days + 1))
    return ExchangeCalendar(zone, start, end, {day: time(13) if market == "usa" and day in NYSE_EARLY_CLOSES else close
                                                for day in days if day.weekday() < 5 and day not in holidays})
