"""Fail the run when a CRITICAL orchestrator step failed. Replaces `|| echo`.

WHY
---
The India workflow called the daily orchestrator as:

    python scripts/aegis_daily_v2.py --continue || echo "...(non-fatal)"

`|| echo` discarded the exit code, so a failed step - including one the
step table marks `optional: False`, meaning "a silent failure here makes
the next stage score yesterday's data and look healthy doing it" - was
indistinguishable from success.

Because the artifacts those steps write are TRACKED, a failed fetch does
not leave a gap. It leaves last week's committed data sitting in place,
looking entirely plausible, until the run contract blocks several steps
later naming a source nobody would trace back here.

THREE CLASSES, DELIBERATELY DISTINCT
------------------------------------
  critical  a non-optional producer that failed OR wrote nothing. Stale
            substrate must never reach scoring, so this FAILS the run.
            "Wrote nothing" counts: a feature store that exits 0 having
            refreshed no artifact means the day's recommendations are
            scored from stale features.

  reporter  a step that exits non-zero when it FINDS problems rather
            than when it breaks - ops_check is the case. Surfaced
            loudly, never blocking. Delivery authority belongs to the
            run contract's eight gates; a broader, research-inclusive
            health signal must not quietly outrank it.

  optional  everything marked optional=True. One flaky news fetch must
            not cost the day's delivery - that trades a silent failure
            for a loud outage, which is not a fix either.

Exit codes:
  0  OK, REPORTER_FINDINGS or DEGRADED
  1  CRITICAL_FAILURE - a non-optional step failed or refreshed nothing
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
    crit = v.get("critical_failures") or []
    rep = v.get("reporter_findings") or []
    opt = v.get("optional_failures") or []

    print("ORCHESTRATOR VERDICT  %s" % v.get("verdict"))
    print("  steps   %s   success %s   failed %s"
          % (v.get("n_steps"), v.get("n_success"), v.get("n_failure")))

    if rep:
        print("")
        print("  REPORTER FINDINGS - these ran correctly and FOUND problems.")
        print("  They do not block delivery; the run contract holds that")
        print("  authority. They are real debt, not noise:")
        for r in rep:
            print("     %-22s %s" % (r.get("step"),
                                     str(r.get("note") or "")[:100]))
    if opt:
        print("  DEGRADED - optional step(s) failed, not fatal: %s"
              % ", ".join(opt))

    if not crit:
        print("")
        print("OK - every non-optional step succeeded and refreshed.")
        return 0

    print("")
    print("CRITICAL - %d non-optional step(s) failed or refreshed nothing:"
          % len(crit))
    for c in crit:
        print("  %-26s %s" % (c.get("step"), c.get("verdict")))
        if c.get("not_refreshed"):
            print("       did not refresh: %s"
                  % ", ".join(c["not_refreshed"][:6]))
        for ln in (c.get("stderr_tail") or [])[-3:]:
            print("       err: %s" % str(ln)[:120])
    print("")
    print("These steps write TRACKED artifacts, so their failure does not")
    print("leave a gap - it leaves the last committed copy in place, which")
    print("reads as fresh to everything downstream. Failing here, where the")
    print("cause is named, instead of at the run contract several steps on.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
