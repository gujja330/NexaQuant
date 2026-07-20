"""Promotion Gate — Sprint 2.6.

No feature or model reaches production automatically. Promotion requires:
  - Successful backtest (if applicable)
  - Successful walk-forward validation
  - Statistical significance
  - Stability across regimes
  - Explicit operator approval

The gate returns PromotionDecision — the operator's UI (or a CLI) invokes
`approve_feature()` / `approve_model()` after reviewing the evidence.
"""
from backend.promotion.promotion_gate import (                                             # noqa: F401
    PromotionDecision, PromotionCriteria,
    check_promotion, approve_feature, approve_model,
)
