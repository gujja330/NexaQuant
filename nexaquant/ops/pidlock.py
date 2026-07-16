"""OPS001-B daemon-scope PID lock with stale detection.

Distinct from MON001's SingleInstanceLock (which guards a single MON001 pipeline
pass). This lock guards the *daemon process itself* — only one nexaquant daemon
may run per host.

Design:
- Lock file is a JSON object: {pid, started_utc, host, cmdline}.
- acquire() creates the file if absent, breaks stale locks (dead pid OR age
  above the configured stale window).
- release() removes the file if the current process owns it. Never raises.
- read() returns the current holder metadata (or None if unlocked).

Portable across Windows and Linux: uses os.kill(pid, 0) for liveness check
(the Windows Python behaves correctly here), and a well-defined process-start
time check as a fallback.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_STALE_HOURS = 6.0


@dataclass
class LockHolder:
    pid: int
    started_utc: str
    host: str
    cmdline: str

    def as_dict(self) -> dict:
        return {"pid": self.pid, "started_utc": self.started_utc,
                "host": self.host, "cmdline": self.cmdline}

    @classmethod
    def current(cls) -> "LockHolder":
        return cls(
            pid=os.getpid(),
            started_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            host=socket.gethostname(),
            cmdline=" ".join(sys.argv),
        )


def _pid_alive(pid: int) -> bool:
    """Return True if the given pid corresponds to a live process. Cross-platform."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but not owned by us; still counts as alive.
        return True
    except OSError:
        return False
    return True


def _age_hours(started_utc_iso: str) -> float:
    try:
        dt = datetime.fromisoformat(started_utc_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return float("inf")


class PidLock:
    """File-based PID lock. Not a mutex — a cooperative marker.

    Two independent processes racing on acquire() may both succeed on the
    same instant; that's tolerable here because callers only spin up daemons
    from systemd/Task Scheduler (single-shot) or from an operator CLI, both
    of which serialize naturally.
    """

    def __init__(self, path: Path | str, stale_hours: float = DEFAULT_STALE_HOURS):
        self.path = Path(path)
        self.stale_hours = float(stale_hours)
        self._owned = False

    def _read_raw(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def read(self) -> LockHolder | None:
        d = self._read_raw()
        if not d:
            return None
        try:
            return LockHolder(
                pid=int(d.get("pid", 0)),
                started_utc=str(d.get("started_utc", "")),
                host=str(d.get("host", "")),
                cmdline=str(d.get("cmdline", "")),
            )
        except (ValueError, TypeError):
            return None

    def is_stale(self, holder: LockHolder) -> tuple[bool, str]:
        if not _pid_alive(holder.pid):
            return True, f"pid {holder.pid} is dead"
        if _age_hours(holder.started_utc) > self.stale_hours:
            return True, (f"held for {_age_hours(holder.started_utc):.1f}h "
                          f"(> stale_hours={self.stale_hours})")
        return False, "live"

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns True if acquired (or stole a stale
        lock), False if a live holder blocks us."""
        holder = self.read()
        if holder is not None:
            stale, reason = self.is_stale(holder)
            if not stale:
                return False
            # Stale: break it.
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(LockHolder.current().as_dict(), ensure_ascii=False),
                encoding="utf-8")
        except OSError:
            return False
        self._owned = True
        return True

    def release(self) -> None:
        if not self._owned:
            return
        try:
            existing = self.read()
            if existing and existing.pid == os.getpid():
                self.path.unlink()
        except OSError:
            pass
        finally:
            self._owned = False

    def refresh(self) -> None:
        """Rewrite the lock with a bumped started_utc — used by long-running
        daemons to keep age below stale_hours on quiet nights (no pipeline runs).
        Only writes if we own the lock."""
        if not self._owned:
            return
        try:
            existing = self.read()
            if not existing or existing.pid != os.getpid():
                return
            fresh = LockHolder.current()
            self.path.write_text(
                json.dumps(fresh.as_dict(), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    @property
    def owned(self) -> bool:
        return self._owned


__all__ = [
    "DEFAULT_STALE_HOURS",
    "LockHolder",
    "PidLock",
]
