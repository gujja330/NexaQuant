"""Institutional Memory v1.0 · combined CLI.

Runs the three primitives in dependency order:
  1. Archive today's canonical bundle → data/archive/YYYY/MM/DD/bundle/
  2. Rebuild recommendation lifecycle ledger → reports/recommendation_lifecycle.{parquet,json}
  3. Mine missed opportunities → reports/missed_opportunities.json

Each primitive is deterministic and append-only. The pipeline runs this
as a single step at the tail of aegis_daily_v2.
"""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from institutional_memory.lib import archive, lifecycle, missed_opportunities   # noqa: E402


_ROOT = Path(__file__).resolve().parents[2]
REPORTS = _ROOT / "reports"


def main() -> int:
    t0 = time.time()
    print("=" * 68)
    print("  INSTITUTIONAL MEMORY v1.0 · archive + lifecycle + missed-opps")
    print("=" * 68)

    # ── Step 1: archive today's bundle
    print("\n[1/3] Archive today's bundle")
    m = archive.archive_today()
    if m.get("already_archived"):
        print(f"      already archived · {m['run_date']} · {m['n_files']} files "
              f"({m['total_bytes'] / 1024:.1f} KB)")
    else:
        print(f"      run_date={m['run_date']}  files={m['n_files']}  "
              f"size={m['total_bytes'] / 1024:.1f} KB  code_sha={m['code_sha']}")

    # ── Step 2: rebuild lifecycle ledger
    print("\n[2/3] Rebuild recommendation lifecycle ledger")
    df = lifecycle.build_lifecycle()
    summary = lifecycle.build_summary(df)
    if not df.empty:
        df.to_parquet(REPORTS / "recommendation_lifecycle.parquet", index=False)
    (REPORTS / "recommendation_lifecycle.json").write_text(
        json.dumps({
            "engine": "institutional_memory",
            "version": "v1.0",
            "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
            **summary,
        }, indent=2, default=str), encoding="utf-8")
    print(f"      n_total={summary.get('n_total', 0)}  by_state={summary.get('by_state', {})}")
    print(f"      win_rate={summary.get('win_rate')}  "
          f"avg_realized={summary.get('avg_realized')}  "
          f"avg_alpha_capture={summary.get('avg_alpha_capture')}")

    # ── Step 3: mine missed opportunities
    print("\n[3/3] Mine missed opportunities")
    missed = missed_opportunities.mine_missed()
    missed["engine"]  = "institutional_memory"
    missed["version"] = "v1.0"
    missed["run_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"
    # Write the compact version for the dashboard (drop full all_events to keep it small)
    compact = {k: v for k, v in missed.items() if k != "all_events"}
    (REPORTS / "missed_opportunities.json").write_text(
        json.dumps(compact, indent=2, default=str), encoding="utf-8")
    print(f"      n_days_scanned={missed.get('n_days_scanned')}  "
          f"n_events={missed.get('n_events')}  "
          f"lookbacks={missed.get('lookbacks')}  "
          f"threshold={missed.get('threshold_pct')}")
    breakdown = missed.get("reason_breakdown") or {}
    if breakdown:
        print("      blocking-reason breakdown:")
        for k, v in list(breakdown.items())[:6]:
            print(f"        {k:36s} {v}")

    print(f"\nElapsed: {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
