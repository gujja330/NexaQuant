"""backend.recommendation.opportunity_cost — Opportunity Cost Engine.

Wave 5 · Phase 9 · CODE BUILD (2026-07-27)

Every HOLD must justify "why not rotate". Enrichment engine that annotates
each HOLD with: oc_next_best_ticker · oc_expected_alpha_delta · oc_reason.

Owner:     04_recommendation/opportunity_cost (Layer 5)
Inputs:    HOLDs from recommendations_v3.json + full candidate universe
Outputs:   enrichment fields on each HOLD rec
Schema:    aegis.opportunity_cost.v1
Validator: validation/recommendation_validation/opportunity_cost_validator.py
"""
from __future__ import annotations

from backend.recommendation.opportunity_cost.engine import (  # noqa: F401
    OpportunityCostEngine,
    OpportunityCostEnrichment,
    enrich_holds,
)

__version__ = "1.0.0"
__schema_fingerprint__ = "aegis.opportunity_cost.v1.20260727"
__constitution_articles__ = ("Article 21", "Article 25")
