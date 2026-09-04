# AEGIS Cross-Cutting Evidence Engine · Design Document

**Locked:** 2026-09-05 by CEO
**Status:** RESEARCH INFRASTRUCTURE ONLY · additive extension · does NOT modify R2 production behavior
**Reference:** AEGIS Master Document v2 · walk-forward 252/5/63/21 + paired bootstrap 10k + DSR/Reality Check + forward paper/shadow

---

## Purpose

One reusable evidence-collection and validation engine that can evaluate any AEGIS research item through **three independent evidence clocks**:

1. **Retrospective PIT / Historical** · walk-forward OOS on historical data
2. **Walk-Forward Out-of-Sample** · locked 252/5/63/21 protocol per PDF
3. **Forward Paper / Shadow / Realized** · frozen candidate against R2 + standing comparator

**Not a new alpha strategy.** Common research infrastructure that every existing R2/R3/F0X research item feeds into.

---

## Non-Goals (explicit)

- Does NOT resume P3
- Does NOT resume R3 Tier 2/3
- Does NOT promote any strategy
- Does NOT modify R2 production paths
- Does NOT lower any sample-size or statistical gate
- Does NOT create a competing state machine (13-stage Coverage Tracker stays sole SoT for governance)
- Does NOT change how confidence is delivered in the workbook

---

## Architecture

```
                     AEGIS EVIDENCE ENGINE
                             │
              ┌──────────────┼──────────────┐
              ↓              ↓              ↓
         RETROSPECTIVE    WALK-FWD       FORWARD
           PIT/OOS          OOS         PAPER/REAL
              │              │              │
              └──────────────┼──────────────┘
                             ↓
                     STATISTICAL GATE
                        (bootstrap + LR)
                             ↓
                     MULTIPLE-TESTING
                       (DSR / Reality Check)
                             ↓
                       EVIDENCE LOG
                    (immutable append-only)
                             ↓
                      13-STAGE TRACKER
                    (canonical governance SoT)
```

---

## Module Layout

```
backend/research/evidence/
  __init__.py
  walk_forward.py            # Section A · 252/5/63/21 fold generator + leakage guards
  statistical_gates.py       # Section C · paired bootstrap · LR · DSR wrappers
  evidence_clock.py          # Section G · 6-state evidence clock (measurement layer)
  evidence_log.py            # Section M · immutable append-only run log
  forward_paper.py           # Section D · candidate freeze + daily ledger
  three_way_comparator.py    # Section E · candidate vs R2 vs standing comparator
  engine.py                  # top-level orchestrator · runs all three clocks

scripts/
  evidence_engine_daily.py   # Section N · daily runner
  evidence_engine_weekly.py  # Section N · weekly regenerator

tests/research/
  test_evidence_engine.py    # Section O · leakage/embargo/dedupe/immutability tests
```

---

## Section A · Walk-Forward Protocol (LOCKED per PDF)

```
TRAIN   = 252 trading days
EMBARGO = 5   trading days   (prevents forward-outcome leakage across boundary)
OOS     = 63  trading days   (untouched · never looked at during fit)
STEP    = 21  trading days   (advance one month between folds)
```

Rules mechanically enforced by the fold generator:
- no random train/test split
- no OOS fitting
- no OOS threshold selection
- no hindsight parameter selection
- no feature leakage
- no future universe membership
- no future fundamental revision
- no future KG community assignment

Every fold persists to `reports/research/evidence/<ITEM_ID>/walk_forward/`:
```
fold_manifest.json      # (train_start, train_end, embargo, oos_start, oos_end)
predictions.parquet     # OOS predictions only
outcomes.parquet        # matured OOS returns
metrics.json            # per-fold metrics + aggregated
oos_report.md           # human-readable summary
leakage_audit.json      # zero-leakage assertions passed
```

## Section B · Metrics (uniform)

Per candidate: `n · mean · median · hit_rate · expectancy · Sharpe · Sortino · max_dd · profit_factor · turnover · exposure · concentration · MAE · MFE · winner_capture · loser_creation · winner_sacrifice · recovered_winner_sacrifice` plus `market/regime/sector/cap/calendar` splits. Never a single aggregate without underlying sample.

## Section C · Statistical Gates

| Test | Use case | Corrections |
|---|---|---|
| Paired bootstrap (10k) | Compare two strategies on same positions | none · empirical CI |
| Likelihood-ratio test | Nested Cap vs Cap+Sector | chi-squared p |
| Deflated Sharpe / Reality Check | Multiple variants of same family | trial-count correction |

Every experiment records `experiment_family_id · trial_count · parameter_variants · correction_method · corrected_result`. **No hidden trial counts.**

## Section D · Forward Paper / Shadow Engine

For every candidate that clears its historical/OOS gate: **FREEZE THE CANDIDATE**. Daily ledger records candidate signal + R2 production signal + standing comparator signal, with unresolved observations retained until 5d/10d/20d/60d maturity.

Persisted to `reports/research/forward_validation/<ITEM_ID>/`:
```
daily_ledger.jsonl
realized_outcomes.parquet
forward_dashboard.json
forward_report.md
```

## Section E · Three-Way Comparison

Report `candidate − R2 · candidate − comparator · R2 − comparator` (never candidate-only against itself). Metrics: `n · mean_delta · median_delta · bootstrap_CI · p_value · Sharpe_delta · drawdown_delta · turnover_delta · exposure_delta`.

## Section F · Fundamentals F01-F05

Same engine · each signal tested individually first · combinations only after per-signal attribution. For each signal record `PIT availability · earliest_asof · latest_asof · unique_dates · unique_tickers · usable_obs · missingness · revision_timing · sector_cap_coverage`.

## Section G · Evidence Clock (measurement layer · NOT governance)

Six states · distinguished mechanically · NOT collapsed:

```
DATA_EXISTS  →  DATA_USABLE  →  HISTORICAL_TESTED  →  OOS_TESTED
                    ↓                                       ↓
              FORWARD_RUNNING  ← ← ← ← ← ← ← ← ← ← ← ← ← ←
                    ↓
              FORWARD_VALIDATED
```

**The 13-stage Coverage Tracker remains the canonical governance state machine.** This clock is a per-item evidence-measurement layer only. Two views · one truth.

## Section H · Sample-Size Governance

Locked thresholds preserved:
- `<5` OBSERVATION
- `5-14` HYPOTHESIS
- `15-29` RESEARCH SIGNAL
- `30-49` STRONGER EVIDENCE
- `50+` VALIDATION CANDIDATE

Insufficient sample → `INSUFFICIENT_SAMPLE` (not FAIL). Missing substrate → `BLOCKED` (not FAIL).

## Section I · Decision Output

Exactly one of: `PASS · FAIL · BLOCKED · INSUFFICIENT_SAMPLE · RESEARCH_FURTHER`.

`validated` only when · PIT clean + walk-forward OOS complete + statistical gate passed + multiple-testing correction applied + forward evidence satisfied.

## Section J · Missed-Winner / Negative Control

Every candidate reports · missed_winners · losers_created · winners_sacrificed · recovered_winners_sacrificed · MFE_forfeited · loss_reduction · drawdown · turnover · concentration. Joined with POS-PNL-CAPTURE-60D and NEG-PNL-CONTROL-60D where Position IDs permit.

## Section K · R3 Isolation

Engine READS R3 shadow artifacts. Never writes R2 production paths · never modifies R2 ensemble weights · never modifies R2 Registry · never writes delivered production workbook · never shares model artifacts. R3 Day-30/60/90 gates unchanged.

## Section L · P1/P3/P4/P5 Governance

Engine reports `READY_FOR_RESEARCH` when substrate + evidence requirements are satisfied. Does NOT automatically reopen blocked items. Substrate-before-sophistication rule preserved.

## Section M · Immutable Evidence Log

Every run appends one record (never overwrites):
```
timestamp · git_commit · item_id · experiment_id · market · data_snapshot
PIT_status · fold_definition · trial_count · parameters · sample_size · metrics
statistical_test · multiple_testing_correction · decision · artifact_paths
```

Reruns get new `experiment_id`. Path: `reports/research/evidence/evidence_log.jsonl` (append-only).

## Section N · Daily Operation

Daily workflow adds:
1. accumulate PIT fundamentals (already wired)
2. accumulate signal ledger
3. accumulate forward candidate observations
4. mature 5/10/20/60-day outcomes
5. update forward dashboards
6. update evidence clocks
7. run integrity checks
8. **never modify production**

Weekly regenerates evidence summaries · calculates forward deltas · flags newly eligible items.

## Section O · Required Tests

Mechanical validators covering: PIT leakage · future-universe leakage · OOS contamination · embargo correctness · fold chronology · no random split · trial accounting · bootstrap reproducibility · forward outcome maturity · Position ID uniqueness · candidate freeze · no forward retuning · R3 isolation · R2 production immutability · Evidence Log append-only · India/USA separation · deduplication · missing-data handling · evidence-clock correctness.

## Section P · Deliverables

1. this design document ✓
2. evidence engine (`backend/research/evidence/`)
3. historical/OOS runner (`engine.py`)
4. forward-validation runner (`forward_paper.py`)
5. evidence clock (`evidence_clock.py`)
6. immutable Evidence Log (`evidence_log.py`)
7. trial matrix integration (via `statistical_gates.py`)
8. fundamentals integration F01-F05 (Section F)
9. forward dashboard (weekly script)
10. missed-winner report (Section J)
11. positive-vs-negative joint report (Section J)
12. tests (`tests/research/test_evidence_engine.py`)
13. documentation (this doc)
14. regenerated scorecard

## Ship discipline

- Implementation complete
- Documentation complete
- Artifacts generated
- Mechanical validators pass
- Targeted regression passes
- Scorecard reconciles mechanically
- Git diff reviewed · no unintended production-path changes
- Final evidence report generated

**THEN STOP AND REPORT · DO NOT PUSH AUTOMATICALLY.**
