"""Signal base + score contract + registry."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..session_clock import SessionWindow, TradingSlot


@dataclass
class SignalScore:
    signal_id:      str
    ticker:         str
    direction:      str      # "LONG" | "SHORT" | "SKIP"
    score:          float    # magnitude · [-1, +1] typical
    entry:          float    # suggested entry price
    stop:           float    # hard stop
    target_1:       float    # T1
    target_2:       float    # T2
    at_ts_utc:      str      # ISO timestamp
    window:         str      # SessionWindow value
    slot:           str      # TradingSlot value
    reasoning:      str = ""
    metadata:       dict = field(default_factory=dict)


class SignalBase:
    """Base class · subclasses declare active slots/windows + implement compute()."""
    signal_id:      str = "abstract"
    display_name:   str = "Abstract Signal"
    active_slots:   list[TradingSlot] = []
    active_windows: list[SessionWindow] = []

    def is_active(self, slot: TradingSlot | str, window: SessionWindow | str) -> bool:
        s = slot.value if isinstance(slot, TradingSlot) else slot
        w = window.value if isinstance(window, SessionWindow) else window
        slots_ok = not self.active_slots or any(
            (x.value if isinstance(x, TradingSlot) else x) == s for x in self.active_slots)
        windows_ok = not self.active_windows or any(
            (x.value if isinstance(x, SessionWindow) else x) == w for x in self.active_windows)
        return slots_ok and windows_ok

    def compute(self, bars, meta: dict) -> SignalScore | None:
        raise NotImplementedError


SIGNAL_REGISTRY: dict[str, type] = {}


def register(cls):
    """Class decorator to auto-add signals to the global registry."""
    SIGNAL_REGISTRY[cls.signal_id] = cls
    return cls
