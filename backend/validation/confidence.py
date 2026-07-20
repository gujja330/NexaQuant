"""Confidence aggregator.

Combines freshness / schema / completeness / quality / lineage
confidences into a single per-dataset confidence score using a
weighted geometric mean (so any single failing dimension drags
overall confidence down).
"""
from __future__ import annotations

import math
import time

from .base import Validator, ValidationResult, Verdict, Issue, Severity


WEIGHTS = {
    "freshness":     0.30,
    "schema":        0.25,
    "completeness":  0.20,
    "quality":       0.15,
    "lineage":       0.10,
}


class ConfidenceAggregator(Validator):
    """Not a validator per se — takes other validators' outputs and
    produces a rollup ValidationResult with the per-dataset confidence."""
    name = "confidence"

    def validate(self, spec: dict, root):
        raise NotImplementedError("Use aggregate() with existing results")

    def aggregate(self, dataset: str,
                    per_validator_results: list[ValidationResult]) -> ValidationResult:
        t0 = time.time()
        if not per_validator_results:
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.NOT_APPLICABLE,
                confidence=0.0, elapsed_ms=(time.time() - t0) * 1000)

        # Weighted geometric mean of confidences, weighted by WEIGHTS
        total_weight = 0.0
        log_sum = 0.0
        contributions = {}
        for r in per_validator_results:
            w = WEIGHTS.get(r.validator, 0.05)
            # Convert NOT_APPLICABLE to neutral (0.5) rather than zero
            c = r.confidence if r.verdict != Verdict.NOT_APPLICABLE else 0.5
            c = max(0.01, c)   # clamp so log is defined
            total_weight += w
            log_sum += w * math.log(c)
            contributions[r.validator] = {
                "verdict":    r.verdict.value,
                "confidence": round(c, 4),
                "weight":     w,
                "n_issues":   len(r.issues),
            }

        composite = math.exp(log_sum / total_weight) if total_weight > 0 else 0.0

        # Roll-up verdict from constituent verdicts
        verdicts = [r.verdict for r in per_validator_results]
        if any(v == Verdict.FAIL for v in verdicts):
            verdict = Verdict.FAIL
        elif any(v == Verdict.WARNING for v in verdicts):
            verdict = Verdict.WARNING
        elif all(v == Verdict.NOT_APPLICABLE for v in verdicts):
            verdict = Verdict.NOT_APPLICABLE
        else:
            verdict = Verdict.PASS

        total_issues = sum(len(r.issues) for r in per_validator_results)
        return ValidationResult(
            validator=self.name, dataset=dataset, verdict=verdict,
            confidence=round(composite, 4),
            evidence={
                "contributions": contributions,
                "n_issues_total": total_issues,
                "weights_used":  {k: v for k, v in WEIGHTS.items()},
            },
            elapsed_ms=(time.time() - t0) * 1000,
        )
