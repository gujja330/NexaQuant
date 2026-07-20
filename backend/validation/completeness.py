"""Completeness validator.

For parquet: row counts, null percentages per column, ticker coverage
against a declared universe. For JSON: presence of expected array
elements + non-empty arrays.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from .base import Validator, ValidationResult, Verdict, Issue, Severity


class CompletenessValidator(Validator):
    name = "completeness"

    def validate(self, spec: dict, root: Path) -> ValidationResult:
        t0 = time.time()
        path = root / spec["path"]
        dataset = spec["name"]
        rules = spec.get("completeness", {})

        if not path.exists():
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.NOT_APPLICABLE,
                confidence=0.0, evidence={"reason": "file_missing"},
                elapsed_ms=(time.time() - t0) * 1000)

        issues = []; evidence = {}; suggested = []

        try:
            if path.suffix == ".parquet":
                df = pd.read_parquet(path)
                evidence["n_rows"] = int(len(df))
                min_rows = rules.get("min_rows")
                if min_rows and len(df) < min_rows:
                    issues.append(Issue(Severity.WARNING,
                        f"row count {len(df)} < min {min_rows}",
                        {"n_rows": len(df), "min_rows": min_rows}))

                # Null percentage per critical column
                max_null_pct = rules.get("max_null_pct_per_column", {})
                for col, threshold in max_null_pct.items():
                    if col in df.columns:
                        pct = float(df[col].isna().mean())
                        if pct > threshold:
                            issues.append(Issue(Severity.WARNING,
                                f"column {col} null% = {pct:.3f} > {threshold}",
                                {"column": col, "null_pct": pct, "threshold": threshold}))
                        evidence.setdefault("null_pct", {})[col] = round(pct, 4)

                # Ticker coverage — array of expected symbols
                ticker_col = rules.get("ticker_column")
                expected_universe_size = rules.get("expected_universe_size")
                if ticker_col and ticker_col in df.columns:
                    unique_tickers = int(df[ticker_col].nunique())
                    evidence["unique_tickers"] = unique_tickers
                    if expected_universe_size:
                        coverage = unique_tickers / expected_universe_size
                        evidence["coverage_pct"] = round(coverage * 100, 2)
                        if coverage < 0.9:
                            issues.append(Issue(Severity.WARNING,
                                f"ticker coverage {coverage:.1%} of expected {expected_universe_size}",
                                {"coverage": coverage}))

            elif path.suffix == ".json":
                obj = json.loads(path.read_text(encoding="utf-8"))
                required_arrays = rules.get("required_non_empty_arrays", [])
                for arr_key in required_arrays:
                    arr = obj.get(arr_key)
                    if not isinstance(arr, list):
                        issues.append(Issue(Severity.CRITICAL,
                            f"'{arr_key}' not a list (got {type(arr).__name__})",
                            {"key": arr_key}))
                    elif not arr:
                        issues.append(Issue(Severity.WARNING,
                            f"'{arr_key}' is empty", {"key": arr_key}))
                    else:
                        evidence.setdefault("array_sizes", {})[arr_key] = len(arr)
        except Exception as e:
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.FAIL,
                confidence=0.0,
                issues=[Issue(Severity.CRITICAL, f"read failed: {e}",
                               {"error": str(e)[:200]})],
                elapsed_ms=(time.time() - t0) * 1000)

        n_critical = sum(1 for i in issues if i.severity == Severity.CRITICAL)
        n_warning = sum(1 for i in issues if i.severity == Severity.WARNING)
        if n_critical:      verdict = Verdict.FAIL; conf = 0.3
        elif n_warning:     verdict = Verdict.WARNING; conf = 0.7
        else:               verdict = Verdict.PASS; conf = 1.0

        if issues:
            suggested.append(f"Investigate producer of {dataset} — completeness degraded")

        return ValidationResult(
            validator=self.name, dataset=dataset, verdict=verdict, confidence=conf,
            issues=issues, evidence=evidence, suggested_fixes=suggested,
            elapsed_ms=(time.time() - t0) * 1000)
