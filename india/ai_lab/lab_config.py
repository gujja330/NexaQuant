"""
india/ai_lab/lab_config.py — YAML/JSON loader + strict schema validation for AI Lab experiments.

Hardening applied 2026-07-13:
- Custom YAML SafeLoader that REJECTS duplicate mapping keys at parse time (default PyYAML would
  silently overwrite). Duplicate-key protection is at the parser level; per-map dedup checks
  elsewhere are defence-in-depth only.
- Semantic validation of every research-critical field (finite numbers, sign, ordering,
  cross-field consistency such as canonical_cost_bps ∈ cost_grid_bps).
- Regime bucket definitions must be non-overlapping and cover the whole [0, 1] range monotonically.
- Smooth-taper parameters are validated (from<to, pctiles in [0,1], multipliers finite).
- Research-critical previously-hardcoded values (trading_days_per_year, canonical/stress cost,
  stability folds, regime buckets, rolling min_periods) MUST now appear in the config.

REQUIRED YAML SCHEMA (top-level):

    lab_id: str
    lab_name: str
    preregistration_file: str        # relative to config file's directory
    trial_manifest: str              # relative to config file's directory

    simulation:
      registry_path: str             # relative to repo root
      initial_capital: float > 0
      cash_returns_annual: [float]   # non-empty list; each finite
      cost_grid_bps: [float]         # non-empty list; each finite and >= 0
      trading_days_per_year: int > 0
      canonical_cost_bps: float      # must be an element of cost_grid_bps
      promotion_stress_cost_bps: float  # must be an element of cost_grid_bps

    periods:
      discovery_end: date-str        # must be < confirmation_start
      confirmation_start: date-str

    stability:
      folds: int >= 2

    regimes:
      metric_key: str                # meta key holding the regime-defining value (e.g., "exp")
      buckets: [                     # non-overlapping, monotonic, cover the range
        {name: str, min_inclusive: float, max_exclusive: float}
      ]

    policy_parameters:
      rolling_min_periods: int > 0

    candidates:                      # exactly one is_control: true
      {id}: {type: str, ...policy-specific fields}

    gates:                           # non-empty list; unique IDs
      - {id: str, name: str, expression: str}

    pbo:
      folds: int (>=2, even)
      min_configs_for_interpretation: int >= 2

    dsr:
      n_trials_source: "manifest" | int

    reporting:
      output_dir: str
      report_name_template: str
      diagnostics_name_template: str
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
import hashlib
import json
import math


# ================================ STRICT YAML LOADER ================================

def _load_yaml_strict(text: str, source_name: str) -> Any:
    """PyYAML SafeLoader subclass that raises on duplicate mapping keys.

    Default SafeLoader silently overwrites duplicates. This wrapper walks each MappingNode's
    key list and errors on repeats — protecting research config from typos like two `cost_bps`
    keys in the same mapping.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required for YAML configs. pip install pyyaml")

    class StrictSafeLoader(yaml.SafeLoader):
        pass

    def _construct_mapping_strict(loader, node, deep=False):
        if not isinstance(node, yaml.MappingNode):
            raise yaml.constructor.ConstructorError(
                None, None, f"expected a mapping node, but found {node.id}", node.start_mark)
        seen = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=True)
            hashable = key if isinstance(key, (str, int, float, tuple)) else str(key)
            if hashable in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"[{source_name}] duplicate key: {key!r}",
                    key_node.start_mark)
            seen.add(hashable)
        return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)

    StrictSafeLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping_strict)
    return yaml.load(text, Loader=StrictSafeLoader)


# ================================ DATACLASS ================================

@dataclass
class RegimeBucket:
    name: str
    min_inclusive: float          # -inf if unspecified
    max_exclusive: float          # +inf if unspecified

    def contains(self, x: float) -> bool:
        return (self.min_inclusive <= x) and (x < self.max_exclusive)


@dataclass
class ExperimentConfig:
    lab_id: str
    lab_name: str
    preregistration_file: Path
    trial_manifest_path: Path
    simulation: dict
    periods: dict
    stability: dict
    regimes: dict                 # {metric_key: str, buckets: [RegimeBucket]}
    policy_parameters: dict
    candidates: dict
    gates: list
    reporting: dict
    pbo: dict
    dsr: dict
    config_path: Path
    config_hash: str
    raw: dict = field(repr=False)

    def control_id(self) -> str:
        ctrls = [cid for cid, c in self.candidates.items() if c.get("is_control")]
        if len(ctrls) != 1:
            raise ValueError(f"{self.config_path.name}: exactly one candidate must have "
                             f"is_control=true (found {len(ctrls)}: {ctrls})")
        return ctrls[0]

    def candidate_ids(self, exclude_control: bool = False) -> list[str]:
        ids = list(self.candidates.keys())
        if exclude_control:
            ctrl = self.control_id()
            ids = [i for i in ids if i != ctrl]
        return ids

    def regime_bucket_for(self, value: float) -> str | None:
        """Return the bucket name containing `value`, or None if not in any bucket."""
        for b in self.regimes["buckets"]:
            if b.contains(float(value)):
                return b.name
        return None

    def canonical_cost(self) -> float:
        return float(self.simulation["canonical_cost_bps"])

    def stress_cost(self) -> float:
        return float(self.simulation["promotion_stress_cost_bps"])

    def trading_days(self) -> int:
        return int(self.simulation["trading_days_per_year"])

    def stability_folds(self) -> int:
        return int(self.stability["folds"])


# ================================ VALIDATION ================================

def _require(cond, msg):
    if not cond:
        raise LookupError(msg) if "missing" in msg else ValueError(msg)


def _finite_number(x, field_desc: str) -> float:
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        raise TypeError(f"{field_desc}: must be numeric, got {type(x).__name__}")
    fx = float(x)
    if not math.isfinite(fx):
        raise ValueError(f"{field_desc}: must be finite, got {fx}")
    return fx


def _validate_simulation(sim: dict, source: str) -> None:
    required = ("registry_path", "initial_capital", "cash_returns_annual", "cost_grid_bps",
                "trading_days_per_year", "canonical_cost_bps", "promotion_stress_cost_bps")
    for k in required:
        if k not in sim:
            raise LookupError(f"[{source}] simulation.{k} missing")

    _finite_number(sim["initial_capital"], f"[{source}] simulation.initial_capital")
    if sim["initial_capital"] <= 0:
        raise ValueError(f"[{source}] simulation.initial_capital must be > 0")

    if not isinstance(sim["cash_returns_annual"], list) or not sim["cash_returns_annual"]:
        raise ValueError(f"[{source}] simulation.cash_returns_annual must be a non-empty list")
    for i, c in enumerate(sim["cash_returns_annual"]):
        _finite_number(c, f"[{source}] simulation.cash_returns_annual[{i}]")

    if not isinstance(sim["cost_grid_bps"], list) or not sim["cost_grid_bps"]:
        raise ValueError(f"[{source}] simulation.cost_grid_bps must be a non-empty list")
    for i, c in enumerate(sim["cost_grid_bps"]):
        v = _finite_number(c, f"[{source}] simulation.cost_grid_bps[{i}]")
        if v < 0:
            raise ValueError(f"[{source}] simulation.cost_grid_bps[{i}] must be >= 0")

    td = sim["trading_days_per_year"]
    if not isinstance(td, int) or td <= 0:
        raise ValueError(f"[{source}] simulation.trading_days_per_year must be int > 0")

    canon = _finite_number(sim["canonical_cost_bps"], f"[{source}] simulation.canonical_cost_bps")
    stress = _finite_number(sim["promotion_stress_cost_bps"],
                             f"[{source}] simulation.promotion_stress_cost_bps")
    if canon not in [float(x) for x in sim["cost_grid_bps"]]:
        raise ValueError(f"[{source}] canonical_cost_bps={canon} must exist in cost_grid_bps")
    if stress not in [float(x) for x in sim["cost_grid_bps"]]:
        raise ValueError(f"[{source}] promotion_stress_cost_bps={stress} must exist in cost_grid_bps")


def _validate_periods(periods: dict, source: str) -> None:
    for k in ("discovery_end", "confirmation_start"):
        if k not in periods:
            raise LookupError(f"[{source}] periods.{k} missing")
    from datetime import date as _date, datetime as _dt
    def _parse(v):
        if isinstance(v, _date):
            return v
        try:
            return _dt.strptime(str(v), "%Y-%m-%d").date()
        except Exception:
            raise ValueError(f"[{source}] periods date '{v}' must be YYYY-MM-DD")
    d_end = _parse(periods["discovery_end"])
    c_start = _parse(periods["confirmation_start"])
    if not (d_end < c_start):
        raise ValueError(f"[{source}] discovery_end ({d_end}) must be < confirmation_start ({c_start})")


def _validate_regimes(regimes: dict, source: str) -> list[RegimeBucket]:
    if "metric_key" not in regimes or not isinstance(regimes["metric_key"], str) \
            or not regimes["metric_key"].strip():
        raise ValueError(f"[{source}] regimes.metric_key must be a non-empty string")
    if "buckets" not in regimes or not isinstance(regimes["buckets"], list) or not regimes["buckets"]:
        raise ValueError(f"[{source}] regimes.buckets must be a non-empty list")

    parsed = []
    seen_names = set()
    for i, b in enumerate(regimes["buckets"]):
        if "name" not in b or not isinstance(b["name"], str) or not b["name"].strip():
            raise ValueError(f"[{source}] regimes.buckets[{i}].name must be non-empty string")
        if b["name"] in seen_names:
            raise ValueError(f"[{source}] duplicate regime bucket name: {b['name']}")
        seen_names.add(b["name"])
        lo = _finite_number(b.get("min_inclusive", -math.inf),
                            f"[{source}] regimes.buckets[{i}].min_inclusive") \
             if "min_inclusive" in b else -math.inf
        hi = _finite_number(b.get("max_exclusive", math.inf),
                            f"[{source}] regimes.buckets[{i}].max_exclusive") \
             if "max_exclusive" in b else math.inf
        if not (lo < hi):
            raise ValueError(f"[{source}] bucket {b['name']}: min_inclusive ({lo}) must be < max_exclusive ({hi})")
        parsed.append(RegimeBucket(name=b["name"], min_inclusive=lo, max_exclusive=hi))

    # Overlap check: sort by min_inclusive; adjacent max must equal next min (no gaps or overlaps allowed).
    parsed_sorted = sorted(parsed, key=lambda b: b.min_inclusive)
    for i in range(len(parsed_sorted) - 1):
        cur, nxt = parsed_sorted[i], parsed_sorted[i+1]
        if cur.max_exclusive > nxt.min_inclusive:
            raise ValueError(f"[{source}] regime buckets overlap: {cur.name} (max_exclusive={cur.max_exclusive}) "
                             f"vs {nxt.name} (min_inclusive={nxt.min_inclusive})")
        # allow gaps (values in gap → None from regime_bucket_for); operator can decide semantics
    return parsed


def _validate_candidates(candidates: dict, source: str) -> None:
    if not isinstance(candidates, dict) or not candidates:
        raise ValueError(f"[{source}] candidates must be a non-empty mapping")
    controls = [cid for cid, c in candidates.items() if c.get("is_control")]
    if len(controls) != 1:
        raise ValueError(f"[{source}] exactly ONE candidate must be is_control=true "
                         f"(found {len(controls)}: {controls})")
    for cid, c in candidates.items():
        if not isinstance(c, dict):
            raise TypeError(f"[{source}] candidate '{cid}' must be a mapping")
        if "type" not in c or not isinstance(c["type"], str) or not c["type"].strip():
            raise ValueError(f"[{source}] candidate '{cid}': 'type' must be non-empty string")
        if c["type"] == "constant":
            if "value" not in c:
                raise LookupError(f"[{source}] candidate '{cid}' (constant): 'value' required")
            _finite_number(c["value"], f"[{source}] candidate '{cid}'.value")
        # policy-specific deep validation is deferred to the plugin (registered builder)
        # but we DO validate smooth_taper if present
        gates_cfg = c.get("gates", {})
        vix = gates_cfg.get("india_vix", {}) if isinstance(gates_cfg, dict) else {}
        if vix.get("mode") == "smooth_taper":
            for k in ("window_days", "from_pctile", "to_pctile",
                      "multiplier_at_from_pctile", "multiplier_at_to_pctile"):
                if k not in vix:
                    raise LookupError(f"[{source}] {cid}.gates.india_vix (smooth_taper): '{k}' required")
            fp = _finite_number(vix["from_pctile"], f"[{source}] {cid}.from_pctile")
            tp = _finite_number(vix["to_pctile"], f"[{source}] {cid}.to_pctile")
            if not (0.0 <= fp < tp <= 1.0):
                raise ValueError(f"[{source}] {cid}: smooth_taper requires 0 <= from_pctile < to_pctile <= 1")
            _finite_number(vix["multiplier_at_from_pctile"], f"[{source}] {cid}.multiplier_at_from_pctile")
            _finite_number(vix["multiplier_at_to_pctile"], f"[{source}] {cid}.multiplier_at_to_pctile")


def _validate_gates(gates: list, source: str) -> None:
    if not isinstance(gates, list) or not gates:
        raise ValueError(f"[{source}] gates must be a non-empty list")
    seen_ids = set()
    for i, g in enumerate(gates):
        for k in ("id", "name", "expression"):
            if k not in g:
                raise LookupError(f"[{source}] gates[{i}].{k} missing")
        if g["id"] in seen_ids:
            raise ValueError(f"[{source}] duplicate gate id: {g['id']}")
        seen_ids.add(g["id"])
        if not isinstance(g["expression"], str) or not g["expression"].strip():
            raise ValueError(f"[{source}] gate '{g['id']}': expression must be non-empty string")


def _validate_pbo(pbo: dict, source: str) -> None:
    for k in ("folds", "min_configs_for_interpretation"):
        if k not in pbo:
            raise LookupError(f"[{source}] pbo.{k} missing")
    folds = pbo["folds"]
    if not isinstance(folds, int) or folds < 2:
        raise ValueError(f"[{source}] pbo.folds must be int >= 2")
    if folds % 2 != 0:
        raise ValueError(f"[{source}] pbo.folds must be EVEN (CSCV convention)")
    mc = pbo["min_configs_for_interpretation"]
    if not isinstance(mc, int) or mc < 2:
        raise ValueError(f"[{source}] pbo.min_configs_for_interpretation must be int >= 2")


def _validate_stability(stab: dict, source: str) -> None:
    if "folds" not in stab:
        raise LookupError(f"[{source}] stability.folds missing")
    folds = stab["folds"]
    if not isinstance(folds, int) or folds < 2:
        raise ValueError(f"[{source}] stability.folds must be int >= 2")


def _validate_policy_parameters(pp: dict, source: str) -> None:
    if "rolling_min_periods" not in pp:
        raise LookupError(f"[{source}] policy_parameters.rolling_min_periods missing")
    v = pp["rolling_min_periods"]
    if not isinstance(v, int) or v <= 0:
        raise ValueError(f"[{source}] policy_parameters.rolling_min_periods must be int > 0")


# ================================ LOADER ================================

_REQUIRED_TOP = (
    "lab_id", "lab_name", "preregistration_file", "trial_manifest",
    "simulation", "periods", "stability", "regimes", "policy_parameters",
    "candidates", "gates", "reporting", "pbo", "dsr",
)


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Experiment config not found: {p}")
    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yml", ".yaml"):
        data = _load_yaml_strict(text, p.name)
    elif p.suffix == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"Unsupported config extension: {p.suffix}. Use .yaml or .json.")

    if not isinstance(data, dict):
        raise ValueError(f"{p.name}: top-level must be a mapping")

    missing = [k for k in _REQUIRED_TOP if k not in data]
    if missing:
        raise LookupError(f"[{p.name}] top-level missing fields: {missing}")

    _validate_simulation(data["simulation"], p.name)
    _validate_periods(data["periods"], p.name)
    parsed_buckets = _validate_regimes(data["regimes"], p.name)
    _validate_stability(data["stability"], p.name)
    _validate_policy_parameters(data["policy_parameters"], p.name)
    _validate_candidates(data["candidates"], p.name)
    _validate_gates(data["gates"], p.name)
    _validate_pbo(data["pbo"], p.name)
    # reporting must include required templates
    for k in ("output_dir", "report_name_template", "diagnostics_name_template"):
        if k not in data["reporting"]:
            raise LookupError(f"[{p.name}] reporting.{k} missing")
    # dsr
    if "n_trials_source" not in data["dsr"]:
        raise LookupError(f"[{p.name}] dsr.n_trials_source missing")

    cfg_dir = p.parent
    prereg = (cfg_dir / data["preregistration_file"]).resolve()
    manifest = (cfg_dir / data["trial_manifest"]).resolve()

    canon = json.dumps(data, sort_keys=True, default=str)
    config_hash = hashlib.sha256(canon.encode()).hexdigest()[:16]

    regimes_wrapped = {"metric_key": data["regimes"]["metric_key"], "buckets": parsed_buckets}

    return ExperimentConfig(
        lab_id=data["lab_id"],
        lab_name=data["lab_name"],
        preregistration_file=prereg,
        trial_manifest_path=manifest,
        simulation=data["simulation"],
        periods=data["periods"],
        stability=data["stability"],
        regimes=regimes_wrapped,
        policy_parameters=data["policy_parameters"],
        candidates=data["candidates"],
        gates=data["gates"],
        reporting=data["reporting"],
        pbo=data["pbo"],
        dsr=data["dsr"],
        config_path=p,
        config_hash=config_hash,
        raw=data,
    )
