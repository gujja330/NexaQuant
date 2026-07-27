"""backend.portfolio.monitoring — Portfolio Attribution + drift + rebalance-diff.

Wave 5 · Phase 10 · CODE BUILD (2026-07-27)

Owner:     05_portfolio/monitoring (Layer 6)
Purpose:   Every position exposes its return contribution decomposed across
           13 factors (Momentum · Value · Quality · Growth · Sector · Macro
           · Risk · Fundamentals · News · Corp Actions · Execution · Learning
           · Residual).
"""
from __future__ import annotations

from backend.portfolio.monitoring.attribution import (  # noqa: F401
    PortfolioAttributionEngine,
    PositionAttribution,
    PortfolioAttribution,
    AttributionSource,
    compute_attribution,
    ATTRIBUTION_FACTORS,
)

__version__ = "1.0.0"
__schema_fingerprint__ = "aegis.portfolio_attribution.v1.20260727"
__constitution_articles__ = ("Article 21", "Article 25")
