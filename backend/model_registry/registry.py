"""Model Registry — every model version stamped, versioned, approval-gated.

Storage: `model_registry.jsonl` at repo root (append-only ledger). Each
downstream engine calls `stamp(model_id, ...)` when emitting a decision;
the stamp is embedded in the engine's output so consumers can verify
which model + features + approval were in effect.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path


REGISTRY_PATH = "model_registry.jsonl"


class ModelStatus(str, Enum):
    EXPERIMENTAL = "experimental"
    APPROVED     = "approved"          # promotion gate cleared
    DEPRECATED   = "deprecated"


@dataclass
class ModelRecord:
    model_id:              str            # e.g. "aegis.recommendation.v3"
    version:               str            # semantic
    engine:                str            # "recommendation" | "risk" | "portfolio" | ...
    market:                str            # "india" | "usa" | "shared"
    feature_set_version:   str            # from feature_intelligence selection output
    schema_version:        str            # feature store schema fingerprint
    calibration_version:   str = ""
    walk_forward_metrics:  dict = field(default_factory=dict)
    approval_status:       ModelStatus = ModelStatus.EXPERIMENTAL
    approved_by:           str = ""
    approved_on:           str = ""       # ISO date
    created_on:            str = ""
    notes:                 str = ""


# ── In-memory registry (loaded from disk on demand) ─────────────
_MEMORY: dict[str, ModelRecord] = {}


def _load(repo_root: Path) -> None:
    """Load the registry file into _MEMORY."""
    p = Path(repo_root) / REGISTRY_PATH
    _MEMORY.clear()
    if not p.exists(): return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        try:
            row["approval_status"] = ModelStatus(row.get("approval_status", "experimental"))
        except Exception:
            row["approval_status"] = ModelStatus.EXPERIMENTAL
        rec = ModelRecord(**row)
        _MEMORY[rec.model_id] = rec        # last-write-wins (per model_id)


def register_model(repo_root: Path, model_id: str, engine: str, market: str,
                    version: str, feature_set_version: str, schema_version: str,
                    calibration_version: str = "",
                    walk_forward_metrics: dict | None = None,
                    approval_status: ModelStatus = ModelStatus.EXPERIMENTAL,
                    approved_by: str = "", approved_on: str = "",
                    notes: str = "") -> ModelRecord:
    """Add or update a model record. Enforces: PRODUCTION requires approval."""
    _load(repo_root)
    rec = ModelRecord(
        model_id=model_id, engine=engine, market=market, version=version,
        feature_set_version=feature_set_version, schema_version=schema_version,
        calibration_version=calibration_version,
        walk_forward_metrics=walk_forward_metrics or {},
        approval_status=approval_status,
        approved_by=approved_by, approved_on=approved_on,
        created_on=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        notes=notes,
    )
    _MEMORY[model_id] = rec

    row = asdict(rec)
    row["approval_status"] = rec.approval_status.value
    p = Path(repo_root) / REGISTRY_PATH
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return rec


def get_model(repo_root: Path, model_id: str) -> ModelRecord | None:
    _load(repo_root)
    return _MEMORY.get(model_id)


def list_models(repo_root: Path, market: str | None = None,
                  engine: str | None = None,
                  status: ModelStatus | None = None) -> list[ModelRecord]:
    _load(repo_root)
    out = []
    for r in _MEMORY.values():
        if market and r.market != market and r.market != "shared": continue
        if engine and r.engine != engine: continue
        if status and r.approval_status != status: continue
        out.append(r)
    return sorted(out, key=lambda r: (r.engine, r.market, r.version))


def stamp(repo_root: Path, model_id: str) -> dict:
    """Return a stamp dict that a downstream engine embeds in its output.

    Downstream engines emit e.g.:
        json.dump({..., "model_stamp": stamp(root, "aegis.recommendation.v3")}, ...)
    """
    rec = get_model(repo_root, model_id)
    if rec is None:
        return {"model_id": model_id, "status": "UNREGISTERED",
                "warning": "engine emitted a decision without registering a model"}
    return {
        "model_id":            rec.model_id,
        "version":             rec.version,
        "engine":              rec.engine,
        "market":              rec.market,
        "feature_set_version": rec.feature_set_version,
        "schema_version":      rec.schema_version,
        "calibration_version": rec.calibration_version,
        "approval_status":     rec.approval_status.value,
        "approved_by":         rec.approved_by,
        "approved_on":         rec.approved_on,
    }
