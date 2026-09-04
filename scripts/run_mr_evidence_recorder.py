"""C.1 · Run MR trial-accounting hook · both markets.

Reads cached mr_forward_validation_{market}.json · records each cohort as
a trial in a declared family. Never re-computes MR itself. Never touches
production paths. Emits summary JSON.
"""
from __future__ import annotations
import argparse, io, json, sys
from datetime import datetime
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from backend.research.evidence.mr_evidence_recorder import record_family_to_evidence_log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    ap.add_argument("--correction", default="benjamini_hochberg_fdr_planned")
    args = ap.parse_args()
    markets = ["india","usa"] if args.market == "both" else [args.market]
    combined = {"engine": "mr_evidence_recorder", "run_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "per_market": {}}
    for m in markets:
        r = record_family_to_evidence_log(_ROOT, m, correction_method=args.correction)
        combined["per_market"][m] = r
        print(f"{m.upper()}: status={r.get('status')} · family_id={r.get('family_id')} "
                f"· trials={r.get('total_planned_trials')}")
    out = _ROOT / "reports" / "research" / "evidence" / "mr_evidence_recorder_summary.json"
    out.write_text(json.dumps(combined, indent=2, default=str), encoding="utf-8")
    print(f"[C.1] wrote {out.relative_to(_ROOT)}")


if __name__ == "__main__":
    main()
