"""Sprint G-E · Portfolio Correlation Adapter · reads correlation_matrix.json.

For each recommendation, checks avg correlation to currently-held R006
portfolio positions. Rewards diversification · penalizes concentration.

Rules:
    · avg_corr_to_others > 0.75  → concentration risk -3.0 (critical)
    · avg_corr_to_others > 0.55  → mild concentration -1.5
    · avg_corr_to_others < 0.25  → diversification bonus +1.5
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class CorrelationAdapter:
    engine_name = "portfolio"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        p = root / "reports" / "correlation_matrix.json"
        if not p.exists():
            return zero_contribution(self.engine_name + "_corr",
                                              "correlation_matrix.json missing")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return zero_contribution(self.engine_name + "_corr",
                                              f"parse error · {type(e).__name__}")

        if not d.get("available"):
            return zero_contribution(self.engine_name + "_corr",
                                              d.get("reason", "correlation unavailable"))

        ticker = str(rec.get("ticker") or "").replace(".NS", "").replace(".BO", "").upper()
        risk = d.get("portfolio_concentration_risk") or []
        entry = next((r for r in risk if r.get("ticker") == ticker), None)
        if not entry:
            return zero_contribution(self.engine_name + "_corr",
                                              f"{ticker} not in correlation matrix")

        avg_corr = entry.get("avg_corr_to_others") or 0
        if avg_corr > 0.75:   pts, sev = -3.0, "critical"; label = "high concentration risk"
        elif avg_corr > 0.55: pts, sev = -1.5, "warning"; label = "mild concentration"
        elif avg_corr < 0.25: pts, sev = 1.5, "info"; label = "adds diversification"
        else:
            return zero_contribution(self.engine_name + "_corr",
                                              f"{ticker} moderate correlation ({avg_corr})")

        reason = f"{ticker} avg-corr {avg_corr:.2f} to universe · {label} → {pts:+.1f}pts"
        return ContextContribution(
            engine_name=self.engine_name + "_corr", contribution_pts=pts,
            reason=reason, severity=sev, data_available=True,
            metadata={"ticker": ticker, "avg_corr": avg_corr},
        )
