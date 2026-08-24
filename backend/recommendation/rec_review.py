"""Part 9 (Dynamic Confidence · full) + Part 14 (Recommendation Review).

Every ACTIVE opportunity is re-evaluated daily against the fresh
market state. Two overlapping outputs:

  Part 9 · Dynamic Confidence
    Track confidence trajectory day-over-day per position. Confidence
    rising = "AEGIS is more sure than before". Confidence falling below
    a threshold = "position is deteriorating".

  Part 14 · Recommendation Review
    Same re-eval but framed as ACTION SUGGESTIONS: HOLD unchanged ·
    ADD (confidence rising + still under-weight) · TIGHTEN STOP
    (confidence sliding) · REVIEW (confidence collapsed).

Both consume the just-emitted recommendations + Registry state · no
new upstream engines needed.

Config in configs/opportunity_registry.yaml::review_engine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, date
from pathlib import Path

from backend.research import opportunity_registry as oreg


@dataclass
class PositionReview:
    opportunity_id:      str = ""
    ticker:              str = ""
    runner:              str = ""
    days_held:           int | None = None
    conf_today:          float | None = None
    conf_at_entry:       float | None = None
    conf_delta_pp:       float | None = None
    trend:               str = ""    # "rising" · "falling" · "flat" · "collapsed"
    review_action:       str = "HOLD"
    reason:              str = ""


@dataclass
class RecReviewReport:
    engine:              str = "aegis.rec_review.v1"
    generated_utc:       str = ""
    market:              str = ""
    asof:                str = ""
    n_positions:         int = 0
    n_rising:            int = 0
    n_falling:           int = 0
    n_flat:              int = 0
    n_collapsed:         int = 0
    n_action_hold:       int = 0
    n_action_tighten:    int = 0
    n_action_review:     int = 0
    n_action_add:        int = 0
    reviews:             list = field(default_factory=list)


def _load_config(root: Path) -> dict:
    p = root / "configs" / "opportunity_registry.yaml"
    if not p.exists(): return {}
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cfg.get("review_engine", {}) or {}
    except Exception:
        return {}


def _load_recs(root: Path, market: str) -> dict:
    p = ((root / "usa" / "reports" / "recommendations.json")
             if market == "usa" else (root / "reports" / "recommendations.json"))
    if not p.exists(): return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return {str(r.get("ticker","")).upper().replace(".NS","").replace(".BO",""): r
                     for r in d.get("recommendations", [])}
    except Exception:
        return {}


def _classify_trend(delta_pp: float | None, collapse_thr_pp: float,
                            rising_thr_pp: float) -> str:
    if delta_pp is None: return "flat"
    if delta_pp <= -collapse_thr_pp: return "collapsed"
    if delta_pp <= -rising_thr_pp: return "falling"
    if delta_pp >= rising_thr_pp: return "rising"
    return "flat"


def _review_action(trend: str, days_held: int | None) -> tuple:
    """Map trend to a review action + short reason."""
    if trend == "collapsed":
        return ("REVIEW",
                    f"confidence collapsed · immediate review recommended")
    if trend == "falling":
        return ("TIGHTEN STOP",
                    f"confidence declining · consider trailing stop closer")
    if trend == "rising" and (days_held or 0) >= 5:
        return ("ADD", f"confidence rising · position mature · consider adding")
    return ("HOLD", "confidence stable")


def compute(root: Path, market: str, asof: str) -> RecReviewReport:
    market = market.lower(); asof = asof[:10]
    cfg = _load_config(root)
    collapse_thr = float(cfg.get("collapse_threshold_pp", 30.0))
    rising_thr   = float(cfg.get("rising_threshold_pp", 5.0))

    rep = RecReviewReport(
        market=market, asof=asof,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    reg = oreg.load_all(root)
    recs = _load_recs(root, market)

    for opps in reg.values():
        for opp in opps:
            if opp.market.lower() != market: continue
            if not opp.is_active(): continue
            rep.n_positions += 1

            rec_today = recs.get(opp.ticker.upper())
            if rec_today is None:
                continue     # ticker not re-emitted today · no review possible
            _conf_today = (rec_today.get("regime_adjusted_confidence")
                                    or rec_today.get("calibrated_confidence")
                                    or rec_today.get("confidence"))
            _conf_entry = opp.initial_score if opp.initial_score is not None else None

            try:
                _cd = date.fromisoformat(opp.created_date)
                days_held = (date.fromisoformat(asof) - _cd).days
            except Exception:
                days_held = 0

            delta_pp = None
            if isinstance(_conf_today, (int, float)) and isinstance(_conf_entry, (int, float)):
                # Both are 0..1 typically · scale to pp
                delta_pp = round((float(_conf_today) - float(_conf_entry)) * 100, 2)

            trend = _classify_trend(delta_pp, collapse_thr, rising_thr)
            action, reason = _review_action(trend, days_held)

            r = PositionReview(
                opportunity_id=opp.opportunity_id, ticker=opp.ticker,
                runner=opp.runner, days_held=days_held,
                conf_today=(float(_conf_today) if isinstance(_conf_today, (int, float)) else None),
                conf_at_entry=(float(_conf_entry) if isinstance(_conf_entry, (int, float)) else None),
                conf_delta_pp=delta_pp,
                trend=trend, review_action=action, reason=reason,
            )
            rep.reviews.append(asdict(r))
            if trend == "rising":    rep.n_rising += 1
            elif trend == "falling": rep.n_falling += 1
            elif trend == "collapsed": rep.n_collapsed += 1
            else:                    rep.n_flat += 1
            if action == "HOLD":            rep.n_action_hold += 1
            elif action == "TIGHTEN STOP":  rep.n_action_tighten += 1
            elif action == "REVIEW":        rep.n_action_review += 1
            elif action == "ADD":           rep.n_action_add += 1
    return rep


def emit(root: Path, rep: RecReviewReport) -> Path:
    p = (root / "reports" / "context"
             / f"rec_review_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def summary_line(rep: RecReviewReport) -> str:
    return (f"review · {rep.n_positions} positions · rising={rep.n_rising} · "
                f"falling={rep.n_falling} · collapsed={rep.n_collapsed} · "
                f"tighten={rep.n_action_tighten} · review={rep.n_action_review}")
