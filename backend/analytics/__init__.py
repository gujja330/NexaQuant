"""AEGIS analytics · trust-surface modules.

v2.4 shift: from "build features" to "institutionalize + prove outcomes".
Each module here READS existing data (learning.parquet, snapshot_store,
position_store, ensemble.json) and produces operator-visible trust
surfaces. No new analytics engines. No new recommendations.

Modules:
  backtrack   — per-ticker timeline across snapshot history
  scorecard   — 6-metric star rating computed from learning.parquet
  attribution — per-model contribution decomposition per rec
"""
