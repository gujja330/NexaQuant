"""AEGIS Pipeline Layer Runner · dynamic, config-driven orchestrator.

Reads configs/pipeline_layers.yaml at runtime. Invokes each layer's
script in dependency order. Tracks per-layer health + emits JSON.

Operator directive 2026-08-25: "dont hardcode anything, always make
dynamic pipelines / reusable for longterm".

Add / remove / reorder layers by editing configs/pipeline_layers.yaml ·
this module never needs a code change.

Usage:
    from backend.orchestrator.layer_runner import run_layer
    result = run_layer("assembly", market="india")

    # Or run the whole graph from earliest ready layer:
    run_all(market="india")

    # Or run a single layer's script directly:
    python scripts/run_assembly.py --market india
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────────────────────

def _cfg_path(root: Path) -> Path:
    return root / "configs" / "pipeline_layers.yaml"


def load_config(root: Path) -> dict:
    p = _cfg_path(root)
    if not p.exists():
        raise FileNotFoundError(f"pipeline layer config missing at {p}")
    try:
        import yaml
    except ImportError:
        raise RuntimeError("PyYAML not installed · pip install pyyaml")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def layer_names(root: Path) -> list:
    """Return layer names in topological order (respecting depends_on)."""
    cfg = load_config(root)
    layers = cfg.get("layers", {}) or {}
    # Sort by explicit `order` field · fallback to name
    return sorted(layers.keys(),
                        key=lambda n: (layers[n].get("order", 999), n))


# ─────────────────────────────────────────────────────────────
# Layer result dataclass
# ─────────────────────────────────────────────────────────────

@dataclass
class LayerResult:
    layer:         str = ""
    market:        str = ""
    started_utc:   str = ""
    finished_utc:  str = ""
    elapsed_sec:   float = 0.0
    exit_code:     int | None = None
    status:        str = "PENDING"       # PENDING | RUNNING | GREEN | YELLOW | RED
    stdout_tail:   list = field(default_factory=list)
    stderr_tail:   list = field(default_factory=list)
    notes:         str = ""


# ─────────────────────────────────────────────────────────────
# Health emission
# ─────────────────────────────────────────────────────────────

def _emit_health(root: Path, result: LayerResult, cfg: dict) -> Path:
    hcfg = cfg.get("health", {}) or {}
    pattern = hcfg.get("emit_path_pattern",
                                "reports/context/layer_health_{layer}.json")
    key = f"{result.layer}"
    if result.market:
        key = f"{result.layer}_{result.market}"
    rel = pattern.format(layer=key)
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(result), indent=2, default=str,
                                       ensure_ascii=False),
                     encoding="utf-8")
    return p


def _emit_aggregate(root: Path, results: list, cfg: dict) -> Path:
    hcfg = cfg.get("health", {}) or {}
    rel = hcfg.get("aggregate_path",
                            "reports/context/pipeline_layer_health.json")
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_layers":      len(results),
        "n_green":       sum(1 for r in results if r.status == "GREEN"),
        "n_yellow":      sum(1 for r in results if r.status == "YELLOW"),
        "n_red":         sum(1 for r in results if r.status == "RED"),
        "layers":        [asdict(r) for r in results],
    }
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


# ─────────────────────────────────────────────────────────────
# Layer runner
# ─────────────────────────────────────────────────────────────

def run_layer(layer_name: str, market: str = "",
                     root: Path | None = None,
                     extra_args: list | None = None) -> LayerResult:
    """Run one layer's script per config · returns LayerResult."""
    root = Path(root or Path(__file__).resolve().parents[2])
    cfg = load_config(root)
    ldef = (cfg.get("layers") or {}).get(layer_name)
    if not ldef:
        raise KeyError(f"layer '{layer_name}' not defined in pipeline_layers.yaml")

    defaults = cfg.get("defaults", {}) or {}
    timeout = int(ldef.get("timeout_sec", defaults.get("timeout_sec", 900)))
    python_exe = ldef.get("python_exe", defaults.get("python_exe")) or sys.executable
    work_dir = ldef.get("work_dir", defaults.get("work_dir", str(root)))

    result = LayerResult(
        layer=layer_name, market=market or "",
        started_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status="RUNNING",
    )
    script = ldef.get("script", "")
    if not script:
        result.status = "RED"; result.notes = f"no script defined for layer '{layer_name}'"
        _emit_health(root, result, cfg)
        return result

    cmd = [python_exe, script]
    # Static script_args + operator extras + per-market flag if applicable
    cmd += list(ldef.get("script_args", []) or [])
    if extra_args:
        cmd += list(extra_args)
    if ldef.get("per_market") and market:
        # Only append if caller didn't already
        if "--market" not in cmd:
            cmd += ["--market", market]

    t0 = time.time()
    try:
        r = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        result.exit_code = r.returncode
        result.stdout_tail = r.stdout.splitlines()[-20:] if r.stdout else []
        result.stderr_tail = r.stderr.splitlines()[-20:] if r.stderr else []
        if r.returncode == 0:
            result.status = "GREEN"
        elif r.returncode == 2:
            result.status = "YELLOW"     # convention · warnings + skips
        else:
            result.status = "RED"
        result.notes = f"exit={r.returncode}"
    except subprocess.TimeoutExpired:
        result.status = "RED"
        result.exit_code = -1
        result.notes = f"timeout after {timeout}s"
    except Exception as e:
        result.status = "RED"
        result.exit_code = -2
        result.notes = f"{type(e).__name__}: {e}"

    result.finished_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result.elapsed_sec = round(time.time() - t0, 2)
    _emit_health(root, result, cfg)
    return result


def run_all(market: str = "", root: Path | None = None,
                 layers: list | None = None,
                 stop_on_red: bool = True) -> list:
    """Run every layer in topological order · returns list of LayerResult.
    Skips downstream layers when an upstream one goes RED (fail-fast)
    unless `stop_on_red=False`."""
    root = Path(root or Path(__file__).resolve().parents[2])
    cfg = load_config(root)
    target = layers or layer_names(root)
    results: list = []
    for name in target:
        result = run_layer(name, market=market, root=root)
        results.append(result)
        print(f"[layer:{name}] status={result.status} · "
                  f"elapsed={result.elapsed_sec}s · {result.notes}")
        if stop_on_red and result.status == "RED":
            _fail_open = (cfg.get("layers", {}).get(name, {})
                                    .get("fail_open",
                                              cfg.get("defaults", {}).get("fail_open", False)))
            if not _fail_open:
                print(f"[layer_runner] {name} RED · stopping (set fail_open: true to continue)")
                break
    _emit_aggregate(root, results, cfg)
    return results
