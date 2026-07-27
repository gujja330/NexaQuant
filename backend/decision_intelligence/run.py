"""Daily runner for Decision Intelligence · Macro Impact + Portfolio Impact + Consumer Audit."""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.decision_intelligence.macro_decision_impact import run_macro_decision_impact
from backend.decision_intelligence.portfolio_impact import run_portfolio_impact
from backend.decision_intelligence.consumer_audit import run_consumer_audit


def _reports(market): return _ROOT / ("usa/reports" if market == "usa" else "reports")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--only", choices=["macro", "portfolio", "audit"], default=None)
    args = ap.parse_args()
    reports = _reports(args.market)

    if args.only in (None, "macro"):
        out = run_macro_decision_impact(args.market, reports)
        p = reports / "macro_decision_impact.json"
        p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"[macro_decision_impact:{args.market}] n_material_moves={out['n_material_moves']} "
              f"n_sector_impacts={out['n_sector_impacts']} -> {p.name}")

    if args.only in (None, "portfolio"):
        out = run_portfolio_impact(args.market, reports)
        p = reports / "portfolio_decision_impact.json"
        p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"[portfolio_decision_impact:{args.market}] "
              f"n_actionable={out['proposed_n_actions']} "
              f"new_entries={out['proposed_new_entries']} exits={out['proposed_exits']} "
              f"net_deploy={out['net_capital_deployment_pct']:+.2f}% -> {p.name}")

    if args.only in (None, "audit"):
        out = run_consumer_audit(_ROOT)
        p = reports / "consumer_audit.json"
        p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"[consumer_audit] n_artifacts={out['n_artifacts']} healthy={out['n_healthy']} "
              f"orphan={out['n_orphan_report']} broken={out['n_broken_chain']} "
              f"report_only={out['n_report_only']} -> {p.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
