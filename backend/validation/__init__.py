"""Backend validation framework.

Every validator returns a ValidationResult with:
  verdict:      PASS | WARNING | FAIL | NOT_APPLICABLE
  confidence:   0.0 – 1.0
  issues:       [ {severity, message, evidence} ]
  evidence:     {arbitrary key-values proving the verdict}
  suggested_fixes: [ str ]

The ValidationPipeline runs a suite of validators against a dataset
spec and produces an aggregate BackendValidationResult.
"""
from .base import Validator, ValidationResult, Verdict, Issue, Severity   # noqa: F401
