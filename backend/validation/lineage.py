"""Lineage validator.

Verifies that every dataset's declared producer script exists on disk.
Does NOT verify that the producer ran recently (that's freshness's job).
Emits a lineage graph as evidence.
"""
from __future__ import annotations

import time
from pathlib import Path

from .base import Validator, ValidationResult, Verdict, Issue, Severity


class LineageValidator(Validator):
    name = "lineage"

    def validate(self, spec: dict, root: Path) -> ValidationResult:
        t0 = time.time()
        dataset = spec["name"]
        producer = spec.get("producer")

        if not producer:
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.NOT_APPLICABLE,
                confidence=0.5,
                evidence={"reason": "no_producer_declared"},
                elapsed_ms=(time.time() - t0) * 1000)

        # Producer can be a script path OR a well-known label ("yfinance", "manual", "external")
        if producer.startswith(("yfinance", "external", "manual", "google_news",
                                  "nse_api", "sec_edgar", "operator")):
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.PASS,
                confidence=1.0, evidence={"producer": producer, "kind": "external"},
                elapsed_ms=(time.time() - t0) * 1000)

        # Otherwise expect it to be a script path in the repo
        repo_root = Path(__file__).resolve().parents[2]
        producer_path = repo_root / producer
        if not producer_path.exists():
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.FAIL,
                confidence=0.5,
                issues=[Issue(Severity.CRITICAL,
                               f"declared producer {producer} does not exist",
                               {"producer_path": str(producer_path)})],
                evidence={"producer": producer},
                suggested_fixes=[
                    f"Either implement {producer} or update datasets.yaml"],
                elapsed_ms=(time.time() - t0) * 1000)

        # Verify the producer is invoked by SOMETHING in the repo
        # (grep for its filename in scripts + workflows)
        producer_name = Path(producer).name
        callers = self._find_callers(repo_root, producer_name, exclude_self=producer_path)

        issues = []; suggested = []
        evidence = {
            "producer":       producer,
            "producer_path":  str(producer_path),
            "n_callers":      len(callers),
            "callers":        callers[:10],
        }

        if not callers:
            issues.append(Issue(Severity.WARNING,
                f"producer {producer_name} has no known callers in the repo",
                {"producer": producer}))
            suggested.append(f"Wire {producer_name} into an orchestrator OR mark dataset as manual")
            verdict = Verdict.WARNING; conf = 0.7
        else:
            verdict = Verdict.PASS; conf = 1.0

        return ValidationResult(
            validator=self.name, dataset=dataset, verdict=verdict, confidence=conf,
            issues=issues, evidence=evidence, suggested_fixes=suggested,
            elapsed_ms=(time.time() - t0) * 1000)

    def _find_callers(self, repo_root: Path, producer_name: str,
                        exclude_self: Path) -> list[str]:
        """Grep for the producer filename across Python and YAML/PS/BAT files."""
        callers = []
        patterns = ["*.py", "*.yml", "*.yaml", "*.ps1", "*.bat", "*.service", "*.timer"]
        for pat in patterns:
            for f in repo_root.rglob(pat):
                if f == exclude_self or "__pycache__" in f.parts:
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    if producer_name in text:
                        callers.append(str(f.relative_to(repo_root)))
                except Exception:
                    continue
                if len(callers) >= 20:
                    return callers
        return callers
