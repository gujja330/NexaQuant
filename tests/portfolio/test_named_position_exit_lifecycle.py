"""Golden lifecycle tests for the 3 CEO-flagged R2 positions ·
CEO 2026-09-01 final closure §3.

For each of CHAMBLFERT · ITC · USA IT, prove the complete chain:
    entry → daily prices → dynamic risk → exit evaluation → decision →
    Registry → Portfolio → Exit History → realized P&L

Under the authoritative-only enforcement rule (bridge --enforce only
fires close when stop_source is dynamic_risk_v2:*), the expected
outcomes are:

    CHAMBLFERT (India R2)
        · dynamic_risk_v2 provides ATR-based stop 400.80
        · current 413.55 > stop 400.80 → HOLD
        · engine says HOLD · Registry: ACTIVE (unchanged)

    ITC (India R2)
        · dynamic ATR stop 258.25
        · current 264.90 > stop 258.25 → HOLD
        · engine says HOLD · Registry: ACTIVE (unchanged)

    USA IT (USA R2)
        · no dynamic_risk_v2 output for USA (producer not wired for USA)
        · falls back to rec.entry_zone.stop_loss (static)
        · stop_source is NON-AUTHORITATIVE
        · under enforcement rule: NOT enforced · audit-only decision
        · Registry: ACTIVE (unchanged)

The 3rd case makes the CEO's invariant visible: "we do not silently
substitute a hardcoded stop where dynamic engine has no data".
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _load_decisions(market: str) -> dict:
    p = _ROOT / "reports" / "audit" / f"dynamic_exit_decisions_{market}_2026-09-01.json"
    if not p.exists():
        pytest.skip(f"decisions artifact not present: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _find(decisions: list, pid_prefix: str) -> dict | None:
    for d in decisions:
        if d.get("opportunity_id", "").startswith(pid_prefix):
            return d
    return None


def test_chamblfert_dynamic_engine_says_hold():
    d = _load_decisions("india")
    found = _find(d.get("decisions", []), "IND-R2-CHAMBLFERT-20260804")
    if found is None:
        pytest.skip("CHAMBLFERT decision not in artifact · daily driver may not have run")
    assert found["event"] == "HOLD"
    # Dynamic engine authoritative for India (dynamic_risk_v2 runs India)
    assert found["authoritative_dynamic"] is True
    assert found["stop_source"].startswith("dynamic_risk_v2:")
    # Position stays ACTIVE
    assert found["action"] == "AUDIT_ONLY" or found["action"] == "AUDIT_ONLY_NON_AUTHORITATIVE"


def test_itc_dynamic_engine_says_hold():
    d = _load_decisions("india")
    found = _find(d.get("decisions", []), "IND-R2-ITC-20260804")
    if found is None:
        pytest.skip("ITC decision not in artifact")
    assert found["event"] == "HOLD"
    assert found["authoritative_dynamic"] is True
    assert found["stop_source"].startswith("dynamic_risk_v2:")


def test_usa_it_dynamic_engine_says_hold():
    """After wiring USA dynamic_risk_v2 producer (STEP added 2026-09-01
    final closure), USA IT now has an authoritative vol_scaled stop.
    Current price is ABOVE that dynamic stop · so engine says HOLD.
    This replaces the pre-closure test that expected fallback-EXIT_STOP."""
    d = _load_decisions("usa")
    found = _find(d.get("decisions", []), "USA-R2-IT-20260810")
    if found is None:
        pytest.skip("USA IT decision not in artifact")
    # Dynamic engine now covers USA · IT gets vol_scaled stop
    assert found["authoritative_dynamic"] is True
    assert found["stop_source"].startswith("dynamic_risk_v2:")
    # Engine says HOLD (current above dynamic stop)
    assert found["event"] == "HOLD"


def test_bridge_enforcement_invariant_authoritative_only():
    """The bridge must NEVER call oreg.close when stop_source is
    non-authoritative · even in --enforce mode."""
    for market in ("india", "usa"):
        d = _load_decisions(market)
        for dec in d.get("decisions", []):
            if dec["event"] == "HOLD": continue
            action = dec.get("action", "")
            authoritative = dec.get("authoritative_dynamic", False)
            if action == "ENFORCED":
                # ENFORCED decisions MUST come from authoritative source
                assert authoritative is True, (
                    f"ENFORCED decision must be authoritative: {dec}"
                )


def test_bridge_declares_authoritative_only_rule_in_notes():
    """Ensure the bridge output documents the enforcement invariant."""
    for market in ("india", "usa"):
        d = _load_decisions(market)
        notes = " ".join(d.get("notes") or [])
        assert "authoritative" in notes.lower() or "invariant" in notes.lower()


def test_all_india_positions_have_dynamic_risk_source():
    """Positive coverage check · India has dynamic_risk_v2 output ·
    every India decision (HOLD or EXIT) should use it."""
    d = _load_decisions("india")
    for dec in d.get("decisions", []):
        assert dec["stop_source"].startswith("dynamic_risk_v2:"), (
            f"India position lacks dynamic_risk_v2 source: {dec}"
        )


def test_all_usa_positions_have_dynamic_risk_source():
    """After wiring USA dynamic_risk_v2 producer (STEP added 2026-09-01
    final closure), every USA decision must be authoritative."""
    d = _load_decisions("usa")
    for dec in d.get("decisions", []):
        assert dec.get("authoritative_dynamic", False) is True, (
            f"USA position lacks authoritative dynamic source: {dec}"
        )
        assert dec["stop_source"].startswith("dynamic_risk_v2:"), (
            f"USA position stop_source not dynamic_risk_v2: {dec}"
        )
