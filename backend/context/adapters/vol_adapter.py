"""Volatility adapter · reads volatility_intelligence.json · penalizes
recommendations when VIX is elevated (broad risk-off → reduce conviction).

Rules (VIX percentile-based · normalises across regimes):
    percentile < 30    (calm)         → +1.0 pts
    percentile 30-70   (normal)       →  0.0 pts
    percentile 70-90   (elevated)     → -2.0 pts
    percentile 90-100  (stress)       → -4.5 pts
    Absolute VIX > 30 override        → -3.0 pts
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class VolAdapter:
    engine_name = "vol_risk"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        p = root / ("usa/reports" if market == "usa" else "reports") / "volatility_intelligence.json"
        if not p.exists():
            return zero_contribution(self.engine_name, "volatility_intelligence.json missing")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return zero_contribution(self.engine_name, f"parse error · {type(e).__name__}")

        # Try common keys
        vix_level = d.get("vix") or d.get("vix_level") or d.get("india_vix")
        vix_pct = d.get("vix_percentile") or d.get("percentile")

        if vix_level is None and vix_pct is None:
            return zero_contribution(self.engine_name, "no vix data in file")

        pts = 0.0
        severity = "info"
        reason_parts = []

        if isinstance(vix_pct, (int, float)):
            if vix_pct < 30:   pts += 1.0; reason_parts.append(f"vix pctile {vix_pct:.0f} (calm)")
            elif vix_pct < 70: pass       ; reason_parts.append(f"vix pctile {vix_pct:.0f} (normal)")
            elif vix_pct < 90:
                pts += -2.0; severity = "warning"
                reason_parts.append(f"vix pctile {vix_pct:.0f} (elevated)")
            else:
                pts += -4.5; severity = "critical"
                reason_parts.append(f"vix pctile {vix_pct:.0f} (stress)")

        if isinstance(vix_level, (int, float)) and vix_level > 30:
            pts += -3.0
            severity = "critical"
            reason_parts.append(f"absolute VIX {vix_level:.1f} > 30")

        if pts == 0.0 and not reason_parts:
            return zero_contribution(self.engine_name, "vol within normal band")

        reason = " · ".join(reason_parts) + f" → {pts:+.1f}pts"
        return ContextContribution(
            engine_name=self.engine_name, contribution_pts=pts,
            reason=reason, severity=severity, data_available=True,
            metadata={"vix_level": vix_level, "vix_percentile": vix_pct},
        )
