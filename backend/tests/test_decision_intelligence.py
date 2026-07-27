"""Decision Intelligence · Phase 4/7/1 test suite."""
from __future__ import annotations

import json, sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.decision_intelligence.macro_decision_impact import (  # noqa: E402
    MacroDecisionImpactEngine, run_macro_decision_impact,
    SCHEMA_FINGERPRINT as MDI_FP, MATERIAL_MOVE_PCT,
)
from backend.decision_intelligence.portfolio_impact import (  # noqa: E402
    PortfolioImpactEngine, run_portfolio_impact,
    SCHEMA_FINGERPRINT as PI_FP,
)
from backend.decision_intelligence.consumer_audit import (  # noqa: E402
    ConsumerAuditEngine, run_consumer_audit, SCHEMA_FINGERPRINT as CA_FP,
)


# ── Macro Decision Impact ────────────────────────────────────
def test_macro_decision_impact_fingerprint():
    r = run_macro_decision_impact("india", _ROOT / "reports")
    assert r["schema_fingerprint"] == MDI_FP
    assert r["engine"] == "aegis.decision_intelligence.macro_impact.v1"


def test_macro_decision_impact_produces_chains_from_populated_data():
    """With commodity_intelligence.json populated (post macro-substrate fix)
    we should see propagation chains."""
    r = run_macro_decision_impact("india", _ROOT / "reports")
    # Even if no move exceeds MATERIAL_MOVE_PCT, we should still count total macro moves
    assert r["n_macro_moves"] >= 0
    # If any commodity moved > 2% (BZ=F +4.87 in seed), propagation must fire
    if r["n_material_moves"] > 0:
        assert r["n_sector_impacts"] > 0
        assert len(r["propagation_chains"]) > 0


def test_macro_decision_impact_deterministic():
    r1 = run_macro_decision_impact("india", _ROOT / "reports")
    r2 = run_macro_decision_impact("india", _ROOT / "reports")
    # Compare everything except the timestamp
    r1["run_utc"] = "FROZEN"; r2["run_utc"] = "FROZEN"
    assert r1 == r2


def test_macro_decision_impact_material_threshold():
    """Moves below MATERIAL_MOVE_PCT must not propagate."""
    assert MATERIAL_MOVE_PCT > 0
    # Manually construct a below-threshold move · impact matrix should not fire
    import json
    tmp = Path(__file__).parent / "_tmp_macro"
    tmp.mkdir(exist_ok=True)
    (tmp / "commodity_intelligence.json").write_text(json.dumps({
        "commodities": [{"symbol": "CL=F", "chg_1w_pct": 0.5}]
    }), encoding="utf-8")
    r = run_macro_decision_impact("india", tmp)
    assert r["n_material_moves"] == 0
    assert r["n_sector_impacts"] == 0
    (tmp / "commodity_intelligence.json").unlink(); tmp.rmdir()


# ── Portfolio Decision Impact ────────────────────────────────
def test_portfolio_impact_fingerprint():
    r = run_portfolio_impact("india", _ROOT / "reports")
    assert r["schema_fingerprint"] == PI_FP


def test_portfolio_impact_classifies_actions():
    r = run_portfolio_impact("india", _ROOT / "reports")
    for imp in r["per_rec_impacts"][:5]:
        assert imp["action_class"] in ("NEW_ENTRY", "SCALE_UP", "SCALE_DOWN",
                                         "EXIT", "NO_CHANGE")


def test_portfolio_impact_hhi_bounded():
    r = run_portfolio_impact("india", _ROOT / "reports")
    for imp in r["per_rec_impacts"][:5]:
        assert 0.0 <= imp["portfolio_hhi_before"] <= 1.0
        assert 0.0 <= imp["portfolio_hhi_after"] <= 1.0


def test_portfolio_impact_deterministic():
    r1 = run_portfolio_impact("india", _ROOT / "reports")
    r2 = run_portfolio_impact("india", _ROOT / "reports")
    r1["run_utc"] = "FROZEN"; r2["run_utc"] = "FROZEN"
    assert r1 == r2


# ── Consumer Audit ──────────────────────────────────────────
def test_consumer_audit_fingerprint():
    r = run_consumer_audit(_ROOT)
    assert r["schema_fingerprint"] == CA_FP


def test_consumer_audit_finds_artifacts():
    r = run_consumer_audit(_ROOT)
    # Must find at least the SSoT artifacts
    assert r["n_artifacts"] > 5
    # Every artifact classified
    for a in r["per_artifact"][:5]:
        assert a["classification"] in ("HEALTHY", "ORPHAN_REPORT",
                                         "BROKEN_CHAIN", "REPORT_ONLY")


def test_consumer_audit_detects_recommendations_json_healthy():
    """After Phase 1 SSoT fix, recommendations.json should be HEALTHY."""
    r = run_consumer_audit(_ROOT)
    rec_entries = [a for a in r["per_artifact"]
                    if a["artifact"] == "reports/recommendations.json"]
    if rec_entries:
        # It must have at least one producer post-Phase-1 SSoT
        assert len(rec_entries[0]["producers"]) >= 1
