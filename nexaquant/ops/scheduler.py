"""OPS001-B cron-slot scheduler for the daemon.

Not a general cron parser. A minimal, testable slot scheduler where each slot
is expressed as (hour, minute) in a specified timezone, with a weekday filter.
The daemon polls due() every N seconds; when a slot's fire-window is hit AND
that slot has not already fired today, due() returns it and the daemon
executes it.

State file (JSON) records the last successful fire timestamp per slot name,
so a daemon restart cannot double-fire a slot that already ran today.

Rationale for not using APScheduler / croniter:
- Zero dependencies (both are third-party, not in CI install list).
- Semantics we actually need are trivially small.
- Deterministic under test — you can inject a `now()` and assert what fires.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable


DEFAULT_FIRE_WINDOW_MIN = 5     # how late after slot's scheduled minute we still fire


@dataclass(frozen=True)
class Slot:
    """One fire time. `weekdays` uses ISO weekday numbers 1..7 (Mon..Sun)."""
    name: str
    hour: int
    minute: int
    weekdays: tuple[int, ...] = (1, 2, 3, 4, 5)     # Mon..Fri
    fire_window_min: int = DEFAULT_FIRE_WINDOW_MIN
    tz_offset_hours: float = 5.5                     # IST default (Asia/Kolkata)

    def scheduled_local(self, ref_utc: datetime) -> datetime:
        """The scheduled fire-instant, in local (offset) time, for ref_utc's local day."""
        offset = timedelta(hours=self.tz_offset_hours)
        local = ref_utc.astimezone(timezone(offset))
        return local.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)

    def is_due(self, ref_utc: datetime, last_fire_utc: datetime | None) -> bool:
        """True iff ref_utc is inside the fire window AND we haven't fired today."""
        offset = timedelta(hours=self.tz_offset_hours)
        local = ref_utc.astimezone(timezone(offset))
        if local.isoweekday() not in self.weekdays:
            return False
        sched_local = self.scheduled_local(ref_utc)
        window_end = sched_local + timedelta(minutes=self.fire_window_min)
        if not (sched_local <= local <= window_end):
            return False
        if last_fire_utc is None:
            return True
        last_local = last_fire_utc.astimezone(timezone(offset))
        # Already fired today?
        return last_local.date() != local.date()


@dataclass
class ScheduleState:
    """Persistent record of the most recent fire timestamp per slot."""
    last_fires_utc: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "ScheduleState":
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            fires = raw.get("last_fires_utc", {})
            return cls(last_fires_utc={str(k): str(v) for k, v in fires.items()})
        except (json.JSONDecodeError, OSError):
            return cls()

    def save(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"last_fires_utc": self.last_fires_utc},
                            ensure_ascii=False, indent=2),
                encoding="utf-8")
        except OSError:
            pass

    def last_fire(self, slot_name: str) -> datetime | None:
        raw = self.last_fires_utc.get(slot_name)
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None

    def mark_fired(self, slot_name: str, at_utc: datetime) -> None:
        if at_utc.tzinfo is None:
            at_utc = at_utc.replace(tzinfo=timezone.utc)
        self.last_fires_utc[slot_name] = at_utc.astimezone(timezone.utc).isoformat(timespec="seconds")


class Scheduler:
    """Owns a list of slots and a state file. Pure logic — no time.sleep here."""

    def __init__(self, slots: list[Slot], state_path: Path):
        self.slots = list(slots)
        self.state_path = Path(state_path)
        self.state = ScheduleState.load(self.state_path)

    def due(self, now_utc: datetime | None = None) -> list[Slot]:
        """Return every slot whose fire window is currently open AND that hasn't
        fired today. Multiple slots may fire on the same tick (rare)."""
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        return [s for s in self.slots
                if s.is_due(now_utc, self.state.last_fire(s.name))]

    def mark_fired(self, slot_name: str, at_utc: datetime | None = None) -> None:
        self.state.mark_fired(slot_name, at_utc or datetime.now(timezone.utc))
        self.state.save(self.state_path)

    def next_run_utc(self, now_utc: datetime | None = None) -> datetime | None:
        """Earliest future scheduled fire across all slots, in UTC. None if
        no slot has a next fire (e.g. weekend with weekday-only slots)."""
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        best_utc: datetime | None = None
        # Search up to 8 days ahead — covers any weekday-only schedule.
        for day_offset in range(0, 8):
            probe_utc = now_utc + timedelta(days=day_offset)
            for slot in self.slots:
                offset = timedelta(hours=slot.tz_offset_hours)
                local = probe_utc.astimezone(timezone(offset))
                if local.isoweekday() not in slot.weekdays:
                    continue
                sched_local = local.replace(hour=slot.hour, minute=slot.minute,
                                             second=0, microsecond=0)
                if sched_local <= local and day_offset == 0:
                    # Already past today's slot — check tomorrow instead.
                    continue
                if day_offset > 0:
                    # For future days, use start-of-day probe and re-materialize.
                    sched_local = sched_local
                sched_utc = sched_local.astimezone(timezone.utc)
                if best_utc is None or sched_utc < best_utc:
                    best_utc = sched_utc
        return best_utc


def slots_from_config(spec: list[dict]) -> list[Slot]:
    """Parse a list of {name, hour, minute, weekdays?, fire_window_min?, tz_offset_hours?}
    dicts into Slot objects. Missing fields fall back to sane defaults."""
    out: list[Slot] = []
    for entry in spec:
        out.append(Slot(
            name=str(entry["name"]),
            hour=int(entry["hour"]),
            minute=int(entry["minute"]),
            weekdays=tuple(entry.get("weekdays", (1, 2, 3, 4, 5))),
            fire_window_min=int(entry.get("fire_window_min", DEFAULT_FIRE_WINDOW_MIN)),
            tz_offset_hours=float(entry.get("tz_offset_hours", 5.5)),
        ))
    return out


__all__ = [
    "DEFAULT_FIRE_WINDOW_MIN",
    "Slot",
    "ScheduleState",
    "Scheduler",
    "slots_from_config",
]
