"""Session state · position machine with trailing stops + time-stop enforcement."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Position:
    ticker:     str
    side:       str          # LONG / SHORT
    entry:      float
    size:       int
    stop:       float
    target_1:   float
    target_2:   float
    entered_ts_utc:   str
    high_water: float
    low_water:  float
    partial_taken: bool = False
    closed:     bool = False
    exit_price: float | None = None
    exit_ts_utc: str | None = None
    exit_reason: str | None = None
    signal_id:  str = ""
    slot:       str = ""
    window:     str = ""

    def unrealized_pnl(self, mark: float) -> float:
        if self.side == "LONG":
            return (mark - self.entry) * self.size
        return (self.entry - mark) * self.size


@dataclass
class SessionState:
    market:     str = "india"
    positions:  dict[str, Position] = field(default_factory=dict)
    closed_positions: list[Position] = field(default_factory=list)

    def open(self, pos: Position) -> None:
        self.positions[pos.ticker] = pos

    def mark_to(self, ticker: str, price: float) -> None:
        p = self.positions.get(ticker)
        if p is None or p.closed:
            return
        if price > p.high_water:
            p.high_water = price
        if price < p.low_water:
            p.low_water = price

    # Trailing-stop configuration (ATR-based · dynamic · per operator directive)
    trail_atr_mult:  float = 1.0
    trail_active_after: str = "target_1"   # trail activates only after T1 hit

    def check_exits(self, prices: dict[str, float], now: datetime,
                       force_close: bool = False,
                       atr_map: dict[str, float] | None = None) -> list[Position]:
        """Evaluate every open position against current prices + rules.

        Dynamic trailing-stop behavior (MANDATORY per operator directive):
          · After T1 hit → stop trails at `high_water − trail_atr_mult × ATR`
                             (LONG) or `low_water + mult × ATR` (SHORT)
          · Stop can only move in FAVOUR of the position (never widen against)
        """
        exited: list[Position] = []
        atr_map = atr_map or {}
        for t, p in list(self.positions.items()):
            if p.closed:
                continue
            mark = prices.get(t)
            if mark is None:
                if force_close:
                    self._close(p, p.entry, now, "no_price_at_time_stop")
                    exited.append(p)
                continue
            self.mark_to(t, mark)
            if force_close:
                self._close(p, mark, now, "time_stop_force_close")
                exited.append(p); continue
            atr = atr_map.get(t, abs(p.entry - p.stop) / max(1e-9, self.trail_atr_mult))
            if p.side == "LONG":
                if mark <= p.stop:
                    self._close(p, mark, now, "stop_hit")
                    exited.append(p); continue
                if not p.partial_taken and mark >= p.target_1:
                    p.partial_taken = True
                    p.stop = max(p.stop, p.entry)      # move stop to breakeven at T1
                if p.partial_taken:
                    # Dynamic ATR trailing stop · only moves UP
                    trailing = p.high_water - self.trail_atr_mult * atr
                    p.stop = max(p.stop, trailing)
                if mark >= p.target_2:
                    self._close(p, mark, now, "target_2_hit")
                    exited.append(p); continue
            else:
                if mark >= p.stop:
                    self._close(p, mark, now, "stop_hit")
                    exited.append(p); continue
                if not p.partial_taken and mark <= p.target_1:
                    p.partial_taken = True
                    p.stop = min(p.stop, p.entry)
                if p.partial_taken:
                    trailing = p.low_water + self.trail_atr_mult * atr
                    p.stop = min(p.stop, trailing)
                if mark <= p.target_2:
                    self._close(p, mark, now, "target_2_hit")
                    exited.append(p); continue
        return exited

    def _close(self, p: Position, exit_price: float, now: datetime, reason: str) -> None:
        p.closed = True
        p.exit_price = exit_price
        p.exit_ts_utc = now.isoformat()
        p.exit_reason = reason
        self.closed_positions.append(p)
        self.positions.pop(p.ticker, None)
