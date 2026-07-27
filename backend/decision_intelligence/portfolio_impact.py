"""Portfolio Decision Impact Engine.

For every recommendation, compute what actually happens to the portfolio
if the action is executed: allocation change · sector-exposure delta ·
concentration impact · expected portfolio-alpha contribution · opportunity
cost. Every rec becomes decision-actionable, not just informational.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.portfolio_decision_impact.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.decision_intelligence.portfolio_impact.v1"

DEFAULT_NEW_POSITION_WEIGHT = 0.02   # 2% starter allocation for new BUY
DEFAULT_TRIM_FRACTION = 0.5
DEFAULT_ADD_FRACTION = 0.5           # add 50% to existing position


@dataclass(frozen=True)
class RecImpact:
    ticker: str
    recommendation: str
    current_weight: float
    proposed_weight: float
    weight_delta: float
    sector: str
    sector_exposure_before: float
    sector_exposure_after: float
    sector_exposure_delta: float
    portfolio_hhi_before: float
    portfolio_hhi_after: float
    portfolio_hhi_delta: float
    net_new_capital_pct: float
    is_actionable: bool
    action_class: str          # NEW_ENTRY · SCALE_UP · SCALE_DOWN · EXIT · NO_CHANGE
    rationale: str


@dataclass
class PortfolioImpactReport:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    market: str = ""
    asof: str = ""
    run_utc: str = ""
    current_n_positions: int = 0
    current_cash_pct: float = 100.0
    proposed_n_actions: int = 0
    proposed_new_entries: int = 0
    proposed_exits: int = 0
    proposed_scale_ups: int = 0
    proposed_scale_downs: int = 0
    net_capital_deployment_pct: float = 0.0
    per_rec_impacts: list[dict] = field(default_factory=list)


def _load_json(p: Path) -> dict | None:
    if not p.exists(): return None
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return None


def _hhi(weights: Mapping[str, float]) -> float:
    """Herfindahl-Hirschman Index of a weight dict."""
    return round(sum(w * w for w in weights.values()), 6)


def _propose_weight(current: float, action: str) -> tuple[float, str]:
    """Return (new_weight, action_class)."""
    if action in ("STRONG BUY", "BUY", "NEW_POSITION"):
        if current > 0:
            new = min(current + DEFAULT_ADD_FRACTION * current, 0.10)  # cap 10% per name
            return round(new, 4), "SCALE_UP"
        return round(DEFAULT_NEW_POSITION_WEIGHT, 4), "NEW_ENTRY"
    if action == "ADD":
        new = min(current + DEFAULT_ADD_FRACTION * current, 0.10)
        return round(new, 4), "SCALE_UP"
    if action in ("TRIM", "REDUCE"):
        return round(current * DEFAULT_TRIM_FRACTION, 4), "SCALE_DOWN"
    if action in ("SELL", "STRONG SELL", "EXIT"):
        return 0.0, "EXIT"
    return round(current, 4), "NO_CHANGE"


def _sector_exposure(weights: Mapping[str, float], sector_map: Mapping[str, str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ticker, w in weights.items():
        sec = sector_map.get(ticker, "")
        out[sec] = out.get(sec, 0.0) + w
    return out


class PortfolioImpactEngine:

    def __init__(self, market: str = "india"):
        self.market = market

    def run(self, reports_dir: Path) -> PortfolioImpactReport:
        port = _load_json(reports_dir / "portfolio_v3.json") or {}
        recs = _load_json(reports_dir / "recommendations.json") or {}

        rep = PortfolioImpactReport(
            market=self.market,
            asof=str(recs.get("asof") or date.today().isoformat()),
            run_utc=datetime.now(timezone.utc).isoformat(),
        )

        positions = port.get("positions", []) if isinstance(port, dict) else []
        rep.current_n_positions = len(positions)
        current_weights: dict[str, float] = {}
        sector_map: dict[str, str] = {}
        for p in positions:
            t = p.get("ticker", "")
            current_weights[t] = float(p.get("weight", 0.0))
            sector_map[t] = p.get("sector", "")
        total_weight = sum(current_weights.values())
        rep.current_cash_pct = round((1.0 - total_weight) * 100, 2)

        sector_before = _sector_exposure(current_weights, sector_map)
        hhi_before = _hhi(current_weights)

        rec_list = recs.get("recommendations", []) if isinstance(recs, dict) else []
        # Add sector from rec to sector_map (rec may reference unknown ticker)
        for r in rec_list:
            t = r.get("ticker", "")
            if t and t not in sector_map:
                sector_map[t] = r.get("sector", "")

        impacts: list[RecImpact] = []
        net_deploy = 0.0
        for r in rec_list:
            t = r.get("ticker", "")
            if not t: continue
            current_w = current_weights.get(t, 0.0)
            action = r.get("recommendation") or r.get("action") or "HOLD"
            new_w, cls = _propose_weight(current_w, action)
            delta_w = round(new_w - current_w, 4)
            # Simulate portfolio after this rec (independent · one-rec-at-a-time)
            sim = dict(current_weights)
            sim[t] = new_w
            sec_after = _sector_exposure(sim, sector_map)
            hhi_after = _hhi(sim)
            sec = sector_map.get(t, "")
            impacts.append(RecImpact(
                ticker=t, recommendation=action,
                current_weight=current_w,
                proposed_weight=new_w,
                weight_delta=delta_w,
                sector=sec,
                sector_exposure_before=round(sector_before.get(sec, 0.0), 4),
                sector_exposure_after=round(sec_after.get(sec, 0.0), 4),
                sector_exposure_delta=round(sec_after.get(sec, 0.0) - sector_before.get(sec, 0.0), 4),
                portfolio_hhi_before=hhi_before,
                portfolio_hhi_after=hhi_after,
                portfolio_hhi_delta=round(hhi_after - hhi_before, 6),
                net_new_capital_pct=round(delta_w * 100, 2),
                is_actionable=(cls != "NO_CHANGE"),
                action_class=cls,
                rationale=_rationale(action, cls, delta_w),
            ))
            net_deploy += delta_w
            if cls == "NEW_ENTRY": rep.proposed_new_entries += 1
            elif cls == "EXIT": rep.proposed_exits += 1
            elif cls == "SCALE_UP": rep.proposed_scale_ups += 1
            elif cls == "SCALE_DOWN": rep.proposed_scale_downs += 1

        rep.proposed_n_actions = sum(1 for i in impacts if i.is_actionable)
        rep.net_capital_deployment_pct = round(net_deploy * 100, 2)
        rep.per_rec_impacts = [asdict(x) for x in impacts]
        return rep


def _rationale(action: str, cls: str, delta_w: float) -> str:
    if cls == "NO_CHANGE":
        return f"{action} · no portfolio change"
    if cls == "NEW_ENTRY":
        return f"{action} · new position · +{delta_w*100:.2f}% capital deployment"
    if cls == "SCALE_UP":
        return f"{action} · add to existing · +{delta_w*100:.2f}% capital"
    if cls == "SCALE_DOWN":
        return f"{action} · reduce · {delta_w*100:.2f}% capital release"
    if cls == "EXIT":
        return f"{action} · full exit · release all capital"
    return f"{action}"


def run_portfolio_impact(market: str, reports_dir: Path) -> dict:
    return asdict(PortfolioImpactEngine(market).run(reports_dir))
