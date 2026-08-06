"""Sprint G-B · Cross-Asset Risk-On/Off Adapter · reads FRED.

Sources: FRED VIX + WTI + DEXINUS (USD/INR) + M2

Composite risk score:
    · VIX > 25 + crude falling + USD strong    → risk-OFF (-3.0 to all)
    · VIX < 15 + crude rising + USD weak       → risk-ON (+2.0 to all)
    · Mixed                                     → neutral

Applies uniformly to all recommendations · not sector-specific · because
risk-off is a market-wide regime.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class RiskOffAdapter:
    engine_name = "vol_risk"     # reuses vol_risk bucket

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        p = root / "reports" / "fred" / "fred_snapshot.json"
        if not p.exists():
            return zero_contribution(self.engine_name + "_xasset",
                                              "fred_snapshot.json missing")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            series = d.get("series") or {}
        except Exception as e:
            return zero_contribution(self.engine_name + "_xasset",
                                              f"parse error · {type(e).__name__}")

        vix = (series.get("VIXCLS") or {}).get("latest_value")
        crude = (series.get("DCOILWTICO") or {}).get("latest_value")
        crude_30d = (series.get("DCOILWTICO") or {}).get("change_30d_pct")
        usd_inr = (series.get("DEXINUS") or {}).get("latest_value")
        usd_30d = (series.get("DEXINUS") or {}).get("change_30d_pct")

        risk_off_signals = 0
        risk_on_signals = 0
        reasons = []

        if isinstance(vix, (int, float)):
            if vix > 25:  risk_off_signals += 2; reasons.append(f"VIX {vix} > 25")
            elif vix > 20: risk_off_signals += 1; reasons.append(f"VIX {vix} elevated")
            elif vix < 15: risk_on_signals += 1; reasons.append(f"VIX {vix} calm")

        if isinstance(crude_30d, (int, float)):
            if crude_30d < -10: risk_off_signals += 1; reasons.append(f"crude {crude_30d:+.1f}% (falling)")
            elif crude_30d > 10: risk_on_signals += 1; reasons.append(f"crude {crude_30d:+.1f}% (rising)")

        if isinstance(usd_30d, (int, float)):
            if usd_30d > 3: risk_off_signals += 1; reasons.append(f"USD/INR {usd_30d:+.1f}% (strong)")
            elif usd_30d < -3: risk_on_signals += 1; reasons.append(f"USD/INR {usd_30d:+.1f}% (weak)")

        net = risk_on_signals - risk_off_signals

        if net <= -3:  pts, sev = -3.0, "critical"
        elif net <= -1: pts, sev = -1.5, "warning"
        elif net >= 3:  pts, sev = 2.0, "info"
        elif net >= 1:  pts, sev = 1.0, "info"
        else:
            return zero_contribution(self.engine_name + "_xasset",
                                              "cross-asset signals mixed · neutral")

        return ContextContribution(
            engine_name=self.engine_name + "_xasset", contribution_pts=pts,
            reason=" · ".join(reasons) + f" → {pts:+.1f}pts",
            severity=sev, data_available=True,
            metadata={"vix": vix, "crude_30d_pct": crude_30d,
                          "usd_inr_30d_pct": usd_30d,
                          "risk_off_signals": risk_off_signals,
                          "risk_on_signals": risk_on_signals},
        )
