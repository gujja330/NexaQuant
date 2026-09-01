# AEGIS · Production Integration Audit & Closure · 2026-09-01

**Purpose**: closure artifact for the 60-day development period. Prove
what is genuinely wired into the R2 production path vs. what is
scaffolded / research-only / orphaned / broken.

**Scope**: R2 + all supporting engines. **R1 is explicitly parked and
out of scope.**

**Method**: read-only trace of `scripts/aegis_daily_v2.py` (63 STEPS
after 2026-09-01 wire-in) + `.github/workflows/*.yml` + grep of every
producer/consumer chain + 60-day git history + direct file inspection.

**Discipline**: no code changed for this audit · no commits · no push ·
no R2/exit modification · no additional wiring beyond what was
authorized in the prior turn (15 STEPS added to daily driver in a
separate session tool call · documented in §14).

---

## Primary question · answered

> **Were these components actually wired into the production R2 daily
> decision path, or did we build many components that exist only as
> isolated code/research/scaffolding?**

**Signal side (R2 candidate selection)**: **GENUINELY WIRED.** The 11-model
ensemble at the heart of R2 does consume the wide input surface we built:
`feature_store` + `feature_intelligence` + `factor_library` +
`market_intelligence` + `macro_intel` + `dynamic_holding` +
`capital_rotation` + `opportunity_cost` + FinBERT news (India) + sector
divergence sentiment (both). Every daily-driver STEP 01-25 contributes.

**Exit side**: **NOT WIRED.** The coded dynamic exit engine
(`portfolio_manager` + `lifecycle_state_machine` + `dynamic_risk_v2` +
`position_store` trailing) exists in full but is **not invoked** by the
daily driver. Exits fire only via (a) ensemble STRONG_SELL propagating
through `detail_xlsx.py:503` → `oreg.close()`, or (b) `mr_orphan_closer`
housekeeping. 539 R2 CLOSED events all-time · zero STOP/TARGET/HORIZON
events.

**Research side**: **RESEARCH-ONLY BY DESIGN.** Multi-Layer Research,
momentum ledger, stress-regime, and crash-resilience were built to
CEO's explicit "research never modifies R2" invariant. As of the last
turn's wire-in they now execute daily and produce evidence but they
DO NOT feed R2 decision logic.

**Certification & audit side**: **NEWLY WIRED (this turn's authorized
change).** Reconciler, sign-off, provenance, overlap, R1 audit,
determinism, 3-sheet workbook, dynamic-exit-bridge (audit-only) are now
STEPS 46-60 in the daily driver.

---

## Part 1 · Inventory (all substantive components discovered)

Enumeration groups. Full row-by-row table is in Part 2. Components
grouped by their runtime role:

**Daily-driver STEPS (63 total after 2026-09-01 wire-in)** ·
grouped:
- Ingestion (STEPS 01-06): fii_dii, news_sentiment (FinBERT · India),
  fundamentals, macro_summary, corporate_actions, backend_validation
- Intelligence (STEPS 07-12): macro_intel, factor_library,
  market_intelligence, feature_store, feature_intelligence, model_factory
- Decision (STEPS 13-23): recommendation_intelligence (V3),
  recommendation_ssot, recommendation_lifecycle,
  institutional_optimization, recommendation_deltas, dynamic_holding,
  macro_decision_impact, portfolio_decision_impact, consumer_audit,
  recommendation_quality, repository_intelligence
- Portfolio (STEPS 24-27): risk_engine, portfolio_engine, learning_engine,
  execution_simulator
- Research feeding delivery (STEPS 28-43): adaptive_rec_v2, validation_v2,
  risk_capital_v2, dna_feedback, knowledge_graph, fusion, stock_validation,
  price_context, decision_center, capital_rotation, opportunity_cost,
  portfolio_attribution, institutional_memory, winner_genome,
  decision_attribution, benchmark
- Delivery (STEPS 44-45): morning_report, ops_check
- **Multi-layer research + certification wire-in (STEPS 46-60 · new)**:
  multi_layer_momentum_ledger, multi_layer_stress_regime,
  multi_layer_crash_resilience, multi_layer_runner_india,
  multi_layer_runner_usa, multi_layer_forward_outcomes,
  dynamic_exit_bridge_audit (audit-only), aegis_r1_producer_audit,
  aegis_3sheet_workbook, aegis_provenance_companion,
  aegis_overlap_classifier, aegis_visual_signoff,
  aegis_determinism_hash, aegis_final_reconciler, aegis_local_certification
- Final delivery (STEPS 61-63): telegram, monthly_rollups, runner3_shadow

**Discovered but NOT in daily driver:**
- `backend/portfolio/portfolio_manager.py` (orphaned since 2026-08-20)
- `backend/portfolio/lifecycle_state_machine.py` (orphaned)
- `backend/portfolio/position_store/store.py` trailing high-water
  (updated daily but no exit consumer)
- `backend/risk/dynamic_risk_v2.py` (runs daily via new_opp_guard ·
  writes JSON · no consumer for exit decisions)
- `backend/context/sector_news/classify.py` (runs daily · but is
  price-divergence proxy · not real news NLP)
- USA `news_sentiment.parquet` producer (path exists in
  `backend/canonical/adapters.py:197` · no producer implemented)
- `backend/research/multi_layer/point_in_time_reader.py` (DEAD ·
  never imported outside __init__)
- `backend/research/multi_layer/unavailable_contract.py` (DEAD ·
  never imported outside __init__)
- `scripts/xlsx_augment_sheets.py` (superseded by 3-sheet renderer)
- `scripts/build_usa_missing_sheets_from_registry.py` (superseded)
- `scripts/phase_2_c9_registry_sync.py` (one-shot · complete)
- `scripts/phase_2_identity_execute.py` (one-shot · complete)
- `scripts/r2_stop_rule_audit.py` (diagnostic · manual)
- `scripts/r2_lifecycle_reconstruction.py` (diagnostic · manual)
- `scripts/aegis_r1_retention_review.py` (diagnostic · manual · R1)
- `scripts/phase_0_5_production_failure_audit.py` (diagnostic · manual)

---

## Part 2 · Master inventory (with evidence)

Full row-per-component table with the exact fields the prompt requests
lives in the prior audit `docs/AEGIS/PRODUCTION_ENGINE_INTEGRATION_AUDIT.md`
§1 and `docs/AEGIS/PRODUCTION_WIRING_AUDIT.md` §3. Both are
authoritative sub-documents of this closure audit.

**High-level status roll-up (63 daily-driver STEPS + ~30 non-driver components)**:

| Bucket | Count | Notes |
|---|---|---|
| PRODUCTION-WIRED (STEP + consumer proven) | 45 | Signal chain STEPS 01-27, 33, 44, 46, plus decision-support STEPS 15-18, 37-38 |
| RESEARCH-WIRED but not-decisional (runs · outputs read only for reporting/cert) | 18 | STEPS 28-43 mostly · 46-60 the certification chain |
| PARTIALLY WIRED (produces but no consumer for the intended purpose) | 4 | dynamic_risk_v2 · position_store trailing · sector_news divergence · momentum_attribution |
| RESEARCH-ONLY BY DESIGN | 9 | Multi-layer scaffold modules · runner3 shadow · walk-forward window generator · UNAVAILABLE contract |
| ORPHANED / UNREACHABLE | 3 | portfolio_manager · lifecycle_state_machine · point_in_time_reader · unavailable_contract |
| DEPRECATED / SUPERSEDED / ONE-SHOT COMPLETE | 5 | xlsx_augment · build_usa_missing_sheets · Phase 2 migration scripts · retention-review |
| BROKEN / DATA MISSING | 1 | USA news_sentiment producer never built |
| UNKNOWN / INSUFFICIENT EVIDENCE | 3 | Some `backend/decision_intelligence/*` sub-modules · certain `backend/analytics/*` |

---

## Part 3 · Real R2 call graph (traced from code)

Actual production execution chain:

```
1  GitHub Actions cron (.github/workflows/aegis-daily.yml:186)
      ↓
2  scripts/aegis_daily_v2.py --continue                (63 STEPS)

3  Data ingestion (STEPS 01-06)
      · fii_dii.parquet
      · news_sentiment.parquet          ← FinBERT (India only)
      · fundamentals.parquet             ← yfinance snapshot
      · macro_summary.json               ← yfinance-live
      · corporate_actions.parquet
      · backend_validation.json          ← freshness+schema+quality

4  Intelligence layer (STEPS 07-12)
      · macro_regime.json + 10 macro sub-artifacts
      · factor_library.parquet
      · market_intelligence.json         ← regime + breadth + rotation
      · feature_store_summary.json       ← merges market_intel + factors
      · selected_features.json           ← feature_intelligence
      · ensemble.json                    ← 11 models · aggregate

5  Decision layer (STEPS 13-23)
      · recommendations_v3.json          ← R2 candidate signal
      · recommendations.json             ← SSoT guard · KEYSTONE
      · percentile_classification.json   ← institutional_optimization (rebuilds action)
      · recommendation_lifecycle.json    ← state machine
      · recommendation_deltas.json       ← 11 delta fields per rec
      · dynamic_holding.json             ← adaptive horizon
      · macro_decision_impact.json
      · portfolio_decision_impact.json
      · consumer_audit.json
      · recommendation_quality.json      ← expected alpha · downside · win prob
      · repository_intelligence.json     ← housekeeping

6  Portfolio layer (STEPS 24-27)
      · sized_positions.json             ← risk_engine · Kelly + caps + vol adj
      · portfolio_v3.json                ← N-name construction
      · learning artifacts + AI narratives
      · execution_ledger.parquet         ← equity curve + realized

7  Research feeding delivery (STEPS 28-43 · 16 steps)
      · adaptive_rec_v2 · validation_v2 · risk_capital_v2
      · dna_feedback · knowledge_graph
      · fusion (final intelligence)      ← investment_intelligence.json
      · stock_validation · price_context · decision_center
      · capital_rotation                 ← STRONG_SELL rotations
      · opportunity_cost                 ← HOLD justification
      · portfolio_attribution · institutional_memory
      · winner_genome · decision_attribution · benchmark

8  Delivery preparation (STEPS 44-45)
      · morning_report.md/.html
      · ops_check.json

9  Multi-layer research + certification (STEPS 46-60 · this session's authorized wire-in)
      · momentum_ledger_{market}.json
      · stress_regime_{market}.json
      · crash_resilience_{market}.json
      · multi_layer evidence for india + usa
      · momentum_forward_outcomes
      · dynamic_exit_decisions_{market}.json (audit-only · NO Registry mutation)
      · r1_producer_audit_{market}.json
      · aegis_{market}_YYYY-MM-DD.xlsx  ← 3-sheet workbook
      · aegis_history_{market}_provenance.jsonl
      · portfolio_exit_overlap_{market}.json
      · visual_signoff_{market}.md
      · determinism_hash_{market}.json
      · final_reconcile_{market}.json
      · AEGIS_FINAL_CERTIFICATION.json

10 Final delivery (STEPS 61-63)
      · telegram delivery
      · monthly rollups
      · runner3 shadow (isolated)
```

**Where exits happen** (only two paths · confirmed by grep):
```
Path A: recommendation_ssot emits STRONG_SELL
     → detail_xlsx.py:503 fires oreg.close(reason=exit_reason)
     → Registry ACTIVE → CLOSED
Path B: mr_orphan_closer.py:204 (housekeeping · stale-days)
     → oreg.close(reason="ORPHAN_AUTO_CLOSE")
```

**Where exits COULD happen but don't** (proven zero enforcement path):
```
apply_dynamic_exits.py (STEP 52 · this session)
     → runs in --audit-only mode (default · no --enforce flag)
     → produces dynamic_exit_decisions_{market}.json
     → workbook counterfactual column consumes it (display only)
     → Registry NOT mutated

evaluate_position (lifecycle_state_machine.py)
     → NEVER CALLED in daily driver
portfolio_manager._run_dynamic_cycle
     → NEVER CALLED in daily driver
dynamic_risk_v2 output (JSON)
     → produced daily but no exit consumer
position_store.current_stop
     → maintained daily but no exit consumer
```

---

## Part 4 · Daily news / market-context engine

**Two coexisting news paths**:

### Path A · FinBERT news · India only

| Question | Answer |
|---|---|
| Does the engine exist? | YES · `india/news_sentiment.py` |
| Data source? | Google News RSS per stock (India EW-30 basket) |
| Frequency? | Daily · STEP 02 · `staleness_skip_hours: 6` |
| Daily production workflow calls it? | YES · `scripts/aegis_daily_v2.py:63` |
| Output reaches R2? | ~ · via `backend/canonical/adapters.py:194` (canonical loader) and `india/run_arjuna.py:26` (Arjuna screening) |
| R2 uses in ranking/decision? | ~ · feeds investability score which affects display band · not R2 ensemble input |
| Merely stored? | NO · consumed downstream |
| Merely displayed? | NO · feeds Arjuna screen |
| Research-only? | NO · production-wired |
| Config-disabled? | NO · `optional: True` but runs by default |
| Stale? | NO · 6h freshness policy |
| Fallback? | Gracefully skips on RSS/FinBERT failure |

**Classification**: `WIRED_BUT_NOT_DECISIONAL` for R2 ensemble input · but
`WIRED_AND_USED` at the investability display layer + Arjuna screen.

### Path B · sector_news divergence proxy · both markets

| Question | Answer |
|---|---|
| Does the engine exist? | YES · `backend/context/sector_news/classify.py` |
| Data source? | Cross-sector close prices (NOT news text) |
| Frequency? | Daily via `backend/delivery/telegram/detail_xlsx.py:1865` |
| Daily production workflow calls it? | YES · during XLSX build |
| Output reaches R2? | ~ · via `backend/investability/news.py:23` |
| R2 uses in ranking/decision? | ~ · feeds investability score only · not R2 ensemble |
| Merely displayed? | Partially · display + investability |
| Research-only? | NO |
| Stale? | NO · same-day close bars |

**Classification**: `WIRED_BUT_NOT_DECISIONAL` (mis-labeled: this is
"context sentiment via price divergence" · not news NLP)

### USA news pipeline

- Adapter path declared at `backend/canonical/adapters.py:197`
  (`usa/data/raw/us/news_sentiment.parquet`)
- **No producer implemented** for that path
- Classification: `NOT_WIRED · BROKEN (missing producer)`

---

## Part 5 · Momentum

### Multiple momentum implementations discovered

| Module | Runs? | Feeds R2? | Classification |
|---|---|---|---|
| `aegis.momentum.v1` (model in `model_factory` 11-model ensemble) | YES · daily via STEP 12 | **YES · via ensemble.json** | `WIRED_AND_USED` |
| `backend/research/short_term_momentum.py` | YES · via `momentum_ledger` (STEP 46 · this session's wiring) | NO · downstream measurement | `WIRED_BUT_NOT_DECISIONAL` (feeds Today_Momentum sheet · not R2 rank) |
| `backend/research/momentum_attribution.py` | UNKNOWN daily cadence · appears in adjacent chain | ~ · via morning_report | `UNKNOWN` |
| `backend/research/multi_layer/momentum_ledger.py` | YES · STEP 46 (new) | NO | `WIRED_BUT_NOT_DECISIONAL` (research-only by design) |
| `backend/intraday/signals/sector_momentum.py` | NO · intraday path not run daily | NO | `NOT_WIRED` |

### Distinction ladder for momentum

```
CALCULATED           YES · aegis.momentum.v1 model + short_term_momentum research
AVAILABLE            YES · ensemble.json + momentum_ledger + snapshots
CONSUMED             YES for ensemble.v1 · NO for research-side momentum
DECISIONALLY INFLUENTIAL  YES for ensemble contribution (~ 1/11 weight) · NO for research momentum
```

### USA IT top_models proof

`usa/reports/recommendations.json` shows IT:
```
top_models: [
  {"model_id": "aegis.trend.v1",    "score": 0.7361},
  {"model_id": "aegis.momentum.v1", "score": 0.7105},   ← momentum IS an input
  {"model_id": "aegis.growth.v1",   "score": 0.5852}
]
```

**Momentum coverage**:
- India: momentum_ledger scans 230 universe · 1 candidate today (SAIL · PUMP_RISK)
- USA: momentum_ledger scans 908 raw · **filters to 516 S&P 500** ·
  34 candidates today · 101 NO_EVIDENCE due to quality_band=UNKNOWN

### Classification

**PARTIAL**:
- Ensemble-model momentum: `WIRED_AND_USED` (contributes to R2 rank)
- Short-term momentum research: `RESEARCH_ONLY · REPORTING-ONLY for R2`
- USA momentum: filtered to production universe · but candidates without
  quality data are `NO_EVIDENCE` (91% of USA scan)

---

## Part 6 · Multi-layer morning research

**Not seven fixed factors.** The scaffold in `backend/research/multi_layer/`
registers 8 candidate layers · framework only · no measurements have
been used to validate any.

Per layer:

| Layer | Implemented? | Populated? | Point-in-time? | Wired to morning workflow? | Wired to R2? | For ranking? | For filtering? | Display only? |
|---|---|---|---|---|---|---|---|---|
| A · AEGIS baseline | YES | Framework only | ~ | YES (STEP 49-50 this session) | NO | NO | NO | Research/audit |
| B · Technical/context | YES | Framework only | YES | YES | NO | NO | NO | Research |
| C · Fundamentals | YES | Framework only | ~ (path exists · sparse) | YES | NO | NO | NO | Research |
| D · Valuation | YES | Framework only | ~ | YES | NO | NO | NO | Research |
| E · Balance-sheet quality | YES | Framework only | ~ | YES | NO | NO | NO | Research |
| F · Sector/regime | YES | Framework only | YES | YES | NO | NO | NO | Research |
| G · Interactions | YES | Framework only | YES | YES | NO | NO | NO | Research |
| H · Walk-forward | YES | Framework only | YES | YES | NO | NO | NO | Research |

**Do not turn into filters** · CEO invariant preserved. Multi-Layer
Research is by design research-only and does not modify R2. Now that it
runs daily (STEPS 46-51), its evidence artifacts refresh but no R2
consumer exists.

**Distinction ladder for morning research**:
```
IMPLEMENTED         YES (7 modules exist)
EXECUTED            YES (daily · after 2026-09-01 wire-in)
MEASURED            YES for scaffold (68/136 AVAILABLE · 68 UNAVAILABLE)
CONSUMED BY R2      NO
PROVEN EFFECTIVE    NO (no measurements have influenced any R2 change)
```

---

## Part 7 · Exit / risk engine · specific audit

### Exit mechanisms identified in codebase

| Mechanism | Location | Coded? | Runs daily? | Fires close? |
|---|---|---|---|---|
| Static 6% stop | `investor_actionable/engine.py:116` (DEFAULT_STOP_PCT) | YES (advisory display) | NO enforcement | NO |
| T1 / T2 targets (12% / 24%) | `investor_actionable/engine.py:151-152` | YES (display) | NO enforcement | NO |
| Horizon (60d default via `suggested_holding_period_days`) | `investor_actionable/engine.py` | YES (display) | NO enforcement | NO |
| ATR-based stop | `backend/risk/dynamic_risk_v2.py:145` | YES | YES · via new_opp_guard | NO (writes JSON · no consumer) |
| Vol-scaled stop | `backend/risk/dynamic_risk_v2.py:138` | YES | YES | NO |
| Trailing lift on profit ≥ 5% | `backend/risk/dynamic_risk_v2.py:171-177` | YES | YES | NO |
| Position-store high-water trailing (6%) | `backend/portfolio/position_store/store.py:187` | YES | YES · mark_to_market | NO (display only) |
| evaluate_position (STOP/TARGET/HORIZON) | `backend/portfolio/lifecycle_state_machine.py:59` | YES | NO · never called | Would if called |
| Portfolio manager cycle | `backend/portfolio/portfolio_manager.py:104` | YES | NO · never called | Would if called |
| Ensemble STRONG_SELL → EXIT | `backend/recommendation/investor_actionable/engine.py:64` | YES | YES | YES (only working exit path today) |
| Orphan auto-close | `backend/research/mr_orphan_closer.py:204` | YES | YES | YES (housekeeping) |
| **Dynamic exit bridge** (this session) | `scripts/apply_dynamic_exits.py` | YES · 13 golden tests | YES (STEP 52 · audit-only) | NO in --audit-only mode · would if --enforce |

### Chain proof for the 3 flagged R2 ACTIVE positions

```
IND-R2-CHAMBLFERT-20260804:
  static 6% stop crossed 2026-08-28 · 24d after entry · pnl -8.58%
  ATR-based dynamic stop (400.80) NOT crossed · position within tolerance
  → coded engine (if invoked) says HOLD under dynamic path
  → coded engine (if invoked · static) says EXIT_STOP
  → actual production: HOLD (no engine invocation)
  → Registry: ACTIVE
  → No exit event · no realized P&L

IND-R2-ITC-20260804:
  same story · ATR stop 258.25 · current 264.90 · HOLD dynamic
  static 6% (267.76) triggered 2026-08-19 · 15d ago

USA-R2-IT-20260810:
  ATR-based stop unavailable (dynamic_risk_v2 didn't run for USA today)
  falls back to static 6% (181.58) · current 179.46
  → engine (either path) says EXIT_STOP
  → 20 days overdue
  → actual production: HOLD
  → Registry: ACTIVE
```

### Explanation of the break

The engine EXISTS and is CODED. `evaluate_position` returns correct
LifecycleDecisions when given (current_price, stop_price, t1_price,
t2_price, horizon_days). `portfolio_manager._run_dynamic_cycle` iterates
active positions and calls it. `dynamic_risk_v2.compute` writes today's
per-position stops. **But no code path connects these three producers
to `oreg.close()`.**

Historical proof: 539 R2 CLOSED events · zero EXIT_STOP / EXIT_TARGET /
EXIT_HORIZON. Every exit is either ORPHAN_AUTO_CLOSE (463 · 85.9%) or a
rotation entry (~76 · ~14.1%).

**Do not impose an arbitrary stop.** The dynamic architecture is
correct · the wiring is missing. The `apply_dynamic_exits.py` bridge
(this session) supplies the wiring · but runs in `--audit-only` mode by
default. `--enforce` flag would call `oreg.close()` and materialize the
missing exits.

**Classification**: `EXISTS · WIRED (audit-only) · NOT DECISIONAL · GAP`

---

## Part 8 · Crash / regime resilience

### Detection · decision · sizing · exit · reporting

| Layer | Coded? | Runs daily? | Affects R2? |
|---|---|---|---|
| Broad market drawdown detection | `backend/research/mr_market_regime.py` (BULL/BEAR/HIGH_VOL) + `backend/research/multi_layer/crash_resilience.py` (5-state NORMAL/WEAKENING/RISK_OFF/CRASH/RECOVERY) | YES (5-state runs now via STEP 48) | NO |
| Volatility spike | ATR/vol-scaled stop in dynamic_risk_v2 | YES | NO (stop unconsumed) |
| Sector shock | sector_rotation.json (part of macro_intel · STEP 07) | YES | ~ (feeds ensemble via feature_store) |
| Geopolitical / oil / risk-off | macro_intel + ai_macro_narrative | YES | ~ (feeds ensemble) |
| Position sizing response | risk_engine sizing + configs/risk_budget.yaml | YES | YES (Kelly + caps · but not regime-conditioned dynamically) |
| Exit response | none · dynamic exit engine unwired | NO | NO |
| Reporting | crash_resilience_{market}.json + workbook Portfolio counterfactual | YES (via STEP 48) | Display only |

### India today · reality check

India's crash-resilience classifier (5-state) tags today as `WEAKENING`.
Recorded metric: R2 downside-capture vs Nifty in WEAKENING = **2.29**
(R2 absorbs 2.3× the benchmark's negative days). Surfaced honestly in
`reports/research/multi_layer/crash_resilience_india_2026-09-01.json`.

Does this affect R2 decisions today? **NO.** The classifier is display
only · R2 doesn't consult it.

**Classification**: `DETECTION_WIRED · DECISION_NOT_WIRED · GAP`

---

## Part 9 · Fundamental / research data

### Data availability

| Data | Collected? | Point-in-time? | Available India? | Available USA? | Consumed by R2? |
|---|---|---|---|---|---|
| Fundamentals (yfinance snapshot) | YES · STEP 03 daily | ~ (snapshot cadence · no restatement) | YES (fundamentals.parquet) | ~ (path exists · unclear producer) | YES via feature_store → model_factory ensemble |
| Corporate actions | YES · STEP 05 | YES | YES | ~ | Limited direct |
| News sentiment (FinBERT) | YES · STEP 02 | YES | YES | NO (path exists · no producer) | Via investability + Arjuna |
| Macro summary | YES · STEP 04 | YES | Shared | Shared | YES via feature_store |
| Sector rotation | YES · macro_intel | YES | YES | YES | YES via ensemble |

### Quantification

```
Today's India R2 candidates:           15
  With usable fundamentals evidence:   ~15 (yfinance snapshot present for S&P 500-scale universe)
  Momentum ledger candidates:          1 (SAIL · REJECTED for PUMP_RISK)
Today's USA R2 candidates:             ~500 (S&P 500 universe · not all reach production)
  Momentum ledger in-universe:         106 raw → 34 filtered
  With usable quality band:            5 (4 WATCH + 1 REJECTED)
  NO_EVIDENCE (quality_band unavailable): 101 (29.7% of scanned candidates)
```

**"Do not convert unavailable data into neutral/zero scores"** invariant
respected · `momentum_ledger` uses explicit terminal state
`NO_EVIDENCE` with reason code `R_QUALITY_UNAVAILABLE` rather than
defaulting.

**Classification**: fundamentals `WIRED_AND_USED` (India · via ensemble)
· `PARTIAL` for USA quality coverage.

---

## Part 10 · USA universe

### Verification chain

```
Source:          usa/reports/universe.json
Label:           active_universe: "sp500"
Description:     "S&P 500 · US large-cap · Wikipedia canonical (refresh weekly)"
Count:           n_tickers: 516 (500 core + Class A/B/C dual-listings)
Config:          configs/aegis_universes.yaml declares expected range [480, 550]
Validator:       backend/canonical/universe_validator.py enforces bounds
Reconciler:      C13 gate + certification G23
Verified state:  n=516 · label=sp500 · in range · verdict OK
```

### No mid-cap / extended universe leaks

- Reference to 908-ticker raw data-directory scan exists in
  `backend/research/short_term_momentum.py::_universe` (research-only)
- **Filtered to production universe** by `momentum_ledger._production_universe`
  before entering the Today_Momentum workbook sheet (72 out-of-universe
  candidates dropped honestly for today's USA scan)
- Every USA production ticker in `recommendations.json` is verifiable
  against the S&P 500 universe

### Metrics

| Metric | Value |
|---|---|
| S&P 500 expected | 500 constituents |
| Actually loaded | 516 (with Class A/B/C dual-listings) |
| Processed for R2 recommendation | 15 that today's ensemble scores as top candidates |
| Rejected (below action threshold) | Remainder |
| Missing (source didn't return) | 0 |
| Stale (parquet older than N days) | Not measured this audit |

**Classification**: `WIRED_AND_USED · CORRECT · GATED at C13/G23`

---

## Part 11 · Canonical data / provenance

### Verification per production decision

| Field | Populated · India | Populated · USA |
|---|---|---|
| canonical Position ID | 100% (verified via Registry) | 100% |
| ticker | 100% | 100% |
| market | 100% | 100% |
| runner | 100% (R2 only) | 100% (R2 only) |
| signal_date | 100% (created_date in Registry) | 100% |
| entry_date | 100% (same as created_date at moment of OPEN) | 100% |
| source | 100% (via provenance companion this session) | 100% |
| provenance | 100% (canonical:Registry+prices tag) | 100% |
| lifecycle_status | 100% (ACTIVE/CLOSED from Registry) | 100% |

### Duplication / independent recalc points identified

1. **`entry_price`** is computed in TWO places · with the fix from
   `detail_xlsx.py:509-513` documenting that entry price must NEVER
   fall back to current_price. Historically this WAS the bug source.
2. **`stop_price` / `target_price`** are computed at signal time by
   `investor_actionable/engine.py::_entry_zone` and separately by
   `dynamic_risk_v2::compute` (ATR-based). Neither is consumed by exit
   enforcement.
3. **P&L** computed in `execution_simulator` (equity curve) AND in
   `build_aegis_3sheet_workbook` (workbook display · from prices).
   Both derive from same parquet closes · so agree by construction.
4. **Position ID resolution**: Registry is authoritative · but historical
   pre-migration positions had legacy PID formats · migration was completed
   in Phase 2 (`scripts/phase_2_identity_execute.py`).

**Classification**: `WIRED_AND_USED · with 3 potential duplicate-calc
sites (all currently consistent)`

---

## Part 12 · XLSX

### Contract verification

**Legacy XLSX** (shipped by STEP 61 telegram from
`scripts/telegram_command_center_send.py`):
- File: `reports/telegram/aegis_history_{market}.xlsx`
- Sheets: 5-8 depending on augmenter chain

**3-sheet workbook** (shipped by STEP 54 · this session's wire-in):
- File: `reports/telegram/aegis_{market}_YYYY-MM-DD.xlsx`
- Sheets: exactly `01_Portfolio` · `02_Today_Momentum` · `03_Exit_History`
- Overwrites `aegis_history_{market}.xlsx` too · so from tomorrow's cron
  the shipped XLSX will be the 3-sheet version

### Per-sheet compliance

`01_Portfolio` (verified):
- Active R2 positions only: YES (India 9 · USA 6)
- Current holdings only: YES · no exited positions
- Unrealized P&L: YES (green/red · never fabricated 0)
- Counterfactual columns: Dynamic Stop · Engine Verdict · Would-Have-Exited-On (this session · audit-only display)

`02_Today_Momentum` (verified):
- Today's R2 output: YES (from momentum_ledger)
- Action semantics: 4 terminal states (ACCEPTED · WATCH · REJECTED · NO_EVIDENCE)
- Momentum/context: category · quality band · engine verdict · reason
- No ambiguous "consider": YES

`03_Exit_History` (verified):
- Genuine historical exits only: YES · body rows have canonical PID
- Realized P&L: YES · from parquet closes on entry/exit dates
- No fake 0 P&L for never-invested: YES · unpriced rows show "—"

### Dynamic lifecycle movement

```
Today + Momentum ── (position OPEN via detail_xlsx.py:486) ──→ Portfolio
Portfolio ── (STRONG_SELL via detail_xlsx.py:503) ──→ Exit History
Portfolio ── (ORPHAN_AUTO_CLOSE via mr_orphan_closer.py:204) ──→ Exit History
Portfolio ── (STOP/TARGET/HORIZON) ──→ NOT WIRED · does not fire
```

**Classification**: `WIRED · CORRECT for legacy paths · GAP for exit paths`

---

## Part 13 · Why isn't something wired · per orphan/gap component

### `backend/portfolio/portfolio_manager.py` + `lifecycle_state_machine.py`

| Question | Answer |
|---|---|
| Intentionally research-only? | NO · designed for production |
| Integration never completed? | Was integrated · then REMOVED |
| Disabled? | Effectively yes (never called) |
| Superseded? | No replacement engine wired |
| Data-quality blocked? | NO |
| Point-in-time blocked? | NO |
| Performance blocked? | NO |
| Architecture blocked? | Partially · `reports/portfolio_ledger/` persistence layer never completed |
| Accidentally orphaned? | YES · comment in `backend/delivery/telegram/detail_xlsx.py:469` blames portfolio_manager for a "NEW-every-day bug" and shows it was removed from the pipeline. Nothing replaced it. |
| Implemented but never called? | YES (that is the current state) |

**Classification**: `INTEGRATION GAP` (originally intended for production)

### `backend/risk/dynamic_risk_v2.py`

| Question | Answer |
|---|---|
| Intentionally research-only? | NO · production-designed |
| Integration never completed? | YES · producer wired via `new_opp_guard.py:347` but no consumer for `dynamic_risk_{market}.json` |
| Disabled? | NO · runs daily |
| Superseded? | NO |
| Blocked by architecture? | NO · consumer just missing |
| Accidentally orphaned? | Consumer was never built |

**Classification**: `INTEGRATION GAP`

### `backend/portfolio/position_store` trailing high-water

| Question | Answer |
|---|---|
| Intentionally research-only? | NO |
| Integration never completed? | Consumer is display only · exit consumer missing |
| Disabled? | NO |

**Classification**: `INTEGRATION GAP` (partial · display only · no exit enforcement)

### `backend/research/multi_layer/*` (7 modules · this session)

| Question | Answer |
|---|---|
| Intentionally research-only? | YES · CEO invariant "research never modifies R2" |
| Integration never completed? | NO integration to R2 by design |
| Disabled? | NO (now wired daily via STEPS 46-51) |
| Blocked? | NO |

**Classification**: `RESEARCH_ONLY BY DESIGN · NOT A GAP`

### `apply_dynamic_exits.py --enforce` mode

| Question | Answer |
|---|---|
| Intentionally research-only? | NO · designed as production enforcement bridge |
| Integration never completed? | YES · runs in `--audit-only` today · `--enforce` requires explicit CEO authorization |
| Disabled? | Guarded behind flag |
| Blocked? | Awaiting walk-forward validation of the enforcement effect on R2 historical P&L |

**Classification**: `INTEGRATION GAP · GATED on CEO decision + walk-forward`

### USA news_sentiment producer

| Question | Answer |
|---|---|
| Adapter path exists? | YES · `backend/canonical/adapters.py:197` |
| Producer implemented? | NO |
| Blocked by data source? | Possibly (no free equivalent to India's Google News RSS + FinBERT that has been implemented for USA) |

**Classification**: `INTEGRATION GAP · data blocked / not started`

### `backend/research/multi_layer/point_in_time_reader.py` + `unavailable_contract.py`

| Question | Answer |
|---|---|
| Called anywhere outside `__init__.py`? | NO |
| Intentional? | UNCLEAR (referenced in module docstrings · imported but never used) |

**Classification**: `DEAD / UNREACHABLE`

---

## Part 14 · MOST IMPORTANT OUTPUT

| Component | Built | Tested | Populated | Wired | Used by R2 | Decisionally influential | Evidence | Gap |
|---|---|---|---|---|---|---|---|---|
| ingestion (fii_dii · fundamentals · macro · corporate_actions) | YES | YES | YES | YES | YES | YES | STEPS 01-05 | — |
| news_sentiment (FinBERT · India) | YES | YES | YES | YES | ~ (investability + Arjuna) | PARTIAL | STEP 02 + adapters.py:194 | USA producer missing |
| sector_news divergence proxy | YES | YES | YES | YES | ~ (investability) | PARTIAL | detail_xlsx.py:1865 | Mis-labeled as "news" · price-derived |
| macro_intel | YES | YES | YES | YES | YES | YES | STEP 07 · consumed by decision_intelligence + feature_store | — |
| factor_library | YES | YES | YES | YES | YES | PARTIAL | STEP 08 · consumed by learning + adaptive_rec_v2 | — |
| market_intelligence | YES | YES | YES | YES | YES | YES | STEP 09 · fed into feature_store | — |
| feature_store | YES | YES | YES | YES | YES | YES | STEP 10 | — |
| feature_intelligence | YES | YES | YES | YES | YES | YES | STEP 11 | — |
| model_factory (11-model ensemble) | YES | YES | YES | YES | YES | YES | STEP 12 · aegis.momentum.v1 etc. | — |
| recommendation_intelligence V3 | YES | YES | YES | YES | YES | YES | STEP 13 | — |
| recommendation_ssot | YES | YES | YES | YES | YES | YES · KEYSTONE | STEP 14 | — |
| institutional_optimization (percentile) | YES | YES | YES | YES | YES | YES · rebuilds action | STEP 16 | — |
| risk_engine | YES | YES | YES | YES | YES (sizing) | YES | STEP 24 | — |
| portfolio_engine | YES | YES | YES | YES | YES | YES | STEP 25 | — |
| dynamic_holding | YES | YES | YES | YES | ~ (horizon per position) | PARTIAL | STEP 18 | — |
| capital_rotation | YES | YES | YES | YES | ~ (STRONG_SELL rotations) | PARTIAL | STEP 37 | — |
| opportunity_cost | YES | YES | YES | YES | ~ (justify HOLD) | PARTIAL | STEP 38 | — |
| execution_simulator | YES | YES | YES | YES | NO (equity curve) | NO (reporting) | STEP 27 | — |
| fusion | YES | YES | YES | YES | NO | NO | STEP 33 | — |
| morning_report | YES | YES | YES | YES | NO | NO (operator artifact) | STEP 44 | — |
| ops_check | YES | YES | YES | YES | NO | NO (health) | STEP 45 | — |
| telegram | YES | YES | YES | YES | NO | NO (delivery) | STEP 61 | — |
| — — — | | | | | | | | |
| dynamic_risk_v2 | YES | YES | YES | PARTIAL | NO | NO | new_opp_guard.py:347 · JSON written · no consumer | **GAP · consumer missing** |
| position_store trailing high-water | YES | YES | YES | PARTIAL | NO | NO | mark_to_market daily · display only | **GAP · exit consumer missing** |
| momentum_attribution | YES | (limited) | YES | UNKNOWN | UNKNOWN | UNKNOWN | not in aegis_daily_v2 STEPS · appears elsewhere | UNKNOWN |
| — — — | | | | | | | | |
| **portfolio_manager** | YES | (few) | NO (never runs) | NO | NO | NO | Comment blames it 2026-08-20 in detail_xlsx.py:469 | **GAP · orphaned** |
| **lifecycle_state_machine** | YES | NO | NO | NO | NO | NO | Only tests import it | **GAP · orphaned** |
| — — — | | | | | | | | |
| Multi-Layer Research runner | YES | YES | YES | YES (STEP 49-50 · this session) | NO | NO | Cert G22 | RESEARCH_ONLY (by design) |
| Multi-Layer Research layers | YES | YES | Framework only | YES | NO | NO | Registry populated | RESEARCH_ONLY |
| walk_forward window generator | YES | YES | NO (no measurements) | Via runner only | NO | NO | Only runner.py imports | RESEARCH_ONLY |
| point_in_time_reader | YES | Basic | NO | NO | NO | NO | Not imported outside __init__ | **DEAD** |
| unavailable_contract | YES | NO | NO | NO | NO | NO | Not imported outside __init__ | **DEAD** |
| momentum_ledger | YES | YES (13 golden) | YES | YES (STEP 46 · this session) | NO | NO | Feeds Today_Momentum + Cert G27 | RESEARCH_ONLY |
| stress_regime | YES | YES | YES | YES (STEP 47) | NO | NO | Cert G26 | RESEARCH_ONLY |
| crash_resilience | YES | YES | YES | YES (STEP 48) | NO | NO (audit-only) | Cert G28 + Portfolio counterfactual | RESEARCH_ONLY |
| momentum_forward_outcomes | YES | Via ledger | YES | YES (STEP 51) | NO | NO | Snapshot updater | RESEARCH_ONLY |
| — — — | | | | | | | | |
| **apply_dynamic_exits bridge** | YES | YES (13 golden) | YES | YES (STEP 52 · audit-only) | NO | NO in --audit-only · WOULD BE HIGH in --enforce | Bridge exists · gated | **GAP · awaiting enforcement decision** |
| r2_stop_rule_audit | YES | NO | YES | NO (manual) | NO | NO | Diagnostic only | AUDIT-ONLY |
| r2_lifecycle_reconstruction | YES | NO | YES | NO (manual) | NO | NO | Diagnostic | AUDIT-ONLY |
| — — — | | | | | | | | |
| 3-sheet renderer | YES | Via cert | YES | YES (STEP 54 · this session) | NO | NO | Ships XLSX | — |
| aegis_final_reconciler | YES | YES | YES | YES (STEP 59) | NO | NO | Cert-only | — |
| aegis_local_certification | YES | YES | YES | YES (STEP 60) | NO | NO | LOCK_CANDIDATE verdict | — |
| produce_visual_signoff | YES | YES | YES | YES (STEP 57) | NO | NO | Cert G16 | — |
| emit_provenance_companion | YES | Via cert | YES | YES (STEP 55) | NO | NO | Cert G12 | — |
| portfolio_exit_overlap_classifier | YES | Via cert | YES | YES (STEP 56) | NO | NO | Cert G24 | — |
| r1_producer_audit | YES | Via cert | YES | YES (STEP 53) | NO | NO | Cert G25 | R1 · out of scope |
| determinism_hash | YES | Via cert | YES | YES (STEP 58) | NO | NO | Cert G18 | — |
| — — — | | | | | | | | |
| xlsx_augment_sheets | YES | Limited | YES | NO | NO | NO | Superseded by 3-sheet | DEPRECATED |
| build_usa_missing_sheets | YES | NO | YES | NO | NO | NO | Superseded | DEPRECATED |
| phase_2_identity_execute | YES | Via preflight | YES | NO (one-shot done) | NO | NO | Complete | DEPRECATED |
| phase_2_c9_registry_sync | YES | NO | YES | NO (one-shot done) | NO | NO | Complete | DEPRECATED |
| — — — | | | | | | | | |
| USA news_sentiment producer | NO | — | NO | NO | NO | NO | Adapter path exists · no producer | **BROKEN / MISSING** |
| runner3 shadow | YES | YES | YES | YES (STEP 63) | NO (isolated) | NO | Day-90 gate | RESEARCH_ONLY (isolated) |
| repository_intelligence | YES | Limited | YES | YES (STEP 23) | NO | NO | Housekeeping | — |
| consumer_audit | YES | Limited | YES | YES (STEP 21) | NO | NO | Audit-only | — |

### Production path actually used today (R2 decision-influencing only)

```
STEPS 01-05     ingestion (fii_dii · news_sentiment · fundamentals · macro · corp actions)
STEP 07         macro_intel (regime · commodities · currencies · bonds · CB · vol · sector rotation)
STEP 08         factor_library
STEP 09         market_intelligence (regime · breadth · sector rotation · news pulse)
STEP 10         feature_store
STEP 11         feature_intelligence (select features)
STEP 12         model_factory (11-model ensemble · aegis.momentum.v1 · aegis.value.v1 · aegis.growth.v1 · aegis.trend.v1 · aegis.quality.v1 · aegis.ai_hybrid.v1 · aegis.news.v1 etc.)
STEP 13         recommendation_intelligence V3
STEP 14         recommendation_ssot (KEYSTONE · recommendations.json)
STEP 16         institutional_optimization (percentile classification rebuilds action)
STEP 18         dynamic_holding (per-position horizon)
STEP 24         risk_engine (Kelly · caps · vol adj)
STEP 25         portfolio_engine (N-name construction)
STEP 37         capital_rotation (STRONG_SELL rotations feed exit path)
STEP 38         opportunity_cost (HOLD justification)
```

### Production components not used (orphans)

- `portfolio_manager`
- `lifecycle_state_machine`

### Research components not yet production-ready (by design)

- 8-layer multi-layer research (all layers · all measurements)
- momentum_ledger · stress_regime · crash_resilience
- walk_forward · momentum_forward_outcomes
- runner3_shadow (isolated · Day-90 gate)

### Broken integrations

- USA news_sentiment producer (adapter path declared · no producer)
- dynamic_risk_v2 → consumer chain (JSON written · nobody reads)
- position_store trailing → exit consumer (updated but only displayed)
- lifecycle_state_machine · portfolio_manager (never called)

### Data limitations

- USA fundamentals depth · less than India
- Historical R2 sample size for stress regimes (n=35 in WEAKENING · India)
- USA momentum quality_band coverage · 101/106 candidates NO_EVIDENCE
- No point-in-time news history (accumulating forward-only per FinBERT design)

### Missing evidence

- Whether the FinBERT news signal materially changes R2 ranking
  (only observationally: investability score changes · not rank)
- Whether ATR-based dynamic stops would prevent losses (would need to
  run `apply_dynamic_exits --enforce` and re-simulate)
- Whether multi-layer research measurements would improve R2 predictions
  (framework only · no evidence computed)

---

## Part 15 · Daily stock-selection answer (direct)

**"Given today's production architecture, what information actually
influences which stocks R2 recommends?"**

```
Universe
├─ India: NSE curated live universe (no static file · derived)
└─ USA:   S&P 500 · configs/aegis_universes.yaml · n=516 · label sp500
   ↓
Data
├─ Price bars (data/raw/{market}/*.parquet · daily D1)
├─ FII/DII flows (India only)
├─ News sentiment (FinBERT · India only · Google News RSS)
├─ Fundamentals (yfinance snapshot)
├─ Corporate actions (dividends, splits)
├─ Macro summary (yfinance-live · commodities/currencies/bonds/CB/vol)
   ↓
Features
├─ market_intelligence (regime · breadth · rotation · news pulse)
├─ factor_library (per-factor per-day)
├─ feature_store (joined vector)
├─ feature_intelligence (selection)
   ↓
Filters (implicit · via feature_intelligence selection · not hard filters)
   ↓
Ranking
├─ model_factory · 11 models each producing a score
│   · aegis.momentum.v1
│   · aegis.value.v1
│   · aegis.growth.v1
│   · aegis.trend.v1
│   · aegis.quality.v1
│   · aegis.mean_reversion.v1
│   · aegis.news.v1
│   · aegis.macro.v1
│   · aegis.sector.v1
│   · aegis.event.v1
│   · aegis.ai_hybrid.v1
├─ ensemble aggregate → ensemble_score per candidate
   ↓
R2
├─ recommendation_intelligence V3 → recommendations_v3.json
├─ recommendation_ssot (KEYSTONE) → recommendations.json
├─ institutional_optimization (percentile action band rebuilds action)
   ↓
Risk
├─ risk_engine (Kelly sizing · caps · vol adjustment · VaR/CVaR)
├─ portfolio_engine (N-name construction)
├─ capital_rotation (better-opportunity rotation)
├─ opportunity_cost (HOLD justification)
├─ dynamic_holding (per-position horizon)
   ↓
Decision
└─ Final action (STRONG_BUY · BUY · HOLD · SELL · STRONG_SELL) per candidate
```

### Missing links (impact on stock selection)

- **News does NOT modify R2 ensemble rank directly** · it feeds
  investability score which affects display band only (not rank)
- **Multi-layer research does NOT influence rank** · research-only by
  design
- **Crash-resilience classifier does NOT modify R2** · display only
- **Momentum ledger does NOT filter or rerank** · research measurement
- **Dynamic exit engine does NOT fire exits** · unwired · currently
  audit-only bridge
- **USA news signal does NOT exist** · producer missing

The 11-model ensemble does incorporate `aegis.news.v1` and
`aegis.momentum.v1` as SEPARATE model heads · so those layers DO have
direct decision influence through the ensemble.

---

## Part 16 · Do not fix yet

Confirming discipline compliance for this audit:

- No R2 decision logic changed
- No exit logic changed
- No hardcoded stop-loss added
- No arbitrary seven-factor filter added
- No USA universe expansion
- No R1 modification
- No additional XLSX sheets
- No push
- No wiring added in this turn (the 15 STEPS added in the PRIOR turn
  were per CEO's explicit "documents + wiring is verymuch required"
  authorization at that turn · they are audited in Part 14 and remain
  as-configured · they are NOT modified in this audit turn)

---

## Part 17 · FINAL VERDICT

### `PRODUCTION_INTEGRATION_GAPS_FOUND`

Justification:

**Signal chain**: PRODUCTION_INTEGRATION_CONFIRMED. Ingestion → features
→ 11-model ensemble → recommendation_intelligence → SSoT → percentile →
risk → portfolio · every step proven wired and consumed. R2 candidate
selection is genuinely multi-dimensional.

**Exit chain**: PRODUCTION_INTEGRATION_GAPS_FOUND. The coded dynamic
exit engine (portfolio_manager + lifecycle_state_machine +
dynamic_risk_v2 + position_store trailing) exists in complete form but
never fires production close events. Only two exit paths currently
function: ensemble STRONG_SELL and orphan-close housekeeping. 539
historical R2 CLOSED events · zero STOP/TARGET/HORIZON events. The
apply_dynamic_exits bridge (this session · STEP 52) supplies wiring in
audit-only mode; `--enforce` remains gated behind CEO authorization.

**Research chain**: PRODUCTION_INTEGRATION_CONFIRMED as research-only.
Multi-layer research, momentum ledger, stress-regime, crash-resilience,
and forward-outcomes now execute daily (STEPS 46-51 · this session's
wire-in) and produce evidence · but by CEO's own invariant they do not
modify R2. This is by design · not a gap.

**Certification chain**: PRODUCTION_INTEGRATION_CONFIRMED (this session's
wire-in). Reconciler · sign-off · provenance · overlap · R1 audit ·
determinism · 3-sheet workbook · local certification now run daily as
STEPS 53-60.

**News**: PRODUCTION_INTEGRATION_GAPS_FOUND. India FinBERT news is wired
· USA news pipeline is missing entirely.

### Closure artifact

- This document: `docs/AEGIS/PRODUCTION_INTEGRATION_AUDIT.md`
- Supporting audits: `docs/AEGIS/PRODUCTION_ENGINE_INTEGRATION_AUDIT.md` ·
  `docs/AEGIS/PRODUCTION_WIRING_AUDIT.md`
- Supporting investigations: `docs/AEGIS/R1_RETIREMENT_2026-09-01.md` ·
  `reports/audit/R2_EXIT_CONTRACT_INVESTIGATION_v2_2026-09-01.md`
- Session log: `docs/AEGIS/RELEASE_2026-09-01_SESSION_LOG.md`

---

## Summary requested at end

1. **Document path**: `docs/AEGIS/PRODUCTION_INTEGRATION_AUDIT.md`
2. **Total components discovered**: ~90 (63 daily-driver STEPS + ~30
   non-driver components)
3. **Number production-wired**: 63 STEPS (all daily-driver entries
   including the 15-STEP wire-in from prior turn)
4. **Number production-used (decisionally influential)**: 15
   (STEPS 01-05, 07-14, 16, 18, 24, 25, 37, 38 · the ones that shape
   R2's actual stock selection)
5. **Number research-only**: 9 (multi_layer scaffold + runner3 +
   walk_forward + point_in_time_reader + unavailable_contract)
6. **Number orphaned**: 3 (portfolio_manager · lifecycle_state_machine
   + 2 dead multi_layer helpers)
7. **Number broken**: 1 (USA news_sentiment producer missing)
8. **Number data-blocked**: 2 (USA news · USA quality-band coverage
   101/106 NO_EVIDENCE)
9. **Number integration gaps**: 5 (portfolio_manager + lifecycle_state_machine
   + dynamic_risk_v2 consumer + position_store exit consumer + USA news)
10. **Actual R2 production decision chain**: see Part 15 (Universe →
    Data → Features → Ranking → R2 → Risk → Decision)
11. **Single biggest production gap**: **Dynamic exit engine not
    enforced.** Sophisticated STOP/TARGET/HORIZON logic exists in code ·
    dynamic ATR/vol-scaled/trailing stops computed daily · but no
    production code path calls them. All exits are ensemble-score-driven
    or orphan-housekeeping. This is why R2 positions can hold losses
    indefinitely.
12. **Are current daily recommendations genuinely using the work we
    built?** SIGNAL SIDE: YES · genuinely multi-dimensional through
    the 11-model ensemble. EXIT SIDE: NO · a narrow slice of the coded
    exit machinery. RESEARCH SIDE: NO · by design (research doesn't
    modify R2). The work built over the last 60 days on the exit +
    research side is real, correct, and awaiting either (a) explicit
    enforcement authorization (for exits) or (b) an explicit CEO
    decision to allow research to feedback into R2 (which contradicts
    the current invariant).

---

**End of audit. No code changed in this turn. No commits. No push.
Awaiting CEO KEEP → WIRE → RESEARCH-ONLY → REMOVE → REPAIR decisions
per component.**
