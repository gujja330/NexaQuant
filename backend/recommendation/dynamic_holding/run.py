"""Daily runner for Dynamic Holding Engine.

Wave Y+FCP · L1 BUILT → L2 WIRED. For every position/rec, compute the
dynamic holding period · replaces `suggested_holding_period_days: 60`
static fields with adaptive values.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.dynamic_holding.engine import (  # noqa: E402
    compute_holding_days, SCHEMA_FINGERPRINT, SCHEMA_VERSION, ENGINE_ID,
)


def _reports(market: str) -> Path:
    return _ROOT / ("usa/reports" if market == "usa" else "reports")


def _load_regime(reports: Path) -> str:
    p = reports / "macro_regime.json"
    if not p.exists(): return "unknown"
    try:
        return str(json.loads(p.read_text(encoding="utf-8")).get("primary_regime", "unknown"))
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=None)
    args = ap.parse_args()

    reports = _reports(args.market)
    recs_path = reports / "recommendations.json"
    if not recs_path.exists():
        print(f"[dynamic_holding:{args.market}] no recommendations.json · skipping")
        return 0
    recs = json.loads(recs_path.read_text(encoding="utf-8")).get("recommendations", [])
    regime = _load_regime(reports)

    decisions = []
    for r in recs:
        d = compute_holding_days(
            r.get("ticker", ""),
            current_confidence=float(r.get("confidence", 0.5)),
            confidence_at_entry=float(r.get("confidence", 0.5)),
            upside_remaining_pct=0.0,      # placeholder · integrate with fundamentals when populated
            sector_strength=0.0,
            macro_regime=regime,
            rotation_score=0.0,
            risk_score=0.5,
            annualized_vol=0.25,
            liquidity_ratio=1.0,
            portfolio_overlap_pct=0.0,
            opp_cost_edge=float(r.get("oc_expected_alpha_delta") or 0.0),
            expected_benchmark_alpha_pct=0.0,
        )
        decisions.append(d)

    out_p = reports / "dynamic_holding.json"
    payload = {
        "engine": ENGINE_ID, "version": "1.0.0",
        "schema_version": SCHEMA_VERSION, "schema_fingerprint": SCHEMA_FINGERPRINT,
        "market": args.market,
        "asof": args.asof or date.today().isoformat(),
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "macro_regime": regime,
        "n": len(decisions),
        "decisions": decisions,
    }
    out_p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    if decisions:
        avg = sum(d["holding_days"] for d in decisions) / len(decisions)
        mn = min(d["holding_days"] for d in decisions)
        mx = max(d["holding_days"] for d in decisions)
        print(f"[dynamic_holding:{args.market}] n={len(decisions)} min={mn} avg={avg:.1f} max={mx} regime={regime} -> {out_p.name}")
    else:
        print(f"[dynamic_holding:{args.market}] no positions · empty output")
    return 0


if __name__ == "__main__":
    sys.exit(main())
