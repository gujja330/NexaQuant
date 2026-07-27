"""Daily runner for Recommendation Delta Engine.

Wave Y+FCP · L1 BUILT → L2 WIRED. Loads today's + yesterday's SSoT recs,
computes deltas, emits `reports/recommendation_deltas.json`.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.delta.engine import (  # noqa: E402
    compute_deltas, SCHEMA_FINGERPRINT, SCHEMA_VERSION, ENGINE_ID,
)


def _reports(market: str) -> Path:
    return _ROOT / ("usa/reports" if market == "usa" else "reports")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=None)
    args = ap.parse_args()

    reports = _reports(args.market)
    today_p = reports / "recommendations.json"
    hist_p = reports / "recommendation_history_snapshot.json"

    if not today_p.exists():
        print(f"[delta:{args.market}] no recommendations.json · skipping")
        return 0

    today = json.loads(today_p.read_text(encoding="utf-8")).get("recommendations", [])
    yesterday = []
    if hist_p.exists():
        try:
            yesterday = json.loads(hist_p.read_text(encoding="utf-8")).get("recommendations", [])
        except Exception:
            yesterday = []

    deltas = compute_deltas(today, yesterday)

    out_p = reports / "recommendation_deltas.json"
    payload = {
        "engine": ENGINE_ID, "version": "1.0.0",
        "schema_version": SCHEMA_VERSION, "schema_fingerprint": SCHEMA_FINGERPRINT,
        "market": args.market,
        "asof": args.asof or date.today().isoformat(),
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "n": len(deltas), "n_prior": len(yesterday),
        "deltas": deltas,
    }
    out_p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    # Roll snapshot for tomorrow
    hist_p.write_text(json.dumps({"recommendations": today, "captured_asof": args.asof or date.today().isoformat()}), encoding="utf-8")

    action_changed = sum(1 for d in deltas if d.get("action_changed"))
    print(f"[delta:{args.market}] n={len(deltas)} action_changed={action_changed} "
          f"prior={len(yesterday)} -> {out_p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
