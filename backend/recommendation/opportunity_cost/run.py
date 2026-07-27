"""Daily runner for Opportunity Cost Engine.

Wave Y · L1 BUILT → L2 WIRED. Consumes recommendations_v3.json (HOLDs +
full candidate universe) · emits reports/opportunity_cost.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.opportunity_cost.engine import enrich_holds  # noqa: E402
from backend.recommendation.opportunity_cost.engine import (  # noqa: E402
    SCHEMA_FINGERPRINT, SCHEMA_VERSION, ENGINE_ID,
)


def _reports_dir(market: str) -> Path:
    if market == "usa":
        return _ROOT.joinpath("usa", "reports")
    return _ROOT / "reports"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=None)
    args = ap.parse_args()

    reports = _reports_dir(args.market)
    reports.mkdir(parents=True, exist_ok=True)

    p = reports / "recommendations_v3.json"
    if not p.exists():
        print(f"[opportunity_cost:{args.market}] no recommendations_v3.json · skipping")
        return 0
    d = json.loads(p.read_text(encoding="utf-8"))
    recs = d.get("recommendations", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])

    def _score(r):
        return float(r.get("ensemble_score", r.get("score", 0.0)))

    holds = [{
        "ticker": r.get("ticker", ""),
        "current_score": _score(r),
        "sector": str(r.get("sector", "")),
    } for r in recs if str(r.get("action", "")).upper() == "HOLD"]

    candidates = [{
        "ticker": r.get("ticker", ""),
        "score": _score(r),
        "sector": str(r.get("sector", "")),
    } for r in recs]

    enrichments = enrich_holds(holds, candidates)

    out_path = reports / "opportunity_cost.json"
    payload = {
        "engine": ENGINE_ID,
        "version": "1.0.0",
        "schema_version": SCHEMA_VERSION,
        "schema_fingerprint": SCHEMA_FINGERPRINT,
        "market": args.market,
        "asof": (args.asof or date.today().isoformat()),
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "n_holds": len(holds),
        "n_candidates": len(candidates),
        "enrichments": enrichments,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"[opportunity_cost:{args.market}] "
          f"holds={len(holds)} candidates={len(candidates)} "
          f"enrichments={len(enrichments)} -> {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
