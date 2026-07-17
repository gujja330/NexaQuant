"""DEV027 — Strategy Doctor · CLI."""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from strategy_doctor.compute import engine                                              # noqa: E402
from strategy_doctor.publish import bundle as publish                                     # noqa: E402


ROOT = HERE.parents[1]


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _now_ist() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")


def _banner(msg: str) -> None:
    print(); print("=" * 70); print(f"  {msg}"); print("=" * 70)


def main() -> int:
    t0 = time.time()
    _banner("DEV027 - STRATEGY DOCTOR ENGINE")
    print(f"  time (IST): {_now_ist()}")
    print(f"  code_sha:   {_git_sha()}")

    _banner("STEP 1/2 · Run diagnostics")
    result = engine.run(verbose=True)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    _banner("STEP 2/2 · Publish 6 outputs")
    publish.build_and_publish(result)

    _banner("STRATEGY DOCTOR SUMMARY")
    print(f"  Trades diagnosed:      {result['n_trades']}")
    print(f"  Winners / Losers:      {result['n_winners']} / {result['n_losers']}")
    print(f"  Total diagnoses fired: {result['n_diagnoses_fired']}")
    print()
    print(f"  TOP FAILURE CATEGORIES:")
    for f in result["failure_patterns"][:8]:
        print(f"    {f['category']:<28}  {f['count']} occurrences")

    print()
    print(f"  TOP WINNING SECTORS:")
    for sec, cnt in result["success_patterns"]["top_winning_sectors"][:5]:
        print(f"    {sec:<28}  {cnt} winners")

    print()
    print(f"  IMPROVEMENT PLAN ({len(result['improvement_plan'])} items):")
    for item in result["improvement_plan"][:5]:
        print(f"    [{item['failure_category']}] {item['action'][:60]}")
        print(f"         target: {item['target_module']}")

    _banner("DEV027 · DONE")
    print(f"  elapsed: {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
