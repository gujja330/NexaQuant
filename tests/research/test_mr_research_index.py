"""CEO 2026-08-27 · research_index.csv/json 8-field contract tests."""
from backend.research.mr_archive_index import (
    CEO_INDEX_FIELDS, _ceo_index_row, _next_action, _evidence_source,
)


def test_ceo_index_has_8_fields():
    assert set(CEO_INDEX_FIELDS) == {
        "research_id", "hypothesis", "evidence", "sample_size",
        "result", "status", "superseded_by", "next_action",
    }


def test_evidence_source_experiment_path():
    p = _evidence_source("experiment", "aegis_mr_experiment_20260827_e1")
    assert "reports/research/experiments/aegis_mr_experiment_20260827_e1" in p


def test_evidence_source_data_gap_path():
    p = _evidence_source("data_gap", "gap")
    assert "data_quality" in p


def test_next_action_accumulate_when_below_target():
    a = _next_action("ACTIVE_SHADOW", 50, 100)
    assert "ACCUMULATE" in a
    assert "50/100" in a


def test_next_action_run_acceptance_when_at_target():
    a = _next_action("ACTIVE_SHADOW", 100, 100)
    assert a == "RUN_ACCEPTANCE_EVALUATION"


def test_next_action_paper_trade_when_passed():
    a = _next_action("PASSED", 100, 100)
    assert "PAPER_TRADE" in a


def test_next_action_recheck_when_failed():
    a = _next_action("FAILED", 100, 100)
    assert "RECHECK" in a
    assert "300" in a  # min_n * 3


def test_next_action_refer_when_superseded():
    a = _next_action("SUPERSEDED_BY", 100, 100)
    assert "REFER_TO_SUCCESSOR" in a


def test_next_action_data_gap_fix_first():
    a = _next_action("DATA_GAP", 0, 100)
    assert a == "FIX_DATA_SOURCE_FIRST"


def test_ceo_index_row_has_all_8_keys():
    card = {
        "experiment_id":     "aegis_mr_experiment_20260827_e1",
        "hypothesis":        "R1 top-3 weak · filter improves WR by 5pp",
        "hist_n":            185,
        "fwd_n":             30,
        "min_sample_size":   100,
        "decision":          "PENDING (accumulating)",
        "status_5way":       "PROMISING_NEED_MORE_DATA",
        "current_status":    "ACTIVE_SHADOW",
        "superseded_by":     None,
        "kind":              "experiment",
    }
    row = _ceo_index_row(card)
    assert set(row.keys()) == set(CEO_INDEX_FIELDS)
    assert row["research_id"] == "aegis_mr_experiment_20260827_e1"
    assert row["evidence"].endswith("aegis_mr_experiment_20260827_e1/")
    assert "historical_n=185" in row["sample_size"]
    assert "forward_n=30" in row["sample_size"]
    assert "target_n=100" in row["sample_size"]
    assert row["superseded_by"] == "—"
    assert "ACCUMULATE" in row["next_action"]


def test_ceo_index_row_superseded_shows_successor():
    card = {
        "experiment_id":     "aegis_mr_old",
        "hypothesis":        "h",
        "hist_n":            100,
        "fwd_n":             1,
        "min_sample_size":   100,
        "decision":          "RETIRED",
        "status_5way":       "SUPERSEDED_KEEP_HISTORY",
        "current_status":    "SUPERSEDED_BY",
        "superseded_by":     "aegis_mr_e1",
        "kind":              "experiment",
    }
    row = _ceo_index_row(card)
    assert row["superseded_by"] == "aegis_mr_e1"
