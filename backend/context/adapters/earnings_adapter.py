"""Earnings pre-event adapter · reads economic_calendar.jsonl ·
penalizes positions when the ticker's own earnings are within 3 days.

Rule: NEVER take fresh positions 1-3 days before scheduled earnings
without an explicit event-driven thesis. Institutional discipline.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class EarningsAdapter:
    engine_name = "earnings"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        p = root / "reports" / "context" / "economic_calendar.jsonl"
        if not p.exists():
            return zero_contribution(self.engine_name, "economic_calendar.jsonl missing")

        ticker = (rec.get("ticker") or "").upper()
        short = ticker.replace(".NS", "").replace(".BO", "")
        try:
            asof_dt = date.fromisoformat(asof)
        except (ValueError, TypeError):
            return zero_contribution(self.engine_name, "bad asof format")

        best = None
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try: d = json.loads(line)
            except json.JSONDecodeError: continue
            if d.get("category") != "earnings": continue
            aff = str(d.get("tickers_affected") or "").upper()
            if aff not in (ticker, short): continue
            try:
                edt = date.fromisoformat((d.get("event_date") or "")[:10])
            except (ValueError, TypeError):
                continue
            if edt < asof_dt: continue        # already happened
            days = (edt - asof_dt).days
            if best is None or days < best[0]:
                best = (days, d)

        if best is None:
            return zero_contribution(self.engine_name,
                                              "no upcoming earnings in calendar")

        days_to, evt = best
        if days_to == 0:   pts, sev = -3.5, "critical"
        elif days_to <= 1: pts, sev = -3.0, "critical"
        elif days_to <= 3: pts, sev = -2.0, "warning"
        elif days_to <= 7: pts, sev = -0.8, "info"
        else:
            return zero_contribution(self.engine_name,
                                              f"earnings {days_to}d away · no adjustment")

        reason = (f"{evt.get('event_name', 'earnings')} in {days_to}d "
                     f"(impact={evt.get('expected_impact')}) → {pts:+.1f}pts")
        return ContextContribution(engine_name=self.engine_name,
                                             contribution_pts=pts, reason=reason,
                                             severity=sev, data_available=True,
                                             metadata={"days_to_earnings": days_to,
                                                           "event_id": evt.get("event_id")})
