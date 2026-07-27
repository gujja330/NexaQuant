"""Daily runner for Recommendation Quality Engine."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.quality.engine import (  # noqa: E402
    compute_quality, SCHEMA_FINGERPRINT, SCHEMA_VERSION, ENGINE_ID,
)


def _reports(market): return _ROOT / ("usa/reports" if market == "usa" else "reports")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=None)
    args = ap.parse_args()

    reports = _reports(args.market)
    recs_p = reports / "recommendations.json"
    dh_p = reports / "dynamic_holding.json"
    if not recs_p.exists():
        print(f"[quality:{args.market}] no recommendations.json · skipping")
        return 0
    recs = json.loads(recs_p.read_text(encoding="utf-8")).get("recommendations", [])
    holdings: dict[str, int] = {}
    if dh_p.exists():
        for d in json.loads(dh_p.read_text(encoding="utf-8")).get("decisions", []):
            holdings[d.get("ticker", "")] = int(d.get("holding_days", 21))

    q = compute_quality(recs, holdings)

    out_p = reports / "recommendation_quality.json"
    tiers: dict[str, int] = {}
    for x in q:
        tiers[x["quality_tier"]] = tiers.get(x["quality_tier"], 0) + 1
    payload = {
        "engine": ENGINE_ID, "version": "1.0.0",
        "schema_version": SCHEMA_VERSION, "schema_fingerprint": SCHEMA_FINGERPRINT,
        "market": args.market,
        "asof": args.asof or date.today().isoformat(),
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "n": len(q),
        "tier_distribution": tiers,
        "quality": q,
    }
    out_p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"[quality:{args.market}] n={len(q)} tiers={tiers} -> {out_p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
