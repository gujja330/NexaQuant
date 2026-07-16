"""OPS001-B interrupted-pipeline recovery.

Reads leftover run state (`run_state.json`) written by the daemon each time a
pipeline pass STARTS, and describes what a fresh daemon should do about it.

Recovery philosophy (safe by default):
- If the previous run reached "completed" state — nothing to do.
- If it was still "running" when the daemon exited — safe to re-fire from scratch
  because MON001 stages, AEGIS, dashboard, and Telegram are all idempotent for
  a given asof (they overwrite dated artifacts).
- If it was "aborted" (SIGTERM mid-stage) — emit a WARN alert, then re-fire.

Never mutates the pipeline itself. Only inspects/updates run_state.json.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class RunPhase(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class RecoveryAction(str, Enum):
    NONE = "none"                 # clean state — proceed normally
    RESUME = "resume"             # previous run interrupted mid-flight, safe to re-run
    ATTENTION = "attention"       # previous run in an unexpected state — alert but proceed
    STALE_LOCK = "stale_lock"     # previous run's PID lock left behind


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RunState:
    """The persistent state of a single pipeline pass."""
    pipeline_name: str = ""
    phase: str = RunPhase.IDLE.value
    started_at_utc: str = ""
    updated_at_utc: str = ""
    finished_at_utc: str = ""
    current_stage: str = ""
    stages_completed: list[str] = field(default_factory=list)
    slot_name: str = ""
    pid: int = 0
    last_error: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls, path: Path) -> "RunState":
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            state = cls()
            for k, v in raw.items():
                if hasattr(state, k):
                    setattr(state, k, v)
            return state
        except (json.JSONDecodeError, OSError):
            return cls()

    def save(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.updated_at_utc = _iso_utc()
            path.write_text(json.dumps(self.as_dict(), ensure_ascii=False, indent=2),
                             encoding="utf-8")
        except OSError:
            pass


@dataclass
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    previous_phase: str
    previous_stage: str = ""
    started_at_utc: str = ""
    slot_name: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def decide(state: RunState) -> RecoveryDecision:
    """Given a previous RunState, decide what the freshly-started daemon should do."""
    if state.phase in (RunPhase.IDLE.value, RunPhase.COMPLETED.value):
        return RecoveryDecision(
            action=RecoveryAction.NONE,
            reason=f"previous phase '{state.phase}' — no recovery needed",
            previous_phase=state.phase,
            previous_stage=state.current_stage,
            started_at_utc=state.started_at_utc,
            slot_name=state.slot_name,
        )
    if state.phase == RunPhase.RUNNING.value or state.phase == RunPhase.STARTING.value:
        return RecoveryDecision(
            action=RecoveryAction.RESUME,
            reason=(f"previous pass was in phase '{state.phase}' at stage "
                    f"'{state.current_stage or '<none>'}' when the daemon exited"),
            previous_phase=state.phase,
            previous_stage=state.current_stage,
            started_at_utc=state.started_at_utc,
            slot_name=state.slot_name,
        )
    if state.phase == RunPhase.ABORTED.value:
        return RecoveryDecision(
            action=RecoveryAction.RESUME,
            reason=("previous pass was aborted mid-flight (SIGTERM / process kill) "
                    f"at stage '{state.current_stage or '<none>'}'"),
            previous_phase=state.phase,
            previous_stage=state.current_stage,
            started_at_utc=state.started_at_utc,
            slot_name=state.slot_name,
        )
    if state.phase == RunPhase.FAILED.value:
        return RecoveryDecision(
            action=RecoveryAction.ATTENTION,
            reason=("previous pass FAILED — re-firing on next slot but review "
                    f"logs. last_error='{state.last_error or '<no message>'}'"),
            previous_phase=state.phase,
            previous_stage=state.current_stage,
            started_at_utc=state.started_at_utc,
            slot_name=state.slot_name,
        )
    return RecoveryDecision(
        action=RecoveryAction.ATTENTION,
        reason=f"unrecognized previous phase '{state.phase}'",
        previous_phase=state.phase,
        previous_stage=state.current_stage,
        started_at_utc=state.started_at_utc,
        slot_name=state.slot_name,
    )


def mark_starting(path: Path, pipeline_name: str, slot_name: str, pid: int) -> RunState:
    st = RunState(
        pipeline_name=pipeline_name,
        phase=RunPhase.STARTING.value,
        started_at_utc=_iso_utc(),
        current_stage="",
        stages_completed=[],
        slot_name=slot_name,
        pid=pid,
    )
    st.save(path)
    return st


def mark_running(path: Path, current_stage: str) -> None:
    st = RunState.load(path)
    st.phase = RunPhase.RUNNING.value
    st.current_stage = current_stage
    st.save(path)


def mark_stage_completed(path: Path, stage_name: str) -> None:
    st = RunState.load(path)
    if stage_name not in st.stages_completed:
        st.stages_completed.append(stage_name)
    st.save(path)


def mark_completed(path: Path) -> None:
    st = RunState.load(path)
    st.phase = RunPhase.COMPLETED.value
    st.finished_at_utc = _iso_utc()
    st.current_stage = ""
    st.save(path)


def mark_failed(path: Path, err: str) -> None:
    st = RunState.load(path)
    st.phase = RunPhase.FAILED.value
    st.finished_at_utc = _iso_utc()
    st.last_error = err[:2048]
    st.save(path)


def mark_aborted(path: Path, reason: str) -> None:
    st = RunState.load(path)
    st.phase = RunPhase.ABORTED.value
    st.finished_at_utc = _iso_utc()
    st.last_error = reason[:2048]
    st.save(path)


__all__ = [
    "RunPhase",
    "RecoveryAction",
    "RunState",
    "RecoveryDecision",
    "decide",
    "mark_starting",
    "mark_running",
    "mark_stage_completed",
    "mark_completed",
    "mark_failed",
    "mark_aborted",
]
