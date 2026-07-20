"""Schema validator.

For parquet: verifies required columns are present. For JSON: verifies
required top-level keys are present. Emits missing + unexpected columns
as evidence.

Verdicts:
  PASS     — all required keys/columns present, no extras (or extras allowed)
  WARNING  — extras present but strict_extras=false
  FAIL     — any required key/column missing
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from .base import Validator, ValidationResult, Verdict, Issue, Severity


class SchemaValidator(Validator):
    name = "schema"

    def validate(self, spec: dict, root: Path) -> ValidationResult:
        t0 = time.time()
        path = root / spec["path"]
        dataset = spec["name"]
        schema = spec.get("schema", {})
        strict_extras = schema.get("strict_extras", False)

        if not path.exists():
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.NOT_APPLICABLE,
                confidence=0.0, evidence={"reason": "file_missing"},
                elapsed_ms=(time.time() - t0) * 1000)

        try:
            if path.suffix == ".parquet":
                df = pd.read_parquet(path)
                present = list(df.columns) + ([df.index.name] if df.index.name else [])
                required = schema.get("required_columns", [])
            elif path.suffix == ".json":
                obj = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    present = list(obj.keys())
                else:
                    return ValidationResult(
                        validator=self.name, dataset=dataset, verdict=Verdict.FAIL,
                        confidence=0.5,
                        issues=[Issue(Severity.CRITICAL, "JSON root is not an object",
                                       {"root_type": type(obj).__name__})],
                        elapsed_ms=(time.time() - t0) * 1000)
                required = schema.get("required_keys", [])
            elif path.suffix in (".csv", ".jsonl"):
                if spec.get("schema"):
                    return ValidationResult(
                        validator=self.name, dataset=dataset, verdict=Verdict.NOT_APPLICABLE,
                        confidence=0.5, evidence={"reason": f"{path.suffix} schema not yet supported"},
                        elapsed_ms=(time.time() - t0) * 1000)
                return ValidationResult(
                    validator=self.name, dataset=dataset, verdict=Verdict.PASS,
                    confidence=1.0, evidence={"suffix": path.suffix},
                    elapsed_ms=(time.time() - t0) * 1000)
            else:
                return ValidationResult(
                    validator=self.name, dataset=dataset, verdict=Verdict.NOT_APPLICABLE,
                    confidence=0.0, evidence={"suffix": path.suffix},
                    elapsed_ms=(time.time() - t0) * 1000)
        except Exception as e:
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.FAIL,
                confidence=0.0,
                issues=[Issue(Severity.CRITICAL, f"Could not read: {e}",
                               {"error": str(e)[:200]})],
                elapsed_ms=(time.time() - t0) * 1000)

        missing = [k for k in required if k not in present]
        extras  = [k for k in present if k not in required] if strict_extras else []

        issues = []; suggested = []
        evidence = {
            "required":       required,
            "present":        present,
            "missing":        missing,
            "extras":         extras,
            "n_columns":      len(present),
        }

        if missing:
            issues.append(Issue(Severity.CRITICAL,
                                 f"Missing required keys/columns: {missing}",
                                 {"missing": missing}))
            suggested.append(f"Update producer of {dataset} to emit {missing}")
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.FAIL,
                confidence=0.3, issues=issues, evidence=evidence,
                suggested_fixes=suggested, elapsed_ms=(time.time() - t0) * 1000)

        if extras and strict_extras:
            issues.append(Issue(Severity.WARNING,
                                 f"Unexpected extras: {extras}",
                                 {"extras": extras}))
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.WARNING,
                confidence=0.8, issues=issues, evidence=evidence,
                elapsed_ms=(time.time() - t0) * 1000)

        return ValidationResult(
            validator=self.name, dataset=dataset, verdict=Verdict.PASS, confidence=1.0,
            evidence=evidence, elapsed_ms=(time.time() - t0) * 1000)
