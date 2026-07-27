"""Recommendation Quality Engine · Constitution-compliant.

Converts a rec (score, confidence, vol) into a rich institutional quality
profile: expected alpha with confidence interval, downside risk, win
probability, stability, decay.

Deterministic. Given identical inputs → identical output.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from typing import Iterable, Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.recommendation_quality.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.recommendation.quality.v1"

# Score-to-alpha mapping. A score of +1.0 with full confidence maps to a
# 20% expected alpha. This is a bounded institutional prior · not a
# marketing number. Adjustable via config in future.
ALPHA_PER_UNIT_SCORE_PCT = 20.0

# Confidence-based CI width. Higher confidence → tighter interval.
CI_WIDTH_MULTIPLIER = 2.0   # standard-error style


@dataclass(frozen=True)
class QualityScore:
    ticker: str
    action: str
    expected_alpha_pct: float
    expected_alpha_ci_low: float
    expected_alpha_ci_high: float
    downside_risk_pct: float
    win_probability: float
    expected_holding_horizon_days: int
    entry_confidence: float
    exit_confidence: float
    recommendation_stability: float   # [0,1] · 1=steady 0=volatile actions
    recommendation_decay: float        # confidence loss per day · [0,1]
    quality_tier: str                  # STRONG · MODERATE · WEAK · INSUFFICIENT
    reason: str
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    schema_version: str = SCHEMA_VERSION


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def _win_probability(score: float, confidence: float) -> float:
    """Logistic map: score × confidence → win probability in [0, 1].
    Zero-score with zero-conf → 0.5 (fair coin)."""
    s = _clip(score, -1.0, 1.0)
    c = _clip(confidence, 0.0, 1.0)
    z = 3.0 * s * c   # steepness · empirical
    return round(1.0 / (1.0 + math.exp(-z)), 6)


def _expected_alpha(score: float, confidence: float) -> tuple[float, float, float]:
    """Return (point, ci_low, ci_high) in pct. Bounded [-50, +50]."""
    s = _clip(score, -1.0, 1.0)
    c = _clip(confidence, 0.0, 1.0)
    point = s * c * ALPHA_PER_UNIT_SCORE_PCT
    # CI width shrinks with confidence · widens with uncertainty
    sigma = ALPHA_PER_UNIT_SCORE_PCT * (1.0 - c) * 0.5
    ci_low = _clip(point - CI_WIDTH_MULTIPLIER * sigma, -50.0, 50.0)
    ci_high = _clip(point + CI_WIDTH_MULTIPLIER * sigma, -50.0, 50.0)
    return round(point, 4), round(ci_low, 4), round(ci_high, 4)


def _downside_risk(score: float, confidence: float, historical_vol: float) -> float:
    """95% worst-case return · scaled by inverse confidence + vol.
    Returns negative pct."""
    c = _clip(confidence, 0.0, 1.0)
    v = _clip(historical_vol, 0.05, 1.5)
    # Base: 1.65-sigma downside (95% Gaussian) scaled by vol
    base = -1.65 * v * 100  # in %
    # Confidence tightens (less downside), disagreement widens (more downside)
    return round(_clip(base * (1.5 - c), -80.0, 0.0), 4)


def _quality_tier(action: str, expected_alpha: float, win_prob: float, conf: float) -> str:
    if action == "INSUFFICIENT DATA" or action == "INSUFFICIENT_DATA":
        return "INSUFFICIENT"
    if abs(expected_alpha) < 0.5 or conf < 0.10 or win_prob <= 0.55:
        return "WEAK"
    if abs(expected_alpha) < 5.0 or conf < 0.40 or win_prob <= 0.65:
        return "MODERATE"
    return "STRONG"


def _reason(action, expected_alpha, ci_low, ci_high, win_prob, downside) -> str:
    if action in ("INSUFFICIENT DATA", "INSUFFICIENT_DATA"):
        return "quality tier INSUFFICIENT · data substrate depleted · no reliable estimate available"
    return (f"{action} · expected alpha {expected_alpha:+.2f}% "
            f"(95% CI [{ci_low:+.2f}%, {ci_high:+.2f}%]) · "
            f"win_prob {win_prob:.2%} · downside {downside:+.2f}%")


class QualityEngine:
    """Deterministic Recommendation Quality Engine."""

    def compute_one(self, ticker: str, action: str,
                     ensemble_score_norm: float,  # normalized [-1, +1]
                     confidence: float,
                     historical_vol: float = 0.25,
                     dynamic_holding_days: int = 21,
                     rec_stability: float = 1.0,
                     rec_decay: float = 0.0) -> QualityScore:
        point, ci_low, ci_high = _expected_alpha(ensemble_score_norm, confidence)
        win_prob = _win_probability(ensemble_score_norm, confidence)
        downside = _downside_risk(ensemble_score_norm, confidence, historical_vol)
        tier = _quality_tier(action, point, win_prob, confidence)
        reason = _reason(action, point, ci_low, ci_high, win_prob, downside)
        entry_conf = round(_clip(confidence * 1.0, 0.0, 1.0), 4)
        exit_conf = round(_clip((1.0 - confidence) * 0.5 + 0.3, 0.0, 1.0), 4)
        return QualityScore(
            ticker=ticker, action=action,
            expected_alpha_pct=point,
            expected_alpha_ci_low=ci_low,
            expected_alpha_ci_high=ci_high,
            downside_risk_pct=downside,
            win_probability=win_prob,
            expected_holding_horizon_days=int(dynamic_holding_days),
            entry_confidence=entry_conf,
            exit_confidence=exit_conf,
            recommendation_stability=round(_clip(rec_stability, 0.0, 1.0), 4),
            recommendation_decay=round(_clip(rec_decay, 0.0, 1.0), 4),
            quality_tier=tier,
            reason=reason,
        )

    def compute_batch(self, recs: Sequence[Mapping],
                       dynamic_holdings: Mapping[str, int] | None = None) -> list[QualityScore]:
        out = []
        for r in recs:
            # SSoT rec uses [0, 100] score · translate back to normalized [-1, +1]
            score_100 = float(r.get("composite_decision_score", 50.0))
            score_norm = (score_100 - 50.0) / 50.0
            action = r.get("recommendation") or r.get("action") or "HOLD"
            conf = float(r.get("confidence", 0.0))
            ticker = r.get("ticker", "")
            holding = 21
            if dynamic_holdings and ticker in dynamic_holdings:
                holding = dynamic_holdings[ticker]
            out.append(self.compute_one(ticker, action, score_norm, conf,
                                          historical_vol=0.25,
                                          dynamic_holding_days=holding))
        return out


def compute_quality(recs: Sequence[Mapping],
                     dynamic_holdings: Mapping[str, int] | None = None) -> list[dict]:
    return [asdict(q) for q in QualityEngine().compute_batch(recs, dynamic_holdings)]
