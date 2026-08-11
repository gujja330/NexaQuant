"""AEGIS · P1 · run attribution/interaction analysis · CLI driver.

Run: python scripts/run_attribution.py

Reads reports/research/outcome_dataset.parquet · emits:
  reports/research/attribution_analysis.json (machine)
  reports/research/attribution_report.md     (human)
"""
from __future__ import annotations

import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, str(_ROOT))
    from backend.research.attribution_engine import run, emit_json, emit_markdown

    result = run(_ROOT)
    if "error" in result:
        print(f"[attribution] ERROR · {result['error']}")
        return 1

    json_path = emit_json(_ROOT, result)
    md_path = emit_markdown(_ROOT, result)

    print(f"[attribution] n_positions={result['n_positions']} · "
              f"closed={result['n_closed']} · open={result['n_open']}")
    print(f"[attribution] json: {json_path.relative_to(_ROOT)}")
    print(f"[attribution] markdown: {md_path.relative_to(_ROOT)}")
    print()

    # Print single-dim summaries
    print("=== SINGLE-DIMENSION BREAKDOWNS (closed only) ===")
    for dim, cells in (result.get("single_dimensions") or {}).items():
        print(f"\n{dim}:")
        rows = sorted(cells.items(), key=lambda x: (-(x[1].get("avg_pnl_pct") or -999)))
        for value, m in rows:
            if m.get("n", 0) == 0: continue
            print(f"  {str(value):20} n={m['n']:>3} · "
                      f"win={m.get('win_pct','?'):>5}% · "
                      f"avg={m.get('avg_pnl_pct','?'):>+6.2f}% · "
                      f"tier={m.get('tier','?')}")

    print("\n=== TOP 5 WINNERS (Runner x Cap x Sector) ===")
    for i, w in enumerate(result.get("winner_profile") or [], 1):
        print(f"  {i}. {w['runner']:3} · {w['cap']:14} · {w['sector']:20} "
                  f"n={w['n']} · win={w['win_pct']}% · avg={w['avg_pnl']:+.2f}% · [{w['tier']}]")

    print("\n=== BOTTOM 5 FAILURES ===")
    for i, w in enumerate(result.get("failure_profile") or [], 1):
        print(f"  {i}. {w['runner']:3} · {w['cap']:14} · {w['sector']:20} "
                  f"n={w['n']} · win={w['win_pct']}% · avg={w['avg_pnl']:+.2f}% · [{w['tier']}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
