"""USA Runner 1 · derives defensive core from R2 recs.

Method (transparent · reproducible):
    1. Load R2 canonical recs from usa/reports/recommendations.json
    2. Score each rec on defensive dimensions:
        · Quality attribution share (from R2 attribution.per_model)
        · Low volatility (inverse of risk_score if present)
        · Sector defensive tilt (Healthcare · Consumer Staples · Utilities · Financials boost)
        · Momentum stability (evolution.momentum_direction == STABLE)
    3. Rank by composite defensive_score descending
    4. Take top 10 as USA R1 · emit in R1-orphan shape

The 10 selected form a stable core rotation that changes far less than
R2's daily churn. Same daily refresh · but with a defensive lens.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


DEFENSIVE_SECTORS = {
    "Healthcare": 1.0, "Consumer Staples": 1.0, "Utilities": 1.0,
    "Financials": 0.8, "Communication Services": 0.5,
    "Industrials": 0.3, "Energy": 0.3,
    "Technology": 0.1, "Consumer Discretionary": 0.1,
    "Materials": 0.1, "Real Estate": 0.4,
}


def _defensive_score(rec: dict) -> float:
    """Higher = more defensive. Range roughly 0-100."""
    score = 50.0

    # Quality attribution boost
    attr = (rec.get("attribution") or {}).get("per_model") or []
    for m in attr:
        mid = str(m.get("model_id") or "").lower()
        share = m.get("share_pct") or 0
        if "quality" in mid:  score += float(share) * 0.5
        elif "value" in mid:  score += float(share) * 0.3
        elif "mean_reversion" in mid: score += float(share) * 0.2
        # Penalize speculative signals
        elif "momentum" in mid and float(share) > 30: score -= float(share) * 0.15

    # Sector defensive tilt
    sector = rec.get("sector") or ""
    score += DEFENSIVE_SECTORS.get(sector, 0.0) * 15.0

    # Momentum stability
    ev = rec.get("evolution") or {}
    if str(ev.get("momentum_direction") or "").upper() == "STABLE":
        score += 5.0
    elif str(ev.get("momentum_direction") or "").upper() == "DOWN":
        score -= 8.0

    # Confidence · calibrated only (Raw is noise for defensive picks)
    conf = rec.get("calibrated_confidence") or 0
    if isinstance(conf, (int, float)) and conf > 0.6:
        score += 10.0

    # Penalize rotation candidates (indicates R2 is churning · not defensive)
    ri = rec.get("rotation_intelligence") or {}
    if ri.get("should_rotate"):
        score -= 20.0

    return round(score, 2)


def _rec_to_r1_orphan(rec: dict, defensive_score: float) -> dict:
    """Convert R2 rec into R1-orphan-shaped dict for cross-market XLSX parity."""
    ez = ((rec.get("position_plan") or {}).get("entry_zone") or {})
    price = ez.get("current_price")
    stop = ez.get("stop_loss")
    t1 = ez.get("target_1")
    conf_frac = rec.get("calibrated_confidence") or rec.get("confidence") or 0
    conf_pct = conf_frac * 100 if conf_frac <= 1 else conf_frac

    # Map defensive score to strength label
    if defensive_score >= 80:   strength = "STRONG BUY"
    elif defensive_score >= 65: strength = "BUY"
    elif defensive_score >= 50: strength = "ACCUMULATE"
    else:                        strength = "HOLD"

    reason_parts = []
    attr = (rec.get("attribution") or {}).get("per_model") or []
    for m in attr[:3]:
        lbl = m.get("label") or ""
        s = m.get("share_pct")
        if lbl and s: reason_parts.append(f"{lbl} {s:.0f}%")
    reason = " · ".join(reason_parts) if reason_parts else \
                  f"Defensive score {defensive_score:.1f} · sector {rec.get('sector', '')}"

    buy_low = ez.get("ideal_buy_low") or (price * 0.98 if price else None)
    buy_high = ez.get("ideal_buy_high") or (price * 1.02 if price else None)

    return {
        "ticker":         rec.get("ticker") or "?",
        "sector":         rec.get("sector") or "—",
        "action":         "BUY" if strength in ("STRONG BUY", "BUY", "ACCUMULATE") else "HOLD",
        "strength":       strength,
        "score":          defensive_score,
        "confidence":     round(conf_pct, 1),
        "price":          price,
        "buy_range":      f"{buy_low:.2f} - {buy_high:.2f}" if buy_low and buy_high else "",
        "hist_target":    t1,
        "expected_range": "+2% to +8%",       # R1 conservative default
        "holding":        "3 months (3M)",    # 90d default for USA R1 (per operator: 60-180d)
        "valid_until":    None,               # filled by caller
        "reason":         reason,
    }


def derive(root: Path, asof: str, top_n: int = 10) -> dict:
    """Load R2 recs · score defensively · emit top N as R1 orphans."""
    from datetime import date, timedelta
    r2_path = root / "usa" / "reports" / "recommendations.json"
    if not r2_path.exists():
        return {"engine": "aegis.recommendation.usa_runner1.v1",
                    "asof": asof, "available": False,
                    "reason": "USA R2 recs not available"}
    try:
        d = json.loads(r2_path.read_text(encoding="utf-8"))
        recs = d.get("recommendations") or []
    except Exception as e:
        return {"engine": "aegis.recommendation.usa_runner1.v1",
                    "asof": asof, "available": False,
                    "reason": f"R2 parse error · {type(e).__name__}: {e}"}

    if not recs:
        return {"engine": "aegis.recommendation.usa_runner1.v1",
                    "asof": asof, "available": False,
                    "reason": "no R2 recs to derive from"}

    scored = [(r, _defensive_score(r)) for r in recs]
    scored.sort(key=lambda x: -x[1])
    top = scored[:top_n]

    valid_until = (date.fromisoformat(asof) + timedelta(days=7)).isoformat()

    orphans = []
    for rec, sc in top:
        o = _rec_to_r1_orphan(rec, sc)
        o["valid_until"] = valid_until
        orphans.append(o)

    return {
        "engine":         "aegis.recommendation.usa_runner1.v1",
        "asof":           asof,
        "generated_utc":  datetime.now(timezone.utc).isoformat(),
        "available":      True,
        "n_source_recs":  len(recs),
        "n_r1_orphans":   len(orphans),
        "method":         "defensive derivative · quality + low-vol + sector tilt",
        "philosophy":     "60-180 day holds · rare rotations · stable core",
        "runner1_orphans": orphans,
    }


def emit(root: Path, payload: dict) -> Path:
    """Persist USA R1 to usa/reports/runner1_orphans.json for XLSX renderer."""
    p = root / "usa" / "reports" / "runner1_orphans.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return p
