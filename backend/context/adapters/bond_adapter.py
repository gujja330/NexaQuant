"""Sprint G-A · Bond Yield Regime Adapter · reads FRED yield curve data.

Sources: reports/fred/fred_snapshot.json (DGS10, DGS2, T10Y2Y, DFF)

Rules:
    · 10y > 4.5% AND rising (30d change > 5%)     → growth stocks -2.0
    · 10y < 3.5% AND falling (30d change < -5%)   → growth boost +1.5
    · 10y-2y spread inverted (T10Y2Y < 0)          → recession signal -3.0
    · Fed Funds > 5% + rising                      → market-wide -2.5

Growth sectors we penalize when yields spike:
    Technology · Communication Services · Consumer Discretionary
Value sectors we boost when yields spike:
    Financials · Energy
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


GROWTH_SECTORS = {"Technology", "Communication Services",
                            "Consumer Discretionary", "IT"}
VALUE_SECTORS = {"Financials", "Energy", "Banks"}


class BondAdapter:
    engine_name = "bond"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        p = root / "reports" / "fred" / "fred_snapshot.json"
        if not p.exists():
            return zero_contribution(self.engine_name, "fred_snapshot.json missing")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            series = d.get("series") or {}
        except Exception as e:
            return zero_contribution(self.engine_name,
                                              f"parse error · {type(e).__name__}")

        dgs10 = series.get("DGS10", {})
        t10y2y = series.get("T10Y2Y", {})
        dff = series.get("DFF", {})

        y10 = dgs10.get("latest_value") if dgs10.get("available") else None
        y10_chg30d = dgs10.get("change_30d_pct")
        spread = t10y2y.get("latest_value") if t10y2y.get("available") else None
        fed_funds = dff.get("latest_value") if dff.get("available") else None
        fed_chg30d = dff.get("change_30d_pct")

        if y10 is None and spread is None:
            return zero_contribution(self.engine_name, "no yield data")

        sector = str(rec.get("sector") or "")
        pts = 0.0
        severity = "info"
        reasons = []

        # Recession signal (highest priority)
        if spread is not None and spread < 0:
            pts += -3.0
            severity = "critical"
            reasons.append(f"10y-2y INVERTED ({spread:+.2f})")
        elif spread is not None and spread < 0.2:
            pts += -1.0
            reasons.append(f"10y-2y flat ({spread:+.2f})")

        # 10y regime routing (sector-conditional)
        if y10 is not None and y10 > 4.5:
            rising = isinstance(y10_chg30d, (int, float)) and y10_chg30d > 5
            if sector in GROWTH_SECTORS:
                pts += -2.0 if rising else -1.0
                severity = "warning" if severity == "info" else severity
                reasons.append(f"10y={y10}% high · {sector} growth penalty")
            elif sector in VALUE_SECTORS:
                pts += 1.5
                reasons.append(f"10y={y10}% high · {sector} value boost")
        elif y10 is not None and y10 < 3.5:
            falling = isinstance(y10_chg30d, (int, float)) and y10_chg30d < -5
            if sector in GROWTH_SECTORS:
                pts += 1.5 if falling else 0.8
                reasons.append(f"10y={y10}% low · {sector} growth boost")

        # Fed hike surprise
        if fed_funds is not None and fed_funds > 5 \
           and isinstance(fed_chg30d, (int, float)) and fed_chg30d > 3:
            pts += -1.5
            severity = "warning" if severity == "info" else severity
            reasons.append(f"Fed Funds {fed_funds}% + rising")

        if pts == 0.0 or not reasons:
            return zero_contribution(self.engine_name,
                                              f"yields neutral for {sector or 'this ticker'}")

        return ContextContribution(
            engine_name=self.engine_name, contribution_pts=pts,
            reason=" · ".join(reasons) + f" → {pts:+.1f}pts",
            severity=severity, data_available=True,
            metadata={"10y_yield": y10, "10y_2y_spread": spread,
                          "fed_funds": fed_funds, "sector": sector},
        )
