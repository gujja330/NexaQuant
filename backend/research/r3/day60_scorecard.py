"""R3 · Day-60 Interim Scorecard
CEO 2026-09-03

Halfway checkpoint (Days 31-60). Reports:
  - Sharpe, Brier, ECE trending vs Day-30
  - Sample size growth
  - Sector/regime distribution of picks

Not a kill gate · informational report to guide Day-90 evaluation.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def compute_day60(root: Path, market: str) -> dict:
    from backend.research.r3.shadow_ledger import read_shadow_ledger
    r3 = read_shadow_ledger(root, market)
    return {
        "market": market,
        "n_picks_total": len(r3),
        "picks_by_asof_recent": list({p.get("asof") for p in r3})[-5:],
        "note": "Interim scorecard · not a kill gate · guides Day-90 evaluation",
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    args = ap.parse_args()
    r = compute_day60(Path(_ROOT), args.market)
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
