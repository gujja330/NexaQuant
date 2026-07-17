"""DEV026 publish — writes memo/report JSON files."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[3]
PUBLISH_DIR = _ROOT / "reports"


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.integer, np.floating)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    return obj


def write(name: str, payload: dict) -> Path:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
    p = PUBLISH_DIR / name
    with p.open("w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, indent=2, default=str)
    return p
