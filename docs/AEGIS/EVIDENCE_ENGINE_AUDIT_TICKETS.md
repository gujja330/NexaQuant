# Evidence Engine · Remaining Audit Tickets

**Filed:** 2026-09-05 by CEO
**Classification:** Follow-up work · NOT this session
**Precondition to close:** Each ticket needs its own STP-passing evidence + tests before promotion to "closed"

CEO 2026-09-05 correctly classified prior commits `9da28e2e` + `f2bfce4a` as **Evidence Engine v1 infrastructure + blocker discovery**, NOT closure. The following gaps remain before verdicts from this engine can be trusted.

---

## AUDIT-01 · Exchange-aware trading-day handling

**Issue:** `backend/research/evidence/walk_forward.py:_add_trading_days` uses `weekday() < 5` only · treats Mon-Fri as trading days regardless of exchange holidays. India NSE observes ~15 trading holidays/year (Republic Day, Independence Day, Diwali, etc.); USA NYSE observes ~10 (New Year, MLK, July 4, etc.). Over 252-day training windows the drift compounds · walk-forward boundaries could straddle a real holiday cluster.

**Impact:** Embargo could be 5 weekdays but only 3-4 actual trading days.

**Fix:** Import a per-market trading calendar (pandas_market_calendars or a static holiday YAML) · replace `_add_trading_days` with `_add_trading_days(d, n, market)`.

**Effort:** Small · one function + one config file per market.

---

## AUDIT-02 · Fold-outcome attribution is top-decile return, not candidate-vs-baseline

**Issue:** `scripts/evidence_engine_run_f01_f05.py` currently measures "mean forward-20d return of top-decile by signal". That's a decile-lift test, NOT the candidate-vs-R2-vs-standing-comparator attribution CEO's Section E requires. The comparator infrastructure (`three_way_comparator.py`) exists but isn't invoked yet.

**Impact:** Verdicts of PASS/FAIL from the engine measure "does the signal rank forward returns?" — a weaker question than "does it beat R2's ensemble?"

**Fix:** Wire the top-decile stocks into candidate paired lists · pull R2 recommendation history for the same asof/ticker pairs · pull standing comparator (equal-weight top-10 by 3-month momentum from P5.5) · then call `three_way_compare()`. Report `candidate − R2` as the primary decision metric.

**Effort:** Medium · needs P5.5 standing comparator implementation first (currently PENDING in registry).

---

## AUDIT-03 · Statistical gate simpler than full PDF protocol

**Issue:** Current gate = "positive mean + DSR p<0.10". PDF protocol requires:
- Paired bootstrap 10k (implemented in `paired_bootstrap`)
- Likelihood-ratio test for nested models (implemented but not wired)
- Deflated Sharpe / Reality Check (wrapper works)
- Multiple-testing correction across experiment family (not enforced yet)
- Reliability diagram + ECE for calibration items (P1 has it separately)

**Impact:** A pass can slip through if the item is one of many trials tested but the trial-count wasn't declared.

**Fix:** Add an `experiment_family` registry that records every variant tested for a candidate (α values, β values, threshold sweeps) · engine must consume this and pass `n_trials=<family_size>` to DSR · not `n_trials=1`.

**Effort:** Medium · trial-accounting matrix exists (`configs/outcome_dataset_schema.yaml trial_accounting`) · needs wiring.

---

## AUDIT-04 · No genuine frozen forward candidate running yet

**Issue:** `forward_paper.py` has `freeze_candidate()`, `append_daily_observation()`, `mature_outcomes()`. But no candidate has actually been frozen and no daily ledger is being written. The forward-validation directory tree exists in code but is empty on disk.

**Impact:** "Forward evidence" claims in the engine's verdict would be vacuous today.

**Fix:** Once any candidate clears backward+OOS, wire it into a daily cron that appends to `daily_ledger.jsonl`. But per substrate-before-sophistication, NO candidate is currently eligible · F01-F05 must reach `Tested` first. So this audit item is BLOCKED on substrate maturity · will unblock automatically as accumulator advances.

**Effort:** Small once eligible · but zero work until substrate matures.

---

## AUDIT-05 · "30 dates" is stronger-evidence tier, not validation

**Issue:** Engine currently reports PASS when OOS n≥30. Locked sample tiers say n≥50 is validation-candidate.

**Impact:** An item with 30 OOS samples could be reported as PASS · but per governance it's only stronger-evidence tier, not validation-worthy.

**Fix:** Two-level gate in `engine.py`:
- n≥30: eligible for `RESEARCH_FURTHER` verdict
- n≥50 + statistical gate passed: eligible for `PASS` verdict
Anything below 30 stays `INSUFFICIENT_SAMPLE` as it does today.

**Effort:** Small · one-line branch.

---

## AUDIT-06 · Universe drift audit not yet wired

**Issue:** V2 §P5.4 PIT universe audit is separately implemented but the walk-forward folds don't currently verify universe membership at each fold's start-date. A ticker delisted mid-fold could still contribute a signal.

**Impact:** Minor for F01-F05 (fundamentals are ticker-stable) · larger for D06 sector-rotation candidates.

**Fix:** Add optional `universe_at_date(asof) -> list[ticker]` argument to `run_historical_evidence` · filter signal_scores/outcomes to only eligible tickers per fold.

**Effort:** Small.

---

## Resolution discipline

Each audit ticket must be closed by:
1. Concrete code fix
2. New mechanical validator in `tests/research/test_evidence_engine.py`
3. Re-execution of the F01-F05 evidence program after fix
4. Immutable Evidence Log entry for the re-run
5. Registry `EVIDENCE-ENGINE` item's `next_stp_action` updated

None of these six tickets is a research task · they are engineering-hardening tasks that must precede treating engine verdicts as trustable.

## Blocking status

- AUDIT-01, AUDIT-03, AUDIT-05, AUDIT-06 · unblocked · can start any time
- AUDIT-02 · blocked on P5.5 standing comparator (registry PENDING)
- AUDIT-04 · blocked on F01-F05 substrate maturity (per substrate-before-sophistication rule)

Nothing here reopens P3 · nothing modifies R2 · nothing lowers a gate.
