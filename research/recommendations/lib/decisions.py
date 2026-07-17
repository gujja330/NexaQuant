"""DEV023 decision rules.

Deterministic rules for converting DEV020/DEV022 signals into one of 8
recommendation types. Every rule is a pure function: same input → same output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RecType(str, Enum):
    STRONG_BUY  = "Strong-Buy"
    BUY         = "Buy"
    ACCUMULATE  = "Accumulate"
    HOLD        = "Hold"
    REDUCE      = "Reduce"
    SELL        = "Sell"
    AVOID       = "Avoid"
    WATCHLIST   = "Watchlist"


class ActionType(str, Enum):
    NEW_POSITION      = "NEW_POSITION"
    INCREASE_POSITION = "INCREASE_POSITION"
    DECREASE_POSITION = "DECREASE_POSITION"
    CLOSE_POSITION    = "CLOSE_POSITION"
    NO_ACTION         = "NO_ACTION"


@dataclass
class DecisionInput:
    """Everything the decision rules need for one ticker."""
    ticker: str
    company_score: float
    classification: str                             # from DEV020: Strong-Bullish etc.
    confidence: float

    industry_score: float | None = None
    industry_classification: str | None = None
    sector_score: float | None = None
    sector_classification: str | None = None
    global_posture: str | None = None                # Risk-On/Off/Neutral

    in_target_portfolios: list[str] = field(default_factory=list)
    currently_held: bool = False
    current_weight: float | None = None
    avg_cost: float | None = None
    latest_close: float | None = None
    unrealised_pnl_pct: float | None = None

    # Overall ranks
    overall_rank: int | None = None


@dataclass
class Decision:
    ticker: str
    recommendation: RecType
    action: ActionType
    composite_decision_score: float
    conviction_pct: float                            # 0-100
    reasons_for: list[str] = field(default_factory=list)
    reasons_against: list[str] = field(default_factory=list)


# ─── Composite decision score ─────────────────────────────────────────────────

def composite_decision_score(inp: DecisionInput) -> float:
    """Blend company / industry / sector / global into a single [0, 100]."""
    parts = [(inp.company_score, 0.50)]
    if inp.industry_score is not None:
        parts.append((inp.industry_score, 0.20))
    if inp.sector_score is not None:
        parts.append((inp.sector_score, 0.15))
    if inp.global_posture in ("Risk-On",):
        parts.append((70.0, 0.10))
    elif inp.global_posture in ("Risk-Off",):
        parts.append((30.0, 0.10))
    else:
        parts.append((50.0, 0.10))

    # Confidence attenuates the top end (never boosts beyond raw signals)
    weight_sum = sum(w for _, w in parts)
    score = sum(v * w for v, w in parts) / weight_sum
    return float(max(0.0, min(100.0, score * inp.confidence + score * (1 - inp.confidence) * 0.6)))


# ─── Rule engine ──────────────────────────────────────────────────────────────

def decide(inp: DecisionInput) -> Decision:
    """Apply deterministic rules. First-match discipline; no ties.

    Priority order:
      1. If currently held → SELL / REDUCE / HOLD / ACCUMULATE logic
      2. Else new-position logic → STRONG_BUY / BUY / WATCHLIST / AVOID
    """
    cds = composite_decision_score(inp)

    for_reasons = []
    against_reasons = []

    # Populate rationale (order = importance)
    _score_reasons(inp, for_reasons, against_reasons)

    # ── Currently-held path ────────────────────────────────────────────────
    if inp.currently_held:
        # SELL: classification bearish OR score < 30 OR unrealised loss beyond stop
        if inp.classification == "Bearish" or inp.company_score < 30:
            return Decision(
                ticker=inp.ticker, recommendation=RecType.SELL,
                action=ActionType.CLOSE_POSITION,
                composite_decision_score=cds,
                conviction_pct=_conviction_from_cds(cds, direction="down"),
                reasons_for=for_reasons, reasons_against=against_reasons,
            )
        if inp.unrealised_pnl_pct is not None and inp.unrealised_pnl_pct < -8:
            against_reasons.append(f"stop_loss_triggered:{inp.unrealised_pnl_pct:.1f}%")
            return Decision(
                ticker=inp.ticker, recommendation=RecType.SELL,
                action=ActionType.CLOSE_POSITION,
                composite_decision_score=cds,
                conviction_pct=_conviction_from_cds(cds, direction="down"),
                reasons_for=for_reasons, reasons_against=against_reasons,
            )

        # REDUCE: score deteriorated OR sector deteriorating OR classification weak
        if inp.classification == "Weak" or inp.company_score < 45:
            return Decision(
                ticker=inp.ticker, recommendation=RecType.REDUCE,
                action=ActionType.DECREASE_POSITION,
                composite_decision_score=cds,
                conviction_pct=_conviction_from_cds(cds, direction="down"),
                reasons_for=for_reasons, reasons_against=against_reasons,
            )
        if inp.sector_score is not None and inp.sector_score < 40:
            against_reasons.append(f"sector_weakening:{inp.sector_score:.1f}")
            return Decision(
                ticker=inp.ticker, recommendation=RecType.REDUCE,
                action=ActionType.DECREASE_POSITION,
                composite_decision_score=cds,
                conviction_pct=_conviction_from_cds(cds, direction="down"),
                reasons_for=for_reasons, reasons_against=against_reasons,
            )

        # ACCUMULATE: still in target portfolio + strong-bullish + score improving
        if (inp.in_target_portfolios and inp.classification == "Strong-Bullish"
                and inp.company_score >= 70):
            for_reasons.append("still_in_target_portfolio")
            return Decision(
                ticker=inp.ticker, recommendation=RecType.ACCUMULATE,
                action=ActionType.INCREASE_POSITION,
                composite_decision_score=cds,
                conviction_pct=_conviction_from_cds(cds, direction="up"),
                reasons_for=for_reasons, reasons_against=against_reasons,
            )

        # HOLD (default for existing positions still in reasonable shape)
        return Decision(
            ticker=inp.ticker, recommendation=RecType.HOLD,
            action=ActionType.NO_ACTION,
            composite_decision_score=cds,
            conviction_pct=_conviction_from_cds(cds, direction="stable"),
            reasons_for=for_reasons, reasons_against=against_reasons,
        )

    # ── Not held: new-position path ────────────────────────────────────────
    # STRONG BUY: top-decile score + high confidence + in target portfolio + Strong-Bullish
    if (inp.company_score >= 75 and inp.classification == "Strong-Bullish"
            and inp.confidence >= 0.7 and inp.in_target_portfolios):
        return Decision(
            ticker=inp.ticker, recommendation=RecType.STRONG_BUY,
            action=ActionType.NEW_POSITION,
            composite_decision_score=cds,
            conviction_pct=_conviction_from_cds(cds, direction="up"),
            reasons_for=for_reasons, reasons_against=against_reasons,
        )

    # BUY: strong classification + reasonable score
    if (inp.classification in ("Strong-Bullish", "Bullish") and inp.company_score >= 60
            and inp.confidence >= 0.6):
        return Decision(
            ticker=inp.ticker, recommendation=RecType.BUY,
            action=ActionType.NEW_POSITION,
            composite_decision_score=cds,
            conviction_pct=_conviction_from_cds(cds, direction="up"),
            reasons_for=for_reasons, reasons_against=against_reasons,
        )

    # AVOID: bearish OR very-low score
    if inp.classification == "Bearish" or inp.company_score < 35:
        return Decision(
            ticker=inp.ticker, recommendation=RecType.AVOID,
            action=ActionType.NO_ACTION,
            composite_decision_score=cds,
            conviction_pct=_conviction_from_cds(cds, direction="down"),
            reasons_for=for_reasons, reasons_against=against_reasons,
        )

    # WATCHLIST: near-Buy — 55-59 score OR confidence too low but classification good
    if (55 <= inp.company_score < 60) or \
        (inp.classification in ("Bullish", "Neutral") and inp.company_score >= 50):
        for_reasons.append("watching_for_improvement")
        return Decision(
            ticker=inp.ticker, recommendation=RecType.WATCHLIST,
            action=ActionType.NO_ACTION,
            composite_decision_score=cds,
            conviction_pct=_conviction_from_cds(cds, direction="stable"),
            reasons_for=for_reasons, reasons_against=against_reasons,
        )

    # AVOID by default (score 35-49, no clear signal)
    return Decision(
        ticker=inp.ticker, recommendation=RecType.AVOID,
        action=ActionType.NO_ACTION,
        composite_decision_score=cds,
        conviction_pct=_conviction_from_cds(cds, direction="down"),
        reasons_for=for_reasons, reasons_against=against_reasons,
    )


def _score_reasons(inp: DecisionInput, for_r: list[str], against_r: list[str]) -> None:
    """Populate for/against reason strings from the raw signal set."""
    if inp.company_score >= 75:
        for_r.append(f"company_score_top_decile:{inp.company_score:.1f}")
    elif inp.company_score >= 60:
        for_r.append(f"company_score_bullish:{inp.company_score:.1f}")
    elif inp.company_score >= 45:
        for_r.append(f"company_score_neutral:{inp.company_score:.1f}")
    elif inp.company_score >= 30:
        against_r.append(f"company_score_weak:{inp.company_score:.1f}")
    else:
        against_r.append(f"company_score_bearish:{inp.company_score:.1f}")

    if inp.confidence >= 0.8:
        for_r.append(f"high_confidence:{inp.confidence:.2f}")
    elif inp.confidence >= 0.6:
        for_r.append(f"moderate_confidence:{inp.confidence:.2f}")
    else:
        against_r.append(f"low_confidence:{inp.confidence:.2f}")

    if inp.industry_score is not None:
        if inp.industry_score >= 65:
            for_r.append(f"industry_strong:{inp.industry_display_or_key()}:{inp.industry_score:.1f}")
        elif inp.industry_score < 40:
            against_r.append(f"industry_weak:{inp.industry_display_or_key()}:{inp.industry_score:.1f}")

    if inp.sector_score is not None:
        if inp.sector_score >= 65:
            for_r.append(f"sector_strong:{inp.sector_score:.1f}")
        elif inp.sector_score < 40:
            against_r.append(f"sector_weak:{inp.sector_score:.1f}")

    if inp.global_posture == "Risk-On":
        for_r.append("global_regime_risk_on")
    elif inp.global_posture == "Risk-Off":
        against_r.append("global_regime_risk_off")

    if inp.in_target_portfolios:
        for_r.append(f"in_target_portfolios:{len(inp.in_target_portfolios)}")

    if inp.currently_held and inp.unrealised_pnl_pct is not None:
        if inp.unrealised_pnl_pct > 5:
            for_r.append(f"unrealised_gain:{inp.unrealised_pnl_pct:.1f}%")
        elif inp.unrealised_pnl_pct < -5:
            against_r.append(f"unrealised_loss:{inp.unrealised_pnl_pct:.1f}%")


def _conviction_from_cds(cds: float, direction: str) -> float:
    """Turn composite score + direction into a 0-100 conviction figure."""
    if direction == "up":
        return round(min(100.0, cds), 1)
    if direction == "down":
        return round(min(100.0, 100.0 - cds), 1)
    return round(50.0 + (cds - 50.0) * 0.3, 1)


# Add a convenience method to DecisionInput (patch class dynamically for readability)
def _industry_display_or_key(self):
    return self.industry_classification or "n/a"
DecisionInput.industry_display_or_key = _industry_display_or_key
