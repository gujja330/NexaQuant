"""AEGIS · P0 · build canonical Outcome Dataset · CLI driver.

Run: python scripts/build_outcome_dataset.py

Reads position_store + rank_history + investability + parquets · emits:
  reports/research/outcome_dataset.parquet
  reports/research/outcome_dataset_summary.json

Runs safely daily · idempotent · deterministic per (position_id).
"""
from __future__ import annotations

import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, str(_ROOT))
    from backend.research.outcome_dataset import build, emit

    rows = build(_ROOT)
    summary = emit(_ROOT, rows)

    print(f"[outcome_dataset] n_positions={summary.get('n_positions', 0)} "
              f"closed={summary.get('n_closed', 0)} "
              f"open={summary.get('n_open', 0)}")
    print(f"[outcome_dataset] by_country={summary.get('by_country', {})}")
    print(f"[outcome_dataset] by_runner={summary.get('by_runner', {})}")
    print()
    print("=== RUNNER PERFORMANCE · CLOSED positions only ===")
    for runner_label, perf in (summary.get("runner_perf_closed_only") or {}).items():
        n = perf.get("n_closed", 0)
        if n == 0:
            print(f"  {runner_label}: n=0 · tier={perf.get('tier','?')}")
            continue
        print(f"  {runner_label}: n={n} · win_rate={perf.get('win_rate_pct')}% · "
                  f"avg={perf.get('avg_pnl_pct')}% · median={perf.get('median_pnl_pct')}% · "
                  f"tier={perf.get('tier','?')}")
    print(f"\n[outcome_dataset] parquet: {summary.get('parquet_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
