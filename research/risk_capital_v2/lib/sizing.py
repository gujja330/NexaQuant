"""Risk & Capital v2.0 · position sizing.

The exit criterion (PHASE2_MASTER_ROADMAP.md §6): every position
must answer three counter-questions in evidence terms —
  Why 6% allocation?  Why not 4%?  Why not 12%?

We express size as a stack of multiplicative factors, each traceable
to a specific input. The final size = base_size · Product(factors).
Every factor lives in [factor_min, factor_max] so the extreme output
is bounded. Every factor emits an explanation string that the operator
can read alongside the number.

Advisory-only. This module produces a target size + explanation. It
does not write to broker state, does not modify DEV022 portfolio.json,
does not auto-execute anything."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import numpy as np


# ─── Constants (transparent, documented, not tuned per-run) ─────────
BASE_WEIGHT              = 0.05        # 5% default target
FLOOR_WEIGHT             = 0.01        # 1% minimum meaningful position
CEILING_WEIGHT           = 0.15        # 15% maximum concentration
CONFIDENCE_FACTOR_RANGE  = (0.5, 1.5)  # [-50% .. +50%] based on calibrated confidence
REGIME_FACTOR_RANGE      = (0.5, 1.2)  # dampen in Risk-Off, mild boost in Risk-On
VOLATILITY_FACTOR_RANGE  = (0.6, 1.3)  # smaller sizes for high-vol names
SECTOR_CONC_FACTOR_RANGE = (0.3, 1.0)  # damp if sector already concentrated


@dataclass
class SizingFactor:
    name:        str
    value:       float
    explanation: str


@dataclass
class SizingDecision:
    ticker:            str
    base_weight:       float
    target_weight:     float
    floor:             float
    ceiling:           float
    factors:           list[SizingFactor]
    counterfactuals:   dict[str, dict]   # "at_4pct" / "at_12pct" comparisons
    verdict:           str               # PASS / WARNING / BLOCK
    explanation:       str


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _confidence_factor(calibrated_confidence: float | None) -> SizingFactor:
    """Higher calibrated confidence -> bigger size, bounded."""
    lo, hi = CONFIDENCE_FACTOR_RANGE
    if calibrated_confidence is None:
        return SizingFactor("confidence", 1.0,
                              "no calibrated confidence; neutral factor")
    # Anchor at base rate 0.58 (from DEV025 findings); above -> boost, below -> dampen
    baseline = 0.58
    scale = (calibrated_confidence - baseline) / 0.30    # 0.30 mapping span
    factor = 1.0 + scale
    factor = _clamp(factor, lo, hi)
    return SizingFactor(
        "confidence", round(factor, 4),
        f"calibrated confidence {calibrated_confidence:.3f} vs base {baseline:.2f}"
        f" -> factor {factor:.3f} (bounded [{lo}, {hi}])",
    )


def _regime_factor(regime: str | None) -> SizingFactor:
    lo, hi = REGIME_FACTOR_RANGE
    if regime is None or regime == "Unknown":
        return SizingFactor("regime", 1.0, "regime unknown; neutral")
    mapping = {"Risk-On": 1.2, "Neutral": 1.0, "Risk-Off": 0.5}
    factor = mapping.get(regime, 1.0)
    factor = _clamp(factor, lo, hi)
    return SizingFactor(
        "regime", round(factor, 4),
        f"regime='{regime}' -> factor {factor:.2f}",
    )


def _volatility_factor(annualised_vol: float | None,
                          reference_vol: float = 0.35) -> SizingFactor:
    """Higher vol -> smaller size. reference_vol anchors the neutral point."""
    lo, hi = VOLATILITY_FACTOR_RANGE
    if annualised_vol is None:
        return SizingFactor("volatility", 1.0, "vol unknown; neutral")
    if annualised_vol <= 0:
        return SizingFactor("volatility", 1.0, "vol non-positive; neutral")
    factor = reference_vol / annualised_vol
    factor = _clamp(factor, lo, hi)
    return SizingFactor(
        "volatility", round(factor, 4),
        f"annualised vol {annualised_vol:.3f} vs reference {reference_vol:.2f}"
        f" -> factor {factor:.3f} (bounded [{lo}, {hi}])",
    )


def _sector_concentration_factor(sector_share_so_far: float,
                                      sector_cap: float = 0.30) -> SizingFactor:
    """Dampen size as the sector approaches its concentration cap."""
    lo, hi = SECTOR_CONC_FACTOR_RANGE
    utilisation = sector_share_so_far / sector_cap if sector_cap > 0 else 0
    if utilisation >= 1.0:
        factor = 0.0
        expl = f"sector at cap {sector_cap:.0%} — BLOCK further concentration"
    else:
        factor = 1.0 - utilisation
        factor = _clamp(factor, lo, hi)
        expl = (f"sector share {sector_share_so_far:.2%} of cap {sector_cap:.0%}"
                 f" -> factor {factor:.3f}")
    return SizingFactor("sector_concentration", round(factor, 4), expl)


def size_position(ticker: str,
                     calibrated_confidence: float | None,
                     regime: str | None,
                     annualised_vol: float | None,
                     sector_share_so_far: float,
                     sector_cap: float = 0.30,
                     base_weight: float = BASE_WEIGHT) -> SizingDecision:
    """Compute target weight with a full explanation stack + counterfactuals."""
    factors = [
        _confidence_factor(calibrated_confidence),
        _regime_factor(regime),
        _volatility_factor(annualised_vol),
        _sector_concentration_factor(sector_share_so_far, sector_cap),
    ]
    multiplier = float(np.prod([f.value for f in factors]))
    target = base_weight * multiplier
    target = _clamp(target, FLOOR_WEIGHT, CEILING_WEIGHT)

    # Verdict
    if any(f.name == "sector_concentration" and f.value == 0.0 for f in factors):
        verdict = "BLOCK"
    elif target <= FLOOR_WEIGHT + 1e-6:
        verdict = "WARNING"
    elif target >= CEILING_WEIGHT - 1e-6:
        verdict = "WARNING"
    else:
        verdict = "PASS"

    # Counterfactuals: at 4% and 12%, which factors would need to change?
    def _cf(target_pct: float) -> dict:
        needed_mult = target_pct / base_weight
        current_mult = multiplier or 1e-6
        delta_mult = needed_mult / current_mult
        return {
            "target_weight":     target_pct,
            "needed_multiplier": round(needed_mult, 4),
            "current_multiplier": round(current_mult, 4),
            "delta_multiplier":  round(delta_mult, 4),
            "reasoning":         (
                f"to size at {target_pct*100:.0f}%, the composite factor "
                f"would need to become {needed_mult:.3f}x base "
                f"(currently {current_mult:.3f}x). "
                f"Change ratio: {delta_mult:.2f}x on the current stack."
            ),
        }

    counterfactuals = {
        "at_4pct":  _cf(0.04),
        "at_12pct": _cf(0.12),
    }

    factor_summary = " · ".join(f"{f.name}={f.value}" for f in factors)
    explanation = (
        f"target {target*100:.2f}% = base {base_weight*100:.0f}% × ({factor_summary})"
        f" -> {verdict}"
    )

    return SizingDecision(
        ticker=ticker,
        base_weight=base_weight,
        target_weight=round(target, 5),
        floor=FLOOR_WEIGHT,
        ceiling=CEILING_WEIGHT,
        factors=factors,
        counterfactuals=counterfactuals,
        verdict=verdict,
        explanation=explanation,
    )


def sizing_decision_to_dict(d: SizingDecision) -> dict:
    return {
        "ticker":           d.ticker,
        "base_weight":      d.base_weight,
        "target_weight":    d.target_weight,
        "floor":            d.floor,
        "ceiling":          d.ceiling,
        "factors":          [asdict(f) for f in d.factors],
        "counterfactuals":  d.counterfactuals,
        "verdict":          d.verdict,
        "explanation":      d.explanation,
    }
