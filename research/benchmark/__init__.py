"""Continuous Benchmark v1.0.

Compares every recommendation's realised return against a market
benchmark (NIFTY 50) and a synthetic sector-peer benchmark. Reports
per-trade excess alpha, per-ticker averages, portfolio-level
aggregates, and per-sector aggregates.

Post-LOCK addition (2026-07-18). Not a new engine — a comparison
layer on top of learning.parquet + NSEI price series.
"""
