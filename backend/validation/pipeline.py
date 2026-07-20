"""Validation pipeline.

Walks a dataset registry (dict) and runs every validator against every
dataset. Produces a `BackendValidationResult` dict shaped for JSON emit.

Callers (india/backend_validation/run.py, usa/backend_validation/run.py)
just point this at their datasets.yaml + data root.
"""
from __future__ import annotations

import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import Validator, ValidationResult, Verdict, combine_verdicts
from .freshness import FreshnessValidator
from .schema import SchemaValidator
from .completeness import CompletenessValidator
from .quality import QualityValidator
from .lineage import LineageValidator
from .confidence import ConfidenceAggregator


DEFAULT_VALIDATORS: list[Validator] = [
    FreshnessValidator(),
    SchemaValidator(),
    CompletenessValidator(),
    QualityValidator(),
    LineageValidator(),
]


class BackendValidationPipeline:

    def __init__(self, market: str, datasets: list[dict], root: Path,
                    validators: list[Validator] = None):
        """
        market:    "india" or "usa"
        datasets:  list of dataset specs loaded from datasets.yaml
        root:      market root (e.g. repo_root for India datasets that live
                    under data/raw/india, or repo_root for USA datasets under usa/)
        validators: default = DEFAULT_VALIDATORS
        """
        self.market = market
        self.datasets = datasets
        self.root = Path(root)
        self.validators = validators or DEFAULT_VALIDATORS
        self.aggregator = ConfidenceAggregator()

    def run(self) -> dict:
        t0 = time.time()
        per_dataset: dict[str, dict] = {}
        all_results: list[ValidationResult] = []

        for spec in sorted(self.datasets, key=lambda s: s["name"]):
            ds_name = spec["name"]
            per_val_results: list[ValidationResult] = []
            for v in self.validators:
                try:
                    result = v.validate(spec, self.root)
                except Exception as e:
                    result = ValidationResult(
                        validator=v.name, dataset=ds_name, verdict=Verdict.FAIL,
                        confidence=0.0,
                        evidence={"validator_crashed": True, "error": str(e)[:200]},
                    )
                per_val_results.append(result)
                all_results.append(result)

            rollup = self.aggregator.aggregate(ds_name, per_val_results)
            per_dataset[ds_name] = {
                "spec":              {k: v for k, v in spec.items() if k != "schema"},
                "rollup_verdict":    rollup.verdict.value,
                "rollup_confidence": rollup.confidence,
                "n_issues":          rollup.evidence.get("n_issues_total", 0),
                "validators":        {r.validator: r.to_dict() for r in per_val_results},
            }

        # Aggregate market-level verdict
        rollups = [Verdict(d["rollup_verdict"]) for d in per_dataset.values()]
        market_verdict = combine_verdicts(rollups)

        # Aggregate market-level confidence — mean of per-dataset confidences
        confs = [d["rollup_confidence"] for d in per_dataset.values()
                    if d["rollup_verdict"] != Verdict.NOT_APPLICABLE.value]
        market_confidence = round(sum(confs) / len(confs), 4) if confs else 0.0

        counts: dict[str, int] = {v.value: 0 for v in Verdict}
        for d in per_dataset.values():
            counts[d["rollup_verdict"]] += 1

        return {
            "engine":         "backend_validation",
            "version":        "v1.0",
            "market":         self.market,
            "run_utc":        datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
            "n_datasets":     len(per_dataset),
            "verdict":        market_verdict.value,
            "confidence":     market_confidence,
            "counts":         counts,
            "elapsed_s":      round(time.time() - t0, 3),
            "datasets":       per_dataset,
        }

    def summary(self, full: dict) -> dict:
        """Compact summary consumed by ops_check + dashboard tiles."""
        return {
            "engine":       "backend_validation_summary",
            "market":       self.market,
            "run_utc":      full["run_utc"],
            "verdict":      full["verdict"],
            "confidence":   full["confidence"],
            "n_datasets":   full["n_datasets"],
            "counts":       full["counts"],
            "elapsed_s":    full["elapsed_s"],
            "top_issues":   self._top_issues(full),
        }

    def _top_issues(self, full: dict, k: int = 10) -> list[dict]:
        """Extract top-K issues across all datasets, sorted by severity."""
        issues = []
        for ds_name, ds in full["datasets"].items():
            for v_name, v_res in ds["validators"].items():
                for iss in v_res.get("issues", []):
                    issues.append({
                        "dataset":   ds_name,
                        "validator": v_name,
                        "severity":  iss["severity"],
                        "message":   iss["message"],
                    })
        priority = {"CRITICAL": 3, "WARNING": 2, "INFO": 1}
        issues.sort(key=lambda i: -priority.get(i["severity"], 0))
        return issues[:k]

    def append_history(self, summary: dict, history_path: Path) -> None:
        """Append this run's summary to the per-market history ledger."""
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(summary, default=str) + "\n")
