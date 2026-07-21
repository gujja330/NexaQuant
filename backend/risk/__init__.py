"""Sprint 4 · Risk Engine — sizes recommendations into positions with explicit risk budgets.

Consumes Sprint 3's `recommendations_v3.json`. Applies:
  - Kelly-fractional × confidence-tier sizing
  - Inverse-volatility scaling
  - Per-ticker / per-sector exposure caps
  - Portfolio-level VaR + CVaR budgeting
  - Regime-aware dampeners (via market_intelligence_summary)

Produces `sized_positions.json` + `risk_report.json` per market. Downstream
Sprint 5 Portfolio Engine consumes the sized positions.

Contracts:
  - Deterministic (same inputs + cutoff → identical output)
  - Walk-forward safe (accepts cutoff; no future data)
  - Human-in-the-loop for promotion (engine outputs marked EXPERIMENTAL)
  - AI Risk Analyst never promotes
  - Model registry stamp on every sized position
"""
from backend.risk.types            import (                                                # noqa: F401
    SizedPosition, RiskBudget, RiskReport, CapReason,
)
from backend.risk.sizing           import kelly_fractional_size, confidence_tier_multiplier # noqa: F401
from backend.risk.exposure_caps    import apply_per_ticker_cap, apply_per_sector_cap        # noqa: F401
from backend.risk.vol_adjustment   import vol_adjusted_size, vix_regime_dampener            # noqa: F401
from backend.risk.concentration    import herfindahl_hirschman, top_k_concentration_pct     # noqa: F401
from backend.risk.var_cvar         import parametric_var_cvar                                # noqa: F401
from backend.risk.engine           import RiskEngine                                        # noqa: F401
