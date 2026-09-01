"""AEGIS · Runner retirement resolver · CEO 2026-09-01.

Reads `configs/aegis_retirement.yaml` once per process (cached with
mtime check) and exposes helpers so every delivery-layer consumer
respects the same retirement state.

Never modifies any Registry entry.
Never touches R1/R2 decision logic.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


_CACHE = {"config": None, "mtime": 0.0}


def _config_path(root: Path) -> Path:
    return root / "configs" / "aegis_retirement.yaml"


def _load(root: Path) -> dict:
    p = _config_path(root)
    if not p.exists():
        return {"retired_runners": [], "active_runners": ["R1", "R2"]}
    mt = p.stat().st_mtime
    if _CACHE["config"] is not None and _CACHE["mtime"] == mt:
        return _CACHE["config"]
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        cfg = {"retired_runners": [], "active_runners": ["R1", "R2"]}
    _CACHE["config"] = cfg
    _CACHE["mtime"] = mt
    return cfg


def is_retired(root: Path, runner: str) -> bool:
    """True if the runner is formally retired from production."""
    cfg = _load(root)
    retired = {str(r).upper() for r in cfg.get("retired_runners", [])}
    return str(runner or "").upper() in retired


def active_runners(root: Path) -> set:
    """Set of runners currently active in production."""
    cfg = _load(root)
    return {str(r).upper() for r in cfg.get("active_runners", ["R1", "R2"])}


def retired_runners(root: Path) -> set:
    """Set of runners formally retired from production."""
    cfg = _load(root)
    return {str(r).upper() for r in cfg.get("retired_runners", [])}


def retirement_summary(root: Path) -> dict:
    """Full retirement config for reporting."""
    cfg = _load(root)
    return {
        "retired": list(retired_runners(root)),
        "active": list(active_runners(root)),
        "events": cfg.get("retirement_events", []),
    }
