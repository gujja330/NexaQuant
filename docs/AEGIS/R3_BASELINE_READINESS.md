# R3 BASELINE READINESS

**Phase R3-1 · reconcile what already exists · CEO 2026-09-07**

Mechanical inventory of the R3 implementation against the AEGIS R1/R2/R3
Implementation & Strategy PDF. Every status below was produced by running
the code, not by reading it. No assumptions.

Status vocabulary (as specified):

| Status | Meaning |
|---|---|
| `BUILT` | Code exists |
| `EXECUTABLE` | Runs end-to-end without error |
| `DATA-COMPLETE` | Its inputs are actually populated |
| `EVIDENCE-COMPLETE` | It has produced the evidence it exists to produce |
| `BLOCKED` | Cannot progress without a fix or a decision |

---

## 0 · Headline

R3 is **not** blocked by missing engineering scaffolding, and it is **not**
merely "15 picks short of the Day-30 gate". It is blocked by four
structural defects that make evidence accumulation impossible today:

1. **Two competing R3 implementations** exist with different schemas,
   markets, and dates. Only one is wired into the pipeline, and it is not
   the PDF-aligned one.
2. **Neither shadow ledger can accumulate.** One is excluded from every CI
   commit set; the other is `.gitignore`d.
3. **Tier-1 has 5 usable features, not 24.** The other 19 are 100% null,
   and all 5 survivors are re-scorings of R2's own output — so Tier-1
   currently carries no information independent of R2.
4. **The R2 baseline replication gate FAILS** (gap 0.109 vs tolerance
   0.02), which by the PDF's own rule blocks all Tier-2 work.

Consequently the Day-30 gate has never had a chance to fire. The correct
first sprint is to fix accumulation and the feature baseline — not to
build Tier-2/Tier-3 sophistication.

---

## 1 · Two implementations

| | **Impl A** | **Impl B** |
|---|---|---|
| Path | `backend/recommendation/runner3/` | `backend/research/r3/` |
| Wired into pipeline | **YES** (`runner3_shadow`, India only) | **NO** |
| Producer | `backend/recommendation/runner3/run.py` | `scripts/r3_daily_shadow_feed.py` (orphaned) |
| Ledger | `reports/research/runner3/shadow_ledger.jsonl` | `reports/research/r3/shadow_ledger.jsonl` |
| Ledger tracked in git | yes (but never committed by CI) | **`.gitignore`d** |
| Records | 476 (India) | 15 (USA) |
| Distinct shadow days | **2** (2026-08-05, 2026-09-07) | **1** (2026-09-03) |
| Markets | India only | USA only |
| Model | none — "logging feature snapshots only" | Tier-1 GBM |
| PDF-aligned (Tier-1 GBM + Platt + gates) | no | yes |

The PDF-aligned implementation is the one that is **not** running. The one
that runs daily has never trained a model.

**Decision required (CEO):** which implementation is canonical R3. This
document recommends **Impl B** (`backend/research/r3/`) because it matches
the PDF's Tier-1 architecture and owns the Day-30/60/90 gates, with Impl A
retained only for its risk fields and 3-runner comparator until ported.

---

## 2 · Inventory table

| Area | Question | Status | Evidence |
|---|---|---|---|
| Tier 1 | Executes end-to-end? | `EXECUTABLE` (USA) · `BLOCKED` (India) | USA trains on n=500. India returns `INSUFFICIENT_SAMPLE` at n=24 |
| Features | Actually populated? | **`BLOCKED`** | 5 of 24 declared `FEATURE_COLUMNS` populated. 19 are 100% null in both markets |
| GBM | Training reproducible? | `EXECUTABLE`, **not reproducible** | `random_state=42` is fixed, but the artifact stores only metrics — no serialized model, no calibrator. A prediction cannot be regenerated from the artifact |
| Calibration | Platt actually fitted/evaluated? | **`BLOCKED`** | Docstring claims Platt calibration; the code fits **none**. It computes ECE on raw out-of-fold GBM probabilities. No sigmoid fit, no calibrator persisted |
| Shadow | Daily picks generated? | **`BLOCKED`** | 2 distinct days in 33 calendar days (Impl A); 1 day (Impl B) |
| Ledger | Picks + outcomes persisted? | **`BLOCKED`** | No outcome fields at all in either ledger. No 5d/10d/20d/60d, no MAE/MFE, no realized P&L |
| Comparator | R3 vs R2 compared correctly? | `BUILT` | `three_runner_comparison.py` runs, but compares a model-less feature dump against R2 |
| Attribution | Feature attribution recorded? | `BUILT` (model-level only) | `top_features` in the model artifact. No per-prediction attribution in the ledger |
| Isolation | Can R3 touch production? | `EVIDENCE-COMPLETE` | 34 isolation tests pass. Three required boundaries untested — see §5 |
| PIT | Are historical features PIT? | **`BLOCKED`** | Training uses `KFold(shuffle=True)` on time-ordered data — no walk-forward, no embargo. Feature-store join is a current snapshot, not PIT |

---

## 3 · The feature defect in detail

`FEATURE_COLUMNS` declares 24 features. The trained model used 5.

Two independent causes, both silent:

**(a) Merge-suffix collision.** The outcome dataset *already* contains all
19 fundamental columns. `build_training_frame` merges it with the
fundamentals feature store on `(market, ticker, entry_date↔asof)`, so
pandas suffixes the collisions into `piotroski_f_x` / `piotroski_f_y`.
`FEATURE_COLUMNS` looks for the **unsuffixed** names, so all 19 silently
disappear from `X`. No error, no warning — the model simply trains on
whatever survived.

**(b) The data is null anyway.** All 19 at-entry fundamental columns in the
outcome dataset are **100% null** in both markets (India 0/24 rows, USA
0/500 rows).

**(c) The feature store is not PIT.** Its `asof` range is 2026-09-03..04
while outcome-dataset entry dates are 2026-08-04..06 — **zero key
overlap**. Joining it would attach *today's* fundamentals to an August
entry, which is lookahead. Per the PDF this must resolve to
`NOT_AVAILABLE_AT_ASOF`, never a forward-filled value.

**Consequence.** The 5 surviving features are `entry_signal_score`,
`entry_calibrated_conf`, `entry_regime_adj_conf`, `entry_model_agreement`,
`entry_n_models_scoring` — all derived from R2's own scoring. R3 Tier-1 is
therefore a re-scoring of R2's output with no independent information,
which is the most likely explanation for its measured performance below.

---

## 4 · Measured Tier-1 performance

| Metric | USA | India |
|---|---|---|
| n_train | 500 | 24 → `INSUFFICIENT_SAMPLE` |
| **AUC** | **0.4465** | — |
| Brier | 0.2545 | — |
| ECE | 0.0106 | — |

**AUC 0.4465 is below 0.5 — worse than random.** Brier 0.2545 is worse
than the 0.25 a constant p=0.5 predictor achieves. The good ECE is not
meaningful: a model with no discrimination can still be well calibrated by
predicting the base rate.

### R2 baseline replication gate (Phase R3-3)

```
market            usa
ic_r2             0.00186
ic_r3_proxy       -0.10698
gap               0.10884
tolerance         0.02
gate_pass         FALSE
next_action       Tier-2 features BLOCKED · R3 must first replicate R2 baseline
```

This is the PDF's mandatory pre-Tier-2 gate and it **fails**. Every Tier-2
and Tier-3 ticket is therefore correctly evidence-blocked.

---

## 5 · Isolation contract (Phase R3-0)

**Currently enforced — 34 tests, all passing:**

- `test_r3_never_writes_to_production_paths`
- `test_r3_never_imports_production_modules`
- `test_r3_never_calls_registry_writers`
- `test_r3_runner_registry_status_shadow_only`
- `test_runner3_does_not_touch_forbidden_paths`
- `test_runner3_writes_only_under_allowed_dir`

**The three R3-0 gaps found by this audit — now CLOSED**, enforced by
`tests/isolation/test_r3_contract_r3_0.py` (12 tests):

| Gap | Enforcement now in place |
|---|---|
| Model-artifact namespace isolation | R3 source may not reference R2 model artifacts; R3 outputs must live under an R3 dir; write sites outside the R3 namespace fail. Read-only consumption of R2 outputs stays permitted, as the PDF allows |
| R3 absent from the production XLSX | Word-boundary R3 scan across all five sheets, both markets, plus a check that no R3 sheet enters the delivery contract |
| R3 Position ID namespace (`runner=R3`) | Every ledger record must declare `runner=R3`; R3 IDs may never carry an `-R1-`/`-R2-` token; R3 may never appear in the production Registry |

Total R3 isolation coverage: **46 tests, all passing.**

---

## 6 · Ledger schema vs the required daily shadow record

The PDF/CEO spec requires Signal + Risk + Outcome + Comparator +
Attribution per record.

| Block | Required | Impl A | Impl B |
|---|---|---|---|
| Signal | score, probability, rank, model version, features | partial (no model version) | partial |
| Risk | entry, stop, target, sizing, horizon | **present** | absent |
| Outcome | 5d/10d/20d/60d, P&L, MAE, MFE | **absent** | **absent** |
| Comparator | R2 score, R2 outcome, relative perf, rotation accuracy | absent (separate file) | absent |
| Attribution | top feature contribution, model, regime | absent | absent |
| Identity | Position ID, `runner=R3` | **absent** | **absent** |

No outcome block in either ledger means **no evidence can be computed for
any gate**, regardless of how many days accumulate.

---

## 7 · Why accumulation is impossible today

The wired step reports `SUCCESS` on all 12 recent pipeline runs, yet only
2 distinct shadow days exist. The step genuinely runs and genuinely
appends — to a workspace that is then discarded.

- `.github/workflows/aegis-daily.yml` `git add` sets include
  `reports/research/opportunity_registry.jsonl`, `portfolio_ledger.jsonl`,
  `rotation_ledger.jsonl` — **but no `reports/research/runner3/` or
  `reports/research/r3/` path**. Impl A's ledger is therefore restored to
  its stale committed state on every run.
- `.gitignore:82` contains `reports/research/r3/`, so Impl B's ledger can
  never be committed at all.

This is the same silent-success failure mode found across the delivery
layer this week: a green step that persists nothing.

---

## 8 · Blockers, ranked

| # | Blocker | Blocks | Fix owner | Status |
|---|---|---|---|---|
| B1 | Two competing implementations; canonical one not wired | everything | **CEO decision** | OPEN |
| B2 | Neither ledger persists across runs (CI commit set + `.gitignore`) | all evidence accumulation | engineering | OPEN |
| B3 | No outcome block in the ledger | Day-30/60/90 gates | engineering | OPEN |
| B4 | 19/24 features null + merge-suffix collision | Tier-1 baseline quality | engineering + data | OPEN |
| B5 | Platt calibration documented but not implemented | calibration evidence | engineering | OPEN |
| B6 | `KFold(shuffle=True)` on time-ordered data — leakage risk | PIT integrity of every metric | engineering | OPEN |
| B7 | AUC 0.4465 (worse than random); R2 replication gate fails | Tier-2 unlock | research | OPEN |
| B8 | India cannot train (n=24) | India R3 entirely | data accumulation | OPEN |
| B9 | No `runner=R3` Position ID namespace | isolation contract R3-0 | engineering | **CLOSED** |
| B10 | Model artifact stores metrics only — not reproducible | reproducibility requirement | engineering | OPEN |
| B11 | Shadow ledger not idempotent — duplicate appends inflate the gate | Day-30 position count | engineering | **CLOSED** |

### B11 · duplicate inflation (found while closing B9)

The ledger is append-only with no dedupe, despite Impl B's docstring
claiming "idempotent per (asof,ticker,model)". Re-running a day appended
the entire day again.

Measured on the **committed** Impl A ledger:

```
records                                60
distinct (market, ticker, asof)        31
duplicate rows                         29   (48%)
worst case                             TCS.NS  ×4 on 2026-08-05
```

**This corrects the scorecard.** Impl B's "15 picks" is **10 unique
picks** — 5 were duplicates. The Day-30 threshold is 20 positions across
30 days; the true starting point is 10 picks across 1 day.

Both writers now dedupe on the deterministic R3 Position ID, and the
existing ledgers have been compacted. Verified idempotent: two consecutive
runs hold at `n_pos=418`.

### B9 · resolution

`backend/research/r3/identity.py` mints canonical shadow Position IDs
(`IND-R3-TATASTEEL-20260907-57fd07`) with byte-exact parity to
`opportunity_registry.make_opportunity_id(market, "R3", ...)`, verified by
test. R3 mints its own rather than importing that module so the R3 tree
retains no import path into Registry-mutating code. Every record now
carries `runner`, `opportunity_id` and `shadow_only`; both writers stamp
on write and all existing records were backfilled.

---

## 9 · Recommended Sprint 1 order

Strictly within the CEO-approved Sprint 1 scope. **No Tier-2 work** — the
replication gate fails, so Tier-2 stays blocked by rule.

1. **CEO decision on B1** (canonical implementation).
2. Close B2 — make the ledger persist (remove the `.gitignore` entry for
   the ledger path, add it to the CI commit set). Without this nothing
   else produces evidence.
3. Close B9 + the three isolation gaps in §5 — this is the R3-0 contract
   and must be green before any research expansion.
4. Close B3 — add the outcome block and a daily outcome accumulator.
5. Close B4/B5/B6 — fix the merge-suffix collision, implement Platt
   properly, replace shuffled KFold with walk-forward + 5-day embargo.
   Mark genuinely unavailable features `NOT_AVAILABLE_AT_ASOF`.
6. Re-measure the baseline. Only then re-run the R2 replication gate.
7. Accumulate daily shadow toward the Day-30 gate (**20 positions across
   30 distinct days** — currently 2 days).

**Do not unlock Tier-2 until the replication gate passes and the Day-30
gate actually fires.**

---

## 10 · Verification commands

```bash
python -m pytest tests/isolation/ backend/tests/test_runner3_isolation.py \
                 tests/research/test_tier2_tier3_tickets.py -q     # 34 passed
python -m backend.research.r3.tier1_gbm --market usa               # AUC 0.4465
python -m backend.research.r3.tier1_gbm --market india             # INSUFFICIENT_SAMPLE n=24
python -m backend.research.r3.baseline_replicate_gate --market usa # gate_pass false
python backend/recommendation/runner3/run.py --market india        # "model not trained yet"
```

All figures in this document were produced by the commands above on
2026-09-07 against the repository at commit `18576d3c`.
