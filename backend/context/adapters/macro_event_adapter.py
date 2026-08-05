"""Macro event pre-event adapter · reads economic_calendar.jsonl ·
penalizes ALL positions when a high-impact macro event (Fed/RBI/CPI/NFP)
is within 2 days.

Institutional rule: reduce position sizes 1-2 days before scheduled
central-bank meetings + top-tier macro prints. Broad market-wide drag.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class MacroEventAdapter:
    engine_name = "macro"       # reuses macro weight bucket

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        p = root / "reports" / "context" / "economic_calendar.jsonl"
        if not p.exists():
            return zero_contribution(self.engine_name + "_event",
                                              "economic_calendar.jsonl missing")
        try:
            asof_dt = date.fromisoformat(asof)
        except (ValueError, TypeError):
            return zero_contribution(self.engine_name + "_event", "bad asof")

        # Region routing: India recs care about RBI/India-macro + US high-impact (global spill)
        # USA recs care about Fed/US-macro
        relevant_regions = ("INDIA", "USA", "GLOBAL") if market == "india" \
                                else ("USA", "GLOBAL")

        events_ahead = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try: d = json.loads(line)
            except json.JSONDecodeError: continue
            if d.get("category") in ("earnings", "corporate"): continue
            if d.get("region") not in relevant_regions: continue
            if d.get("expected_impact") not in ("high", "medium"): continue
            try:
                edt = date.fromisoformat((d.get("event_date") or "")[:10])
            except (ValueError, TypeError):
                continue
            if edt < asof_dt: continue
            days = (edt - asof_dt).days
            if days > 3: continue
            events_ahead.append((days, d))

        if not events_ahead:
            return zero_contribution(self.engine_name + "_event",
                                              "no high-impact macro events in next 3d")

        # Take most-impactful nearest event
        events_ahead.sort(key=lambda x: (x[0], 0 if x[1].get("expected_impact") == "high" else 1))
        days_to, evt = events_ahead[0]
        is_high = evt.get("expected_impact") == "high"

        if days_to == 0:
            pts = -2.5 if is_high else -1.0; sev = "warning"
        elif days_to == 1:
            pts = -2.0 if is_high else -0.8; sev = "warning"
        elif days_to == 2:
            pts = -1.0 if is_high else -0.4; sev = "info"
        else:
            pts = -0.5 if is_high else -0.2; sev = "info"

        n_more = len(events_ahead) - 1
        extra = f" (+{n_more} more)" if n_more > 0 else ""
        reason = (f"{evt.get('event_name')} in {days_to}d "
                     f"({evt.get('expected_impact')}){extra} → {pts:+.1f}pts")
        return ContextContribution(engine_name=self.engine_name + "_event",
                                             contribution_pts=pts, reason=reason,
                                             severity=sev, data_available=True,
                                             metadata={"days_to": days_to,
                                                           "n_events_ahead": len(events_ahead),
                                                           "event_id": evt.get("event_id")})
