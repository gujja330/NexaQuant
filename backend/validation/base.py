"""Base validator classes + result dataclasses.

Every validator inherits `Validator` and implements `validate(spec)` →
`ValidationResult`. Results are structured so the aggregator + dashboard
can consume them uniformly across India + USA.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any


class Verdict(str, Enum):
    PASS           = "PASS"
    WARNING        = "WARNING"
    FAIL           = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Severity(str, Enum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class Issue:
    severity: Severity
    message:  str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "message":  self.message,
            "evidence": self.evidence,
        }


@dataclass
class ValidationResult:
    """One validator's finding on one dataset."""
    validator:        str       # e.g. "freshness"
    dataset:          str       # dataset key from the registry
    verdict:          Verdict
    confidence:       float     # 0.0 - 1.0
    issues:           list[Issue] = field(default_factory=list)
    evidence:         dict[str, Any] = field(default_factory=dict)
    suggested_fixes:  list[str] = field(default_factory=list)
    elapsed_ms:       float = 0.0

    def to_dict(self) -> dict:
        return {
            "validator":       self.validator,
            "dataset":         self.dataset,
            "verdict":         self.verdict.value,
            "confidence":      round(self.confidence, 4),
            "n_issues":        len(self.issues),
            "issues":          [i.to_dict() for i in self.issues],
            "evidence":        self.evidence,
            "suggested_fixes": self.suggested_fixes,
            "elapsed_ms":      round(self.elapsed_ms, 2),
        }


class Validator(ABC):
    """Every validator inherits this."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def validate(self, spec: dict, root: Path) -> ValidationResult:
        """Run this validator against one dataset spec.

        `spec` is a dict loaded from the market's `datasets.yaml`.
        `root` is the market's data root (india/ or usa/data root).
        """
        ...


def combine_verdicts(verdicts: list[Verdict]) -> Verdict:
    """Roll up a list of verdicts to a single overall verdict.

    Priority (worst wins):  FAIL > WARNING > PASS > NOT_APPLICABLE
    """
    priority = {Verdict.FAIL: 3, Verdict.WARNING: 2, Verdict.PASS: 1,
                  Verdict.NOT_APPLICABLE: 0}
    if not verdicts:
        return Verdict.NOT_APPLICABLE
    return max(verdicts, key=lambda v: priority[v])
