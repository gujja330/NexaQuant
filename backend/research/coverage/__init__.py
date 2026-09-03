"""AEGIS Coverage Tracker · CEO 2026-09-03 13-stage discipline.

Every sub-signal across the 20 domains is classified honestly into ONE of:
    Mapped · Data-required · PIT-ready · Populated · Implemented · Tested ·
    OOS · Corrected · Incremental · Paper · Shadow · Candidate · Production

Only PRODUCTION = "AEGIS is actually using it in production."
Everything else is degrees of NOT USED.

This prevents "schema exists" from ever looking like "fundamentals integrated."
"""
from backend.research.coverage.tracker import (
    STAGES, COVERAGE_MAP, coverage_summary, coverage_full,
    coverage_by_domain, domain_readiness_score,
)

__all__ = ["STAGES", "COVERAGE_MAP", "coverage_summary", "coverage_full",
           "coverage_by_domain", "domain_readiness_score"]
