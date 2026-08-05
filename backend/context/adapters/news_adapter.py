"""News adapter · reads ai_news_narrative.json + market_intelligence.json
· penalizes recommendations in sectors with negative sector-level news
sentiment.

Rules (sentiment score per sector · scale [-1, +1]):
    sentiment > 0.3         → +1.5 pts
    sentiment in [-0.3, 0.3] → 0 pts (neutral)
    sentiment in [-0.6, -0.3] → -2.0 pts (soft negative)
    sentiment < -0.6         → -4.0 pts (hard negative)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class NewsAdapter:
    engine_name = "news"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        reports = root / ("usa/reports" if market == "usa" else "reports")

        # Try multiple sources · defensive per operator's "never crash" rule
        sentiment_map = {}
        for name in ("news_sentiment_summary.json", "ai_news_narrative.json",
                          "market_intelligence.json"):
            p = reports / name
            if not p.exists(): continue
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            # Common shapes: {"sector_sentiment": {"IT": -0.5, ...}}
            for key in ("sector_sentiment", "per_sector_sentiment",
                             "sector_scores", "sector_news"):
                v = d.get(key)
                if isinstance(v, dict):
                    sentiment_map.update({k: float(x) if isinstance(x, (int, float))
                                                    else 0.0 for k, x in v.items()})

        if not sentiment_map:
            return zero_contribution(self.engine_name, "no sector news sentiment found")

        sector = str(rec.get("sector") or "")
        if not sector or sector not in sentiment_map:
            return zero_contribution(self.engine_name, f"sector '{sector}' not in news map")

        score = sentiment_map[sector]
        # Normalise if the source was 0-100 instead of -1..1
        if abs(score) > 1: score = (score - 50) / 50

        if score > 0.3:    pts, sev = 1.5, "info"
        elif score > -0.3: pts, sev = 0.0, "info"
        elif score > -0.6: pts, sev = -2.0, "warning"
        else:               pts, sev = -4.0, "critical"

        if pts == 0.0:
            return zero_contribution(self.engine_name,
                                              f"sector news neutral (score={score:+.2f})")

        reason = f"news for {sector} score={score:+.2f} → {pts:+.1f}pts"
        return ContextContribution(
            engine_name=self.engine_name, contribution_pts=pts,
            reason=reason, severity=sev, data_available=True,
            metadata={"sector": sector, "sentiment": score},
        )
