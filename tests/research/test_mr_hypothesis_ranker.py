"""M-R · hypothesis ranker property tests."""
from backend.research.mr_hypothesis_ranker import (
    _evidence_pts, _preventability_pts, _fetch_finding_severity,
    SEVERITY_PTS, VERDICT_PTS,
)


def test_evidence_pts_ladder():
    assert _evidence_pts(1000) == 3
    assert _evidence_pts(500) == 3
    assert _evidence_pts(499) == 2
    assert _evidence_pts(100) == 2
    assert _evidence_pts(99) == 1
    assert _evidence_pts(20) == 1
    assert _evidence_pts(19) == 0
    assert _evidence_pts(0) == 0


def test_preventability_flags_relevant_ids():
    assert _preventability_pts("aegis_mr_ticket_20260827_india_confidence_anti_signal") == 2
    assert _preventability_pts("aegis_mr_ticket_20260827_india_top3_rank_inversion") == 2
    assert _preventability_pts("aegis_mr_ticket_20260827_india_band_boundary") == 2
    assert _preventability_pts("aegis_mr_ticket_20260827_india_stop_policy") == 2
    assert _preventability_pts("aegis_mr_ticket_20260827_something_unrelated") == 0


def test_severity_pts_ladder():
    assert SEVERITY_PTS["CRITICAL"] == 5
    assert SEVERITY_PTS["HIGH"]     == 4
    assert SEVERITY_PTS["MEDIUM"]   == 3
    assert SEVERITY_PTS["LOW"]      == 2
    assert SEVERITY_PTS["INFO"]     == 1


def test_verdict_pts_ladder():
    assert VERDICT_PTS["PRODUCTION_CANDIDATE"]  == 3
    assert VERDICT_PTS["INSUFFICIENT_EVIDENCE"] == 2
    assert VERDICT_PTS["OBSERVATION_ONLY"]      == 1


def test_fetch_finding_severity_heuristics():
    findings = []
    assert _fetch_finding_severity(findings,
        "aegis_mr_ticket_20260827_india_negative_alpha") == "CRITICAL"
    assert _fetch_finding_severity(findings,
        "aegis_mr_ticket_20260827_india_confidence_anti_signal") == "HIGH"
    assert _fetch_finding_severity(findings,
        "aegis_mr_ticket_20260827_india_top3_rank_inversion") == "HIGH"
    assert _fetch_finding_severity(findings,
        "aegis_mr_ticket_20260827_india_band_boundary") == "MEDIUM"


def test_fetch_finding_severity_prefers_exact_match():
    findings = [{"finding_id": "F001_INDIA_ALPHA", "severity": "LOW"}]
    # exact match should override heuristic
    assert _fetch_finding_severity(findings, "F001_INDIA_ALPHA") == "LOW"
