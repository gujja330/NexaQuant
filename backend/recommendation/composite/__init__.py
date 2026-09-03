"""Composite Meta-Ensemble Layer · reads admitted runners · writes to none.

Sprint A · CEO 2026-09-03 · GAP 2 reconciliation.

Configuration lives in configs/aegis_runner_registry.yaml under `composite:`.
Runner admission is staged · R1+R2 from Day 0 · R3 admitted when
trailing_closed_trades(R3) >= 50 (typically post Day-60 shadow).

Trust_Weight(r) is derived from trailing realized IC per runner · with a
hard sample-size floor:

    Trust_Weight(r) = 0  if trailing_closed_trades(r) < 50

Meaning R3 contributes zero to Composite_Score until its shadow sample
matures. Writes ONLY to reports/research/composite/ · never Registry.
"""
from backend.recommendation.composite.engine import (
    compute_composite_score, admission_state, trust_weight,
)

__all__ = ["compute_composite_score", "admission_state", "trust_weight"]
