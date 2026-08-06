"""Sprint G-C · Insider Buying Adapter · reads SEC EDGAR Form 4.

Sources: reports/edgar/insider_recent.json (Dow 30 + configurable universe)

Rules (based on Form 4 count last 90d · note: doesn't distinguish buy vs sell
without parsing filing bodies · treats HIGH-activity as bullish signal for now):
    · ≥ 10 filings last 90d  → +2.0 pts (very active insider trading)
    · 5-9 filings            → +1.0 pts
    · 0-2 filings            → 0.0 (neutral)

Phase 2 upgrade: parse Form 4 body to distinguish net buy vs sell.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class InsiderAdapter:
    engine_name = "insider"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        # India · no EDGAR equivalent yet (SEBI shipping in Sprint H)
        if market == "india":
            return zero_contribution(self.engine_name,
                                              "insider data for India pending SEBI ingest")

        p = root / "reports" / "edgar" / "insider_recent.json"
        if not p.exists():
            return zero_contribution(self.engine_name, "insider_recent.json missing")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return zero_contribution(self.engine_name, f"parse error · {type(e).__name__}")

        ticker = str(rec.get("ticker") or "").upper()
        per = (d.get("per_ticker") or {}).get(ticker) or {}
        if not per.get("available"):
            return zero_contribution(self.engine_name,
                                              f"ticker {ticker} not in insider universe")

        n_form4 = per.get("n_form4_last_90d") or 0
        if n_form4 >= 10:   pts, sev = 2.0, "info"
        elif n_form4 >= 5:  pts, sev = 1.0, "info"
        elif n_form4 == 0:  return zero_contribution(self.engine_name,
                                                                       f"{ticker} zero insider activity 90d")
        else:                return zero_contribution(self.engine_name,
                                                                       f"{ticker} low insider activity ({n_form4})")

        reason = (f"{n_form4} insider Form 4 filings last 90d → {pts:+.1f}pts "
                     f"(note: buy/sell parse pending)")
        return ContextContribution(
            engine_name=self.engine_name, contribution_pts=pts,
            reason=reason, severity=sev, data_available=True,
            metadata={"ticker": ticker, "n_form4_90d": n_form4},
        )
