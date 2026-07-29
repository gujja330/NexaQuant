"""Daily runner for Recommendation Lifecycle state machine.

Wave Y+FCP · L1 BUILT → L2 WIRED. Reads today's recommendations.json (SSoT)
+ previous lifecycle_ledger.jsonl · applies transitions · persists.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.lifecycle.state_machine import (  # noqa: E402
    LifecycleLedger, RecommendationState, SCHEMA_FINGERPRINT, SCHEMA_VERSION, ENGINE_ID,
)


ACTION_TO_STATE = {
    "STRONG BUY": RecommendationState.BUY,
    "BUY":        RecommendationState.BUY,
    "ADD":        RecommendationState.ADD,
    "HOLD":       RecommendationState.HOLD,
    "TRIM":       RecommendationState.TRIM,
    "REDUCE":     RecommendationState.TRIM,
    "SELL":       RecommendationState.EXIT,
    "STRONG SELL":RecommendationState.EXIT,
    "EXIT":       RecommendationState.EXIT,
    "ROTATED":    RecommendationState.ROTATED,
    "INSUFFICIENT DATA": RecommendationState.WATCHLIST,   # honest: watch, don't act
}


def _reports(market: str) -> Path:
    return _ROOT / ("usa/reports" if market == "usa" else "reports")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=None)
    args = ap.parse_args()

    reports = _reports(args.market)
    recs_path = reports / "recommendations.json"
    if not recs_path.exists():
        print(f"[lifecycle:{args.market}] no recommendations.json · skipping")
        return 0
    ledger_path = reports / "recommendation_lifecycle_ledger.jsonl"
    ledger = LifecycleLedger.from_jsonl(ledger_path)

    d = json.loads(recs_path.read_text(encoding="utf-8"))
    recs = d.get("recommendations", [])
    asof = args.asof or date.today().isoformat()
    ts_utc = datetime.now(timezone.utc).isoformat()

    applied = 0
    skipped_illegal = 0
    for r in recs:
        ticker = r.get("ticker", "")
        if not ticker: continue
        action = r.get("recommendation") or r.get("action")
        target = ACTION_TO_STATE.get(action, RecommendationState.HOLD)
        try:
            ledger.apply(ticker, target,
                          reason=f"daily rec {action} · asof {asof}",
                          metadata={"score": r.get("composite_decision_score"),
                                     "confidence": r.get("confidence"),
                                     "signal_quality": r.get("signal_quality")},
                          ts_utc=ts_utc)
            applied += 1
        except ValueError as e:
            skipped_illegal += 1
            continue

    # Persist ledger (append-only)
    ledger.write_jsonl(ledger_path)

    # Emit summary snapshot
    snap_path = reports / "recommendation_lifecycle.json"
    snap = ledger.to_dict()
    snap["asof"] = asof
    snap["market"] = args.market
    snap["applied"] = applied
    snap["skipped_illegal"] = skipped_illegal
    # Schema-compat aliases · scripts/aegis_ops_check.py + usa_ops_check.py
    # expect `n_total` + `by_ticker` + `by_state`. Provide alongside the
    # current `n_tickers` + `records` shape.
    snap["n_total"] = snap.get("n_tickers", 0)
    snap["by_ticker"] = snap.get("records") or {}
    # by_state = {state_name: count} across all tracked tickers
    from collections import Counter
    _states = Counter((rec.get("current_state") or "UNKNOWN")
                       for rec in (snap.get("records") or {}).values()
                       if isinstance(rec, dict))
    snap["by_state"] = dict(_states)
    snap_path.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")

    print(f"[lifecycle:{args.market}] applied={applied} illegal_skipped={skipped_illegal} "
          f"tickers_tracked={ledger.n_tickers} -> {snap_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
