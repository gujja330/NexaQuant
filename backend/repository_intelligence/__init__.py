"""backend.repository_intelligence — automatic dead-code + orphan-artifact detection.

Enterprise Completion Program · Phase L.

Discovers:
    dead modules       (no consumer imports them)
    orphan reports     (produced but never consumed)
    stale artifacts    (mtime > threshold)
    duplicate configs  (same content, different paths)
    unused workflows   (never triggered)

Read-only · does NOT delete. Produces a report for operator review.
"""
from __future__ import annotations

from backend.repository_intelligence.scanner import (  # noqa: F401
    RepositoryScanner,
    RepositoryFinding,
    scan_repository,
    SCHEMA_FINGERPRINT, SCHEMA_VERSION, ENGINE_ID,
)

__version__ = "1.0.0"
