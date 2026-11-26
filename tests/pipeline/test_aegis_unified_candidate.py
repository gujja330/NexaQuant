import json

import pytest

from backend.research.fundamentals.snapshot import eps_snapshot
from scripts.aegis_shadow.pipeline import Stage, _atomic, _execute, _recover


def test_eps_preserves_reporting_currency_and_distinguishes_missing_values():
    observed = "2026-11-26T07:00:00+00:00"
    india = eps_snapshot({"trailingEps": -1.25, "forwardEps": float("nan"),
                         "financialCurrency": "INR"}, observed)
    usa = eps_snapshot({"trailingEps": 0, "forwardEps": "2.5",
                       "financialCurrency": "USD"}, observed)
    assert (india["eps_trailing"], india["eps_forward"], india["eps_currency"]) == (-1.25, None, "INR")
    assert (usa["eps_trailing"], usa["eps_forward"], usa["eps_currency"]) == (0, 2.5, "USD")
    assert india["eps_availability"] == "PARTIAL"
    assert india["eps_point_in_time"] is False
    assert eps_snapshot({"currency": "USD"}, observed)["eps_currency"] is None


def test_stage_failure_blocks_only_dependents():
    def fail(_):
        raise ValueError("missing evidence")

    stages = (Stage("data", fail), Stage("decisions", fail, ("data",)),
              Stage("independent", lambda _: None, required=False))
    results = _execute({"market": "india"}, stages)
    assert [row["status"] for row in results.values()] == ["FAIL", "BLOCKED", "PASS"]


def test_private_writer_rejects_path_escape(tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    protected = tmp_path / "protected.json"
    protected.write_bytes(b"protected")
    with pytest.raises(RuntimeError, match="invalid project-relative"):
        _atomic(private, "../protected.json", b"changed")
    assert protected.read_bytes() == b"protected"


def test_private_recovery_is_idempotent_and_blocks_skipped_checkpoint(tmp_path):
    source = tmp_path / "inputs"
    source.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    fixture = source / "shadow_recovery.json"
    evidence = {
        "market": "usa", "last_committed": "2026-11-25",
        "completed_through": "2026-11-27", "sessions": ["2026-11-27"],
        "positions": [{
            "opportunity_id": "episode1", "admitted": "2026-11-25",
            "bars": {"2026-11-27": {"close": 90, "price_basis": "raw"}},
            "levels": {"2026-11-27": {"authorized_on": "2026-11-25", "stop": 95, "price_basis": "raw"}},
        }],
    }
    fixture.write_text(json.dumps(evidence), encoding="utf-8")
    context = {"market": "usa", "source": source, "output": state,
               "lifecycle": {"market_data_asof": "2026-11-27"},
               "positions": {"episode1": {"created_date": "2026-11-25"}}}
    _recover(context)
    saved = (state / "recovery.json").read_bytes()
    assert len(json.loads(saved)["events"]) == 1
    _recover(context)
    assert (state / "recovery.json").read_bytes() == saved
    evidence.update(last_committed="2026-11-30", completed_through="2026-11-30", sessions=[], positions=[])
    fixture.write_text(json.dumps(evidence), encoding="utf-8")
    context["lifecycle"]["market_data_asof"] = "2026-11-30"
    with pytest.raises(ValueError, match="checkpoint"):
        _recover(context)
    assert (state / "recovery.json").read_bytes() == saved
