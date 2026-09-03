# AEGIS · Evidence Log

**Status:** IMMUTABLE · APPEND-ONLY · CEO 2026-09-03 controlling contract.

## Governance rule

> **PDF = immutable research/governance contract.**
> **Current repository state = implementation status.**
> **New work = additive advancement only.**
> **A failed experiment = evidence, never something we erase.**

This log records every experiment run, its exact acceptance criteria per the PDF, and its outcome. Entries are **never** deleted, rewritten, or "improved after the fact." An improvement is a new entry with a new `experiment_id` that references the prior one. Any correction to a prior entry lives as an errata note appended to that entry (and dated).

Categories used everywhere:

| Badge | Meaning |
|---|---|
| 🟢 PASSED | Real acceptance criteria met against real substrate |
| 🔴 FAILED | Experiment ran with adequate substrate · acceptance criteria not met |
| 🟠 BLOCKED | Foundation gap prevents the experiment from producing a meaningful result · rerun after foundation is fixed · do NOT interpret as negative |

"Code exists" is not a category. A green isolation-CI is only 🟢 if the acceptance criterion is "isolation CI passes."

---

## Entries

### E-001 · P0-original · Dynamic Exit Bridge · 2026-09-03

- **Runner scope:** R2 (production)
- **PDF acceptance criteria** (verbatim from spec):
  - ≥ 539 historical R2 closes replayed
  - Actual vs counterfactual per position
  - 10 000 paired bootstrap
  - Segmented by regime (NORMAL / WEAKENING / RISK_OFF / CRASH / RECOVERY)
  - Counterfactual expectancy ≥ actual with **n ≥ 50**
  - After validation · ≥ 1 genuine enforcement fire within first 20 trading days
- **Parameters tested (single point):**
  - `k_stop = 2.0`
  - `m_target = 3.0`
  - `horizon = 60` trading days
  - `atr_window = 14`
  - OHLC ambiguity resolution: `PESSIMISTIC_STOP_FIRST` (CANONICAL 1)
- **Substrate used:**
  - Outcome Dataset · USA n=479 non-admin closed R2 · India n=20
  - Regime segmentation: **not honored** — `regime_at_entry` null on every row (enricher not wired). This is a substrate deficiency vs the PDF spec, recorded here so the E-001 result is qualified.
- **Result:** 🔴 **FAILED**
  - USA · mean_delta = −0.03% · 95% CI [−0.12%, +0.06%] · p = 0.56 · trade Sharpe counterfactual 0.067 vs actual 0.078
  - India · mean_delta = +0.75% · 95% CI [−0.64%, +2.23%] · p = 0.30 · n=20 (below acceptance floor of 50)
  - Counterfactual exit-reason distribution (USA): `HORIZON_EXPIRED 452 · STOP_HIT 25 · TARGET_HIT 2` — 94% never fired stop or target within 60d.
- **Interpretation:** at this single parameter point, the dynamic ATR-trailing doctrine does not clear the PDF gate. Stops/targets are too wide relative to typical R2 holding excursions in the tested sample.
- **Artifacts (do not delete):**
  - `reports/research/r2_upgrades/p0_exit_bridge_replay_usa.json`
  - `reports/research/r2_upgrades/p0_exit_bridge_replay_india.json`
- **Substrate qualification (transparency):** regime segmentation missing → this FAIL cannot be attributed to any specific regime. If regime enrichment later reveals the doctrine works in RISK_OFF but not NORMAL, that is a NEW entry (E-001-errata or E-P0-EXT-01), not a rewrite of E-001.

---

### E-002 · R2 zero-entry funnel · symptom count · 2026-09-03

- **Runner scope:** R2
- **PDF acceptance criteria:** preliminary diagnosis with **root cause identified**, classified against {NO_QUALIFYING_SIGNAL / RUNNER_NOT_EXECUTED / PIPELINE_FAILURE / DORMANT_BY_DESIGN}.
- **What was produced:** per-stage funnel counts M1–M8. India collapses M3→M4 (dropped 228 of 230 tickers). USA collapses same transition (dropped 802 of 908). Bottleneck **location** identified.
- **Result:** 🟠 **BLOCKED / INCOMPLETE** — location named, cause not opened. Cannot yet classify against the 4 PDF categories.
- **Follow-up:** written readout with root cause traced through momentum engine code → `docs/AEGIS/R2_ZERO_ENTRY_READOUT.md` (pending).
- **Artifacts:**
  - `reports/research/momentum_funnel/india/latest.json`
  - `reports/research/momentum_funnel/usa/latest.json`

**Errata / follow-up · 2026-09-03 (same day):** root cause traced through code in `backend/research/short_term_momentum.py:260-340` (`categorize()` returns IGNORE for any ticker outside ±4/±8/±12% 1d/3d/5d bands with vol-adjustment cap 2x). 227/230 India + 802/908 USA correctly classified as IGNORE in the tested calm-market window. Classified as **DORMANT_BY_DESIGN** per PDF Sec 2. Signal Silence correctly does NOT fire (all runners simultaneously quiet · condition explicitly held by trigger). MVS reports below floor but relaxation NOT applied (relaxation is pre-registered and validated per PDF · Sprint A hasn't done that pre-work · budget stays at 15/15). Readout at `docs/AEGIS/R2_ZERO_ENTRY_READOUT.md`. E-002 status upgraded 🟠 → **CLOSED** (classified, not "passed" — the classification itself is the deliverable per PDF).

---

### E-003 · R3 isolation CI · 2026-09-03

- **Runner scope:** R3 (research challenger)
- **PDF acceptance criteria:** R3 cannot write to production paths · cannot import R2 SSoT / Registry writers · cannot appear in delivered workbook · cannot mutate R2 weights.
- **What was produced:** 4 CI tests in `tests/isolation/test_r3_no_production_writes.py` + 1 CI test in `tests/isolation/test_composite_no_registry_writes.py` + 1 in `test_r1_advisory_no_pnl.py` · pytest verifies isolation on every push.
- **Result:** 🟢 **PASSED**
- **Note:** this is the only 🟢 Sprint A entry. Every other item is 🔴 or 🟠.
- **Artifacts:** `tests/isolation/`

---

### E-004 · R3 Tier-1 GBM baseline · 2026-09-03

- **Runner scope:** R3 shadow
- **PDF acceptance criteria:** GBM baseline trained · walk-forward folds per PDF Part 4 protocol (train=252, test=63, step=21, embargo=5) · Platt calibration on OOF predictions · SHAP importance emitted · R3 must **replicate the R2 baseline** (within ±5% IC / 0.02 abs) before adding new features.
- **Substrate used:** Outcome Dataset USA n=500 with **effectively empty features** (Fundamentals Feature Store has 1 synthetic RELIANCE row today · all 19 fundamentals fields null-then-zero-filled in training).
- **Result:** 🔴 **FAILED** on the baseline-replicate gate specifically (IC gap 0.10 vs tol 0.02). Substrate insufficient to interpret as evidence about the GBM doctrine itself — the model trained on zeros.
- **Interpretation:** baseline gate correctly BLOCKS Tier-2 features (this is the design working). Whether the R3 doctrine has any edge is not yet testable — needs real fundamentals populated first.
- **Artifacts:**
  - `reports/research/r3/models/gbm_tier1_usa.json`
  - `reports/research/r3/baseline_replicate_usa.json`

---

### E-005 · P2 sector/regime α,β grid · 2026-09-03

- **Runner scope:** R2 (research)
- **PDF acceptance criteria:** walk-forward folds · out-of-sample separation · deflated Sharpe for grid size (9 trials).
- **Substrate deficiency:** `sector_regime_score` and `market_regime_score` are 0 for every row (enricher not wired). "Folds" used are naive contiguous slices, not walk-forward per Part 4.
- **Result:** 🟠 **BLOCKED / NOT INTERPRETABLE** — best (α=0, β=0) is a trivially true statement about multiplying regime features that are zero. This is not evidence about the P2 doctrine.
- **Artifacts:** `reports/research/r2_upgrades/p2_sector_regime_usa.json`

---

### E-006 · P3 KG-community γ grid · 2026-09-03

- **Runner scope:** R2 (research)
- **PDF acceptance criteria:** PIT community snapshots (CANONICAL 3) · community stability check · incremental info beyond Cap×Sector · permutation importance · out-of-sample fold.
- **Substrate deficiency:** historical KG snapshots archived aggregate stats only — per-node community IDs were never persisted. Backfill assigns `community_id = UNKNOWN` sentinel · γ effectively 0 for every historical position.
- **Result:** 🟠 **BLOCKED** — γ grid ran on zero communities. Not a P3 result.
- **Fix path:** start persisting per-node community IDs going forward · accumulate → rerun.
- **Artifacts:** `reports/research/r2_upgrades/p3_kg_community_usa.json` · `reports/research/kg_pit_snapshots/{market}/*.json`

---

### E-007 · P4 Cap × Sector interaction · 2026-09-03

- **Runner scope:** R2 (research)
- **PDF acceptance criteria:** Runner × Cap × Sector × **Investability** table · LR test (Cap-only vs Cap+Sector).
- **Substrate deficiency:** `cap_bucket` null everywhere in Outcome Dataset · **Investability** axis not declared in schema at all.
- **Result:** 🟠 **BLOCKED / NOT TESTABLE** — n=0 usable rows in LR fit. Cannot be interpreted as "Cap × Sector has no relationship."
- **Fix path:** wire cap-bucket enricher (market-cap lookup at entry_date) · add investability axis to schema · rebuild Outcome Dataset · rerun.
- **Artifacts:** `reports/research/r2_upgrades/p4_cap_sector_usa.json`

---

### E-008 · P1 joint Platt calibration · 2026-09-03

- **Runner scope:** R2
- **PDF acceptance criteria:** weekly refit · ECE ≤ 0.05 for 4 consecutive weekly refits · calibrated confidence replaces raw in Telegram/XLSX AFTER gate · confidence never drives sizing before gate.
- **Substrate deficiency:** Signal Ledger has only 3 historical snapshot files → 12 valid rows for the joint fit · below n=50 sample floor.
- **Result:** 🟠 **BLOCKED / INSUFFICIENT SAMPLE** — previous calibration retained per PDF rule (never deploy worse calibration).
- **Fix path:** accumulate ledger snapshots via daily orchestrator · rerun weekly.
- **Artifacts:** `reports/research/r2_upgrades/p1_calibration_usa.json`

---

## P0-EXTENSION-01 · declared, not run

- **Extends:** E-001 (P0-original).
- **Motivation:** E-001 FAILED at one parameter point. PDF does not permit reinterpreting the doctrine as failed on a single-trial evidence base. Extension explores an additive parameter surface.
- **Design:**
  - `k_stop ∈ {1.0, 1.5, 2.0, 2.5, 3.0}` (5 values)
  - `m_target ∈ {1.5, 2.0, 3.0, 4.0}` (4 values)
  - `horizon ∈ {20, 40, 60}` trading days (3 values)
  - **Total trial family: 60 · trial accounting matrix updated when extension runs.**
  - Deflated Sharpe applied with `n_trials = 60`, not `1`.
  - Regime segmentation mandatory once regime enricher lands.
  - Walk-forward folds (252 / 63 / 21 / 5) applied per PDF Part 4.
- **Preservation invariant:** E-001 result stays. E-P0-EXT-01 is a separate entry with its own fingerprint. Even if extension finds a passing parameter point, the ORIGINAL point (k=2, m=3, 60d) remains recorded as FAIL forever.
- **Status:** DECLARED · not yet run · gated on regime enricher landing first (segmentation is mandatory per PDF).

## R2-EXT-EXIT-DOCTRINE-01 · alternative exit doctrines · declared

- **Motivation:** if E-P0-EXT-01 also fails, alternative doctrines are tested as separate research tickets (not P0 replacements).
- **Candidates:**
  - Chandelier stop (trailing off n-bar high, not close)
  - Fixed-% stop (no ATR dependence)
  - MFE-anchored stop (trail from realized max)
  - Volatility-regime-aware k (different k under RISK_OFF vs NORMAL)
- Each becomes its own experiment entry when run. None can call itself "P0."

---

---

## Batch B enricher entries · 2026-09-03

### E-009 · B1 Regime enricher · 2026-09-03
- **Deliverable:** populate `regime_at_entry` on Outcome Dataset per PDF regime vocabulary.
- **Source:** `reports/research/mr_market_regime_{market}.json` · 1472 India / 1194 USA daily labels.
- **Mapping (locked):** `BULL→NORMAL · NEUTRAL→NORMAL · HIGH_VOL→RISK_OFF · BEAR→WEAKENING`.
- **Missing states declared:** `CRASH_DETECTOR_01` and `RECOVERY_DETECTOR_01` — additive detectors not yet built. Enricher covers 4 of 6 PDF states.
- **Result:** 🟢 **ENRICHED** · USA 556 rows (all NORMAL under current mapping/source-coverage); India 68 rows.
- **PIT invariant:** for entry_date D, uses largest source date ≤ D · never looks forward · verified by 8 tests in `tests/enrichers/test_regime_enricher.py`.
- **No fabrication:** missing → UNKNOWN with `regime_source="missing"`; unmapped label → UNKNOWN with `regime_source="unmapped:<label>"`.
- **Artifacts:** `reports/research/enrichers/regime_{market}.json`.

### E-010 · B3 Cap + Investability enricher · 2026-09-03
- **Deliverable:** populate `cap_bucket` and `investability` columns.
- **Cap thresholds (USD-locked · INR converted at 83/USD):** micro <300M · small 300M-2B · mid 2B-10B · large 10B-200B · mega ≥200B.
- **Investability thresholds:** liquid ≥ $10M ADV · less_liquid $1M-$10M · illiquid < $1M.
- **Provenance:** `cap_source="yfinance:current_fallback"` (yfinance marketCap is current-value; PIT market_cap would need shares_out(entry_date) × close(entry_date) · declared as `CAP_PIT_STRICT_01` extension). `investability_source="parquet_pit_adv"` is fully PIT-safe.
- **Result:** 🟢 **ENRICHER READY** · smoke-tested with `--no-yfinance` (fills nulls with `cap_source="yfinance_skipped"`). Full population batch is a network job (not run today · rate-limited).
- **Unblocks:** P4 Cap×Sector×Investability LR test.
- **Artifacts:** `reports/research/enrichers/cap_investability_{market}.json`.

### E-011 · B4 Sector + Market regime scores enricher · 2026-09-03
- **Deliverable:** populate `sector_regime_score` and `market_regime_score`.
- **Methodology:** sector = 20d mean return per sector on asof, z-scored cross-sectionally across sectors, clamped [−3,3]. Market = universe-mean 20d return on asof, z-scored across trailing 90d of same measure, clamped [−3,3]. Fully PIT.
- **Result:** 🟢 **ENRICHED** · USA 13 rows got market score (only 8 unique dates in dataset · trailing-90d z requires ≥5 window values); sector scores 0 (each date has 1-2 tickers per sector · cross-section requires ≥3 peers).
- **Interpretation:** sample thinness at present · rerun once Outcome Dataset accumulates. Substrate ready.
- **Unblocks:** P2 α·sector_regime_score + β·market_regime_score lift measurement (when sample fills).
- **Artifacts:** `reports/research/enrichers/regime_scores_{market}.json`.

### E-012 · B5 KG persistence hook · 2026-09-03
- **Deliverable:** helper for the daily KG runner to persist per-node community IDs into PIT snapshots with `confidence="HIGH"` (vs backfill scaffolds at `confidence="LOW"`).
- **Result:** 🟢 **HOOK SHIPPED** · daily KG runner integration is a one-line call: `persist_pit_snapshot(root, market, asof, communities, graph_stats, algorithm, modularity_q)`.
- **Preservation:** historical UNKNOWN snapshots stay UNKNOWN · this hook is forward-looking only, per CEO governance.
- **Unblocks:** P3 KG-community γ scoring once the daily runner is wired.
- **Artifacts:** `backend/research/enrichers/kg_persistence_hook.py`.

### E-013 · B7 Signal Ledger walker · 2026-09-03
- **Deliverable:** walk every historical snapshot path (recommendations_history + archive bundles + live) and feed to ledger builder.
- **Result:** 🟠 **DISCOVERED** · only 3 snapshot files per market exist historically (2026-07-29, 2026-07-30, 2026-09-02). No hidden history to unlock. Ledger will accumulate as the daily orchestrator runs.
- **Signal Ledger current:** 30 India rows / 45 USA rows · below n=50 for P1 calibration gate.
- **P1 gate stays BLOCKED** until natural accumulation.
- **Artifacts:** `reports/research/enrichers/signal_ledger_walker_{market}.json` (not persisted separately · reported inline).

### E-014 · B2 India PIT universe · 2026-09-03
- **Deliverable:** India historical universe reconstruction per PDF Sec 5 (NIFTY 200 target).
- **Best auditable source found:** `configs/india_universe_tiers.yaml` largecap_tickers block = **NIFTY 50 only**. NIFTY 200 full list NOT SPECIFIED in PDF and NOT PRESENT in repo.
- **Action taken (per CEO governance):** emitted `reports/india_universe.json` with 50 tickers + explicit note. Wired `configs/aegis_universes.yaml → india.source_file`. PIT audit now produces 3250 rows (50 × 65 days) with `confidence=LOW` for the 65-day window.
- **No fabrication:** rest of NIFTY 200 constituents NOT invented.
- **Extension declared:** `UNIVERSE_EXT_NIFTY200` · pending an authoritative NIFTY 200 constituent source. When landed, becomes an additive extension.
- **Artifacts:** `reports/research/pit_universe/india.parquet` + `reports/india_universe.json`.

### E-015 · R3 Daily Shadow Feed live · 2026-09-03
- **Deliverable:** start the Day-30 shadow clock per PDF Phase 3.
- **Result USA:** 🟢 **APPENDED** · 5 picks written to `reports/research/r3/shadow_ledger.jsonl` for asof=2026-09-03. Day-30 gate fires at ≥20 accumulated picks (4-5 daily runs at n=5).
- **Result India:** 🟠 **TRAIN_SKIPPED** · n=24 < 30 sample minimum; will begin appending once Outcome Dataset grows.
- **Isolation invariant:** verified by CI · never writes to Registry / Portfolio / Exit History / delivered workbook.
- **Artifacts:** `reports/research/r3/shadow_ledger.jsonl`.

---

### E-016 · NEG-PNL-CONTROL-60D · additive research family FIRST RUN · 2026-09-03

- **Research family:** additive · declared by CEO 2026-09-03 · not a P0 replacement.
- **Question:** during the latest 60 calendar days of AEGIS output, could an earlier, more disciplined control/exit rule have reduced negative P&L WITHOUT destroying positions that subsequently recovered or won?
- **Scope:** 18 tests declared · core (T1, T2, T3, T5, T6, T12, T13, T14, T15, T16) implemented in this run · T4/T7/T8/T9/T10 deferred pending substrate enrichers.
- **Window:** entry_date ≥ (2026-09-03 − 60d) OR still active in window OR fresh exit in window.
- **Trial family count:** 9 counterfactual variants (6 static-% thresholds + 3 static-timing) · Deflated Sharpe applies with `n_trials = 9`, not `1`.

#### USA · 536 positions in window · **verdict: no control variant improves baseline**

Trajectory classification:
  - IMMEDIATE_LOSER 217 · TEMPORARY_LOSER 53 · WINNER 229 · FLAT 36 · DEEP_LOSER 1

MFE/MAE buckets (key intervention group HIGH_MAE_LOW_MFE = 34):
  - LOW_MAE_LOW_MFE 446 · HIGH_MAE_LOW_MFE 34 · LOW_MAE_HIGH_MFE 47 · HIGH_MAE_HIGH_MFE 9

Depth cohorts: 108 crossed −2% · 62 crossed −3% · 26 crossed −5% · 9 crossed −7%.

Counterfactual variants vs baseline (10 000 paired-bootstrap, α=0.05):

| Variant | n_exit | Δ mean P&L | 95% CI | p_two | winners_sacrificed | winner_rate |
|---|---:|---:|---|---:|---:|---:|
| static_pct@−2% | 108 | **−0.133%** | [−0.255%, −0.025%] | **0.016** | 15 | 13.9% |
| static_pct@−3% | 62 | **−0.130%** | [−0.249%, −0.029%] | **0.012** | 10 | 16.1% |
| static_pct@−4% | 38 | **−0.098%** | [−0.197%, −0.017%] | **0.018** | 4 | 10.5% |
| static_pct@−5% | 26 | −0.062% | [−0.129%, +0.000%] | 0.051 | 2 | 7.7% |
| static_pct@−6% | 17 | −0.039% | [−0.091%, +0.004%] | 0.077 | 1 | 5.9% |
| static_pct@−7% | 9 | −0.008% | [−0.033%, +0.019%] | 0.508 | 0 | 0.0% |
| static_time@3d | 41 | −0.042% | [−0.138%, +0.046%] | 0.352 | 18 | 43.9% |
| static_time@5d | 59 | **−0.193%** | [−0.327%, −0.073%] | **0.000** | 23 | 39.0% |
| static_time@10d | 0 | −0.000% | [−0.000%, +0.000%] | 0.480 | 0 | 0.0% |

**Result:** 🔴 **NO CONTROL VARIANT IMPROVES BASELINE.**

Three tighter static-% stops (−2%, −3%, −4%) are statistically-significantly WORSE at p < 0.02. Static 5-day time-stop is worse at p ≈ 0. Every tighter variant sacrifices winners (up to 44% sacrifice rate on static_time@3d). The loosest variant (−7% or 10d) has effectively no effect (delta ≈ 0, non-significant). After Deflated-Sharpe deflation by 9 trials, none of these results survives as a positive edge either.

**Empirical answer to the research question:** during this 60-day window, **an earlier control rule would have hurt or done nothing**. R2's current exit discipline should not be tightened based on this evidence.

#### India · 67 positions in window

Historical baseline present but sample thinner. Full panel produced in `reports/research/neg_pnl_control_60d/panel_india.json`.

#### Governance preserved

- P0-original (E-001) unchanged · this is NOT a P0 replacement.
- No R2 change proposed.
- No production stop tightened.
- All 9 variants counted in trial family.
- Bootstrap paired · same-position comparison as PDF Sec 27 requires.
- Deflated Sharpe deflation flagged with n_trials=9 for any future "best variant" claim.

#### Deferred tests

- T4 (static vs dynamic ATR comparison) · needs dynamic-risk producer for both markets · Sprint A Week-3 slot.
- T7 (signal deterioration replay) · needs richer Signal Ledger · blocked by natural accumulation (E-013).
- T8 (regime-conditioned loss control) · needs sufficient rows per regime · regime enricher landed (E-009) · rerun once sample matures.
- T9 (Sector × Cap × Investability interaction) · blocked on B3 batch (cap network job pending).
- T10 (R1 vs R2 control comparison) · needs R1 daily archive.
- T11 (administrative-exit separation) · already applied in E-002 · re-verified in this run.

- **Artifacts:**
  - `reports/research/neg_pnl_control_60d/dataset_{market}.json`
  - `reports/research/neg_pnl_control_60d/panel_{market}.json`
  - `reports/research/neg_pnl_control_60d/summary_{market}.md`

---

### E-022 · Final 28-report aggregation · V2 §37 · 2026-09-03

- **Deliverable:** consolidated 28-report set in `docs/AEGIS/FINAL_28_REPORTS.md`.
- **Method:** `scripts/aegis_final_28_reports.py` aggregates every JSON panel + evidence entry + registry entry into ONE document with explicit KEEP/REJECT/RESEARCH FURTHER/PROMOTE-CANDIDATE recommendation per item.
- **Result:** 23 recommendations issued today · 6 KEEP · 3 REJECT (all correct rejections: NEG-PNL variants · POS-PNL threshold loosening · joint pareto strategies) · 14 RESEARCH FURTHER · **0 PROMOTE-CANDIDATE**.
- **Governance:** V2 §37 satisfied · no production promotion authorized · no PDF gate weakened.

### E-021 · Fundamentals Feature Store · synthetic smoke batch · 2026-09-03

- **Deliverable:** substrate priming for V2 §5 · Layer-1..Layer-5 all populated with realistic values across India top-10 tickers.
- **Method:** `scripts/populate_fundamentals_smoke.py` seeds using RELIANCE-magnitude inputs with per-ticker `market_cap` variation.
- **Result:** Fundamentals FS India → 10 rows (was 1 · synthetic RELIANCE only). All 5 layers populated (n_with_signal_by_layer = {1:10, 2:10, 3:10 incl. inst_13f_change, 4:10, 5:10}).
- **Data-source tag:** `synthetic_smoke` · every row is transparently marked · **does NOT unblock any downstream PDF gate** (V2 §36 · substrate must be genuine PIT for gate-crossing).
- **What it does unlock:** Winner Genome extraction can now emit non-null Fundamentals fields for smoke testing · R3 Tier-1 GBM `build_training_frame` receives populated columns · downstream code paths exercised end-to-end.
- **What it does NOT do:** replace the pending B6 network batch. E-004 R3 baseline-replicate FAIL stands.
- **Recommendation:** RESEARCH FURTHER · schedule B6 batch (25 tickers · sleep 2s) against real yfinance data before any Tier-2 interpretation.

### E-020 · R1 Advisory Attribution · 2026-09-03

- **Deliverable:** V2 §18 · R1 vs R2 early-warning study substrate.
- **Method:** `backend/research/r1_advisory_attribution.py` cross-references R1 daily archive against R2 Registry.
- **Result USA:** r1_archive_days=**0** · early_warnings=0 · r2_days_open=4. India same shape (r2_days_open=14).
- **Data gap flagged:** R1 daily archive is a Week-3 Sprint A deliverable (`data/r1_daily_archive/YYYY-MM-DD.csv`) not yet running. Module reports the gap transparently rather than fabricating early-warning counts.
- **Governance:** R1 stays RETIRED_ADVISORY · this attribution is DIAGNOSTIC · does NOT authorize R1 to acquire production authority per V2 §2/§18.
- **Recommendation:** RESEARCH FURTHER · start daily R1 archive to fill this substrate over coming weeks.

### E-019 · Paper Comparator daily tick · V2 Phase H · 2026-09-03

- **Deliverable:** V2 §27 forward validation substrate.
- **Method:** `backend/research/paper_comparator/daily_tick.py` records daily JSONL line per (market, asof) with:
  - R2 production picks · from `recommendations_v3.json`
  - Standing comparator picks · equal-weight top-10 3-mo momentum · **PERMANENT · never optimized** (V2 §17 P5.5)
  - Candidate strategy picks · currently empty (no research strategy has cleared gates)
- **First tick:** India 15 R2 picks + 10 standing comparator · USA 15 R2 picks + 10 standing comparator.
- **Substrate:** append-only ledger at `reports/research/paper_comparator/{market}.jsonl`.
- **Recommendation:** KEEP daily tick · accumulate forward evidence · REJECT any promotion until sustained forward window (per PDF requires paper period before controlled change).

### E-018 · Joint Positive+Negative P&L frontier · V2 §11 · 2026-09-03

- **Research family:** joint objective per V2 §11 · every candidate strategy scored on BOTH sides simultaneously.
- **Method:** `backend/research/joint_pnl/joint_score.py` crosses NEG-PNL variants (9) × chosen POS winner definition (h20_t10pct) → 9 joint scorecards. Applies Pareto-frontier filter dominating on {delta_pnl↑, pos_tp↑, winners_sacrificed↓, forfeited_upside↓}.
- **Result USA:** **Pareto frontier size = 1** · only `static_time@10d + POS[h20_t10pct]` survives dominance. That strategy has delta_pnl≈0 · pos_tp=0 · winners_sacrificed=0 · forfeited_upside=0.049 — essentially "do nothing" is the only non-dominated point.
- **Interpretation:** the joint frontier confirms E-016 and E-017 read together: no NEG-control variant beats baseline on the pos-capture side either. Cross-side improvement isn't available at these parameters on this data window.
- **Governance:** even a frontier strategy would still require PIT audit + walk-forward + OOS + stat-sig + MT-correction + evidence gate + paper period + explicit CEO authorization before any production consideration (V2 §34).
- **Recommendation:** REJECT all pareto strategies · KEEP the frontier engine as diagnostic infrastructure.
- **Artifact:** `reports/research/joint_pnl/panel_{market}.json`.

---

### E-017 · POS-PNL-CAPTURE-60D · additive research family FIRST RUN · 2026-09-03

- **Research family:** additive · declared by CEO 2026-09-03 master prompt · mirror of NEG-PNL-CONTROL-60D.
- **Question:** during the latest 60 calendar days of AEGIS output, which profitable opportunities were missed, why were they missed, and can the new AEGIS techniques recover those opportunities without materially increasing losses / drawdown / turnover / concentration / winner sacrifice?
- **Scope:** 18 tests declared · core (T1 dataset + T3 winner definition + T4 missed-winner funnel A-F + T5 selection metrics) implemented in this run · T2/T6-T18 documented at call sites pending enricher wiring.
- **Winner definition trial family:** 16 (4 horizons × 4 thresholds · PREDECLARED before inspecting results) · Deflated Sharpe deflation applies `n_trials=16` for any "best" claim.
- **PIT rule:** every candidate uses only features available at decision date · future returns are outcome labels only.

#### USA · 31 476 candidate × date rows · 30 950 with data (98.3%)

Per-winner-definition selection quality (subset):

| Definition | TP | FP | FN | Precision | Recall | Missed cost sum |
|---|---:|---:|---:|---:|---:|---:|
| h5_t5pct   | 1 | 88 | 2652 | 0.011 | 0.000 | +23 766% |
| h5_t10pct  | 0 | 89 |  682 | 0.000 | 0.000 | +10 311% |
| h5_t15pct  | 0 | 89 |  234 | 0.000 | 0.000 |  +4 933% |
| h5_t20pct  | 0 | 89 |  111 | 0.000 | 0.000 |  +2 828% |
| h10_t5pct  | 1 |  3 | 3526 | 0.250 | 0.000 | +36 009% |
| h10_t10pct | 0 |  4 | 1295 | 0.000 | 0.000 | +20 067% |
| h10_t15pct | 0 |  4 |  478 | 0.000 | 0.000 | +10 219% |
| h10_t20pct | 0 |  4 |  210 | 0.000 | 0.000 |  +5 611% |

Aggregate missed-winner cost by horizon (sum of forward-returns of missed winners across all thresholds):
- 5d:  +41 839%
- 10d: +71 907%
- 20d: +74 382%
- 60d:  0% (out-of-window · needs longer parquet reach)

**Miss-category classification (h20_t10pct):**
- C_FUNNEL_STAGE_MISS: **1 417** (100% of the missed winners at that definition)
- All misses trace to the same upstream filter identified in E-002 · `short_term_momentum.py:340` returns IGNORE for tickers outside ±4/±8/±12% bands. Not only were 227/230 India universe tickers dropped that way, so were thousands of USA candidates that subsequently became winners.

#### Interpretation

- The system's precision-when-selecting is essentially zero at short horizons (h5) — AEGIS's 89 USA selections in the window produced ~1 TP against the h5_t5pct definition.
- The overwhelming majority of missed winners were dropped upstream by the volatile-mover filter (C_FUNNEL_STAGE_MISS). This is the SAME finding as E-002 (R2 zero-entry) — the short_term_momentum filter is DORMANT_BY_DESIGN, and that design has a cost visible from the positive side.
- The 88 false-positives in h5_t5pct selections show current AEGIS selections rarely produce a +5% 5-day return.
- Precision improves at longer horizons (h10 shows prec=0.250 for at least one TP) but recall stays at 0 across every horizon+threshold combination.

#### What this evidence does NOT justify

Per governance:
- Does NOT justify tightening R2 (that's E-016's job · already showed no control variant helps)
- Does NOT justify LOOSENING the short_term_momentum thresholds (that would replace a volatile-mover detector with a broadband filter · silent doctrine change)
- Does NOT justify adding a second candidate-source path yet · that's a NEW research ticket requiring its own gate

#### What this evidence DOES suggest for future research

- Test whether the PDF techniques (P1/P2/P3/P4/P5) can recover any of the C_FUNNEL_STAGE misses when substrate lands · this is exactly the "PDF technique tests" section of the master prompt.
- The short_term_momentum IGNORE filter is worth a formal research ticket · not a threshold change, but a study of whether an ALTERNATE candidate-generation path (fundamentals-first · KG-community-first · flow-first) would recover any missed winners.
- Per PDF Sec 9 · Signal Silence + MVS discipline stays in place.

#### Deferred tests (each with named blocker)

- T2 winner cohort analysis by class · blocked on trajectory reconstruction of PIT candidates (not just Registry positions)
- T6 joint pos+neg counterfactual · blocked on candidate-strategy definition
- T7 timing "would AEGIS have caught it earlier?" · blocked on daily-rank history
- T8 signal deterioration replay · blocked on rank/confidence timeseries
- T9 Cap × Sector × Investability winner rate · blocked on B3 batch (yfinance)
- T10 R1 vs R2 winner discovery · blocked on R1 daily archive
- T11 fundamentals attribution of winners · blocked on B6 batch (yfinance)
- T12 KG community winner concentration · blocked on real per-node KG snapshots

- **Artifacts:**
  - `reports/research/pos_pnl_capture_60d/dataset_{market}.summary.json`
  - `reports/research/pos_pnl_capture_60d/panel_{market}.json`
  - `reports/research/pos_pnl_capture_60d/summary_{market}.md`

#### Governance preserved

- P0-original (E-001) unchanged.
- NEG-PNL-CONTROL-60D (E-016) unchanged.
- No R2 change proposed.
- No PDF gate lowered.
- Trial family (16) counted; Deflated Sharpe deflation applies to any future "best" claim.
- Master controlling prompt saved verbatim at `docs/AEGIS/MASTER_CONTROLLING_PROMPT_2026-09-03.md`.

---

## Additive extensions declared (not yet run)

- **P0-EXTENSION-01** · 60-trial (k×m×horizon) parameter surface · gated on regime enricher landing first (now unblocked · can proceed after Batch B commit).
- **R2-EXT-EXIT-DOCTRINE-01** · alternative exit doctrines · separate research tickets.
- **CRASH_DETECTOR_01** · WEAKENING + market_1d < −3σ event detector · additive to regime enricher.
- **RECOVERY_DETECTOR_01** · trailing NORMAL/BULL after a CRASH · additive.
- **CAP_PIT_STRICT_01** · shares_out(entry_date) × close(entry_date) instead of yfinance current-fallback · replaces the current cap approximation for PIT strictness.
- **UNIVERSE_EXT_NIFTY200** · full NIFTY 200 constituent list · replaces the NIFTY 50 subset once an auditable source lands.

---

## Errata policy

Any correction to an existing entry lives here as a dated errata line, never as an in-place rewrite of the entry above.

_(no errata yet)_
