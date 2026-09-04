"""C.1 · Tests · MR trial-accounting hook records family/trial metadata correctly."""
from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.research.evidence import evidence_log
from backend.research.evidence.mr_evidence_recorder import (
    record_family_to_evidence_log, _enumerate_cohorts, FAMILY_ID_TEMPLATE,
)


def _fake_mr_json():
    return {
        "engine": "test.mr_forward_validation.fake",
        "market": "usa",
        "asof": "2026-08-27",
        "n_observations": 100,
        "forward_horizons_days": [1, 3, 5, 10, 17],
        "cohort_ALL": {"n": 100, "statistical_verdict": "PRODUCTION_CANDIDATE",
                        "fwd_5d_avg": -0.5, "fwd_5d_win_rate_pct": 35.0},
        "cohort_by_runner": {
            "R2": {"n": 90, "statistical_verdict": "PRODUCTION_CANDIDATE",
                    "fwd_5d_avg": -0.6, "fwd_5d_win_rate_pct": 34.0},
            "R1": {"n": 10, "statistical_verdict": "OBSERVATION_ONLY",
                    "fwd_5d_avg": 0.4, "fwd_5d_win_rate_pct": 45.0},
        },
        "cohort_by_investability": {
            "QUALITY": {"n": 20, "statistical_verdict": "INSUFFICIENT",
                          "fwd_5d_avg": -1.0, "fwd_5d_win_rate_pct": 30.0},
            "MARGINAL": {"n": 25, "statistical_verdict": "INSUFFICIENT",
                           "fwd_5d_avg": 0.2, "fwd_5d_win_rate_pct": 40.0},
        },
        "cohort_by_runner_band": {
            "R2·QUALITY": {"n": 18, "statistical_verdict": "OBSERVATION_ONLY",
                             "fwd_5d_avg": -1.1, "fwd_5d_win_rate_pct": 28.0},
        },
        "cohort_by_entry_type": {
            "FIRST-ENTRY": {"n": 100, "statistical_verdict": "PRODUCTION_CANDIDATE",
                             "fwd_5d_avg": -0.5, "fwd_5d_win_rate_pct": 35.0},
        },
    }


def test_c1_enumerate_cohorts_flattens_all_kinds():
    """_enumerate_cohorts must produce one row per cohort_* leaf."""
    cohorts = _enumerate_cohorts(_fake_mr_json())
    # 1 ALL + 2 runners + 2 bands + 1 runner_band + 1 entry_type = 7
    assert len(cohorts) == 7
    kinds = {c["kind"] for c in cohorts}
    assert kinds == {"overall", "runner", "investability", "runner_band", "entry_type"}


def test_c1_family_id_deterministic():
    """Same market + asof → same family_id · reproducible."""
    fid1 = FAMILY_ID_TEMPLATE.format(market="usa", asof="2026-08-27")
    fid2 = FAMILY_ID_TEMPLATE.format(market="usa", asof="2026-08-27")
    assert fid1 == fid2
    assert "MR_FWD_COHORT" in fid1
    assert "usa" in fid1 and "2026-08-27" in fid1


def test_c1_records_family_metadata_to_evidence_log(tmp_path: Path):
    """Every recorded trial must carry family_id + trial_number + total_planned_trials
    in the Evidence Log fold_definition + multiple_testing_correction blocks."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True); (root / ".git" / "HEAD").write_text("abcd\n", encoding="utf-8")
    # Seed a fake MR JSON at the expected path
    mr_p = root / "reports" / "research" / "mr_forward_validation_usa.json"
    mr_p.parent.mkdir(parents=True, exist_ok=True)
    mr_p.write_text(json.dumps(_fake_mr_json()), encoding="utf-8")

    r = record_family_to_evidence_log(root, "usa")
    assert r["status"] == "OK"
    assert r["family_id"] == "MR_FWD_COHORT_usa_2026-08-27"
    assert r["total_planned_trials"] == 7

    # Read back the evidence log · verify every record has the metadata
    log = evidence_log.read_evidence_log(root)
    assert len(log) == 7, f"expected 7 records · got {len(log)}"
    for i, rec in enumerate(log, start=1):
        fd = rec["fold_definition"]
        assert fd["family_id"] == r["family_id"]
        assert fd["trial_number"] == i
        assert fd["total_planned_trials"] == 7
        assert fd["cohort_key"]
        assert fd["cohort_kind"]
        assert rec["trial_count"] == 7    # AUDIT-03 · full family size
        mtc = rec["multiple_testing_correction"]
        assert mtc["family_id"] == r["family_id"]
        assert mtc["trial_number"] == i
        assert mtc["total_planned_trials"] == 7
        assert mtc["applied"] is False   # correction applied post-facto


def test_c1_sample_tier_classification(tmp_path: Path):
    """Every trial gets a sample tier per locked V2 rules · n<5 obs · 5-14 hyp ·
    15-29 research_signal · 30-49 stronger_evidence · 50+ validation_candidate."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True); (root / ".git" / "HEAD").write_text("abcd\n", encoding="utf-8")
    mr_p = root / "reports" / "research" / "mr_forward_validation_usa.json"
    mr_p.parent.mkdir(parents=True, exist_ok=True)
    mr_p.write_text(json.dumps(_fake_mr_json()), encoding="utf-8")
    record_family_to_evidence_log(root, "usa")
    log = evidence_log.read_evidence_log(root)
    tier_by_n = {rec["sample_size"]: rec["parameters"]["sample_tier"] for rec in log}
    # From fake · n values are 100 (x2 · ALL + entry_type + FIRST-ENTRY), 90, 10, 20, 25, 18
    if 100 in tier_by_n: assert tier_by_n[100] == "validation_candidate"
    if 90 in tier_by_n:  assert tier_by_n[90]  == "validation_candidate"
    if 25 in tier_by_n:  assert tier_by_n[25]  == "research_signal"
    if 20 in tier_by_n:  assert tier_by_n[20]  == "research_signal"
    if 18 in tier_by_n:  assert tier_by_n[18]  == "research_signal"
    if 10 in tier_by_n:  assert tier_by_n[10]  == "hypothesis"


def test_c1_missing_mr_json_returns_clean_error(tmp_path: Path):
    """No MR json · return MR_JSON_MISSING · never crash."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True); (root / ".git" / "HEAD").write_text("abcd\n", encoding="utf-8")
    r = record_family_to_evidence_log(root, "usa")
    assert r["status"] == "MR_JSON_MISSING"


def test_c1_never_writes_to_production_paths(tmp_path: Path):
    """The recorder must ONLY write to reports/research/evidence/evidence_log.jsonl."""
    import inspect
    src = inspect.getsource(record_family_to_evidence_log)
    # Should not reference production paths
    forbidden = ("reports/telegram", "configs/ensemble_weights",
                  "backend/recommendation/", "opportunity_registry")
    for f in forbidden:
        assert f not in src, f"C.1 recorder references forbidden production path: {f}"
