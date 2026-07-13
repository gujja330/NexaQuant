# LAB006 — Cumulative Trial Manifest

Every Lab experiment updates this file BEFORE reporting metrics. DSR `n_trials` is derived from
`strategy_search_count` below, not hardcoded per-experiment. Multi-testing inflation must reflect
the FULL search that produced the reported best.

**Counting rule** (Bailey-López de Prado convention):
- **Strategy-search trials** = distinct hypothesis × parameter × policy combinations tested for their
  effect on portfolio outcomes. These INFLATE the DSR expected max-Sharpe threshold.
- **Cost-sensitivity variants** = the SAME strategy under different friction assumptions. These are
  robustness stress tests, NOT search trials. They do NOT inflate DSR.
- **Baseline runs** count once (used to normalize against).

## Ledger

| Rule | Date | Configs tested | Category | Count | Notes |
|---|---|---|---|---|---|
| Baseline (hold-to-mature) | 2026-07-13 | 1 | reference | 1 | Not counted in DSR n_trials |
| Rule B (vol-spike) | 2026-07-13 | k ∈ {1.6, 1.8, 2.0, 2.5, 3.0} × {P1, P2, P3} | strategy-search | 15 | all rejected |
| Rule C (trailing stop) — provisional | 2026-07-13 | stop ∈ {5, 8, 10, 12}% × {P1, P2, P3} | strategy-search | 12 | provisional; scaffold-buggy |
| Rule C cost sensitivity — provisional | 2026-07-13 | top-3 configs × {30, 50} bps | cost-stress | 0 (not counted) | robustness stress test |
| Rule C — audit-closure rerun | (pending) | 12 same configs, fixed scaffold | strategy-search-rerun | 0 (SAME configs, not new search) | Rerun of already-counted configs |
| Rule C1 (regime-gated 5% P3 Weak) | 2026-07-13 | 1 (pre-registered, executed once) | strategy-search | 1 | **REJECTED** — 2 of 6 gates pass. See `reports/rule_C1_regime_gated_2026-07-13.md` |
| Rule C1 cost stress | 2026-07-13 | 1 config × {30, 50} bps | cost-stress | 0 (not counted) | 50bps also fails full-period gate |
| Rule D (sentiment) | (pending) | TBD after news_sentiment.py archive audit | (pending) | TBD | Next |

## Cumulative counts (as of 2026-07-13)

- **strategy_search_count (before C1 run)**: **28** (15 Rule B + 12 provisional Rule C + 1 pre-registered C1 hypothesis frozen but not yet tested)

  Wait — C1 is 1 additional strategy-search trial (a new hypothesis), so:
- **strategy_search_count (including C1 evaluation)**: **29** — use this for C1's DSR
- **cost_stress_variants (all-time)**: 6 provisional Rule C + 6 Rule C audit-closure + up to 2 C1 = up to 14 (NOT counted in DSR)

## DSR usage in downstream code

```python
# Read this file to get the current strategy-search count.
# See india/ai_lab/LAB006_Exit_Strategy/exit_lab.py::dsr_n_trials()
n_trials = 28  # cumulative as of C1 run
dsr = deflated_sharpe(equity_returns, n_trials=n_trials)
```

## Update protocol

1. Every new experiment MUST append its row to this ledger BEFORE reporting.
2. New configurations (parameter or policy changes) → strategy-search count.
3. Cost / friction variations of an already-tested config → cost-stress column, NOT counted.
4. Reruns of the same config (bug fix, scaffold change, re-execution) → NOT counted (marked as "same configs").
5. Retracted evidence (e.g. Rule B PBO) does NOT reduce the trial count — those searches still happened.
