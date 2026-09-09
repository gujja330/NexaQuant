"""AEGIS RUN CONTRACT · the five fail-closed gates.

Each test below corresponds to a failure that actually shipped:

  DATA/FEATURES  a 50-day-old feature store scored as if it were today
  SCORES         four qualified BUYs discarded before any rule saw them
  DECISION       a BUY that reached no registry entry and nothing stopped
  FIELDS         rows delivered with an empty Stop column
  DELIVERY       a gate that measured staleness and allowed the send

The point of every one is the same: the pipeline must REFUSE, not report.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.pipeline.contract import completeness, readiness, scoring
from backend.pipeline.contract.run_context import (RunContext, StageContract,
                                                   new_run_id, resolve_asof)

ROOT = Path(__file__).resolve().parents[2]
MARKETS = ("india", "usa")


def _ctx(market="india", asof=None):
    return RunContext(market=market, requested_asof=asof or resolve_asof(),
                      root=ROOT)


# ── identity and fail-closed plumbing ───────────────────────────────────

def test_run_id_carries_market_and_asof():
    rid = new_run_id("india", "2026-09-09")
    assert rid.startswith("AEGIS-2026-09-09-INDIA-")


def test_asof_is_decided_once():
    ctx = _ctx(asof="2026-09-09")
    a = ctx.stage("X")
    assert a.input_asof == "2026-09-09"
    assert ctx.requested_asof == "2026-09-09"


def test_downstream_refuses_when_upstream_blocked():
    ctx = _ctx()
    c = ctx.stage("DATA_READY").block("SOURCE_STALE", "50 days old")
    ctx.record(c)
    why = ctx.upstream_ok("DATA_READY")
    assert why and "BLOCKED" in why


def test_downstream_refuses_when_upstream_never_ran():
    assert "did not run" in (_ctx().upstream_ok("DATA_READY") or "")


def test_first_failure_is_singular_and_named():
    ctx = _ctx()
    ctx.record(ctx.stage("A").block("FIRST", "one"))
    ctx.record(ctx.stage("B").block("SECOND", "two"))
    assert ctx.first_failure["code"] == "FIRST"
    assert ctx.blocked


# ── GATE 1/2 · the July-21 failure ──────────────────────────────────────

def test_stale_substrate_blocks_the_run():
    """A snapshot older than its budget must stop everything."""
    ctx = _ctx(asof=(date.today() + timedelta(days=400)).isoformat())
    c = readiness.check_data_ready(ctx)
    assert c.status == "BLOCK"
    assert any("SOURCE_STALE" in f["code"] for f in c.failures)


def test_feature_budget_is_zero_days():
    """Today's scoring needs today's features · not 'the latest file'."""
    assert readiness.SOURCE_BUDGETS["feature_snapshot"] == 0


def test_snapshot_lookup_is_by_requested_date_not_latest():
    src = Path(readiness.__file__).read_text(encoding="utf-8")
    assert "never 'the latest one'" in src
    # the resolver must compare against the requested date
    assert "if want not in set(list_snapshots" in src


def test_features_ready_blocks_on_asof_mismatch():
    ctx = _ctx(asof="1999-01-04")
    ctx.record(ctx.stage(readiness.STAGE_DATA).ok())
    c = readiness.check_features_ready(ctx)
    assert c.status == "BLOCK"
    assert any(f["code"] == "FEATURE_SNAPSHOT_ASOF_MISMATCH"
               for f in c.failures)


@pytest.mark.parametrize("market", MARKETS)
def test_universe_resolves_to_a_real_number(market):
    """A silent zero makes every coverage ratio meaningless."""
    n = readiness._universe_size(ROOT, market)
    assert n and n > 50, "universe for %s resolved to %r" % (market, n)


# ── GATE 3 · truncation before eligibility ──────────────────────────────

def test_presentation_truncation_is_a_blocking_condition():
    src = Path(scoring.__file__).read_text(encoding="utf-8")
    assert "TRUNCATION_BEFORE_ELIGIBILITY" in src


def test_ensemble_persists_the_full_universe():
    """top_10 + bottom_5 is a display slice · eligibility needs all."""
    import json
    for rel in ("reports/ensemble.json", "usa/reports/ensemble.json"):
        p = ROOT / rel
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d.get("n_all_candidates"), "%s has no all_candidates" % rel
        assert d["n_all_candidates"] > 15


def test_all_candidates_carry_per_model_scores():
    """Omitting them made every row look like a disagreement -> HOLD."""
    import json
    for rel in ("reports/ensemble.json", "usa/reports/ensemble.json"):
        p = ROOT / rel
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        rows = d.get("all_candidates") or []
        assert rows and rows[0].get("per_model_score") is not None, rel


def test_recommendation_engine_reads_all_candidates():
    for rel in ("usa/research/recommendation_intelligence/run.py",
                "india/recommendation_intelligence/run.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert 'ens.get("all_candidates")' in src, rel


# ── GATE 4 · conservation ───────────────────────────────────────────────

def test_conservation_uses_the_funnel_normalisation():
    """A mismatched spelling reported 228 phantom orphans."""
    assert scoring._norm("MCX.NS") == "MCX"
    assert scoring._norm("BRK.B") == "BRK"
    assert scoring._norm(" aapl ") == "AAPL"


def test_cooling_is_a_terminal_state_not_a_defect():
    src = Path(scoring.__file__).read_text(encoding="utf-8")
    assert "COOLING is a legitimate terminal state" in src


def test_loss_is_judged_by_production_not_by_the_shadow():
    """The shadow re-trains in-process · its BUY is not production's."""
    src = Path(scoring.__file__).read_text(encoding="utf-8")
    assert "_production_buys" in src
    assert "RE-TRAINS the model factory" in src


def test_every_terminal_disposition_is_declared():
    for v in ("L2_hold", "L3_disagreement", "L7_eligible_no_registry",
              "L10_in_current"):
        assert v in scoring.TERMINAL_DISPOSITIONS


# ── FIELDS · the operator-visible gaps ──────────────────────────────────

def test_blank_tokens_are_treated_as_missing():
    for v in (None, "", "None", "nan", "UNAVAILABLE", "N/A"):
        assert completeness._blank(v, "Stop"), repr(v)


def test_em_dash_is_missing_unless_the_contract_allows_it():
    # A Stop is never optional.
    assert completeness._blank("—", "Stop", "NEW") is True
    # Confidence: governed on a legacy holding, never on a NEW row. The
    # twelve USA NEW rows of 2026-09-09 shipped an em-dash here while the
    # SSOT held 0.5905 · that is the gap this distinction closes.
    assert completeness._blank("—", "Confidence %", "NEW") is True
    assert completeness._blank("—", "Confidence %", "ACTIVE") is False
    assert completeness._blank("—", "Confidence %", "ACTIVE+") is False
    # Fields the delivery contract governs outright.
    assert completeness._blank("—", "Target", "NEW") is False


def test_stop_is_required_on_every_actionable_row():
    for action in ("NEW", "ACTIVE+", "ACTIVE"):
        assert "Stop" in completeness.REQUIRED_BY_ACTION[action]
        assert "Entry Price" in completeness.REQUIRED_BY_ACTION[action]


@pytest.mark.parametrize("market", MARKETS)
def test_rendered_workbook_has_no_required_gaps(market):
    res = completeness.scan_workbook(ROOT, market)
    if res.get("error"):
        pytest.skip(res["error"])
    assert not res["required_gaps"], res["required_gaps"][:5]


# ── the run is one path ─────────────────────────────────────────────────

def test_ci_and_manual_execute_the_same_contract():
    for rel in (".github/workflows/aegis-daily.yml",
                ".github/workflows/aegis-usa.yml"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "backend.pipeline.contract.runner" in src, rel


def test_send_is_gated_on_the_contract():
    for rel, step in ((".github/workflows/aegis-daily.yml", "run_contract"),
                      (".github/workflows/aegis-usa.yml", "run_contract_usa")):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert ("steps.%s.outcome == 'success'" % step) in src, rel


def test_critical_substrate_steps_are_not_optional():
    from backend.observability.pipeline_audit import audit_steps
    a = audit_steps(ROOT)
    assert not a["critical_substrate_steps_marked_optional"], a[
        "critical_substrate_steps_marked_optional"]


def test_producers_declare_the_artifact_they_write():
    from backend.observability.pipeline_audit import audit_steps
    a = audit_steps(ROOT)
    assert not a["undeclared_outputs"], a["undeclared_outputs"]


# ── INTERMARKET · the world the stock trades inside ─────────────────────

def test_intermarket_series_are_declared_not_inferred():
    from backend.pipeline.contract import intermarket as im
    labels = {s[0] for s in im.SERIES}
    for required in ("S&P 500", "VIX", "DXY", "USD/INR", "US 10Y",
                     "Oil (Brent/WTI)", "India VIX", "Macro regime"):
        assert required in labels, required


def test_uncollected_series_are_named_not_hidden():
    """A completeness score that counts only what exists is a lie."""
    from backend.pipeline.contract import intermarket as im
    nc = im._not_collected("india")
    assert "Silver" in nc
    assert "India sector indices" in nc
    # USA has no India sector indices to be missing.
    assert "India sector indices" not in im._not_collected("usa")


def test_intermarket_feeds_nothing_into_scoring():
    """Collection is not evidence · D17 stays evidence-blocked."""
    from backend.pipeline.contract import intermarket as im
    s = im.survey(ROOT, "india", resolve_asof())
    assert s["feeds_scoring"] is False
    assert "evidence-BLOCKED" in s["note"]


@pytest.mark.parametrize("market", MARKETS)
def test_no_critical_context_series_is_stale(market):
    """India's global set froze on 2026-06-19 and sat 3 months stale
    while every downstream artifact reported itself fresh."""
    from backend.pipeline.contract import intermarket as im
    s = im.survey(ROOT, market, resolve_asof())
    assert not s["critical_missing"], s["critical_missing"]
    assert not s["critical_stale"], s["critical_stale"]


def test_global_context_producer_is_a_pipeline_step():
    """india/global_risk.py existed but nothing called it."""
    from backend.observability.pipeline_audit import _steps
    names = {s["name"] for s in _steps(ROOT)}
    assert "global_context_bars" in names
    step = next(s for s in _steps(ROOT) if s["name"] == "global_context_bars")
    assert step.get("optional") is False
    assert len(step.get("produces") or []) >= 7


def test_bar_asof_reads_the_last_row_not_the_mtime():
    """mtime moves on a re-run even when the content is unchanged."""
    from backend.pipeline.contract import intermarket as im
    src = Path(im.__file__).read_text(encoding="utf-8")
    assert "never its mtime" in src or "Last row date" in src


def test_global_context_step_actually_fetches():
    """Without --fetch the script only PRINTS · the step would run green
    every day and refresh nothing, recreating the 3-month staleness."""
    from backend.observability.pipeline_audit import _steps
    step = next(s for s in _steps(ROOT) if s["name"] == "global_context_bars")
    assert "--fetch" in (step.get("script_args") or []), step.get("script_args")
    from backend.pipeline.contract import runner
    src = Path(runner.__file__).read_text(encoding="utf-8")
    assert '"india/global_risk.py",\n                            "--fetch"' in src \
        or '"--fetch"' in src
