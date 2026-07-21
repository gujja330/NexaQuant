"""Confidence Calibration — adjust raw ensemble confidence for real trust.

Inputs:
  raw_confidence          from ensemble
  model_agreement         from conflict resolver
  evidence_coverage       fraction of expected features that are non-null
  historical_precision    optional (0..1) — model precision from learning corpus
                            (defaults to None; Sprint 9 fills it)

Output: calibrated_confidence in [0, 1].

Rules (deterministic):
  - Start with raw_confidence
  - Multiply by (0.5 + 0.5 * model_agreement)   — high agreement retains full conf; 50/50 halves it
  - Multiply by max(0.5, evidence_coverage)     — thin data reduces trust
  - If historical_precision available: multiply by (0.3 + 0.7 * historical_precision)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CalibrationInputs:
    raw_confidence:       float
    model_agreement:      float
    evidence_coverage:    float                   # 0..1 fraction of non-null selected features
    historical_precision: float | None = None     # Sprint 9 fills; None = ignored


def calibrate_confidence(inp: CalibrationInputs) -> float:
    conf = max(0.0, min(1.0, inp.raw_confidence))
    conf *= (0.5 + 0.5 * max(0.0, min(1.0, inp.model_agreement)))
    conf *= max(0.5, min(1.0, inp.evidence_coverage))
    if inp.historical_precision is not None:
        p = max(0.0, min(1.0, inp.historical_precision))
        conf *= (0.3 + 0.7 * p)
    return round(max(0.0, min(1.0, conf)), 4)
