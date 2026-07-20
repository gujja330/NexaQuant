"""Quality validator.

Detects duplicates, outliers, negative prices, zero volume runs, and
other data-quality red flags. Configured per dataset via `quality:`
section in datasets.yaml.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from .base import Validator, ValidationResult, Verdict, Issue, Severity


class QualityValidator(Validator):
    name = "quality"

    def validate(self, spec: dict, root: Path) -> ValidationResult:
        t0 = time.time()
        path = root / spec["path"]
        dataset = spec["name"]
        rules = spec.get("quality", {})

        if not path.exists() or path.suffix != ".parquet":
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.NOT_APPLICABLE,
                confidence=0.0,
                evidence={"reason": "not_applicable_to_non_parquet_or_missing"},
                elapsed_ms=(time.time() - t0) * 1000)

        issues = []; evidence = {}

        try:
            df = pd.read_parquet(path)
        except Exception as e:
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.FAIL,
                confidence=0.0,
                issues=[Issue(Severity.CRITICAL, f"read failed: {e}")],
                elapsed_ms=(time.time() - t0) * 1000)

        # Duplicate detection on (ticker + date) pairs if applicable
        dup_cols = rules.get("dedupe_on")
        if dup_cols and all(c in df.columns or df.index.name == c for c in dup_cols):
            candidate_df = df.reset_index() if df.index.name in dup_cols else df
            n_dup = int(candidate_df.duplicated(subset=dup_cols).sum())
            evidence["n_duplicates"] = n_dup
            if n_dup > 0:
                issues.append(Issue(Severity.WARNING,
                    f"{n_dup} duplicate rows on {dup_cols}",
                    {"n_duplicates": n_dup, "columns": dup_cols}))

        # Negative-value detection on price columns
        neg_cols = rules.get("no_negatives", [])
        for col in neg_cols:
            if col in df.columns:
                n_neg = int((df[col].astype(float) < 0).sum())
                if n_neg > 0:
                    issues.append(Issue(Severity.CRITICAL,
                        f"{n_neg} negative values in {col}",
                        {"column": col, "n_negatives": n_neg}))
                    evidence.setdefault("n_negatives", {})[col] = n_neg

        # Outlier detection — pct_change tail beyond N sigma
        outlier_cols = rules.get("outlier_return_check", [])
        outlier_sigma = rules.get("outlier_sigma", 8.0)
        for col in outlier_cols:
            if col in df.columns and len(df) > 20:
                ret = df[col].astype(float).pct_change().dropna()
                if not ret.empty:
                    sigma = float(ret.std())
                    if sigma > 0:
                        max_z = float((ret.abs() / sigma).max())
                        evidence.setdefault("max_return_z", {})[col] = round(max_z, 2)
                        if max_z > outlier_sigma:
                            issues.append(Issue(Severity.WARNING,
                                f"{col} has a {max_z:.1f}-sigma return move (threshold {outlier_sigma}σ)",
                                {"column": col, "max_z": max_z, "threshold": outlier_sigma}))

        # Zero-volume streak detection
        vol_col = rules.get("volume_column")
        if vol_col and vol_col in df.columns:
            recent_vol = df[vol_col].tail(10)
            if len(recent_vol) >= 5:
                n_zero_recent = int((recent_vol == 0).sum())
                if n_zero_recent >= 5:
                    issues.append(Issue(Severity.WARNING,
                        f"{n_zero_recent} of last 10 rows have zero {vol_col}",
                        {"n_zero_recent": n_zero_recent}))

        n_critical = sum(1 for i in issues if i.severity == Severity.CRITICAL)
        n_warning = sum(1 for i in issues if i.severity == Severity.WARNING)
        if n_critical:  verdict = Verdict.FAIL; conf = 0.3
        elif n_warning: verdict = Verdict.WARNING; conf = 0.75
        else:            verdict = Verdict.PASS; conf = 1.0

        return ValidationResult(
            validator=self.name, dataset=dataset, verdict=verdict, confidence=conf,
            issues=issues, evidence=evidence,
            elapsed_ms=(time.time() - t0) * 1000)
