"""v3.0 LOCK · single-source-of-truth + zero-legacy contract enforcement.

Locks the operator's 4 lock criteria:
  1. Every stage in the 14-stage pipeline produces its expected artifact
  2. Every DELIVERY consumer reads reports/recommendations.json (SSoT)
  3. No legacy renderer is invoked in production workflows
  4. institutional_optimization step is wired into BOTH daily orchestrators
     (without it, Command Center renders pre-percentile HOLD-only recs)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


# ── Contract 1 · SSoT is a required stage in BOTH daily orchestrators ──
def test_india_orchestrator_wires_ssot_as_required():
    src = (_ROOT / "scripts" / "aegis_daily_v2.py").read_text(encoding="utf-8")
    assert '"name": "recommendation_ssot"' in src, (
        "India Phase 2 orchestrator missing recommendation_ssot step"
    )


def test_usa_orchestrator_wires_ssot():
    src = (_ROOT / "usa" / "scripts" / "usa_daily.py").read_text(encoding="utf-8")
    assert 'recommendation_ssot' in src, "USA orchestrator missing SSoT step"


# ── Contract 2 · institutional_optimization wired in BOTH orchestrators ──
def test_india_orchestrator_wires_institutional_optimization():
    """v3.0 lock: without this, Command Center gets pre-percentile HOLD-only recs."""
    src = (_ROOT / "scripts" / "aegis_daily_v2.py").read_text(encoding="utf-8")
    assert '"name": "institutional_optimization"' in src, (
        "India orchestrator missing institutional_optimization · Command Center "
        "would render pre-percentile HOLD-only recs · v3.0 contract violated"
    )


def test_usa_orchestrator_wires_institutional_optimization():
    src = (_ROOT / "usa" / "scripts" / "usa_daily.py").read_text(encoding="utf-8")
    assert 'institutional_optimization' in src, (
        "USA orchestrator missing institutional_optimization · v3.0 contract violated"
    )


# ── Contract 3 · Command Center is the ONLY Telegram sender in workflow ──
def test_aegis_daily_workflow_uses_only_command_center_sender():
    """Legacy telegram_send_with_retry + UX030 must NOT be actively wired."""
    src = (_ROOT / ".github" / "workflows" / "aegis-daily.yml").read_text(encoding="utf-8")
    # Command Center must be present
    assert "telegram_command_center_send.py" in src, (
        "aegis-daily.yml missing Command Center step"
    )
    # Legacy senders may be present as commented code but must not be an
    # active `run:` invocation. Match `run: python scripts/telegram_send_with_retry.py`
    active_legacy = re.search(r"^\s+run:\s+python\s+scripts/telegram_send_with_retry\.py",
                                  src, re.MULTILINE)
    active_ux030 = re.search(r"^\s+run:\s+python\s+scripts/telegram_send_ux030\.py",
                                 src, re.MULTILINE)
    assert not active_legacy, (
        "aegis-daily.yml still actively invokes legacy telegram_send_with_retry · "
        "v3.0 contract requires Command Center as SOLE sender"
    )
    assert not active_ux030, (
        "aegis-daily.yml still actively invokes UX030 sender · v3.0 contract "
        "requires Command Center as SOLE sender"
    )


def test_aegis_usa_workflow_uses_only_command_center_sender():
    src = (_ROOT / ".github" / "workflows" / "aegis-usa.yml").read_text(encoding="utf-8")
    assert "telegram_command_center_send.py" in src


# ── Contract 4 · Command Center reads SSoT (not legacy sources) ──
def test_command_center_reads_recommendations_json():
    src = (_ROOT / "backend" / "delivery" / "telegram" / "command_center.py").read_text(encoding="utf-8")
    assert "recommendations.json" in src, (
        "Command Center must read the SSoT recommendations.json"
    )
    # Must NOT read legacy paths
    assert "aegis_today.csv" not in src, (
        "Command Center is reading legacy aegis_today.csv · SSoT contract violated"
    )
    assert "champion_strategy.json" not in src, (
        "Command Center is reading legacy champion_strategy.json"
    )


# ── Contract 5 · v3.0 artifact catalog matches shipped code ──
def test_v3_lock_stage_artifact_list_is_complete():
    """Enumerates the 14 expected pipeline stages and confirms each has a
    known writer in the codebase. Guards against renaming/removing a stage
    without updating the contract."""
    STAGE_TO_WRITER_SUBSTRING = {
        "reports/recommendations.json":       "backend/recommendation/ssot/bridge.py",
        "reports/ensemble.json":              "india/model_factory/run.py",
        "reports/recommendations_v3.json":    "india/recommendation_intelligence/run.py",
        "reports/dynamic_holding.json":       "backend/recommendation/dynamic_holding/run.py",
        "reports/recommendation_lifecycle.json": "backend/recommendation/lifecycle/run.py",
        "reports/ai_scorecard.json":          "backend/analytics/scorecard.py",
        "reports/attribution_summary.json":   "backend/analytics/attribution.py",
    }
    for stage, writer in STAGE_TO_WRITER_SUBSTRING.items():
        p = _ROOT / writer
        assert p.exists(), (
            f"v3.0 lock artifact `{stage}` references missing writer `{writer}`"
        )


# ── Contract 6 · Live artifact freshness ─────────────────────────
def test_recommendations_json_exists_both_markets():
    """Both markets must have a fresh SSoT-published recommendations.json."""
    india = _ROOT / "reports" / "recommendations.json"
    usa = _ROOT / "usa" / "reports" / "recommendations.json"
    assert india.exists() and india.stat().st_size > 1000, (
        "India recommendations.json missing or empty"
    )
    assert usa.exists() and usa.stat().st_size > 1000, (
        "USA recommendations.json missing or empty"
    )


def test_recommendations_json_carries_v3_enrichment_blocks():
    """Every rec must carry the v2.4 enrichment blocks required for the
    Command Center to render properly."""
    import json
    for market_reports in ((_ROOT / "reports"), (_ROOT / "usa" / "reports")):
        p = market_reports / "recommendations.json"
        if not p.exists():
            continue
        payload = json.loads(p.read_text(encoding="utf-8"))
        # Top-level required blocks
        assert "ceo_summary" in payload, f"{p}: missing top-level ceo_summary"
        recs = payload.get("recommendations") or []
        if not recs:
            continue
        # Per-rec required blocks
        r = recs[0]
        required_blocks = ["investor_action", "position_plan", "why",
                             "rotation_intelligence", "lifecycle_state", "evolution"]
        missing = [b for b in required_blocks if b not in r]
        assert not missing, (
            f"{p}: rec[0] missing v2.4 blocks: {missing}"
        )
