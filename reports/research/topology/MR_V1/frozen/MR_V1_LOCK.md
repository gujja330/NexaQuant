# MR_V1_LOCK · Research Engine Lock

**Locked date:** 2026-08-27
**Lock scope:** Sprint M-R · Forward Validation Engine v1
**Sentinel:** `MR_V1_LOCK.v1.0`

---

## What this document locks

**The research/measurement FOUNDATION is locked.**
**The research CONCLUSIONS are NOT locked.**
**No production layer is affected by this lock.**

This is the mirror of `PRODUCTION_LOCK.md` for the research side. The
research engine can now be trusted to produce reproducible, sandbox-safe
evidence. Its conclusions still require walk-forward validation before
they can influence any production decision.

## LOCKED · will not be modified without an explicit "override the mr v1 lock" phrase

### Measurement layer (frozen)

- `backend/research/mr_runner.py` · sandbox host
- `backend/research/mr_prediction_autopsy.py` · historical ingest + fwd 1/3/5/10/20D + MFE/MAE + stop-hit + WIN/LOSS
- `backend/research/mr_feature_enricher.py` · RSI/MA-dist/vol/momentum/cap frozen at prediction time (no look-ahead)
- `backend/research/mr_market_regime.py` · daily index regime tag
- `backend/research/mr_winner_loser_genome.py` · winner vs loser attribution
- `backend/research/mr_studies.py` · sector + cap + technicals + fundamentals + regime + rank slot cohorts
- `backend/research/mr_stop_loss_sweep.py` · 12 stop policy replay
- `backend/research/mr_missed_winners.py` · false-negative discovery
- `backend/research/mr_feature_ranking.py` · per-feature WR-spread scoreboard
- `backend/research/mr_leakage_audit.py` · A2-A8 data-quality checks
- `backend/research/mr_loss_prevention.py` · per-loss avoidability classifier
- `backend/research/mr_control_cohort.py` · alpha vs universe baseline
- `backend/research/mr_score_usefulness.py` · KEEP/PRUNE score verdict
- `backend/research/mr_hypothesis_ranker.py` · deterministic hypothesis scoring
- `backend/research/mr_walkforward_experiment.py` · experiment spec registry
- `backend/research/mr_walkforward_snapshot.py` · immutable day-N capture
- `backend/research/mr_ai_auditor.py` · deterministic narrative synthesizer (no LLM agent)
- `backend/research/mr_research_ticket.py` · DRAFT-ticket generator
- `backend/research/mr_master_report.py` · 14-item consolidated report
- `backend/research/mr_forward_validation_report.py` · 18-section CEO report
- `backend/research/mr_ceo_dashboard.py` · single-page reference
- `backend/research/mr_v1_pipeline.py` · single entrypoint · 20 stages

### Contract layer (frozen)

- `ALLOWED_WRITE_ROOT = reports/research`
- Every M-R module writes ONLY under `reports/research/`
- No M-R module writes to `backend/delivery/`, `configs/ensemble_weights_adaptive.yaml`, `model_registry.jsonl`, `scripts/telegram_command_center_send.py` canonical emit, `reports/telegram/`, R1, R2, Registry
- `EXPERIMENT_ID = "M-R.v0.1"` stamped on every artifact
- Deterministic ordering · same inputs → same outputs
- No use of `Date.now()` / `Math.random()` / non-deterministic RNG (walk-forward would break)

### Statistical discipline (frozen)

- n < 20  = OBSERVATION_ONLY
- n < 100 = INSUFFICIENT_EVIDENCE
- n ≥ 100 = PRODUCTION_CANDIDATE
- Wilson-95 CI on every WR
- No production promotion below n = 100

### Test suite (frozen)

- `tests/research/test_mr_no_lookahead.py` · property tests · past slice invariant under future tampering
- `tests/research/test_mr_sandbox_isolation.py` · no locked-path writes
- `tests/research/test_mr_stop_loss_sweep.py` · simulator property
- `tests/research/test_mr_feature_ranking.py` · scoring property
- `tests/research/test_mr_loss_prevention.py` · classifier property
- `tests/research/test_mr_score_usefulness.py` · verdict property
- `tests/research/test_mr_hypothesis_ranker.py` · ranker property
- `tests/research/test_mr_dataset_regression.py` · 14 dataset-coherence checks
- **181/181 pass at lock time**

---

## NOT LOCKED · still open to iteration

### Research conclusions
- 5 DRAFT tickets in `reports/research/tickets/` are HYPOTHESES only
- 5 registered walk-forward experiments in `reports/research/experiments/` are `NOT_STARTED`
- 9 AI Auditor findings in `mr_ai_auditor_findings.jsonl` are CLAIMS with CAVEATS
- None of these have been validated on out-of-sample data yet

### Forward-capture corpus
- `reports/research/walkforward/{date}/` grows daily from today
- Momentum snapshots start today (n=0 in history)
- After ≥ 20 trading days · first walk-forward experiment can conclude

### Data gaps still to close
- Momentum historical corpus (n=0 · start today)
- USA investability shadow file (94% PENDING band)
- Fundamentals parquet coverage (India 228 tickers only)
- USA canonical portfolio JSON (CI-generated · not yet local)

---

## Explicitly NOT LOCKED · production layer

Zero changes to any of the following ever result from this lock:

- R1 recommendation runner
- R2 recommendation runner
- Registry (position lifecycle)
- `backend/delivery/xlsx_contract.py`
- `backend/delivery/xlsx_validator.py`
- `scripts/telegram_command_center_send.py` canonical INVESTMENT_ACTIVE JSON emit
- `configs/ensemble_weights_adaptive.yaml`
- `model_registry.jsonl`
- `reports/telegram/aegis_history*.xlsx`
- Telegram delivery
- I1-I30 XLSX validator invariants
- Position ID lifecycle (NEW → ACTIVE → ACTIVE+ → EXIT)

These remain governed by `PRODUCTION_LOCK.md`. This document does NOT extend them.

---

## Unlock phrase

To modify anything in the LOCKED list above, the operator must say **verbatim**:

> **"override the mr v1 lock"**

Any other phrasing does NOT unlock. This mirrors the existing production
lock convention.

---

## The 7-step promotion gate remains in force

To promote any research conclusion to production:

1. Research Ticket accepted by CEO
2. Walk-forward test on N ≥ 100 forward predictions
3. Full regression pass on locked delivery invariants (BLOCK == 0)
4. CEO explicit approval + lock-override phrase
5. Config-toggle OFF by default in a new SPRINT_ID branch
6. Paper-trading period ≥ 30 sessions with green metrics
7. Production promotion under new SPRINT_ID with L4 evidence

**No shortcut. No exception. No auto-promotion.**

---

## What operators can do without the unlock phrase

- Run `python -m backend.research.mr_v1_pipeline --market both` daily
- Run `python -m backend.research.mr_walkforward_snapshot --snapshot` daily
- Read every report under `reports/research/`
- Discuss and rank tickets
- Fix bugs in a research module (bug fixes preserve behavior · not features)
- Add NEW research modules under `backend/research/` (additions do not modify locked modules)

## What operators cannot do without the unlock phrase

- Modify any file in the LOCKED list above
- Change `ALLOWED_WRITE_ROOT`
- Reduce statistical discipline thresholds
- Auto-promote a ticket to production
- Skip any of the 7 gate steps
- Weaken any of the 14 dataset-regression tests
- Add write paths outside `reports/research/`

---

## Sign-off

- Foundation locked: **YES**
- Conclusions locked: **NO**
- Production changes: **ZERO**
- Path forward: **M2 · Automated walk-forward · Momentum capture · Conditional cohorts**
