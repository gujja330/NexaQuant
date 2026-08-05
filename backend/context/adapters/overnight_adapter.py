"""Global overnight adapter · reads global_overnight.json ·
routes overnight index weakness to per-sector context drag.

This is the adapter that answers operator's IT-down question:
if NASDAQ was -1.5% overnight, all Indian Technology positions get
a drag proportional to NASDAQ move × Technology sensitivity to NASDAQ.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class OvernightAdapter:
    engine_name = "overnight"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        p = root / "reports" / "context" / "global_overnight.json"
        if not p.exists():
            return zero_contribution(self.engine_name,
                                              "global_overnight.json missing "
                                              "(run scripts/ingest_global_overnight.py)")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return zero_contribution(self.engine_name,
                                              f"parse error · {type(e).__name__}")
        sector_drag = d.get("sector_drag") or {}
        if not sector_drag:
            return zero_contribution(self.engine_name,
                                              "no overnight sector drag today (indices stable)")
        rec_sector = str(rec.get("sector") or "")
        drag = float(sector_drag.get(rec_sector) or 0)
        if abs(drag) < 0.1:
            return zero_contribution(self.engine_name,
                                              f"sector {rec_sector} unaffected by overnight moves")
        # Build reason string with which indices moved
        moves = []
        for yft, v in (d.get("per_index") or {}).items():
            pct = v.get("pct_change")
            if isinstance(pct, (int, float)) and abs(pct) > 0.5:
                moves.append(f"{v.get('name', yft)} {pct:+.1f}%")
        moves_str = " · ".join(moves[:3]) if moves else "overnight weakness"
        severity = "critical" if drag < -2 else ("warning" if drag < -1 else "info")
        reason = f"overnight {moves_str} → {rec_sector} drag {drag:+.1f}pts"
        return ContextContribution(
            engine_name=self.engine_name, contribution_pts=drag,
            reason=reason, severity=severity, data_available=True,
            metadata={"sector": rec_sector, "sector_drag": drag,
                          "n_indices_moved": len(moves)},
        )
