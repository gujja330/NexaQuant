"""Sprint A · Recommendation Health Score.

CEO decision 2026-08-05 · operator ask: "Health = 89/100 · 90–100 → Strong Buy
· 75–90 → Hold · 60–75 → Watch · <60 → Review · <45 → Exit Candidate".

Per-recommendation composite 0-100 score built from 7 factor sub-scores that
each grade an existing signal the ensemble already produces. NEW: the score
itself is emergent · we're not adding data · we're distilling what's already
computed into ONE band the operator can scan.

Factor definition (weighted default · overridable via configs/health_score.json):

    Trend       20%    R2 attribution share of Trend model + momentum direction
    Momentum    20%    R2 attribution share of Momentum + short-term price ROC
    Quality     15%    R2 attribution share of Quality
    Earnings    10%    inverse of event-risk (days-to-earnings gate)
    Risk        15%    inverse of risk_capital_v2 risk_score
    Sector      10%    sector_rotation strength rank position
    Liquidity   10%    turnover / avg_volume vs universe median

Bands:
    90-100  STRONG BUY (strong across all factors)
    75-90   HOLD (steady · no action)
    60-75   WATCH (drift starting · watch closely)
    45-60   REVIEW (multiple factors weak · review conviction)
    <45     EXIT CANDIDATE (thesis breaking down · consider exit)

Emits per-run + per-ticker JSON at
    reports/research/health_scores_{market}.json

Alert firing (band change day-over-day) surfaces in XLSX Alert column via
profit_protection consumer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


DEFAULT_WEIGHTS = {
    "trend":     0.20,
    "momentum":  0.20,
    "quality":   0.15,
    "earnings":  0.10,
    "risk":      0.15,
    "sector":    0.10,
    "liquidity": 0.10,
}


def _load_cfg(root: Path) -> dict:
    p = root / "configs" / "health_score.json"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"weights": DEFAULT_WEIGHTS,
                                          "bands": {
                                              "STRONG_BUY":    [90, 100],
                                              "HOLD":          [75, 90],
                                              "WATCH":         [60, 75],
                                              "REVIEW":        [45, 60],
                                              "EXIT_CANDIDATE": [0, 45],
                                          }}, indent=2), encoding="utf-8")
        return {"weights": DEFAULT_WEIGHTS}
    try:
        return {**{"weights": DEFAULT_WEIGHTS},
                     **json.loads(p.read_text(encoding="utf-8"))}
    except Exception:
        return {"weights": DEFAULT_WEIGHTS}


@dataclass
class HealthCard:
    ticker: str
    asof: str
    overall: float             # 0-100
    band: str                  # STRONG_BUY / HOLD / WATCH / REVIEW / EXIT_CANDIDATE
    factors: dict              # {trend: 92, momentum: 88, ...}
    prior_band: str | None = None
    band_changed: bool = False


def _factor_trend(rec: Mapping) -> float:
    """Grade based on R2's Trend model share + evolution.momentum_direction."""
    attr = (rec.get("attribution") or {}).get("per_model") or []
    trend_share = 0.0
    for m in attr:
        if "trend" in (m.get("model_id") or "").lower():
            trend_share = float(m.get("share_pct") or 0)
            break
    ev = rec.get("evolution") or {}
    momentum_dir = (ev.get("momentum_direction") or "").upper()
    boost = {"UP": 10.0, "STABLE": 0.0, "DOWN": -15.0}.get(momentum_dir, 0.0)
    return max(0.0, min(100.0, trend_share * 2.5 + boost + 40.0))


def _factor_momentum(rec: Mapping) -> float:
    attr = (rec.get("attribution") or {}).get("per_model") or []
    mom_share = 0.0
    for m in attr:
        if "momentum" in (m.get("model_id") or "").lower():
            mom_share = float(m.get("share_pct") or 0)
            break
    conf = float(rec.get("calibrated_confidence") or rec.get("confidence") or 0.5)
    return max(0.0, min(100.0, mom_share * 2.5 + conf * 30.0 + 20.0))


def _factor_quality(rec: Mapping) -> float:
    attr = (rec.get("attribution") or {}).get("per_model") or []
    q_share = 0.0
    for m in attr:
        if "quality" in (m.get("model_id") or "").lower():
            q_share = float(m.get("share_pct") or 0)
            break
    return max(0.0, min(100.0, q_share * 3.0 + 40.0))


def _factor_earnings(rec: Mapping) -> float:
    """Higher = further from earnings = safer. 20d away = 100, 0-3d = 20."""
    ev = rec.get("evolution") or {}
    days = rec.get("days_to_next_earnings") or ev.get("days_to_next_earnings")
    if days is None or days > 30:
        return 90.0
    if days <= 3:
        return 20.0
    if days <= 7:
        return 55.0
    return max(0.0, min(100.0, 55.0 + (days - 7) * 2.5))


def _factor_risk(rec: Mapping) -> float:
    """Inverse of risk_score · we WANT high safety."""
    risk = rec.get("risk_score")
    if risk is None:
        return 65.0    # neutral default
    try:
        r = float(risk)
        if 0 <= r <= 1: r = r * 100
        return max(0.0, min(100.0, 100.0 - r))
    except (TypeError, ValueError):
        return 65.0


def _factor_sector(rec: Mapping, sector_ranks: dict | None) -> float:
    """Higher = sector is a top-3 leader today."""
    if not sector_ranks:
        return 65.0
    sector = rec.get("sector") or ""
    rank = sector_ranks.get(sector)
    if rank is None:
        return 65.0
    if rank <= 3: return 90.0
    if rank <= 6: return 75.0
    if rank <= 10: return 55.0
    return 35.0


def _factor_liquidity(rec: Mapping) -> float:
    """Higher = ticker is highly liquid vs universe median."""
    v = rec.get("liquidity_ratio")
    if v is None:
        return 75.0    # assume decent liquidity for tracked names
    try:
        vf = float(v)
        return max(0.0, min(100.0, min(vf * 50.0 + 40.0, 100.0)))
    except (TypeError, ValueError):
        return 75.0


def _band(overall: float, cfg_bands: dict | None = None) -> str:
    """Sprint H-simplify · operator feedback 2026-08-06: "HOLD/WATCH/REVIEW
    is very confusing · make it simple". Collapsed from 5 bands to 4 with
    clear action verbs.

    Old (5 bands · confusing):
        STRONG_BUY (90-100) · HOLD (75-90) · WATCH (60-75) · REVIEW (45-60) · EXIT_CANDIDATE (<45)
    New (4 bands · clear):
        STRONG (85-100)    ·  Buy or add · position is very healthy
        HOLD   (65-85)     ·  Position healthy · no action needed
        WEAK   (45-65)     ·  Weakening · consider reducing
        EXIT   (<45)        ·  Thesis breaking · exit or hard trail
    """
    if overall >= 85: return "STRONG"
    if overall >= 65: return "HOLD"
    if overall >= 45: return "WEAK"
    return "EXIT"


def _load_prior_card(root: Path, market: str, ticker: str) -> HealthCard | None:
    p = root / "reports" / "research" / f"health_scores_{market}.json"
    if not p.exists(): return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        for c in d.get("cards") or []:
            if c.get("ticker") == ticker:
                return HealthCard(**{k: v for k, v in c.items()
                                                if k in HealthCard.__dataclass_fields__})
    except Exception:
        return None
    return None


def _sector_ranks(root: Path, market: str) -> dict:
    p = root / ("usa/reports" if market == "usa" else "reports") / "sector_rotation.json"
    if not p.exists(): return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        ranked = d.get("ranked_sectors") or d.get("sectors") or []
        return {s.get("sector") or s.get("name"): (i + 1)
                    for i, s in enumerate(ranked) if isinstance(s, dict)}
    except Exception:
        return {}


def score_one(root: Path, market: str, rec: Mapping,
                  asof: str, sector_ranks: dict | None = None) -> HealthCard:
    cfg = _load_cfg(root)
    w = cfg["weights"]
    if sector_ranks is None:
        sector_ranks = _sector_ranks(root, market)

    factors = {
        "trend":     round(_factor_trend(rec), 1),
        "momentum":  round(_factor_momentum(rec), 1),
        "quality":   round(_factor_quality(rec), 1),
        "earnings":  round(_factor_earnings(rec), 1),
        "risk":      round(_factor_risk(rec), 1),
        "sector":    round(_factor_sector(rec, sector_ranks), 1),
        "liquidity": round(_factor_liquidity(rec), 1),
    }
    overall = sum(factors[k] * w.get(k, 0) for k in factors)
    band = _band(overall)

    ticker = rec.get("ticker") or "?"
    prior = _load_prior_card(root, market, ticker)
    prior_band = prior.band if prior else None
    band_changed = prior_band is not None and prior_band != band

    return HealthCard(
        ticker=ticker, asof=asof,
        overall=round(overall, 1), band=band,
        factors=factors, prior_band=prior_band,
        band_changed=band_changed,
    )


def score_all(root: Path, market: str, recs: list, asof: str) -> dict:
    sector_ranks = _sector_ranks(root, market)
    cards = [score_one(root, market, r, asof, sector_ranks) for r in recs]
    return {
        "engine":         "aegis.portfolio.health_score.v1",
        "asof":           asof,
        "market":         market,
        "generated_utc":  datetime.now(timezone.utc).isoformat(),
        "n":              len(cards),
        "band_changes":   sum(1 for c in cards if c.band_changed),
        "cards":          [asdict(c) for c in cards],
    }


def emit(root: Path, market: str, payload: dict) -> Path:
    p = root / "reports" / "research" / f"health_scores_{market}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return p


def load_current(root: Path, market: str) -> dict:
    p = root / "reports" / "research" / f"health_scores_{market}.json"
    if not p.exists(): return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
