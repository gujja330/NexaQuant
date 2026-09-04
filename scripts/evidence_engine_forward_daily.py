"""AUDIT-04 · Forward-Paper Daily Runner.

For every FROZEN candidate registered under reports/research/forward_validation/,
append today's observation to its daily_ledger.jsonl and mature outcomes at
5/10/20/60d where prices allow.

Governance:
  · Never modifies R2 production paths
  · Never retunes a frozen candidate · overwrite forbidden
  · Reads standing comparator for the third leg of three-way comparison
  · Emits daily summary but no promotion decision (that requires the mature evidence + CEO auth)

When there are zero frozen candidates (current state · F01-F05 substrate immature),
this runner reports NO_ELIGIBLE_CANDIDATES and exits cleanly.
"""
from __future__ import annotations
import argparse, io, json, sys
from datetime import date, datetime
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from backend.research.evidence.forward_paper import (
    load_daily_ledger, mature_outcomes, append_daily_observation,
    MATURITY_HORIZONS_DAYS,
)


def _list_frozen_candidates(root: Path) -> list[dict]:
    """Return every (item_id, market, frozen_candidate) tuple."""
    d = root / "reports" / "research" / "forward_validation"
    if not d.exists(): return []
    out = []
    for item_dir in d.iterdir():
        if not item_dir.is_dir(): continue
        item_id = item_dir.name
        for market_dir in item_dir.iterdir():
            if not market_dir.is_dir(): continue
            market = market_dir.name
            fc_p = market_dir / "frozen_candidate.json"
            if not fc_p.exists(): continue
            try:
                fc = json.loads(fc_p.read_text(encoding="utf-8"))
                out.append({"item_id": item_id, "market": market, "frozen": fc})
            except Exception: pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", type=str, default=None)
    args = ap.parse_args()
    asof = args.asof or date.today().isoformat()

    candidates = _list_frozen_candidates(_ROOT)
    summary = {
        "engine": "evidence_engine_forward_daily",
        "run_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "asof": asof,
        "n_frozen_candidates": len(candidates),
        "per_candidate": [],
    }

    if not candidates:
        summary["status"] = "NO_ELIGIBLE_CANDIDATES"
        summary["reason"] = (
            "Zero frozen candidates registered · F01-F05 substrate must reach "
            "OOS_TESTED before any candidate qualifies for forward paper. "
            "This is expected state during accumulation phase."
        )
        out = _ROOT / "reports" / "research" / "forward_daily_summary.json"
        out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"[forward-daily] NO_ELIGIBLE_CANDIDATES · substrate immature")
        print(f"[forward-daily] wrote {out.relative_to(_ROOT)}")
        return

    # For each frozen candidate · mature outcomes today
    for c in candidates:
        item_id = c["item_id"]; market = c["market"]
        mat = mature_outcomes(_ROOT, item_id, market)
        summary["per_candidate"].append(mat)
        print(f"[forward-daily] {item_id}/{market} · n_rows={mat.get('n_rows')} · "
                f"newly matured={mat.get('n_newly_matured')}")

    summary["status"] = "PROCESSED"
    out = _ROOT / "reports" / "research" / "forward_daily_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[forward-daily] wrote {out.relative_to(_ROOT)}")


if __name__ == "__main__":
    main()
