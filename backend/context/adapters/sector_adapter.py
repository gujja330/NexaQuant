"""Sector rotation adapter · reads sector_rotation.json · adjusts based on
where THIS ticker's sector sits in today's leadership ranking.

Rules:
    Sector rank 1-3    (leader)     → +3.0 pts
    Sector rank 4-6    (mid)        →  0.0 pts
    Sector rank 7-10   (laggard)    → -2.5 pts
    Sector rank 11+    (bottom)     → -4.0 pts
    Sector missing               → 0.0 pts (no penalty for unknown)

Solves operator's TCS example: if IT ranks 8/12 today, TCS gets -2.5
even though its own features say STRONG BUY.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class SectorAdapter:
    engine_name = "sector"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        p = root / ("usa/reports" if market == "usa" else "reports") / "sector_rotation.json"
        if not p.exists():
            return zero_contribution(self.engine_name, "sector_rotation.json missing")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return zero_contribution(self.engine_name,
                                              f"parse error · {type(e).__name__}")
        ranked = d.get("ranked_sectors") or d.get("sectors") or []
        if not ranked:
            return zero_contribution(self.engine_name, "no ranked_sectors")

        rec_sector = str(rec.get("sector") or "")
        if not rec_sector:
            return zero_contribution(self.engine_name, "rec has no sector")

        # Find this sector's rank
        rank = None
        for i, s in enumerate(ranked, 1):
            name = s.get("sector") or s.get("name") if isinstance(s, dict) else str(s)
            if name == rec_sector:
                rank = i
                break
        if rank is None:
            return zero_contribution(self.engine_name,
                                              f"sector '{rec_sector}' not in ranking")

        if rank <= 3:   pts, sev = 3.0, "info"
        elif rank <= 6: pts, sev = 0.0, "info"
        elif rank <= 10: pts, sev = -2.5, "warning"
        else:            pts, sev = -4.0, "critical"

        reason = f"sector {rec_sector} rank {rank}/{len(ranked)} → {pts:+.1f}pts"
        return ContextContribution(
            engine_name=self.engine_name, contribution_pts=pts,
            reason=reason, severity=sev, data_available=True,
            metadata={"sector": rec_sector, "rank": rank, "n_sectors": len(ranked)},
        )
