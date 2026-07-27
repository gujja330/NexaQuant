"""backend.benchmark_analytics — Institutional performance analytics.

Enterprise Completion Program · Phase K.

Computes: Alpha · Beta · Sharpe · Sortino · Information Ratio · Hit Ratio ·
Max Drawdown · Sector Alpha · Rotation Alpha · Recommendation Precision · Recall.

Deterministic · walk-forward safe · consumes closed-trade / return series.
"""
from __future__ import annotations

from backend.benchmark_analytics.engine import (  # noqa: F401
    BenchmarkAnalytics,
    PerformanceMetrics,
    compute_metrics,
    SCHEMA_FINGERPRINT, SCHEMA_VERSION, ENGINE_ID,
)

__version__ = "1.0.0"
