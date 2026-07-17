"""Wrapper around `python india/telegram_notify.py` with retry + delivery log.

Non-invasive: does NOT modify india/telegram_notify.py. Preserves the operator
directive "do not touch Telegram core". Instead:

- runs telegram_notify.py as a subprocess
- captures its stdout and searches for success/failure markers
- retries with exponential backoff on failure
- appends every attempt to `reports/telegram_delivery_<YYYY-MM-DD>.jsonl`
- exits 0 only after at least one successful send
- exits 1 after all retries exhausted

Called by `.github/workflows/aegis-daily.yml` in place of the direct
`python india/telegram_notify.py` line (which was masked by `|| echo`).

Run:
    python scripts/telegram_send_with_retry.py             # 3 attempts default
    python scripts/telegram_send_with_retry.py --attempts 5
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
NOTIFY = ROOT / "india" / "telegram_notify.py"
AEGIS_TODAY = ROOT / "data" / "aegis_today.csv"


def _today_ist_str() -> str:
    """Today's IST calendar date as YYYY-MM-DD (independent of host TZ).
    IST is UTC+5:30; no DST in India."""
    from datetime import timedelta
    utc = datetime.now(timezone.utc)
    ist = utc + timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d")


def _pre_send_freshness_check() -> tuple[bool, str]:
    """OPS001-F defense-in-depth: refuse to send if aegis_today.csv is
    missing or was generated on a date other than today IST.

    Returns (ok, reason). If ok=False the caller MUST NOT send and MUST
    return a non-zero exit code so the workflow fails visibly.
    """
    if not AEGIS_TODAY.exists():
        return False, f"aegis_today.csv missing at {AEGIS_TODAY}"
    try:
        # Row-1 = header; row-2 = first data row; first column is `Generated`.
        with AEGIS_TODAY.open("r", encoding="utf-8") as f:
            _hdr = f.readline()
            first = f.readline()
    except OSError as e:
        return False, f"aegis_today.csv unreadable: {e}"
    if not first.strip():
        return False, "aegis_today.csv has no data rows"
    generated = first.split(",", 1)[0].strip().strip('"')
    today_ist = _today_ist_str()
    if generated != today_ist:
        return False, (f"aegis_today.csv Generated={generated!r} != today IST={today_ist!r} "
                       f"— refusing to send stale recommendations")
    return True, f"aegis_today.csv Generated={generated} matches today IST={today_ist}"

# Backoff schedule (seconds between attempts). Attempt count = len + 1.
DEFAULT_BACKOFF: tuple[float, ...] = (5.0, 15.0, 45.0)

# Signals in telegram_notify.py's stdout that indicate outcome.
SUCCESS_MARKERS: tuple[str, ...] = ("sent (",)
FAILURE_MARKERS: tuple[str, ...] = (
    "cannot send",
    "send failed",
    "returned not-ok",
    "MISSING TELEGRAM",
)


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _classify(stdout: str) -> tuple[str, str]:
    """Return (verdict, matched_marker). verdict ∈ {'SUCCESS','FAILURE','UNKNOWN'}."""
    for m in FAILURE_MARKERS:
        if m in stdout:
            return "FAILURE", m
    for m in SUCCESS_MARKERS:
        if m in stdout:
            return "SUCCESS", m
    return "UNKNOWN", ""


def _append_ledger(record: dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    date = _iso_utc()[:10]
    p = REPORTS / f"telegram_delivery_{date}.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return p


def _run_notify(python_exe: str) -> tuple[int, str, str]:
    """Run telegram_notify.py once and return (exit_code, stdout, stderr)."""
    r = subprocess.run(
        [python_exe, str(NOTIFY)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return r.returncode, r.stdout or "", r.stderr or ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=len(DEFAULT_BACKOFF) + 1,
                     help="Max attempts (default: 4 = 1 initial + 3 retries)")
    args = ap.parse_args()

    n_attempts = max(1, int(args.attempts))
    backoff = list(DEFAULT_BACKOFF) + [DEFAULT_BACKOFF[-1]] * max(
        0, n_attempts - 1 - len(DEFAULT_BACKOFF))

    python_exe = sys.executable

    print("=" * 60)
    print(f"  Telegram send with retry — up to {n_attempts} attempt(s)")
    print(f"  wrapper started at {_iso_utc()}")
    print("=" * 60)

    # OPS001-F: refuse to send stale recommendations. This is a
    # defense-in-depth check independent of the workflow-level freshness
    # gate — protects against any invocation path that bypasses the gate.
    ok, reason = _pre_send_freshness_check()
    if not ok:
        print(f"  FRESHNESS CHECK FAILED: {reason}")
        _append_ledger({
            "wrapper_ts_start_utc": _iso_utc(),
            "attempt": 0,
            "max_attempts": n_attempts,
            "verdict": "REFUSED_STALE",
            "matched_marker": "pre_send_freshness_check",
            "notify_exit_code": None,
            "elapsed_s": 0.0,
            "stdout_tail": [reason],
            "stderr_tail": [],
        })
        return 2
    print(f"  freshness check: {reason}")

    for attempt in range(1, n_attempts + 1):
        ts_start = _iso_utc()
        t0 = time.perf_counter()
        exit_code, stdout, stderr = _run_notify(python_exe)
        elapsed = time.perf_counter() - t0
        verdict, marker = _classify(stdout + "\n" + stderr)

        # Print notify's own stdout so operators see the same content in the
        # GitHub Actions log.
        for line in (stdout + stderr).splitlines():
            print(f"  [notify] {line}")
        print(f"  attempt {attempt}/{n_attempts}: verdict={verdict} "
               f"(marker={marker!r}) exit={exit_code} elapsed={elapsed:.2f}s")

        record = {
            "wrapper_ts_start_utc": ts_start,
            "attempt": attempt,
            "max_attempts": n_attempts,
            "verdict": verdict,
            "matched_marker": marker,
            "notify_exit_code": exit_code,
            "elapsed_s": round(elapsed, 3),
            "stdout_tail": (stdout.splitlines()[-8:] if stdout else []),
            "stderr_tail": (stderr.splitlines()[-4:] if stderr else []),
        }
        _append_ledger(record)

        if verdict == "SUCCESS":
            print(f"  Telegram send succeeded on attempt {attempt}/{n_attempts}.")
            return 0

        if attempt < n_attempts:
            wait_s = backoff[attempt - 1]
            print(f"  attempt {attempt} failed — sleeping {wait_s:.0f}s before retry")
            time.sleep(wait_s)

    print(f"  ALL {n_attempts} attempts failed. Emitting non-zero exit to make "
           "the workflow visibly fail.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
