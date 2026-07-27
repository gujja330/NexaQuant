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

import json  # noqa: E402
from backend.recommendation.ssot.bridge import publish_ssot  # noqa: E402
from backend.recommendation.investor_actionable import (  # noqa: E402
    enrich_batch, summarize_batch,
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
    v3 = reports / "recommendations_v3.json"
    out = reports / "recommendations.json"

    payload = publish_ssot(v3, out, market=args.market,
                             asof=(args.asof or date.today().isoformat()),
                             run_utc=datetime.now(timezone.utc).isoformat())
    print(f"[recommendation_ssot:{args.market}] "
          f"n={payload['n']} (source: {payload['source']}) -> {out.name}")

    # Investor-Actionable enrichment · adds investor_action + position_plan + why
    # to every rec so the operator can act without interpreting institutional labels.
    # Article 101.2 · pure enrichment · CEO cycle 2.
    try:
        pub = json.loads(out.read_text(encoding="utf-8"))
        recs = pub.get("recommendations", [])
        if recs:
            enrich_batch(recs)
            pub["recommendations"] = recs
            pub["investor_actionable_engine"] = "aegis.recommendation.investor_actionable.v1"
            out.write_text(json.dumps(pub, indent=2, default=str, ensure_ascii=False),
                            encoding="utf-8")
            summ = summarize_batch(recs)
            (reports / "investor_actionable_summary.json").write_text(
                json.dumps(summ, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[investor_actionable:{args.market}] "
                  f"entry_dist={summ['entry_decision_dist']} "
                  f"if_holding_dist={summ['if_holding_decision_dist']} "
                  f"actionable_entries={len(summ['actionable_entries'])} "
                  f"actionable_exits={len(summ['actionable_exits'])}")
    except Exception as exc:
        # Enrichment failure must NEVER break the SSoT pipeline · log and continue
        print(f"[investor_actionable:{args.market}] enrichment failed · {type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
