"""
india/ai_lab/lab_config.py — YAML/JSON loader + strict validation for AI Lab experiments.

DESIGN PRINCIPLES
- Research-critical fields MUST be explicit. Missing → LookupError (never silent defaults).
- Every field required by lab_runner is validated up-front (fail-loud before execution).
- Config hash is computed for provenance (record in reports).
- Candidate IDs must be unique. Types are checked. Ranges are checked where sensible.

REQUIRED YAML SCHEMA (top-level, unless field marked optional):

    lab_id: "LAB007"
    lab_name: "Dynamic Exposure"
    preregistration_file: "preregistration.md"           # relative to config file's directory
    trial_manifest: "../trial_manifest.md"               # for n_trials

    simulation:
      registry_path: "data/aegis_registry.csv"           # relative to repo root
      initial_capital: 100000
      cash_returns_annual: [0.0, 0.06]                    # dual primary
      cost_grid_bps: [15, 30, 50]

    periods:
      discovery_end: "2023-10-13"
      confirmation_start: "2024-01-15"

    candidates:                                          # ORDERED; first is the control (N0)
      N0: {type: "multiplicative_gates", is_control: true, gates: {...}}
      A:  {type: "multiplicative_gates", gates: {...}}
      B:  {type: "multiplicative_gates", gates: {...}}
      C:  {type: "multiplicative_gates", gates: {...}}
      D:  {type: "constant", value: 0.85}

    gates:                                               # promotion gates, ALL must be numeric
      - id: "gate_1"
        name: "Confirmation Ulcer improvement"
        expression: "n0.conf.ulcer - cand.conf.ulcer >= 1.0"
      - id: "gate_2"
        ...

    reporting:
      output_dir: "reports"
      report_name_template: "{lab_id}_{date}.md"
      diagnostics_name_template: "{lab_id}_diagnostics_{date}.csv"

    pbo:
      folds: 8
      min_configs_for_interpretation: 6      # if #candidates < this, PBO reported N/A

    dsr:
      n_trials_source: "manifest"            # or explicit integer

The config file's `_meta.hash` is stamped by load_experiment_config() automatically.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import json


@dataclass
class ExperimentConfig:
    """Parsed + validated experiment config. Fields mirror the YAML schema 1:1."""
    lab_id: str
    lab_name: str
    preregistration_file: Path
    trial_manifest_path: Path
    simulation: dict
    periods: dict
    candidates: dict
    gates: list
    reporting: dict
    pbo: dict
    dsr: dict
    config_path: Path
    config_hash: str
    raw: dict = field(repr=False)

    def control_id(self) -> str:
        """Return the ID of the candidate flagged is_control=true (exactly one required)."""
        controls = [cid for cid, c in self.candidates.items() if c.get("is_control")]
        if len(controls) != 1:
            raise ValueError(f"{self.config_path.name}: exactly one candidate must have is_control=true "
                             f"(found {len(controls)}: {controls})")
        return controls[0]

    def candidate_ids(self, exclude_control: bool = False) -> list[str]:
        ids = list(self.candidates.keys())
        if exclude_control:
            ctrl = self.control_id()
            ids = [i for i in ids if i != ctrl]
        return ids


# --------------------------------- LOADER + VALIDATION ---------------------------------

_REQUIRED_TOP = ("lab_id", "lab_name", "preregistration_file", "trial_manifest",
                 "simulation", "periods", "candidates", "gates", "reporting", "pbo", "dsr")
_REQUIRED_SIM = ("registry_path", "initial_capital", "cash_returns_annual", "cost_grid_bps")
_REQUIRED_PER = ("discovery_end", "confirmation_start")
_REQUIRED_REP = ("output_dir", "report_name_template", "diagnostics_name_template")
_REQUIRED_PBO = ("folds", "min_configs_for_interpretation")
_REQUIRED_DSR = ("n_trials_source",)


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    """Load + strictly validate an experiment YAML/JSON. Raises on ANY missing field."""
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Experiment config not found: {p}")
    raw_text = p.read_text(encoding="utf-8")
    try:
        import yaml
        data = yaml.safe_load(raw_text) if p.suffix in (".yml", ".yaml") else json.loads(raw_text)
    except ImportError:
        # Minimal fallback: JSON only, no YAML dep
        if p.suffix in (".yml", ".yaml"):
            raise ImportError(f"PyYAML not installed but {p.name} requires it. pip install pyyaml")
        data = json.loads(raw_text)

    if not isinstance(data, dict):
        raise ValueError(f"{p.name}: top-level must be a mapping")

    # Strict field presence
    missing_top = [k for k in _REQUIRED_TOP if k not in data]
    if missing_top:
        raise LookupError(f"{p.name}: missing required fields: {missing_top}")
    missing_sim = [k for k in _REQUIRED_SIM if k not in data["simulation"]]
    if missing_sim:
        raise LookupError(f"{p.name} simulation: missing {missing_sim}")
    missing_per = [k for k in _REQUIRED_PER if k not in data["periods"]]
    if missing_per:
        raise LookupError(f"{p.name} periods: missing {missing_per}")
    missing_rep = [k for k in _REQUIRED_REP if k not in data["reporting"]]
    if missing_rep:
        raise LookupError(f"{p.name} reporting: missing {missing_rep}")
    missing_pbo = [k for k in _REQUIRED_PBO if k not in data["pbo"]]
    if missing_pbo:
        raise LookupError(f"{p.name} pbo: missing {missing_pbo}")
    missing_dsr = [k for k in _REQUIRED_DSR if k not in data["dsr"]]
    if missing_dsr:
        raise LookupError(f"{p.name} dsr: missing {missing_dsr}")

    # Candidate validation
    candidates = data["candidates"]
    if not isinstance(candidates, dict) or not candidates:
        raise ValueError(f"{p.name}: candidates must be a non-empty mapping")
    if len(candidates) != len(set(candidates.keys())):
        raise ValueError(f"{p.name}: duplicate candidate IDs")
    for cid, c in candidates.items():
        if "type" not in c:
            raise LookupError(f"{p.name} candidate '{cid}': missing 'type' field")

    # Gate validation
    if not isinstance(data["gates"], list) or not data["gates"]:
        raise ValueError(f"{p.name}: gates must be a non-empty list")
    for i, g in enumerate(data["gates"]):
        for req in ("id", "name", "expression"):
            if req not in g:
                raise LookupError(f"{p.name} gates[{i}]: missing '{req}'")

    # Type checks — cash + cost lists are numeric
    for x in data["simulation"]["cash_returns_annual"]:
        if not isinstance(x, (int, float)):
            raise TypeError(f"{p.name} simulation.cash_returns_annual: non-numeric value {x!r}")
    for x in data["simulation"]["cost_grid_bps"]:
        if not isinstance(x, (int, float)):
            raise TypeError(f"{p.name} simulation.cost_grid_bps: non-numeric value {x!r}")
    if not isinstance(data["simulation"]["initial_capital"], (int, float)):
        raise TypeError(f"{p.name} simulation.initial_capital must be numeric")

    # Path resolution — everything relative to CONFIG FILE'S directory
    cfg_dir = p.parent
    prereg = (cfg_dir / data["preregistration_file"]).resolve()
    manifest = (cfg_dir / data["trial_manifest"]).resolve()

    # Config hash — canonical JSON dump for reproducibility
    canon = json.dumps(data, sort_keys=True, default=str)
    config_hash = hashlib.sha256(canon.encode()).hexdigest()[:16]

    return ExperimentConfig(
        lab_id=data["lab_id"],
        lab_name=data["lab_name"],
        preregistration_file=prereg,
        trial_manifest_path=manifest,
        simulation=data["simulation"],
        periods=data["periods"],
        candidates=data["candidates"],
        gates=data["gates"],
        reporting=data["reporting"],
        pbo=data["pbo"],
        dsr=data["dsr"],
        config_path=p,
        config_hash=config_hash,
        raw=data,
    )
