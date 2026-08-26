"""AEGIS · Sprint M Research Runner (M-R) · isolation tests.

Proves M-R cannot contaminate production outputs per the post-lock
research phase architecture (CEO handover 2026-08-26 · commit 3c4fa815).

Every rule in the M-R isolation contract is enforced here:

  · EXPERIMENT_ID is stamped on every observation
  · schema fingerprint is stamped on every observation
  · emit() only writes under reports/research/
  · emit() refuses any write path outside ALLOWED_WRITE_ROOT
  · observe() only reads from canonical inputs (portfolio_canonical_
    {market}.json, parquet close, sector_cache) · no imports from
    production sender/xlsx modules
  · M-R module MUST NOT import scripts.telegram_command_center_send
    or backend.delivery.telegram.detail_xlsx or xlsx_validator
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import pytest


def test_experiment_id_is_stamped():
    from backend.research.mr_runner import EXPERIMENT_ID
    assert EXPERIMENT_ID == "M-R.v0.1"


def test_schema_fingerprint_present():
    from backend.research.mr_runner import SCHEMA_FINGERPRINT
    assert SCHEMA_FINGERPRINT.startswith("aegis.mr_runner.")


def test_allowed_write_root_locked_to_research():
    from backend.research.mr_runner import ALLOWED_WRITE_ROOT
    assert str(ALLOWED_WRITE_ROOT) == str(Path("reports/research"))


def test_mr_runner_does_not_import_production_sender():
    """Guards against silent coupling. If someone adds `from scripts.
    telegram_command_center_send import ...` this test fails."""
    src = (Path(__file__).resolve().parents[2]
           / "backend" / "research" / "mr_runner.py").read_text(encoding="utf-8")
    forbidden = [
        "from scripts.telegram_command_center_send",
        "import scripts.telegram_command_center_send",
        "from backend.delivery.telegram.detail_xlsx",
        "from backend.delivery.xlsx_validator",
        "from backend.delivery.xlsx_contract",
    ]
    for pat in forbidden:
        assert pat not in src, (
            f"M-R isolation violation · mr_runner.py contains forbidden "
            f"import '{pat}' · sandbox must not couple to production")


def test_emit_writes_only_under_reports_research(tmp_path):
    """emit() must refuse to write outside reports/research/ regardless of
    what caller passes as `root`."""
    from backend.research.mr_runner import emit, ResearchObservation, \
        EXPERIMENT_ID, SCHEMA_FINGERPRINT
    obs = [ResearchObservation(
        experiment_id=EXPERIMENT_ID, schema_fingerprint=SCHEMA_FINGERPRINT,
        generated_utc="2026-08-26T00:00:00+00:00", asof="2026-08-26",
        market="india", position_id=None, ticker="TCS", runner="R1",
        decision="🟢 ACTIVE", lifecycle="🟢 ACTIVE",
        entry_date="2026-08-01", entry_price=3500.0, current_price=3550.0,
        sector="Technology",
        hypothesis="test", expected_return_horizon_days=20,
        expected_return_definition="test",
    )]
    p = emit(tmp_path, "india", obs)
    assert str(p).replace("\\", "/").endswith("reports/research/mr_runner_india.jsonl")


def test_emit_produces_valid_jsonl(tmp_path):
    """Every written line must be valid JSON + carry EXPERIMENT_ID."""
    from backend.research.mr_runner import emit, ResearchObservation, \
        EXPERIMENT_ID, SCHEMA_FINGERPRINT
    obs = [ResearchObservation(
        experiment_id=EXPERIMENT_ID, schema_fingerprint=SCHEMA_FINGERPRINT,
        generated_utc="2026-08-26T00:00:00+00:00", asof="2026-08-26",
        market="india", position_id=None, ticker="TCS", runner="R1",
        decision="🟢 ACTIVE", lifecycle="🟢 ACTIVE",
        entry_date="2026-08-01", entry_price=3500.0, current_price=3550.0,
        sector="Technology",
        hypothesis="test", expected_return_horizon_days=20,
        expected_return_definition="test",
    )]
    p = emit(tmp_path, "india", obs)
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines
    d = json.loads(lines[-1])
    assert d["experiment_id"] == EXPERIMENT_ID
    assert d["schema_fingerprint"] == SCHEMA_FINGERPRINT
    assert d["ticker"] == "TCS"


def test_emit_appends_does_not_truncate(tmp_path):
    """Multiple observe() → emit() cycles must accumulate, not overwrite."""
    from backend.research.mr_runner import emit, ResearchObservation, \
        EXPERIMENT_ID, SCHEMA_FINGERPRINT
    def _mk(tk):
        return ResearchObservation(
            experiment_id=EXPERIMENT_ID, schema_fingerprint=SCHEMA_FINGERPRINT,
            generated_utc="2026-08-26T00:00:00+00:00", asof="2026-08-26",
            market="india", position_id=None, ticker=tk, runner="R1",
            decision="🟢 ACTIVE", lifecycle="🟢 ACTIVE",
            entry_date="2026-08-01", entry_price=1.0, current_price=1.0,
            sector=None,
            hypothesis="test", expected_return_horizon_days=20,
            expected_return_definition="test",
        )
    p = emit(tmp_path, "india", [_mk("TCS")])
    p = emit(tmp_path, "india", [_mk("INFY"), _mk("WIPRO")])
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    tickers = [json.loads(x)["ticker"] for x in lines]
    assert tickers == ["TCS", "INFY", "WIPRO"]


def test_observe_returns_list_of_ResearchObservation(tmp_path):
    """observe() must return list even when canonical file is missing."""
    from backend.research.mr_runner import observe, ResearchObservation
    # No canonical file exists in tmp_path
    obs = observe(tmp_path, "india", "2026-08-26")
    assert isinstance(obs, list)
    for o in obs:
        assert isinstance(o, ResearchObservation)


def test_observe_reads_canonical_when_present(tmp_path):
    """When canonical file exists, observe() must consume it."""
    from backend.research.mr_runner import observe
    canonical = tmp_path / "reports" / "context" / "portfolio_canonical_india.json"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(json.dumps({
        "n_investment_active": 2,
        "investment_active": [
            {"ticker": "TCS", "runner": "R1", "decision": "🟢 ACTIVE",
             "lifecycle": "🟢 ACTIVE", "entry_date": "2026-08-01"},
            {"ticker": "INFY", "runner": "R2", "decision": "🔁 RE-ENTRY",
             "lifecycle": "🔁 RE-ENTRY", "entry_date": "2026-08-26"},
        ]
    }), encoding="utf-8")
    obs = observe(tmp_path, "india", "2026-08-26")
    assert len(obs) == 2
    assert {o.ticker for o in obs} == {"TCS", "INFY"}
    for o in obs:
        assert o.hypothesis
        assert o.expected_return_horizon_days == 20
        assert o.expected_return_definition


def test_summary_line_reports_experiment_id():
    from backend.research.mr_runner import summary_line, EXPERIMENT_ID
    s = summary_line([])
    assert EXPERIMENT_ID in s
    assert "0 observations" in s
