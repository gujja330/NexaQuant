"""Fail the run when a CRITICAL orchestrator step failed. Replaces `|| echo`.

WHY
---
The India workflow called the daily orchestrator as:

    python scripts/aegis_daily_v2.py --continue || echo "...(non-fatal)"

`|| echo` discards the exit code, so a failed step - including one the
step table marks `optional: False`, meaning "a silent failure here makes
the next stage score yesterday's data and look healthy doing it" - was
indistinguishable from success.

Because the artifacts those steps write are TRACKED, a failed fetch does
not leave a gap. It leaves last week's committed data sitting in place,
looking entirely plausible, until the run contract blocks several steps
later naming a source nobody would trace back here.

WHAT THIS DOES NOT DO
---------------------
It does not fail on optional steps. One flaky news-sentiment fetch must
not cost the day's delivery - that would be trading a silent failure for
a loud outage, not a fix. Optional failures are reported as DEGRADED and
the run continues.

Exit codes:
  0  OK or DEGRADED (optional steps failed · reported, not fatal)
  1  CRITICAL_FAILURE - a non-optional step did not succeed
  2  no verdict file - the orchestrator did not reach the end of main()
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="india", choices=["india"])
    a = ap.parse_args()

    p = ROOT / "reports" / "context" / ("orchestrator_verdict_%s.json"
                                        % a.market)
    if not p.exists():
        print("NO VERDICT at %s" % p.relative_to(ROOT))
        print("The orchestrator did not reach the end of main(). That is")
        print("itself a failure - it means the process died rather than")
        print("completing with failures, so no step list exists to judge.")
        return 2

    v = json.loads(p.read_text(encoding="utf-8"))
    verdict = v.get("verdict")
    crit = v.get("critical_failures") or []
    opt = v.get("optional_failures") or []

    print("ORCHESTRATOR VERDICT  %s" % verdict)
    print("  steps   %s   success %s   failed %s"
          % (v.get("n_steps"), v.get("n_success"), v.get("n_failure")))
    if opt:
        print("  DEGRADED · optional step(s) failed, not fatal: %s"
              % ", ".join(opt))
    if not crit:
        print("\nOK - every non-optional step succeeded.")
        return 0

    print("\nCRITICAL - %d non-optional step(s) failed:" % len(crit))
    for c in crit:
        print("  %-24s %-16s %s" % (c.get("step"), c.get("verdict"),
                                    c.get("note", "")[:120]))
    print("\nThese steps write TRACKED artifacts, so their failure does not")
    print("leave a gap - it leaves the last committed copy in place, which")
    print("reads as fresh to everything downstream. Failing here, where the")
    print("cause is named, instead of at the run contract several steps on.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
