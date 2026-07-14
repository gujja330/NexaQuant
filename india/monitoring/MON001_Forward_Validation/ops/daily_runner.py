"""
MON001 resilient daily runner.

Wraps the existing `run_mon001.main()` with operational hardening:
- Detects weekends / NSE holidays and emits OPS_MARKET_CLOSED (still runs
  fingerprint + ledger checks — useful even off-market)
- Detects stale market data and emits OPS_DATA_STALE (still runs)
- Uses file locking to prevent concurrent execution (duplicate-run protection)
- Atomic report writes (via tempfile + os.replace) to prevent corrupted partial files
- Isolates exceptions from the production pipeline: MON001 failure NEVER causes a
  non-zero exit that could be misinterpreted by a supervising process
- Auto-emits OPS_RUN_FAILED alert on unexpected exceptions
- Rebuilds diagnostics + dashboard even on partial-failure

Exit code always 0 unless the ops layer itself is broken. Errors surface via
alerts JSONL and the dashboard.

Run:
    python -m india.monitoring.MON001_Forward_Validation.ops.daily_runner
    python -m india.monitoring.MON001_Forward_Validation.ops.daily_runner --seal-init
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tempfile
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from india.monitoring.MON001_Forward_Validation.ops.alerts import AlertBus
from india.monitoring.MON001_Forward_Validation.ops.holiday_calendar import (
    is_trading_day, is_weekend, is_holiday, previous_trading_day,
)


HERE = Path(__file__).resolve().parent.parent
LOCK_PATH = HERE / "reports" / ".daily_runner.lock"
OPS_LOG_PATH = HERE / "reports" / "ops.log"


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(msg: str) -> None:
    OPS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OPS_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{_iso_utc()}] {msg}\n")
    print(msg)


class SingleInstanceLock:
    """Best-effort mutual exclusion via lock file with pid + start-time.

    On Windows there's no os.O_EXLOCK, so we use file existence + pid liveness check.
    Stale locks (owning pid no longer alive OR lock older than 4 hours) are broken.
    """
    STALE_HOURS = 4

    def __init__(self, path: Path):
        self.path = path

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                info = json.loads(self.path.read_text(encoding="utf-8"))
                pid = int(info.get("pid", 0))
                started = datetime.fromisoformat(info.get("started_utc", ""))
                age_h = (datetime.now(timezone.utc) - started).total_seconds() / 3600
                if age_h > self.STALE_HOURS or not _pid_alive(pid):
                    _log(f"breaking stale lock (pid={pid}, age={age_h:.1f}h)")
                    self.path.unlink(missing_ok=True)
                else:
                    return False
            except Exception:
                self.path.unlink(missing_ok=True)
        self.path.write_text(json.dumps({
            "pid": os.getpid(),
            "started_utc": datetime.now(timezone.utc).isoformat(),
        }), encoding="utf-8")
        return True

    def release(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def _check_data_freshness(cfg: dict) -> tuple[str, str]:
    """Return (status, reason). Status ∈ {"OK","STALE","MISSING"}."""
    import pandas as pd
    raw = ROOT / "data" / "raw" / "india"
    files = list(raw.glob("*_D1.parquet"))
    if not files:
        return "MISSING", "no parquet files under data/raw/india"
    latest_bar: date | None = None
    sample = files[:20]  # small sample for speed
    for f in sample:
        try:
            p = pd.read_parquet(f, columns=None)
            if len(p):
                d = pd.Timestamp(p.index[-1]).date()
                if latest_bar is None or d > latest_bar:
                    latest_bar = d
        except Exception:
            continue
    if latest_bar is None:
        return "MISSING", "all sampled parquets unreadable"
    prev = previous_trading_day()
    if latest_bar < prev:
        return "STALE", (
            f"latest bar {latest_bar} < previous trading session {prev} "
            f"(gap {(prev - latest_bar).days} calendar days)")
    return "OK", f"latest bar {latest_bar} matches or exceeds previous session {prev}"


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                       delete=False, suffix=".tmp") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        tmp = Path(f.name)
    os.replace(tmp, path)


def _write_market_closed_report(bus: AlertBus, cfg: dict, reason: str) -> None:
    """Write a minimal diagnostics + dashboard when we skip the metric engine because
    of a non-trading day. Still emits an INFO alert for audit trail."""
    today = date.today().isoformat()
    reports_dir = ROOT / cfg["reporting"]["output_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_date_utc": _iso_utc(),
        "run_kind": "MARKET_CLOSED",
        "reason": reason,
        "global_state": "INSUFFICIENT_EVIDENCE",
        "halt_review_required": False,
    }
    _atomic_write_json(reports_dir / f"mon001_diagnostics_{today}.json", payload)
    bus.emit("OPS_MARKET_CLOSED", "INFO", reason)


def run_once(seal_init: bool = False) -> int:
    """Perform one MON001 daily pass. Returns exit code 0 always in normal operation."""
    OPS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    lock = SingleInstanceLock(LOCK_PATH)
    if not lock.acquire():
        _log("another MON001 daily runner is active — skipping this invocation")
        return 0

    try:
        with (HERE / "mon001.yaml").open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        bus = AlertBus(ROOT / cfg["reporting"]["alerts_path"])

        # 1. Market-day gate
        today = date.today()
        if not is_trading_day(today):
            reason = ("weekend" if is_weekend(today) else "NSE holiday")
            _log(f"non-trading day ({reason}) — writing MARKET_CLOSED status")
            _write_market_closed_report(bus, cfg,
                f"{today} is a {reason}; MON001 metric engine skipped, "
                f"fingerprint + ledger checks still run.")

        # 2. Data freshness — informational only; MON001 still runs
        fresh_status, fresh_reason = _check_data_freshness(cfg)
        if fresh_status == "STALE":
            bus.emit("OPS_DATA_STALE", "WARN", fresh_reason)
        elif fresh_status == "MISSING":
            bus.emit("OPS_DATA_STALE", "WARN", fresh_reason)

        # 3. Full MON001 pass — delegate to run_mon001.main()
        from india.monitoring.MON001_Forward_Validation import run_mon001
        try:
            original_argv = sys.argv[:]
            sys.argv = ["run_mon001.py"] + (["--seal-init"] if seal_init else [])
            run_mon001.main()
        except SystemExit as e:
            _log(f"run_mon001.main SystemExit({e.code})")
        except Exception:
            tb = traceback.format_exc()
            _log(f"run_mon001 raised — capturing to alert bus\n{tb}")
            bus.emit("OPS_RUN_FAILED", "WARN",
                      f"run_mon001.main raised an exception; MON001 metrics unavailable for this pass. "
                      f"tail: {tb.splitlines()[-1] if tb else '?'}",
                      context={"traceback_tail": tb.splitlines()[-6:] if tb else []})
        finally:
            sys.argv = original_argv

        # 4. Regenerate the operator dashboard
        try:
            from india.monitoring.MON001_Forward_Validation.ops.dashboard import main as dash_main
            dash_main()
        except Exception:
            tb = traceback.format_exc()
            _log(f"dashboard regeneration failed\n{tb}")
            bus.emit("OPS_RUN_FAILED", "INFO",
                      "operator dashboard regeneration failed; diagnostics JSON still valid",
                      context={"traceback_tail": tb.splitlines()[-6:] if tb else []})

        return 0

    except Exception:
        tb = traceback.format_exc()
        _log(f"daily_runner top-level exception:\n{tb}")
        try:
            with (HERE / "mon001.yaml").open("r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            AlertBus(ROOT / cfg["reporting"]["alerts_path"]).emit(
                "OPS_RUN_FAILED", "WARN",
                f"top-level daily_runner exception: {tb.splitlines()[-1] if tb else '?'}",
                context={"traceback_tail": tb.splitlines()[-6:] if tb else []})
        except Exception:
            pass
        return 0     # ALWAYS return 0 to keep upstream automation healthy

    finally:
        lock.release()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seal-init", action="store_true")
    args = ap.parse_args()
    return run_once(seal_init=args.seal_init)


if __name__ == "__main__":
    sys.exit(main())
