"""Runner 1 Validation Layer · Option D of the AEGIS v3.0 architecture debate.

Runner 1 (legacy adaptive_rec_v2 · produces data/aegis_today.csv) is
DEMOTED from a competing recommendation engine to a validation layer
that checks agreement with the canonical Runner 2 v3 output.

Runner 1 NO LONGER decides what's recommended. It answers:
  · "Does the conservative/defensive model agree with today's Runner 2 picks?"
  · "What defensive picks did Runner 2 miss?"
  · "Any Runner 2 rec that Runner 1 flat-out rejects?"

Runner 1's orphan picks (e.g. APOLLOHOSP, BHARTIARTL, POWERGRID) live in
an ORPHANS section — visible to the operator for continuity, but NOT
promoted as active AEGIS recommendations. The canonical action decision
remains Runner 2's.

Constitutional compliance:
  · Article 4 (Single Source of Truth) — Runner 2 alone owns the SSoT.
  · Article 5 (No Legacy) — Runner 1 is retained not as a legacy renderer
    but as a NEW-purpose validation engine.
  · Article 12 (Rotation Intelligence) — Runner 1's defensive picks feed
    into rotation analysis as alternative candidates.

Consumed by: Command Center (surfaces agreement + orphans)
"""
from .engine import (
    load_runner1_picks,
    compute_agreement,
    build_validation_report,
    SCHEMA_FINGERPRINT,
    ENGINE_ID,
)

__all__ = [
    "load_runner1_picks",
    "compute_agreement",
    "build_validation_report",
    "SCHEMA_FINGERPRINT",
    "ENGINE_ID",
]
