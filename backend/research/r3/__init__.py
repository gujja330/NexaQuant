"""R3 · Aggressive / Innovative Research Challenger
Sprint A · CEO 2026-09-03

Fully isolated per Part 0 contract:
  - Reads: fundamentals feature store, signal ledger, PIT universe, KG PIT snapshots
  - Writes: reports/research/r3/ ONLY · never Registry / Portfolio / production paths
  - Model artifacts: configs/r3_*.yaml + reports/research/r3/models/

Tier 1 = GBM baseline + Platt calibration on the shared 19-signal
fundamentals feature store + existing daily technical features. Must
replicate the R2 baseline before adding any new features (baseline-replicate
gate).

Everything under this package MUST satisfy tests/isolation/test_r3_no_production_writes.py.
"""
