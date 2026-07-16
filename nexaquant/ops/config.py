"""Pipeline configuration loader.

Loads a pipeline YAML into structured StageDefinition objects. Validates
schema at load time so misconfiguration fails LOUDLY (never masked, never
retried at pipeline runtime).

Schema:
    name: aegis_daily
    description: string
    stages:
      - name: string
        command: [python, script.py, --arg]
        timeout_s: float (default 600)
        retries: int (default 0 — 1 attempt total)
        backoff_s: [float, ...]  (default: 5, 15, 45)
        depends_on: [stage_name, ...]  (default: [], meaning sequential)
        continue_on_failure: bool (default false; controls downstream execution)
        env: {KEY: VALUE, ...}  (added to subprocess env)
        cwd: string  (default: repo root)
        working_directory: alias for cwd
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .retry import RetryPolicy


@dataclass
class StageDefinition:
    name: str
    command: list[str]
    retry: RetryPolicy
    depends_on: list[str] = field(default_factory=list)
    continue_on_failure: bool = False
    env: dict = field(default_factory=dict)
    cwd: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("stage.name must be non-empty")
        if not self.command:
            raise ValueError(f"stage '{self.name}': command must be a non-empty list")
        if not isinstance(self.command, list):
            raise ValueError(f"stage '{self.name}': command must be a list of strings")


@dataclass
class PipelineConfig:
    name: str
    description: str
    stages: list[StageDefinition]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("pipeline.name must be non-empty")
        if not self.stages:
            raise ValueError(f"pipeline '{self.name}': must define at least one stage")
        seen: set[str] = set()
        for s in self.stages:
            if s.name in seen:
                raise ValueError(f"pipeline '{self.name}': duplicate stage name '{s.name}'")
            seen.add(s.name)
        # Validate depends_on references
        for s in self.stages:
            for dep in s.depends_on:
                if dep not in seen:
                    raise ValueError(f"stage '{s.name}': depends_on '{dep}' not defined")

    def stage_names(self) -> list[str]:
        return [s.name for s in self.stages]


def load_pipeline(path: Path | str) -> PipelineConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"pipeline config not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"pipeline config must be a YAML mapping, got {type(raw).__name__}")

    name = raw.get("name", "").strip()
    description = raw.get("description", "").strip()
    stages_raw = raw.get("stages", [])
    if not isinstance(stages_raw, list):
        raise ValueError("pipeline.stages must be a list")

    stages: list[StageDefinition] = []
    for i, s in enumerate(stages_raw):
        if not isinstance(s, dict):
            raise ValueError(f"pipeline.stages[{i}] must be a mapping")
        retry = RetryPolicy(
            max_attempts=int(s.get("retries", 0)) + 1,
            backoff_s=tuple(s.get("backoff_s", (5.0, 15.0, 45.0))),
            timeout_per_attempt_s=float(s.get("timeout_s", 600.0)),
        )
        stages.append(StageDefinition(
            name=str(s.get("name", "")).strip(),
            command=list(s.get("command", [])),
            retry=retry,
            depends_on=list(s.get("depends_on", [])),
            continue_on_failure=bool(s.get("continue_on_failure", False)),
            env=dict(s.get("env", {}) or {}),
            cwd=s.get("cwd") or s.get("working_directory"),
        ))
    return PipelineConfig(name=name, description=description, stages=stages)
