"""Build TODAY's canonical feature snapshot. The step CI never had.

WHY THIS EXISTS
---------------
`backend/pipeline/contract/readiness.py` gates DATA_READY on
`feature_snapshot` with a budget of ZERO days - today's scoring must be
built from today's features. That is the correct rule.

But nothing in either workflow ever produced that snapshot.

The only writer of `features/<market>/<date>.parquet` is
`backend.feature_store.feature_snapshot.build_and_persist`, and it was
reachable ONLY through `contract.runner --refresh`, which neither
workflow passes. So every CI run inherited whatever snapshot happened to
be committed - newest tracked is 2026-07-21 - and DATA_READY failed with
SOURCE_STALE:FEATURE_SNAPSHOT before the gate could say anything useful.

This is the alias-drift class again. Two different things are called the
feature store:

    usa/research/feature_store/run.py  -> usa/reports/feature_store_summary.json
    backend/feature_store/feature_snapshot.py -> features/<market>/<date>.parquet

The daily pipeline ran the first one every morning. The contract gate
reads the second. Both are "the feature store" by name, and the gap
between them was invisible because CI never committed the certification
that named the failing source.

BEHAVIOUR
---------
Idempotent: a snapshot that already exists for the date is rebuilt, and
rebuilding is cheap (~516 USA rows, ~228 India rows, seconds).

Exit codes:
  0  snapshot on disk with rows (verdict PASS or WARNING)
  1  no snapshot produced for a requested market - the gate WILL block,
     and this says why here instead of 95 days later
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROFILES = {"india": "INDIA_PROFILE", "usa": "USA_PROFILE"}


def build(market: str, asof: date) -> dict:
    from backend.canonical import model as canon
    from backend.feature_store.feature_snapshot import build_and_persist

    profile = getattr(canon, PROFILES[market])
    try:
        r = build_and_persist(ROOT, profile, asof) or {}
    except Exception as e:                      # noqa: BLE001 - reported, not hidden
        return {"market": market, "ok": False, "verdict": "EXCEPTION",
                "error": "%s: %s" % (type(e).__name__, str(e)[:300])}

    path = ROOT / "features" / market / ("%s.parquet" % asof.isoformat())
    rows = r.get("n_rows")
    ok = path.exists() and bool(rows)
    return {"market": market, "ok": ok, "verdict": r.get("verdict"),
            "asof": r.get("asof"), "n_rows": rows,
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "exists": path.exists(), "error": r.get("error") or r.get("reason")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="both",
                    choices=["india", "usa", "both"])
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD (default: today)")
    a = ap.parse_args()

    asof = date.fromisoformat(a.asof) if a.asof else date.today()
    markets = ["india", "usa"] if a.market == "both" else [a.market]

    print("FEATURE SNAPSHOT BUILD  asof=%s  markets=%s"
          % (asof.isoformat(), ",".join(markets)))

    failed = []
    for m in markets:
        r = build(m, asof)
        print("  %-6s %-9s rows=%-5s %s%s"
              % (m, r.get("verdict") or "?", r.get("n_rows"), r.get("path"),
                 ("  ERROR: %s" % r["error"]) if r.get("error") else ""))
        if not r["ok"]:
            failed.append(r)

    if failed:
        print("\nBLOCKING: %d market(s) have no usable snapshot for %s."
              % (len(failed), asof.isoformat()))
        print("The run contract gates DATA_READY on feature_snapshot at a")
        print("budget of 0 days, so it would fail with SOURCE_STALE anyway -")
        print("this fails here, where the cause is named.")
        return 1

    print("\nOK - every requested market has today's snapshot on disk.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
