"""Percentile-based Classifier · institutional quant pattern.

Fixes the "signal magnitude vs threshold mismatch" that keeps 15/15 recs
in HOLD despite genuine ensemble differentiation.

Absolute-threshold classifier says: score >= +0.20 → BUY. Ensemble produces
scores in [-0.05, +0.05]. Nothing reaches the threshold → all HOLD.

Institutional practice: DECILE the universe by ensemble_score. Top-K get BUY,
bottom-K get SELL, middle gets HOLD. Ranking is what actual quant desks use.

This is NOT "lowering thresholds to force BUY" — it's using the RIGHT
decision framework for cross-sectional signals.

Consumes existing ensemble output · no new architecture. Article 101.2 permitted.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.recommendation.percentile_classifier.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.recommendation.percentile_classifier.v1"


# Institutional defaults · top/bottom 20% = actionable, middle 60% = HOLD.
# Within actionable buckets: top/bottom 10% get STRONG_BUY/STRONG_SELL.
DEFAULT_STRONG_BUY_PCT = 0.10   # top 10% score
DEFAULT_BUY_PCT        = 0.20   # top 20% score (includes STRONG_BUY)
DEFAULT_STRONG_SELL_PCT = 0.10  # bottom 10%
DEFAULT_SELL_PCT       = 0.20   # bottom 20%
# Confidence gate: even strong-percentile candidates need minimum confidence
MIN_CONFIDENCE_FOR_ACTION = 0.001   # very permissive · substrate-tolerant


def _num_or(rec: Mapping, primary: str, fallback: str, *, default: float) -> float:
    """Return the first numeric value among `rec[primary]`, `rec[fallback]`,
    else `default`. Treats None (from JSON null) as missing — this is the
    fix for the 2026-08-11 crash where `dict.get(k, default)` returned None
    because the key was present but its value was JSON null."""
    for k in (primary, fallback):
        v = rec.get(k)
        if isinstance(v, (int, float)):
            # NaN check without importing math — NaN != NaN
            if v == v:
                return float(v)
    return float(default)


@dataclass(frozen=True)
class PercentileDecision:
    ticker: str
    ensemble_score: float
    calibrated_confidence: float
    score_percentile: float          # 0.0 = worst, 1.0 = best
    action: str
    reason: str


@dataclass
class PercentileClassificationReport:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    run_utc: str = ""
    n_recs: int = 0
    thresholds: dict = field(default_factory=dict)
    action_distribution: dict = field(default_factory=dict)
    decisions: list = field(default_factory=list)


def classify_by_percentile(recs: Sequence[Mapping],
                             strong_buy_pct: float = DEFAULT_STRONG_BUY_PCT,
                             buy_pct: float = DEFAULT_BUY_PCT,
                             strong_sell_pct: float = DEFAULT_STRONG_SELL_PCT,
                             sell_pct: float = DEFAULT_SELL_PCT,
                             min_conf: float = MIN_CONFIDENCE_FOR_ACTION) -> PercentileClassificationReport:
    """Rank recs by ensemble_score · top/bottom slices become BUY/SELL.

    Every rec gets a percentile score (0 to 1). Actions are assigned:
      score_percentile >= 1 - strong_buy_pct → STRONG_BUY
      score_percentile >= 1 - buy_pct        → BUY
      score_percentile <= strong_sell_pct    → STRONG_SELL
      score_percentile <= sell_pct           → SELL
      else                                    → HOLD
    Confidence gate: below min_conf, actions clip to HOLD.
    """
    rep = PercentileClassificationReport(run_utc=datetime.now(timezone.utc).isoformat())
    rep.n_recs = len(recs)
    rep.thresholds = {
        "strong_buy_top_pct":  strong_buy_pct,
        "buy_top_pct":         buy_pct,
        "strong_sell_bot_pct": strong_sell_pct,
        "sell_bot_pct":        sell_pct,
        "min_confidence":      min_conf,
    }
    if not recs:
        return rep

    n = len(recs)
    # Extract scores + tickers preserving order.
    #
    # NOTE (2026-08-11 · CEO P0 pipeline hygiene): the fallback used to be
    #   float(r.get("ensemble_score", r.get("score", 0.0)))
    # which crashes when a rec has ensemble_score explicitly set to None
    # (dict.get returns the key's real value when present, not the default).
    # This exact shape lives in usa/reports/recommendations.json today: all
    # 507 legacy rows have ensemble_score=None but score=<0..100 numeric>.
    # `_num_or` treats None as "missing" and walks the fallback chain.
    scored = [(r.get("ticker", ""),
                _num_or(r, "ensemble_score", "score", default=0.0),
                _num_or(r, "calibrated_confidence", "confidence", default=0.0))
               for r in recs]
    # Rank by score ascending (worst → best)
    ranked = sorted(scored, key=lambda x: x[1])
    # Percentile of each = rank/(n-1) · 0=worst, 1=best
    pct_map = {t: (i / (n - 1) if n > 1 else 0.5) for i, (t, _, _) in enumerate(ranked)}

    # Thresholds → percentile boundaries
    strong_buy_cut = 1.0 - strong_buy_pct
    buy_cut        = 1.0 - buy_pct
    strong_sell_cut = strong_sell_pct
    sell_cut       = sell_pct

    dist: dict[str, int] = {"STRONG_BUY": 0, "BUY": 0, "HOLD": 0, "SELL": 0, "STRONG_SELL": 0}
    for ticker, score, conf in scored:
        p = round(pct_map[ticker], 4)
        # Assign action strictly by percentile
        if p >= strong_buy_cut:
            action = "STRONG_BUY"
            reason = f"score {score:+.4f} in top {int(strong_buy_pct*100)}% (percentile {p:.2f})"
        elif p >= buy_cut:
            action = "BUY"
            reason = f"score {score:+.4f} in top {int(buy_pct*100)}% (percentile {p:.2f})"
        elif p <= strong_sell_cut:
            action = "STRONG_SELL"
            reason = f"score {score:+.4f} in bottom {int(strong_sell_pct*100)}% (percentile {p:.2f})"
        elif p <= sell_cut:
            action = "SELL"
            reason = f"score {score:+.4f} in bottom {int(sell_pct*100)}% (percentile {p:.2f})"
        else:
            action = "HOLD"
            reason = f"score {score:+.4f} in middle 60% (percentile {p:.2f})"
        # Confidence gate: dampen extreme actions if conf too low
        if conf < min_conf and action != "HOLD":
            reason += f" · confidence {conf:.4f} below min {min_conf} · dampened to HOLD"
            action = "HOLD"
        dist[action] += 1
        rep.decisions.append(asdict(PercentileDecision(
            ticker=ticker, ensemble_score=round(score, 6),
            calibrated_confidence=round(conf, 6), score_percentile=p,
            action=action, reason=reason,
        )))
    rep.action_distribution = dist
    return rep
