# AEGIS — Operating Mode (12-month forward paper phase)

**Decision (2026-06-19): stop adding models. Operate. Real forward evidence > more AI.**
AEGIS Core v2.0 is FROZEN (HRP + regime + Global Risk; Sharpe 2.04, maxDD 12.8%, DSR 0.996, PBO 0.00).

## Monthly cycle (1st trading day)
1. Refresh data + news (auto via `AegisDailyPaper` scheduled task / `python india/daily_run.py --pull`).
2. `python india/monthly_snapshot.py`  -> writes `reports/YYYY_MM.md` (stocks, weights, cash, regime,
   news, expected return by hold, reasons). This is the dated recommendation of record.
3. Hold through the month. No daily churn.
4. Month-end: the picks' realized returns accumulate in `output/paper_log.csv` + the report card.

## Cadence
- Data/news: daily (scheduled)  ·  Recommendation + rebalance: monthly  ·  Strategy grid: monthly
  (`python india/research/strategy_grid.py` = living leaderboard)  ·  Validation sprint: semiannual
  ·  Full revalidation (DSR/PBO/purged-CV): yearly.

## Core vs Lab (80/20)
- **Core (`india/`)** — frozen, monthly, real (paper) money. No experiments.
- **Lab (`india/research/`)** — experiments only. Promote to Core ONLY after beating it on
  DSR>0.95 + PBO + cross-period/universe robustness (bull AND bear).

## Parallel research (20% effort, Lab only) — do NOT touch Core during the freeze
Dynamic-N by regime · discrete exposure tiers (0/25/50/75/100) · liquidity filter (ADV>Rs10cr) ·
sector caps (20%) · correlation caps. Promote after 12 months only if they beat Core.

## Frozen until 1 year of forward paper
Foundation models (Chronos/PatchTST/TimesFM) · PPO/RL · GNN · world/multi-agent.
Next real unlock (Phase 3, ~24 mo): point-in-time fundamentals · historical news · analyst revisions.
**Data > models.**
