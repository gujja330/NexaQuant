"""Market Breadth adapter · reads market_breadth.json · uses sector breadth
to reduce conviction when the sector as a whole is weak.

Solves: TCS may be strong technically but if only 2/10 IT stocks are up
today, sector-level breadth is 20% (very weak) · reduce conviction.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class BreadthAdapter:
    engine_name = "breadth"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        p = root / "reports" / "context" / "market_breadth.json"
        if not p.exists():
            return zero_contribution(self.engine_name, "market_breadth.json missing")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return zero_contribution(self.engine_name, f"parse error · {type(e).__name__}")
        if not d.get("available"):
            return zero_contribution(self.engine_name,
                                              d.get("reason", "breadth unavailable"))
        rec_sector = str(rec.get("sector") or "")
        per_sector = d.get("per_sector") or {}
        s = per_sector.get(rec_sector)
        if not s:
            # Fallback to overall breadth
            overall_ad = d.get("overall_ad_ratio_pct", 50)
            if overall_ad < 30: pts = -2.0; sev = "warning"
            elif overall_ad < 40: pts = -1.0; sev = "info"
            elif overall_ad > 70: pts = 1.5; sev = "info"
            elif overall_ad > 60: pts = 0.8; sev = "info"
            else: return zero_contribution(self.engine_name,
                                                       f"overall breadth {overall_ad}% neutral")
            reason = f"overall breadth {overall_ad}% → {pts:+.1f}pts"
            return ContextContribution(engine_name=self.engine_name,
                                                 contribution_pts=pts, reason=reason,
                                                 severity=sev, data_available=True,
                                                 metadata={"overall_ad_pct": overall_ad})
        ad_pct = s.get("ad_ratio_pct", 50)
        above_50 = s.get("above_50dma_pct", 50)
        avg_health = (ad_pct + above_50) / 2
        if avg_health < 20:   pts, sev = -4.0, "critical"
        elif avg_health < 35: pts, sev = -2.5, "warning"
        elif avg_health < 50: pts, sev = -1.0, "info"
        elif avg_health > 75: pts, sev =  2.0, "info"
        elif avg_health > 65: pts, sev =  1.0, "info"
        else: return zero_contribution(self.engine_name,
                                                  f"sector {rec_sector} breadth normal ({avg_health:.0f}%)")
        reason = (f"sector {rec_sector} breadth: {s.get('advancers')}/{s.get('n')} "
                     f"adv · {above_50:.0f}% above 50DMA → {pts:+.1f}pts")
        return ContextContribution(engine_name=self.engine_name,
                                             contribution_pts=pts, reason=reason,
                                             severity=sev, data_available=True,
                                             metadata={"sector": rec_sector, **s})
