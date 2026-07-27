"""Investor-Actionable enricher runner · enriches recommendations.json.

Runs downstream of SSoT bridge + percentile classifier. Reads the market's
recommendations.json, calls enrich_batch, writes back in place, and emits
a compact summary at reports/investor_actionable_summary.json.

Idempotent: re-running only refreshes the enrichment fields; base rec data
(ticker/action/score) is untouched.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.investor_actionable import enrich_batch, summarize_batch  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="india", choices=["india", "usa"])
    args = ap.parse_args()

    reports_dir = _ROOT / ("usa/reports" if args.market == "usa" else "reports")
    rec_path = reports_dir / "recommendations.json"
    if not rec_path.exists():
        print(f"[investor_actionable:{args.market}] recommendations.json missing at {rec_path}")
        return 1

    payload = json.loads(rec_path.read_text(encoding="utf-8"))
    recs = payload.get("recommendations", [])
    if not isinstance(recs, list):
        print(f"[investor_actionable:{args.market}] malformed recs field · aborting")
        return 1

    enrich_batch(recs)
    payload["recommendations"] = recs
    payload["investor_actionable_engine"] = "aegis.recommendation.investor_actionable.v1"
    rec_path.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                          encoding="utf-8")

    summary = summarize_batch(recs)
    (reports_dir / "investor_actionable_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    entry = summary.get("entry_decision_dist", {})
    hold = summary.get("if_holding_decision_dist", {})
    n_entries = len(summary.get("actionable_entries", []))
    n_exits = len(summary.get("actionable_exits", []))
    print(f"[investor_actionable:{args.market}] n={len(recs)} "
          f"entry_dist={dict(entry)} if_holding_dist={dict(hold)} "
          f"actionable_entries={n_entries} actionable_exits={n_exits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
