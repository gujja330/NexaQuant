"""Run all 20 Deep Research domain modules · emit results · scorecard input."""
from __future__ import annotations
import argparse, importlib, io, json, sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

DOMAIN_MODULES = [
    "d01_business_quality", "d02_balance_sheet", "d03_accounting_quality_ext",
    "d04_valuation_ext", "d05_growth_quality", "d06_industry_cycle",
    "d07_macro_fci", "d08_flows_crowding", "t09_deep_technical",
    "d10_corp_events_ext", "d11_governance_india_ext", "d12_narrative_ext",
    "d13_kg_ownership", "d14_risk_ext", "d15_portfolio_construction",
    "d16_deep_exit_science", "d17_cross_market_global",
    "d18_data_integrity_audit", "d19_statistical_robustness",
    "d20_failure_research_ext",
    # Integrated fundamentals family (F-prefix per CEO 2026-09-03 naming standard)
    "f01_05_fundamental_intelligence",
    "f01_05_filter_grid",
    "f01_05_oos_walkforward",
    "d06_p2_regime_ranking",
    "d08_flows_walkforward",
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    args = ap.parse_args()
    markets = ["india","usa"] if args.market == "both" else [args.market]
    summary = []
    for m in markets:
        for mod_name in DOMAIN_MODULES:
            try:
                mod = importlib.import_module(f"backend.research.deep.{mod_name}")
                r = mod.evaluate(_ROOT, m)
                summary.append({"module": mod_name, "market": m,
                                "gate_status": r.get("gate_status"),
                                "verdict": r.get("verdict", "")[:60] if r.get("verdict") else ""})
            except Exception as e:
                summary.append({"module": mod_name, "market": m, "error": str(e)[:80]})
    for row in summary:
        print(row)


if __name__ == "__main__":
    main()
