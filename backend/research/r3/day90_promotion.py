"""R3 · Day-90 Promotion Evaluation
CEO 2026-09-03

Final promotion decision after 60-90 trading-day shadow. Evaluates:
  - Sharpe
  - Brier
  - Rotation accuracy vs R2
  - Feature edge
  - R1 consensus (any Cross-runner agreement)
  - Drawdown
  - Required sample size

Recommendation:
  PROMOTE  · R3 clears every gate + CEO authorization requested
  CONTINUE · promising but not yet enough n · keep shadow
  ARCHIVE  · not clearing gates · terminate R3 in this configuration

NO automatic promotion happens · this is a REPORT · CEO authorizes explicitly.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def evaluate_day90(root: Path, market: str) -> dict:
    from backend.research.r3.shadow_ledger import read_shadow_ledger
    from backend.research.r3.day30_kill_gate import evaluate_day30
    r3 = read_shadow_ledger(root, market)
    if len(r3) < 60:
        return {
            "market": market,
            "recommendation": "CONTINUE",
            "reason": f"n={len(r3)} < 60 · not yet enough shadow sample",
        }
    # Reuse Day-30 gate logic on the full 90d window
    day30 = evaluate_day30(root, market)
    passes = day30.get("n_criteria_passed", 0)
    if passes >= 3:
        rec = "PROMOTE_PENDING_CEO_AUTH"
    elif passes == 2:
        rec = "CONTINUE"
    else:
        rec = "ARCHIVE"
    return {
        "market": market,
        "n_r3_picks_90d": len(r3),
        "day30_style_criteria_at_90d": day30,
        "recommendation": rec,
        "ceo_authorization_required": True,
        "note": ("NO automatic promotion · this is a REPORT · CEO must "
                 "provide named + dated + written authorization to promote R3 → R2"),
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    args = ap.parse_args()
    r = evaluate_day90(Path(_ROOT), args.market)
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
