"""Validation Engine v2.0 · CLI."""
from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from validation_v2.compute import engine                                                # noqa: E402
from validation_v2.publish import bundle as publish                                      # noqa: E402


def _banner(msg: str) -> None:
    print(); print("=" * 72); print(f"  {msg}"); print("=" * 72)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                     help="do not persist paper positions / trades / mtm")
    args = ap.parse_args()

    t0 = time.time()
    _banner("VALIDATION ENGINE · v2.0 · LIVE HARNESS")

    _banner("STEP 1/2 · Run daily cycle")
    result = engine.run(dry_run=args.dry_run, verbose=True)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    _banner("STEP 2/2 · Publish daily report")
    outcome = publish.build_and_publish(result)
    for name in outcome["written"]:
        print(f"  written: reports/{name}")

    _banner("SUMMARY")
    print(f"  open positions:    {result['n_open_positions']}")
    print(f"  closed trades:     {result['n_closed_trades']}")
    print(f"  new opens today:   {result['n_new_opens']}")
    print(f"  new closes today:  {result['n_new_closes']}")
    print(f"  portfolio pnl:     {result['portfolio_pnl_pct']*100:+.2f}%")
    print(f"  drift flag:        {(result.get('metric_drift') or {}).get('flag')}")
    rec = result.get("reconciliation") or {}
    print(f"  reconciliation n:  {rec.get('n', 0)}")
    if rec.get("avg_return_delta") is not None:
        print(f"  avg return delta:  {rec['avg_return_delta']}")
    oc = result.get("opportunity_cost") or {}
    print(f"  missed edges:      {oc.get('n_missed_edges', 0)}")

    _banner(f"VALIDATION v2.0 · DONE ({time.time() - t0:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
