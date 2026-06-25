# india/evidence/ — Conclusions, not active work

These scripts are AEGIS's **evidence trail**, not an active research backlog. Each one is a
*concluded experiment* — it exists so that "why not X?" is answered with a runnable proof instead
of being rediscovered two years later.

They answer, with code:
- **Why not return prediction / XGBoost / LSTM / Transformers / GNN / RL?** → AUC ~0.50 (coin flip)
  on public data (`ml_full.py`, `dl_test.py`, `rl_test.py`, `gnn_test.py`, `can_ai_predict.py`).
- **Why not per-stock timing?** → destroys returns (`per_stock_timing.py`).
- **Why not recovery / anti-fragility / persistence ranking?** → just re-derives low-vol
  (`resilience_ranking.py`).
- **Why HRP + regime, quarterly, sector≤2?** → the validation/diagnostic suite
  (`validation_sprint.py`, `diagnostics.py`, `monte_carlo.py`, `risk_analytics.py`, the grids).

Policy: these stay frozen as the record. NEW experiments (only when a data trigger fires — see
`docs/AEGIS_V4_ROADMAP.md`) start fresh in a new `india/lab/`, gated by the reopen protocol.
Do not re-run these expecting a different answer; the answer is the point.
