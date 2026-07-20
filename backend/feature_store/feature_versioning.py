"""Feature Store schema versioning.

`schema_fingerprint()` returns a stable 12-char hex digest of the current
FEATURE_REGISTRY — bumps whenever a feature is added, removed, or its
dtype/category changes. Stored in every snapshot's manifest so consumers
can detect drift.

`SCHEMA_VERSION` is the semantic version; bump manually when the shape
changes in a way that breaks downstream engines.
"""
from __future__ import annotations

import hashlib

from backend.feature_store.feature_registry import FEATURE_REGISTRY

SCHEMA_VERSION = "1.0.0"


def schema_fingerprint() -> str:
    """Order-sensitive hash of the current registry — same set of features
    in the same order yields the same fingerprint."""
    parts = []
    for f in FEATURE_REGISTRY:
        parts.append(f"{f.name}:{f.category.value}:{f.dtype}:{int(f.nullable)}")
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def schema_summary() -> dict:
    return {
        "version":     SCHEMA_VERSION,
        "fingerprint": schema_fingerprint(),
        "n_features":  len(FEATURE_REGISTRY),
        "categories":  sorted({f.category.value for f in FEATURE_REGISTRY}),
    }
