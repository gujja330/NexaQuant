"""backend.feature_monitor — Feature freshness / lineage / usage audit.

Enterprise Completion Program · Phase B.

Scans data/raw/ + reports/ for freshness · counts consumers per artifact ·
flags datasets that are collected but never consumed.
"""
from __future__ import annotations

from backend.feature_monitor.monitor import (  # noqa: F401
    FeatureMonitor,
    FreshnessReport,
    scan_freshness,
    SCHEMA_FINGERPRINT, SCHEMA_VERSION, ENGINE_ID,
)

__version__ = "1.0.0"
