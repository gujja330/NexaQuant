"""Sprint A · Part 0 Isolation Contract · CI test that R3 code cannot
write to any production path.

Fails the build if any file under backend/research/r3/ or scripts/r3_*
imports a production writer or references a production output path."""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# Paths R3 must NEVER write to
_FORBIDDEN_PRODUCTION_PATHS = [
    "reports/telegram/aegis_",              # workbook files
    "reports/recommendations.json",          # R2 SSoT output
    "reports/research/opportunity_registry", # Registry JSONL
    "configs/ensemble_weights_adaptive",     # R2 model weights
    "configs/aegis_retirement",              # retirement config
    "reports/delivery/orphan_audit",         # orphan sink (R2 owns)
]

# Modules R3 must NEVER import
_FORBIDDEN_IMPORTS = [
    "backend.recommendation.ssot",
    "backend.recommendation.engine",
    "backend.recommendation.capital_rotation",
    "backend.recommendation.investor_actionable",
    "backend.portfolio.position_store",
    "backend.delivery.telegram",
    "backend.delivery.canonical.retirement",  # R3 must not mutate retirement state
]

# Registry write functions R3 must NEVER call
_FORBIDDEN_CALLS = [
    "oreg.get_or_create",
    "oreg.close",
    "oreg.reject",
    "opportunity_registry.get_or_create",
    "opportunity_registry.close",
    "opportunity_registry.reject",
    "publish_ssot",
    "update_from_recs",
]


def _r3_source_files():
    """Yield all Python files that are R3-owned."""
    r3_dir = _ROOT / "backend" / "research" / "r3"
    if r3_dir.exists():
        for fp in r3_dir.rglob("*.py"):
            yield fp
    scripts_dir = _ROOT / "scripts"
    if scripts_dir.exists():
        for fp in scripts_dir.glob("r3_*.py"):
            yield fp
        for fp in scripts_dir.glob("runner3_*.py"):
            yield fp


def test_r3_never_writes_to_production_paths():
    """R3 source code must not reference any production output path
    in a write context (open("w"), Path.write_text, to_parquet, to_json,
    to_excel, etc.)."""
    violations = []
    for fp in _r3_source_files():
        text = fp.read_text(encoding="utf-8", errors="replace")
        for line_num, line in enumerate(text.splitlines(), start=1):
            for path in _FORBIDDEN_PRODUCTION_PATHS:
                if path in line:
                    stripped = line.strip()
                    # Allow comments/docstrings that mention the path
                    if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
                        continue
                    violations.append(
                        f"{fp.relative_to(_ROOT)}:{line_num} · references {path}"
                    )
    assert not violations, (
        "R3 code references production output paths. Part 0 isolation "
        "contract forbids this. Violations:\n" + "\n".join(violations[:10])
    )


def test_r3_never_imports_production_modules():
    """R3 source code must not import R2 recommendation modules, Registry
    writers, or the delivery layer."""
    violations = []
    for fp in _r3_source_files():
        text = fp.read_text(encoding="utf-8", errors="replace")
        for line_num, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not (stripped.startswith("from ") or stripped.startswith("import ")):
                continue
            for mod in _FORBIDDEN_IMPORTS:
                if mod in line:
                    violations.append(
                        f"{fp.relative_to(_ROOT)}:{line_num} · imports {mod}"
                    )
    assert not violations, (
        "R3 code imports production modules. Part 0 isolation contract "
        "forbids this. Violations:\n" + "\n".join(violations[:10])
    )


def test_r3_never_calls_registry_writers():
    """R3 source code must not call any Registry mutation function."""
    violations = []
    for fp in _r3_source_files():
        text = fp.read_text(encoding="utf-8", errors="replace")
        for line_num, line in enumerate(text.splitlines(), start=1):
            for call in _FORBIDDEN_CALLS:
                if call in line and not line.strip().startswith("#"):
                    violations.append(
                        f"{fp.relative_to(_ROOT)}:{line_num} · calls {call}"
                    )
    assert not violations, (
        "R3 code calls Registry write functions. Part 0 isolation contract "
        "forbids this. Violations:\n" + "\n".join(violations[:10])
    )


def test_r3_runner_registry_status_shadow_only():
    """configs/aegis_runner_registry.yaml must declare R3.status: SHADOW_ONLY."""
    import yaml
    p = _ROOT / "configs" / "aegis_runner_registry.yaml"
    assert p.exists(), "aegis_runner_registry.yaml missing"
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    r3_status = cfg.get("runners", {}).get("R3", {}).get("status")
    assert r3_status == "SHADOW_ONLY", (
        f"R3 status must be SHADOW_ONLY · got {r3_status!r}. "
        f"Only CEO authorization can flip this."
    )
