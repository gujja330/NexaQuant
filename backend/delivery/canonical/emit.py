"""AEGIS · Canonical JSONL emitter · CEO 2026-09-01 architecture.

Writes canonical-object populations to
`reports/canonical/{market}_{population}_{YYYY-MM-DD}.jsonl` for
downstream consumers (validators · reconciler · XLSX renderer · future
API surfaces).

Deterministic: identical input produces byte-identical JSONL.
Rows are sorted by (population, position_id, runner) for stable output.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Iterable, Union

from backend.delivery.canonical.models import (
    CanonicalDecision, CanonicalExit, CanonicalPosition,
)


CanonicalObject = Union[CanonicalPosition, CanonicalDecision, CanonicalExit]


def _out_path(root: Path, market: str, population_kind: str, asof: str) -> Path:
    p = root / "reports" / "canonical" / \
        f"{market.lower()}_{population_kind}_{asof}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _serialize(obj: CanonicalObject) -> dict:
    d = asdict(obj)
    # Enum values → their string form (dataclasses.asdict handles this
    # for Enum children · but be defensive against nested dicts).
    return d


def emit_positions(root: Path, market: str, asof: str,
                    positions: Iterable[CanonicalPosition]) -> Path:
    """Write portfolio-body positions to canonical JSONL."""
    out = _out_path(root, market, "portfolio", asof)
    rows = sorted(positions, key=lambda p: (
        p.population.value if hasattr(p.population, "value") else str(p.population),
        p.position_id, p.runner))
    with out.open("w", encoding="utf-8") as f:
        for p in rows:
            f.write(json.dumps(_serialize(p), ensure_ascii=False,
                                sort_keys=True, default=str) + "\n")
    return out


def emit_decisions(root: Path, market: str, asof: str,
                    decisions: Iterable[CanonicalDecision]) -> Path:
    """Write today's decisions to canonical JSONL."""
    out = _out_path(root, market, "today_decisions", asof)
    rows = sorted(decisions, key=lambda d: (d.position_id, d.runner))
    with out.open("w", encoding="utf-8") as f:
        for d in rows:
            f.write(json.dumps(_serialize(d), ensure_ascii=False,
                                sort_keys=True, default=str) + "\n")
    return out


def emit_exits(root: Path, market: str, asof: str,
                exits: Iterable[CanonicalExit]) -> Path:
    """Write 90d exit history to canonical JSONL."""
    out = _out_path(root, market, "exit_history_90d", asof)
    rows = sorted(exits, key=lambda e: (e.exit_date, e.position_id, e.runner))
    with out.open("w", encoding="utf-8") as f:
        for e in rows:
            f.write(json.dumps(_serialize(e), ensure_ascii=False,
                                sort_keys=True, default=str) + "\n")
    return out
