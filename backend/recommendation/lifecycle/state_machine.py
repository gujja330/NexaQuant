"""Recommendation Lifecycle State Machine · Constitution-compliant.

Deterministic transitions. Every event append-only. Every transition
validated by `is_valid_transition()`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable

SCHEMA_FINGERPRINT = "aegis.recommendation_lifecycle.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.recommendation.lifecycle.v1"


class RecommendationState(str, Enum):
    DISCOVERED = "DISCOVERED"     # first appearance in candidate universe
    WATCHLIST  = "WATCHLIST"      # analyst-monitored, not sized
    BUY        = "BUY"            # entry decision made
    ADD        = "ADD"            # additional capital deployed
    HOLD       = "HOLD"           # steady state
    TRIM       = "TRIM"           # partial reduction
    EXIT       = "EXIT"           # full exit signaled
    ROTATED    = "ROTATED"        # replaced by a candidate via Capital Rotation
    ARCHIVED   = "ARCHIVED"       # closed · historical


# Legal transitions (directed graph). Any transition not listed is INVALID.
# Institutional practice: DISCOVERED can go directly to HOLD (fresh signal
# we chose not to act on · monitor mode) OR to WATCHLIST (formal analyst
# tracking).
VALID_TRANSITIONS: dict[RecommendationState, set[RecommendationState]] = {
    RecommendationState.DISCOVERED: {RecommendationState.WATCHLIST, RecommendationState.HOLD,
                                       RecommendationState.BUY, RecommendationState.ARCHIVED},
    RecommendationState.WATCHLIST:  {RecommendationState.HOLD, RecommendationState.BUY,
                                       RecommendationState.DISCOVERED, RecommendationState.ARCHIVED},
    RecommendationState.BUY:        {RecommendationState.ADD, RecommendationState.HOLD, RecommendationState.TRIM, RecommendationState.EXIT, RecommendationState.ROTATED},
    RecommendationState.ADD:        {RecommendationState.HOLD, RecommendationState.TRIM, RecommendationState.EXIT, RecommendationState.ROTATED},
    RecommendationState.HOLD:       {RecommendationState.ADD, RecommendationState.BUY, RecommendationState.TRIM, RecommendationState.EXIT, RecommendationState.ROTATED, RecommendationState.HOLD, RecommendationState.WATCHLIST},
    RecommendationState.TRIM:       {RecommendationState.HOLD, RecommendationState.EXIT, RecommendationState.ROTATED},
    RecommendationState.EXIT:       {RecommendationState.ARCHIVED, RecommendationState.ROTATED},
    RecommendationState.ROTATED:    {RecommendationState.ARCHIVED},
    RecommendationState.ARCHIVED:   set(),   # terminal
}


def is_valid_transition(from_state: RecommendationState, to_state: RecommendationState) -> bool:
    if from_state == to_state and from_state == RecommendationState.HOLD:
        return True   # HOLD self-loop explicitly allowed (daily recheck)
    return to_state in VALID_TRANSITIONS.get(from_state, set())


@dataclass(frozen=True)
class LifecycleEvent:
    ticker: str
    state: RecommendationState
    ts_utc: str
    reason: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LifecycleTransition:
    ticker: str
    from_state: RecommendationState | None
    to_state: RecommendationState
    ts_utc: str
    reason: str
    valid: bool
    metadata: dict = field(default_factory=dict)


@dataclass
class LifecycleRecord:
    ticker: str
    current_state: RecommendationState
    events: list[dict] = field(default_factory=list)   # append-only history
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    schema_version: str = SCHEMA_VERSION


class LifecycleLedger:
    """Deterministic append-only ledger over ticker lifecycles.

    Persist as JSONL (one event per line). Ledger is idempotent: replaying
    same events produces same records.
    """

    def __init__(self) -> None:
        self.records: dict[str, LifecycleRecord] = {}

    @property
    def n_tickers(self) -> int:
        return len(self.records)

    def apply(self, ticker: str, to_state: RecommendationState,
                reason: str = "", metadata: dict | None = None,
                ts_utc: str | None = None) -> LifecycleTransition:
        rec = self.records.get(ticker)
        from_state = rec.current_state if rec else None
        # First-ever event bootstraps DISCOVERED if not otherwise specified
        if from_state is None and to_state != RecommendationState.DISCOVERED:
            # Bootstrap DISCOVERED first
            self._append_event(ticker, RecommendationState.DISCOVERED,
                                reason="lifecycle bootstrap", metadata={},
                                ts_utc=ts_utc)
            from_state = RecommendationState.DISCOVERED
        valid = from_state is None or is_valid_transition(from_state, to_state)
        if not valid:
            raise ValueError(
                f"invalid transition for {ticker}: {from_state} -> {to_state}. "
                f"Allowed: {sorted(s.value for s in VALID_TRANSITIONS.get(from_state, set()))}")
        self._append_event(ticker, to_state, reason=reason,
                            metadata=metadata or {}, ts_utc=ts_utc)
        return LifecycleTransition(
            ticker=ticker, from_state=from_state, to_state=to_state,
            ts_utc=self.records[ticker].events[-1]["ts_utc"],
            reason=reason, valid=True, metadata=metadata or {},
        )

    def _append_event(self, ticker: str, state: RecommendationState,
                       reason: str, metadata: dict, ts_utc: str | None) -> None:
        ts = ts_utc or datetime.now(timezone.utc).isoformat()
        evt = {"state": state.value, "ts_utc": ts, "reason": reason,
                "metadata": metadata}
        if ticker not in self.records:
            self.records[ticker] = LifecycleRecord(
                ticker=ticker, current_state=state, events=[evt])
        else:
            self.records[ticker].events.append(evt)
            self.records[ticker].current_state = state

    def to_dict(self) -> dict:
        return {
            "engine": ENGINE_ID,
            "version": "1.0.0",
            "schema_version": SCHEMA_VERSION,
            "schema_fingerprint": SCHEMA_FINGERPRINT,
            "n_tickers": self.n_tickers,
            "records": {t: asdict(r) for t, r in self.records.items()},
        }

    def write_jsonl(self, path: Path) -> int:
        """Append every event to a JSONL ledger. Returns bytes written."""
        n = 0
        with path.open("a", encoding="utf-8") as f:
            for ticker, rec in self.records.items():
                for evt in rec.events:
                    f.write(json.dumps({"ticker": ticker, **evt}) + "\n")
                    n += 1
        return n

    @classmethod
    def from_jsonl(cls, path: Path) -> "LifecycleLedger":
        ledger = cls()
        if not path.exists():
            return ledger
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            evt = json.loads(line)
            ticker = evt["ticker"]
            state = RecommendationState(evt["state"])
            ledger._append_event(ticker, state, evt.get("reason", ""),
                                   evt.get("metadata", {}), evt.get("ts_utc"))
        return ledger
