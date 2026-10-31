"""Fail a run whose delivery was blocked, and name the blocking rows.

WHY THIS EXISTS
---------------
USA certified for weeks while delivering nothing. The run contract wrote
"FINAL: CERTIFIED", the workflow concluded success, and the operator
received no workbook. The gate that actually decided was
`xlsx_validator.should_block_send`, which runs inside the sender AFTER
certification - and the report naming the blocking rows was written on
the runner every morning and never committed.

So the one file that answered "why did nothing arrive?" was produced and
discarded on every run, while Actions logs return 403 on this repository.
The committed verdict IS the audit trail.

WHY A SCRIPT AND NOT SHELL IN THE YAML
--------------------------------------
Same reason as scripts/ci_r3_research_run.py: a shell conditional in a
workflow cannot be unit-tested, and this repository has already paid for
that twice.

WHAT IT REPORTS
---------------
BLOCK/FAIL   -> DELIVERY_BLOCKED, exit 1. The run must not read green.
BLOCK/SKIP   -> warning. A BLOCK invariant that did not evaluate is not a
                passing check. Five of them (I8/I24/I25/I26/I29) stand
                down today on header-format drift, and I28 falls back to
                SKIP on any exception, so the strictest gate in the
                delivery path can go inert on a bad read. Surfaced, not
                failed, because it predates this change.
no file      -> exit 0. The sender never reached the validator; the send
                step's own exit code already covers that case.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def verdict_path(root: Path, market: str) -> Path:
    return root / "reports" / "context" / ("xlsx_validation_%s.json" % market)


def classify(payload: dict) -> dict:
    inv = payload.get("invariants") or []
    blocked = [r for r in inv
               if r.get("severity") == "BLOCK" and r.get("status") == "FAIL"]
    inert = [r for r in inv
             if r.get("severity") == "BLOCK" and r.get("status") == "SKIP"]
    return {"verdict": payload.get("verdict"),
            "market": payload.get("market"),
            "asof": payload.get("asof"),
            "blocked": blocked, "inert": inert,
            "delivery_blocked": bool(blocked)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)

    p = verdict_path(Path(a.root), a.market)
    if not p.exists():
        print("no validator verdict at %s · the sender did not reach the "
              "validator · the send step's own exit code covers this" % p)
        return 0

    res = classify(json.loads(p.read_text(encoding="utf-8")))
    print("validator verdict: %s · market %s · asof %s"
          % (res["verdict"], res["market"], res["asof"]))

    if res["inert"]:
        print("::warning::%d BLOCK invariant(s) did not evaluate: %s"
              % (len(res["inert"]),
                 ", ".join(str(r.get("code")) for r in res["inert"])))
        for r in res["inert"]:
            print("    SKIP %-5s %-28s %s"
                  % (r.get("code"), r.get("name"),
                     str(r.get("detail"))[:70]))

    if not res["delivery_blocked"]:
        print("delivery was not blocked by the validator")
        return 0

    for r in res["blocked"]:
        print("::error::DELIVERY_BLOCKED · %s · %s · %s"
              % (r.get("code"), r.get("name"), str(r.get("detail"))[:110]))
        for v in (r.get("violations") or [])[:5]:
            print("      %s" % v)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
