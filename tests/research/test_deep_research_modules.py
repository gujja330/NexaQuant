"""V2 §21 · Every Deep Research domain module must expose RESEARCH_TICKET
and evaluate() · default gate must be BLOCKED-EVIDENCE / EXECUTED / NOT_APPLICABLE
· never silent PASS."""
from __future__ import annotations
from pathlib import Path
import importlib, pytest, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

MODULES = [
    "backend.research.deep.d01_business_quality",
    "backend.research.deep.d02_balance_sheet",
    "backend.research.deep.d03_accounting_quality_ext",
    "backend.research.deep.d04_valuation_ext",
    "backend.research.deep.d05_growth_quality",
    "backend.research.deep.d06_industry_cycle",
    "backend.research.deep.d07_macro_fci",
    "backend.research.deep.d08_flows_crowding",
    "backend.research.deep.t09_deep_technical",
    "backend.research.deep.d10_corp_events_ext",
    "backend.research.deep.d11_governance_india_ext",
    "backend.research.deep.d12_narrative_ext",
    "backend.research.deep.d13_kg_ownership",
    "backend.research.deep.d14_risk_ext",
    "backend.research.deep.d15_portfolio_construction",
    "backend.research.deep.d16_deep_exit_science",
    "backend.research.deep.d17_cross_market_global",
    "backend.research.deep.d18_data_integrity_audit",
    "backend.research.deep.d19_statistical_robustness",
    "backend.research.deep.d20_failure_research_ext",
]

ALLOWED_STATUSES = {"BLOCKED-EVIDENCE", "EXECUTED", "NOT_APPLICABLE",
                    "INSUFFICIENT_SAMPLE"}


@pytest.mark.parametrize("mod_path", MODULES)
def test_module_exposes_ticket_and_evaluate(mod_path, tmp_path):
    mod = importlib.import_module(mod_path)
    assert hasattr(mod, "RESEARCH_TICKET"), f"{mod_path} missing RESEARCH_TICKET"
    t = mod.RESEARCH_TICKET
    for k in ("ticket_id", "domain", "name", "gate_precondition"):
        assert k in t, f"{mod_path} ticket missing {k}"
    assert 1 <= t["domain"] <= 20
    assert hasattr(mod, "evaluate")
    r = mod.evaluate(tmp_path, "usa")
    assert isinstance(r, dict)
    assert "gate_status" in r
    assert r["gate_status"] in ALLOWED_STATUSES, (
        f"{mod_path} gate_status={r['gate_status']!r} not in allowed set"
    )


def test_all_20_domains_covered():
    domains = set()
    for mp in MODULES:
        mod = importlib.import_module(mp)
        domains.add(mod.RESEARCH_TICKET["domain"])
    assert domains == set(range(1, 21)), f"missing domains: {set(range(1,21)) - domains}"
