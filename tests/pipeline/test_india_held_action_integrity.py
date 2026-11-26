import json
from unittest.mock import Mock

import pytest

from backend.delivery.telegram.detail_xlsx import _rec_to_row
from backend.research import opportunity_registry
from scripts.aegis_local_state import REGISTRY, validate_held_actions


@pytest.mark.parametrize(("held_action", "expected_closes"), [("REDUCE", 0), ("EXIT", 1)])
@pytest.mark.parametrize("market", ["india", "usa"])
def test_materializer_keeps_reduction_advisory(tmp_path, monkeypatch, market, held_action, expected_closes):
    ticker = "ALKEM" if market == "india" else "AAPL"
    episode = opportunity_registry.Opportunity(opportunity_id="IND-R2-ALKEM-20261028-example",
                                               ticker=ticker, market=market, runner="R2",
                                               created_date="2026-10-28")
    monkeypatch.setattr(opportunity_registry, "load_all", lambda *_: {(market, "R2", ticker): [episode]})
    monkeypatch.setattr(opportunity_registry, "get_or_create", lambda *args, **kwargs: episode)
    close = Mock()
    monkeypatch.setattr(opportunity_registry, "close", close)
    recommendation = {"ticker": f"{ticker}.NS" if market == "india" else ticker,
                      "action": "SELL", "percentile_action": "SELL",
                      "investor_action": {"entry": "AVOID", "if_holding": held_action},
                      "rotation_intelligence": {"should_rotate": True, "replacement_ticker": "EXAMPLE.NS"}}

    _rec_to_row(recommendation, market, tmp_path, "R2", "2026-11-25")

    assert close.call_count == expected_closes


def test_reduction_closure_requires_matching_enforced_risk_event(tmp_path):
    workspace = tmp_path / "staged"
    (workspace / REGISTRY).parent.mkdir(parents=True)
    asof = "2026-11-25"
    closed = {"opportunity_id": "episode", "ticker": "ALKEM", "market": "india", "status": "CLOSED",
              "closed_date": asof, "closed_reason": "EXIT_STOP at verified close"}
    (workspace / REGISTRY).write_text(json.dumps(closed) + "\n", encoding="utf-8")
    (workspace / "reports/recommendations.json").write_text(json.dumps({"recommendations": [
        {"ticker": "ALKEM.NS", "investor_action": {"if_holding": "REDUCE"}},
    ]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="full closure conflicts with held REDUCE"):
        validate_held_actions(tmp_path, workspace, asof)

    audit = workspace / "reports/audit" / f"dynamic_exit_decisions_india_{asof}.json"
    audit.parent.mkdir()
    audit.write_text(json.dumps({"decisions": [
        {"opportunity_id": "episode", "action": "ENFORCED", "event": "EXIT_STOP", "asof": asof},
    ]}), encoding="utf-8")
    validate_held_actions(tmp_path, workspace, asof)
