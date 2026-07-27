"""Daily runner for the Recommendation SSoT bridge.

Publishes `reports/recommendations.json` (or `usa/reports/recommendations.json`)
from the fresh Runner 2 v3 output. Slots into the daily orchestrator
IMMEDIATELY after `recommendation_intelligence` (Runner 2) — before every
downstream consumer.

Usage:
    python -m backend.recommendation.ssot.run --market india
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.ssot.bridge import publish_ssot  # noqa: E402


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
    v3 = reports / "recommendations_v3.json"
    out = reports / "recommendations.json"

    payload = publish_ssot(v3, out, market=args.market,
                             asof=(args.asof or date.today().isoformat()),
                             run_utc=datetime.now(timezone.utc).isoformat())
    print(f"[recommendation_ssot:{args.market}] "
          f"n={payload['n']} (source: {payload['source']}) -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
