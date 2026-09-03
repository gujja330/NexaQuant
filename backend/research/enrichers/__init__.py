"""AEGIS Outcome Dataset enrichers · Batch B substrate layer.

Each enricher populates ONE column of the Outcome Dataset from a
source-of-truth artifact. Enrichers are:
  - deterministic
  - PIT-safe (only use data available at entry_date)
  - no-fabrication (missing source → UNKNOWN, never a plausible-looking guess)
  - transparent (record source + mapping in the emitted rows)

Enrichers are the substrate that turns BLOCKED experiments into
interpretable evidence. They do NOT modify experiment code.
"""
from backend.research.enrichers.regime import enrich_regime, REGIME_VOCAB, MR_TO_PDF_MAP

__all__ = ["enrich_regime", "REGIME_VOCAB", "MR_TO_PDF_MAP"]
