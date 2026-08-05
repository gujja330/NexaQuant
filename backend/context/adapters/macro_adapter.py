"""Macro regime adapter · reads macro_regime.json · adjusts confidence.

Rules (deliberately conservative · Phase 2A tune):
    · regime=bull      → +2.0 pts (favorable environment)
    · regime=neutral   → 0.0 pts
    · regime=bear      → -3.0 pts (unfavorable · reduce conviction)
    · regime=unknown   → -0.5 pts (uncertainty penalty)

Additionally · if regime FLIPPED in the last 3 days · add ±1 pt for
directional shift (fresh signal · higher confidence in the change).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..adapter_base import ContextContribution, zero_contribution


class MacroAdapter:
    engine_name = "macro"

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        p = root / ("usa/reports" if market == "usa" else "reports") / "macro_regime.json"
        if not p.exists():
            return zero_contribution(self.engine_name, "macro_regime.json missing")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return zero_contribution(self.engine_name,
                                              f"parse error · {type(e).__name__}")
        regime = str(d.get("primary_regime") or d.get("regime") or "").lower()
        if not regime:
            return zero_contribution(self.engine_name, "no regime field")
        base_pts = {
            "bull":    2.0,
            "neutral": 0.0,
            "bear":   -3.0,
            "unknown": -0.5,
        }.get(regime, 0.0)

        # Check for recent flip via regime_history
        flip_bonus = 0.0
        flip_reason = ""
        hist_p = root / "reports" / "research" / "regime_history.jsonl"
        if hist_p.exists():
            try:
                rows = []
                for line in hist_p.read_text(encoding="utf-8").splitlines():
                    if not line.strip(): continue
                    try: r = json.loads(line)
                    except json.JSONDecodeError: continue
                    if r.get("market") != market: continue
                    rows.append(r)
                rows.sort(key=lambda x: x.get("asof") or "")
                if len(rows) >= 2:
                    prev = rows[-2].get("regime")
                    cur = rows[-1].get("regime")
                    if prev != cur:
                        # Flip → boost if bull, penalize if bear
                        if cur == "bull":  flip_bonus = 1.0
                        elif cur == "bear": flip_bonus = -1.5
                        flip_reason = f" · flipped {prev}→{cur}"
            except Exception:
                pass

        total = base_pts + flip_bonus
        severity = "critical" if regime == "bear" else "info"
        reason = f"macro regime={regime}{flip_reason} → {total:+.1f}pts"
        return ContextContribution(
            engine_name=self.engine_name, contribution_pts=total,
            reason=reason, severity=severity, data_available=True,
            metadata={"regime": regime, "flip_bonus": flip_bonus},
        )
