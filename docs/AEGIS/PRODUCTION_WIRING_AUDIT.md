# AEGIS · Production Wiring & Evidence Audit · 2026-09-01

**Scope**: R2 + all supporting engines/layers + daily production pipeline.
**R1 is explicitly parked and out of scope for this audit.**

**Method**: read-only trace of `scripts/aegis_daily_v2.py` (48 STEPS) +
`.github/workflows/*.yml` + grep for producer/consumer chains + 60-day
git history + direct file inspection.

**No code changed. No commits. No push. No R2/exit modification.**

---

## Executive summary (top)

```
TOTAL COMPONENTS DISCOVERED:                    ~90
PRODUCTION_WIRED:                                48   (STEPS in daily driver)
PARTIALLY_WIRED (produces but no consumer):       4
RESEARCH_ONLY (by design):                        9
GENERATES_UNUSED_OUTPUT:                          6
UNREACHABLE (orphans):                            3
DEPRECATED (superseded / one-shot):               5
UNKNOWN — INVESTIGATION REQUIRED:                 3
```

```
INDIA PRODUCTION DEPTH:                          FULL 48-step pipeline
USA PRODUCTION DEPTH:                            REDUCED (own workflow · fewer steps · no news pipeline)
DAILY NEWS:                                       PARTIAL   (India FinBERT via ingest_news_sentiment · USA not built · sector-context is price-divergence proxy)
MOMENTUM:                                         REPORTING ONLY (short-term momentum is not consumed by R2 ranking · momentum research downstream of R2)
MULTI-LAYER RESEARCH:                             RESEARCH_ONLY (scaffold · manual invocation only · not in STEPS)
FUNDAMENTALS:                                     WIRED (ingest_fundamentals feeds feature_store which feeds model_factory ensemble)
RISK ENGINE:                                      WIRED (risk_engine step 24 sizes positions · dynamic_risk_v2 computes but consumer missing)
DYNAMIC EXIT ENGINE:                              NOT WIRED (coded in portfolio_manager + lifecycle_state_machine · never invoked)
PORTFOLIO LIFECYCLE:                              PARTIAL (open + close events fire but only via ensemble STRONG_SELL and orphan-close · no stop/target/horizon path)
P&L:                                              WIRED (execution_simulator computes · morning_report + Telegram render)
```

## Closure verdict

`PRODUCTION PARTIALLY WIRED — GAPS REMAIN`

Justification: the R2 signal chain is genuinely wired end-to-end
(ingestion → features → ensemble → recommendation → SSoT → portfolio →
delivery). However, several sophisticated engines built during the last
60 days generate outputs that no consumer reads — most consequentially
the dynamic exit engine (portfolio_manager + lifecycle_state_machine +
dynamic_risk_v2), which means R2 exits are effectively only ensemble-
score-driven or orphan-driven. Multi-layer research + momentum ledger +
stress/crash-resilience are research-only by design but currently
require manual invocation to produce evidence. Certification proves
today's file existence but not tomorrow's cron output.

---

## 1 · Primary question · answered

**"Of everything AEGIS has built during the last ~60 days, what is
actually wired into the live/current R2 production path, what is
research-only, what is partially wired, what is dead/unreachable, and
what is producing outputs that are generated but never consumed by R2?"**

Answer, with the master inventory table in §3 as evidence:

- **Wired to R2 (actually influencing decisions)**: 48-step chain in
  `scripts/aegis_daily_v2.py` STEPS 01-48. Notably the R2 signal chain:
  ingestion → macro/factor/market intel → feature_store →
  feature_intelligence → model_factory (11-model ensemble) →
  recommendation_intelligence V3 → SSoT guard → institutional_optimization
  → risk_engine → portfolio_engine → fusion → morning_report + Telegram.
- **Research-only (by design)**: multi-layer scaffold, momentum ledger,
  stress-regime, crash-resilience, walk-forward window generator,
  point-in-time reader, runner3 shadow, momentum forward outcomes,
  UNAVAILABLE contract module.
- **Partially wired (runs but output unconsumed)**: dynamic_risk_v2 ·
  position_store trailing stop · sector_news divergence-proxy (mis-labeled) ·
  momentum_attribution.
- **Generates unused output**: apply_dynamic_exits (audit-only default) ·
  emit_provenance_companion · determinism_hash · portfolio_exit_overlap ·
  R1 producer audit · sign-off audit (all certification-only · consumed
  by cert gates but not by decisions).
- **Unreachable orphans**: portfolio_manager + lifecycle_state_machine
  (blamed by comment in `backend/delivery/telegram/detail_xlsx.py:469`
  for a NEW-every-day bug 2026-08-20 and effectively removed) ·
  `backend/research/multi_layer/point_in_time_reader.py` (never called
  outside __init__) · `backend/research/multi_layer/unavailable_contract.py`
  (never called outside __init__).
- **Deprecated/superseded**: xlsx_augment_sheets · build_usa_missing_sheets ·
  Phase 2 identity migration scripts · Phase 2 C9 sync · legacy 8-sheet
  contract tests.

---

## 2 · Production execution chain (actual · from code)

```
GitHub Actions cron (.github/workflows/aegis-daily.yml)
     ↓
scripts/aegis_daily_v2.py --continue                          ← INDIA driver
scripts/telegram_command_center_send.py (via ux030 wrapper)   ← USA workflow
     ↓
──────────────  INGESTION  ──────────────
STEP 01  ingest_fii_dii                     (india/fii_dii.py)
STEP 02  ingest_news_sentiment              (india/news_sentiment.py · REAL FinBERT)
STEP 03  ingest_fundamentals                (india/fundamentals_nse.py · yfinance)
STEP 04  ingest_macro_summary               (backend/ingest/macro_summary_ingest.py)
STEP 05  ingest_corporate_actions           (india/corporate_actions.py)
STEP 06  backend_validation                 (india/backend_validation/run.py)
     ↓
─────────  NORMALIZATION / CONTEXT  ─────────
STEP 07  macro_intel                        (india/macro_intel/run.py)
STEP 08  factor_library                     (india/factor_library/run.py)
STEP 09  market_intelligence                (india/market_intelligence/run.py)
     ↓
─────────  FEATURES + MODELS  ──────────────
STEP 10  feature_store                      (india/feature_store/run.py)
STEP 11  feature_intelligence               (india/feature_intelligence/run.py)
STEP 12  model_factory                      (india/model_factory/run.py · 11 models · ensemble.json)
     ↓
─────────  R2 SIGNAL + DECISION  ──────────
STEP 13  recommendation_intelligence        (india/recommendation_intelligence/run.py · V3)
STEP 14  recommendation_ssot [KEYSTONE]     (backend/recommendation/ssot/guard.py · recommendations.json)
STEP 15  recommendation_lifecycle           (backend/recommendation/lifecycle/run.py)
STEP 16  institutional_optimization         (LOAD-BEARING · rebuilds recs.json with percentile action)
STEP 17  recommendation_deltas
STEP 18  dynamic_holding
STEP 22  recommendation_quality
     ↓
─────────  DECISION INTELLIGENCE  ─────────
STEP 19  macro_decision_impact
STEP 20  portfolio_decision_impact
STEP 21  consumer_audit
STEP 37  capital_rotation                   (feeds STRONG_SELL rotations)
STEP 38  opportunity_cost
     ↓
─────────  RISK / PORTFOLIO / EXECUTION  ────
STEP 24  risk_engine                        (Kelly sizing + caps + AI narrative)
STEP 25  portfolio_engine                   (portfolio_v3.json)
STEP 26  learning_engine
STEP 27  execution_simulator                (equity curve · realized P&L)
     ↓
────────────  EXIT DECISION  ──────────────
(No dedicated exit-engine step. Exits occur only via:
  · ensemble STRONG_SELL propagating through detail_xlsx.py:503 → oreg.close()
  · mr_orphan_closer.py:204 fires oreg.close(reason=ORPHAN_AUTO_CLOSE)
The coded portfolio_manager + lifecycle_state_machine + dynamic_risk_v2
enforcement paths are NOT INVOKED.)
     ↓
─────────  RESEARCH / EVIDENCE  ────────────
STEP 28  adaptive_rec_v2                    (v2.0 confidence rebuild)
STEP 29  validation_v2                      (paper harness + drift)
STEP 30  risk_capital_v2
STEP 31  dna_feedback
STEP 32  knowledge_graph
STEP 33  fusion                             (v2.1 intelligence fusion final decision)
STEP 34  stock_validation
STEP 35  price_context
STEP 36  decision_center
STEP 39  portfolio_attribution
STEP 40  institutional_memory
STEP 41  winner_genome
STEP 42  decision_attribution
STEP 43  benchmark
     ↓
────────────  DELIVERY  ──────────────────
STEP 44  morning_report                     (.md + .html)
STEP 45  ops_check
STEP 46  telegram (ux030)                   → operator
STEP 47  monthly_rollups
STEP 48  runner3_shadow                     (isolated · Day-90 gate not met)
```

---

## 3 · Master inventory (per §3 required table)

Full inventory in `docs/AEGIS/PRODUCTION_ENGINE_INTEGRATION_AUDIT.md` §1.
The compressed version below focuses on the 60-day components. `R1` items
are omitted per instruction.

| Component | Purpose | Location | Exists | Tested | Called by production | Called by R2 | Output consumed by R2 | Production impact | Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| ingest_news_sentiment (FinBERT) | India news NLP daily | india/news_sentiment.py | ✓ | ✓ | STEP 02 daily | ~ (via canonical adapter) | ~ (feeds investability + Arjuna) | MODERATE (India investability) | PRODUCTION_WIRED | aegis_daily_v2.py:63 |
| sector_news divergence proxy | Cross-sector return divergence | backend/context/sector_news/classify.py | ✓ | ✓ | detail_xlsx.py:1865 daily | ✗ | ~ (feeds investability) | LOW · display + investability | PRODUCTION_WIRED (but mis-labeled as "news") | detail_xlsx.py:1865-1869 |
| market_intelligence | Regime/breadth/rotation | india/market_intelligence/run.py | ✓ | ✓ | STEP 09 | ✓ (via feature_store) | ✓ | HIGH | PRODUCTION_WIRED | aegis_daily_v2.py:141 |
| macro_intel | Commodities/currencies/bonds/CB/vol | india/macro_intel/run.py | ✓ | ✓ | STEP 07 | ✓ (via decision_intelligence) | ✓ | HIGH | PRODUCTION_WIRED | aegis_daily_v2.py:111 |
| factor_library | Per-factor per-day rows | india/factor_library/run.py | ✓ | ✓ | STEP 08 | ✓ (via learning_engine · adaptive_rec_v2) | ~ | MODERATE | PRODUCTION_WIRED | aegis_daily_v2.py:130 |
| feature_store | Feature vectors | india/feature_store/run.py | ✓ | ✓ | STEP 10 | ✓ (direct) | ✓ | HIGH | PRODUCTION_WIRED | aegis_daily_v2.py:151 |
| feature_intelligence | Selection | india/feature_intelligence/run.py | ✓ | ✓ | STEP 11 | ✓ | ✓ | HIGH | PRODUCTION_WIRED | aegis_daily_v2.py:159 |
| model_factory | 11 models + ensemble | india/model_factory/run.py | ✓ | ✓ | STEP 12 | ✓ | ✓ | HIGH | PRODUCTION_WIRED | aegis_daily_v2.py:170 |
| recommendation_intelligence V3 | R2 candidate signal | india/recommendation_intelligence/run.py | ✓ | ✓ | STEP 13 | ✓ (produces candidates) | ✓ | HIGH | PRODUCTION_WIRED | aegis_daily_v2.py:181 |
| recommendation_ssot | Publishes recs.json | backend/recommendation/ssot/guard.py | ✓ | ✓ | STEP 14 | ✓ | ✓ | HIGH · KEYSTONE | PRODUCTION_WIRED | aegis_daily_v2.py:202 |
| institutional_optimization | Percentile classification | backend/certification/institutional_optimization_run.py | ✓ | ✓ | STEP 16 | ✓ (rebuilds action) | ✓ | HIGH | PRODUCTION_WIRED | aegis_daily_v2.py:230 |
| risk_engine | Kelly + caps + vol adj | india/risk_engine/run.py | ✓ | ✓ | STEP 24 | ✓ (sizes) | ~ | HIGH | PRODUCTION_WIRED | aegis_daily_v2.py:307 |
| portfolio_engine | N-name construction | india/portfolio_engine/run.py | ✓ | ✓ | STEP 25 | ✓ | ✓ | HIGH | PRODUCTION_WIRED | aegis_daily_v2.py:317 |
| capital_rotation | Rotation plan | backend/recommendation/capital_rotation/run.py | ✓ | ✓ | STEP 37 | ~ (feeds STRONG_SELL) | ~ | MODERATE | PRODUCTION_WIRED | aegis_daily_v2.py:419 |
| opportunity_cost | Justify HOLD | backend/recommendation/opportunity_cost/run.py | ✓ | ✓ | STEP 38 | ~ | ✗ | LOW-MODERATE | PRODUCTION_WIRED | aegis_daily_v2.py:428 |
| morning_report | Consolidated .md/.html | research/morning_report/run.py | ✓ | ✓ | STEP 44 | ✗ | ✗ (delivery only) | HIGH · operator artifact | PRODUCTION_WIRED | aegis_daily_v2.py:476 |
| telegram (ux030) | Operator delivery | scripts/telegram_send_ux030.py | ✓ | ✓ | STEP 46 | ✗ | ✗ | HIGH · operator | PRODUCTION_WIRED | aegis_daily_v2.py:491 |
| — — — — | — — | — | | | | | | | | |
| dynamic_risk_v2 | ATR/vol/trailing stops | backend/risk/dynamic_risk_v2.py | ✓ | ✓ | new_opp_guard.py:347 daily | ✗ | ✗ (writes JSON · nobody reads) | ZERO | PARTIALLY_WIRED | grep: no consumer of dynamic_risk_{market}.json |
| position_store trailing high-water | Daily high-water + stop | backend/portfolio/position_store/store.py + mark_to_market.py | ✓ | ✓ | daily via mark_to_market | ✗ | ✗ (display only) | ZERO exit impact | PARTIALLY_WIRED | detail_xlsx reads for display, no enforcement |
| momentum_attribution | India momentum attribution | backend/research/momentum_attribution.py | ✓ | (limited) | (chain unclear) | ✗ | ✗ | UNKNOWN | UNKNOWN — INVESTIGATION REQUIRED | Not in aegis_daily_v2 STEPS · may run in adjacent chain |
| — — — — | — — | — | | | | | | | | |
| **portfolio_manager** | Iterate ACTIVE · call evaluate_position · apply_decision | backend/portfolio/portfolio_manager.py | ✓ | (few) | ✗ | ✗ | ✗ | ZERO (was intended HIGH) | UNREACHABLE | Comment detail_xlsx.py:469 removed it; grep: no importer outside backend/portfolio/ |
| **lifecycle_state_machine** | evaluate_position (STOP/TARGET/HORIZON) | backend/portfolio/lifecycle_state_machine.py | ✓ | ✗ | ✗ | ✗ | ✗ | ZERO | UNREACHABLE | Grep: only portfolio_manager + apply_dynamic_exits bridge use it |
| — — — — | — — | — | | | | | | | | |
| Multi-Layer Research runner | Discovery framework | backend/research/multi_layer/runner.py | ✓ | ✓ | ✗ (manual only) | ✗ | ✗ | ZERO for decisions | RESEARCH_ONLY | Not in aegis_daily_v2 · consumed only by cert G22 |
| Multi-Layer Research layers | Candidate registry | backend/research/multi_layer/layers.py | ✓ | ✓ | ✗ | ✗ | ✗ | ZERO | RESEARCH_ONLY | Same |
| walk_forward | Window generator | backend/research/multi_layer/walk_forward.py | ✓ | ✓ | via runner.py only | ✗ | ✗ | ZERO | RESEARCH_ONLY | Only runner.py imports |
| point_in_time_reader | Point-in-time DR | backend/research/multi_layer/point_in_time_reader.py | ✓ | (basic) | ✗ | ✗ | ✗ | ZERO | UNREACHABLE | Not imported anywhere except __init__ |
| unavailable_contract | UNAVAILABLE sentinel | backend/research/multi_layer/unavailable_contract.py | ✓ | ✗ | ✗ | ✗ | ✗ | ZERO | UNREACHABLE | Not imported anywhere except __init__ |
| momentum_ledger | 4 terminal states + prod-universe filter | backend/research/multi_layer/momentum_ledger.py | ✓ | ✓ (13 golden) | ✗ (manual) | ✗ | ✗ | ZERO for R2 decisions · displayed in Today_Momentum sheet | RESEARCH_ONLY | Not in aegis_daily_v2 · consumed only by cert G27 + workbook |
| stress_regime | Reuses mr_market_regime · per-regime R2 P&L | backend/research/multi_layer/stress_regime.py | ✓ | ✓ | ✗ (manual) | ✗ | ✗ | ZERO for decisions | RESEARCH_ONLY | Cert G26 only |
| crash_resilience | 5-state NORMAL/WEAKENING/RISK_OFF/CRASH/RECOVERY | backend/research/multi_layer/crash_resilience.py | ✓ | ✓ | ✗ (manual) | ✗ | ✗ | ZERO (audit-only) | RESEARCH_ONLY | Cert G28 + counterfactual column |
| momentum_forward_outcomes | 1/3/5/10/20d fills | backend/research/multi_layer/momentum_forward_outcomes.py | ✓ | (via ledger) | ✗ (manual) | ✗ | ✗ | ZERO | RESEARCH_ONLY | Not in STEPS |
| — — — — | — — | — | | | | | | | | |
| apply_dynamic_exits bridge | Wires evaluate_position to Registry via oreg.close | scripts/apply_dynamic_exits.py | ✓ | ✓ (13 golden) | ✗ (manual · audit-only default) | ✗ | ✗ | ZERO in --audit-only · WOULD BE HIGH in --enforce | AUDIT_ONLY | Not in aegis_daily_v2 |
| r2_stop_rule_audit | Diagnostic | scripts/r2_stop_rule_audit.py | ✓ | ✗ | ✗ (manual) | ✗ | ✗ | ZERO | AUDIT_ONLY | Not in STEPS |
| r2_lifecycle_reconstruction | Diagnostic | scripts/r2_lifecycle_reconstruction.py | ✓ | ✗ | ✗ (manual) | ✗ | ✗ | ZERO | AUDIT_ONLY | Not in STEPS |
| — — — — | — — | — | | | | | | | | |
| 3-sheet renderer | 01_Portfolio · 02_Today_Momentum · 03_Exit_History | scripts/build_aegis_3sheet_workbook.py | ✓ | ✓ (via cert) | ✗ (manual) | ✗ | ✗ | ZERO · legacy XLSX still ships | GENERATES_UNUSED_OUTPUT (in production terms) | Cert-only consumer today |
| aegis_final_reconciler | 21-check reconciliation | scripts/aegis_final_reconciler.py | ✓ | ✓ | ✗ (manual) | ✗ | ✗ | ZERO for decisions | CERTIFICATION_ONLY | Not in STEPS |
| aegis_local_certification | 50-gate cert | scripts/aegis_local_certification.py | ✓ | ✓ | ✗ (manual) | ✗ | ✗ | ZERO for decisions | CERTIFICATION_ONLY | Not in STEPS |
| produce_visual_signoff | 10-check audit | scripts/produce_visual_signoff.py | ✓ | ✓ | ✗ (manual) | ✗ | ✗ | ZERO | CERTIFICATION_ONLY | Cert G16 only |
| emit_provenance_companion | Position-ID resolution per row | scripts/emit_provenance_companion.py | ✓ | (via cert) | ✗ (manual) | ✗ | ✗ | ZERO for decisions | GENERATES_UNUSED_OUTPUT | Cert G12 only |
| portfolio_exit_overlap_classifier | 5-way classifier | scripts/portfolio_exit_overlap_classifier.py | ✓ | (via cert) | ✗ (manual) | ✗ | ✗ | ZERO | CERTIFICATION_ONLY | Cert G24 |
| r1_producer_audit | Producer-wide retirement proof | scripts/r1_producer_audit.py | ✓ | (via cert) | ✗ (manual) | ✗ | ✗ | R1 evidence · not R2 | CERTIFICATION_ONLY | Cert G25 |
| determinism_hash | Data-only hash | scripts/determinism_hash.py | ✓ | (via cert) | ✗ (manual) | ✗ | ✗ | ZERO | CERTIFICATION_ONLY | Cert G18 |
| — — — — | — — | — | | | | | | | | |
| xlsx_augment_sheets | Legacy augmenter | scripts/xlsx_augment_sheets.py | ✓ | (limited) | ✗ | ✗ | ✗ | ZERO | DEPRECATED (superseded by 3-sheet) | Not in STEPS |
| build_usa_missing_sheets | Legacy USA synth | scripts/build_usa_missing_sheets_from_registry.py | ✓ | ✗ | ✗ | ✗ | ✗ | ZERO | DEPRECATED | Not in STEPS |
| phase_2_identity_execute | Migration one-shot | scripts/phase_2_identity_execute.py | ✓ | (via preflight) | ✗ (one-shot done) | ✗ | ✗ | ZERO (complete) | DEPRECATED | One-time complete |
| phase_2_c9_registry_sync | Sync one-shot | scripts/phase_2_c9_registry_sync.py | ✓ | ✗ | ✗ (one-shot done) | ✗ | ✗ | ZERO (complete) | DEPRECATED | One-time complete |
| — — — — | — — | — | | | | | | | | |
| runner3_shadow | Isolated shadow runner | backend/recommendation/runner3/run.py | ✓ | ✓ | STEP 48 daily | ✗ (isolated) | ✗ | ZERO (Day-90 gate not met) | RESEARCH_ONLY (isolated) | aegis_daily_v2.py:519 |

---

## 4 · Actual call chains for PRODUCTION_WIRED components

### R2 signal chain (proven end-to-end)

```
aegis_daily_v2.py
   → STEP 12 model_factory (india/model_factory/run.py)
     → reports/ensemble.json
   → STEP 13 recommendation_intelligence (india/recommendation_intelligence/run.py)
     → reports/recommendations_v3.json
   → STEP 14 recommendation_ssot (backend/recommendation/ssot/guard.py)
     → reports/recommendations.json  ← canonical R2 output
   → STEP 16 institutional_optimization (backend/certification/institutional_optimization_run.py)
     → rebuilds recs.json with post-percentile action
   → STEP 24 risk_engine (india/risk_engine/run.py)
     → reports/sized_positions.json
   → STEP 25 portfolio_engine (india/portfolio_engine/run.py)
     → reports/portfolio_v3.json
   → STEP 33 fusion (research/adaptive_rec_v2/run_fusion.py)
     → reports/investment_intelligence.json
   → STEP 44 morning_report → operator .md/.html
   → STEP 46 telegram → operator delivery
```

### Registry open chain (proven)

```
telegram_command_center_send.py
   → detail_xlsx.py:486 during XLSX build
     → _oreg.get_or_create(root, market, R2, ticker, asof, ...)
     → assigns canonical opportunity_id
     → Registry updated
```

### Registry close chain (proven · two paths only)

```
Path 1 · ensemble score → EXIT
  recommendation_ssot → recs.json with recommendation=STRONG_SELL
    → detail_xlsx.py Status column = "EXIT"
      → detail_xlsx.py:503 fires _oreg.close(reason=exit_reason)
        → Registry state ACTIVE → CLOSED

Path 2 · housekeeping · position vanished from feed
  mr_orphan_closer.py:204 (invoked from unclear driver · likely daily)
    → _oreg.close(reason="ORPHAN_AUTO_CLOSE")
      → Registry state ACTIVE → CLOSED
```

**Chain stops after these two paths. No STOP/TARGET/HORIZON pathway
exists in production.** `OUTPUT GENERATED BUT NOT CONSUMED` applies to
`dynamic_risk_v2` and `position_store.current_stop`.

---

## 5 · News engine · specific audit

**Two distinct paths coexist:**

### Path A · Real FinBERT news (India only)

1. Executes every production day? **YES** · STEP 02 in aegis_daily_v2
2. Sources: **Google News RSS per stock**
3. Timestamp: as-of date per row
4. Structured features: **YES** · positive/negative/neutral per stock
5. Stored: `data/raw/india/news_sentiment.parquet` (append-only)
6. R2 reads it? **PARTIAL** · via `backend/canonical/adapters.py:194` and `india/run_arjuna.py:26`
7. Can news change ranking? **~** · feeds investability scoring which affects display band · not R2 ensemble input
8. Can news suppress a candidate? **NO** direct suppression
9. Can news alter risk/exit? **NO**
10. Merely written to report? **PARTIAL** · read by investability + Arjuna but not by R2 ensemble

**Code path evidence**:
```
STEP 02 (india/news_sentiment.py)
  → data/raw/india/news_sentiment.parquet
  → backend/canonical/adapters.py:194 (canonical loader)
  → india/run_arjuna.py:26 (Arjuna screen)
```

### Path B · sector_news divergence proxy (both markets)

1. Executes daily? **YES** · via `detail_xlsx.py:1865`
2. Sources: cross-sector close prices (NO news text)
3. Method: return divergence
4. Engine label: `aegis.context.sector_news.v0.1_divergence`
5. Output: `reports/context/sector_news.json` + `reports/ai_news_narrative.json`
6. R2 reads it? **~** · via `backend/investability/news.py:23`
7. Affects R2 ensemble? **NO** · affects investability score only

**Verdict**: News is **PARTIAL** · India has real FinBERT signal that
reaches investability scoring · USA has no news pipeline at all · sector
"news" is a price-derived proxy mis-labeled as news · none of it modifies
the R2 ensemble output directly.

---

## 6 · Momentum · specific audit

**Multiple momentum implementations exist**:

| Module | Runs daily? | Consumer | Affects R2? |
|---|---|---|---|
| `backend/research/short_term_momentum.py` (230/908 universe) | NO · manual | momentum_ledger + workbook | NO |
| `backend/research/short_term_momentum_backtest.py` | NO · manual | Research report | NO |
| `backend/research/momentum_attribution.py` | UNKNOWN (may run in adjacent chain) | morning_report · research | UNKNOWN |
| `backend/intraday/signals/sector_momentum.py` | NO (intraday path not run daily) | Intraday engine | NO |
| `aegis.momentum.v1` model in model_factory (11 models) | YES · via STEP 12 | ensemble.json | **YES · this IS the momentum component of R2** |

**Trace** (proven):
```
raw market data → factor_library → feature_store
                                    → feature_intelligence
                                    → model_factory
                                       → aegis.momentum.v1 (one of 11 models)
                                       → contributes to ensemble.json
                                       → recommendation_intelligence V3
                                       → R2 decision
```

**Verdict**: Momentum influences R2 through the **model-factory ensemble
(`aegis.momentum.v1`)** — proven in USA IT's `top_models` output:
`aegis.momentum.v1 · score=0.7105`. The **separate `short_term_momentum`
research module and the momentum ledger scaffold do NOT affect R2** ·
they are downstream of R2 (measurement · not input).

**MOMENTUM IS PARTIALLY WIRED** · model-factory momentum is wired ·
research-side momentum scoring/ledger is reporting-only.

---

## 7 · Multi-layer research · specific audit

Every module in `backend/research/multi_layer/` was authored in the current session (2026-09-01).

| Layer | Feature/data used | Point-in-time safe? | Measurements produced? | India? | USA? | R2 consumes? | Historical evidence? | Walk-forward validated? |
|---|---|---|---|---|---|---|---|---|
| A · AEGIS baseline | reports/recommendations.json | ~ (uses current file) | Framework only | ✓ | ✓ | ✗ | Scaffold only | ✗ |
| B · technical/context | data/raw/*.parquet + reports/context/* | ✓ (parquet asof) | Framework only | ✓ | ✓ | ✗ | Scaffold only | ✗ |
| C · fundamentals | data/fundamentals/*.parquet | ~ (path exists · sparse) | Framework only | ~ | ✗ | ✗ | Scaffold only | ✗ |
| D · valuation | data/fundamentals/*.parquet | Same | Framework only | ~ | ✗ | ✗ | Scaffold only | ✗ |
| E · balance-sheet quality | data/fundamentals/*.parquet | Same | Framework only | ~ | ✗ | ✗ | Scaffold only | ✗ |
| F · sector/regime | reports/context/sector_news.json + global_overnight.json | ✓ | Framework only | ✓ | ~ | ✗ | Scaffold only | ✗ |
| G · interactions | backend/feature_store | ✓ | Framework only | ✓ | ✓ | ✗ | Scaffold only | ✗ |
| H · walk-forward | reports/backtest/*.jsonl | ✓ | Framework only | ~ | ✗ | ✗ | Scaffold only | ✗ |

**Distinction table**:
```
IMPLEMENTED:       Yes (7 modules exist)
EXECUTED:          Only manually (via python -m backend.research.multi_layer.*)
MEASURED:          Only when the manual invocations run (evidence: today's LOCK_CANDIDATE files)
CONSUMED BY R2:    NO
PROVEN EFFECTIVE:  NO (framework only · no measurements have been used to validate any layer)
```

**MULTI-LAYER RESEARCH IS RESEARCH-ONLY BY DESIGN · but currently the
research doesn't run daily either**.

---

## 8 · Daily production decision trace · real candidates

### India · GNFC (STRONG_BUY · rank 1 · R2 ACTIVE as of 2026-09-01)

```
ticker:                    GNFC.NS (Gujarat Narmada Valley Fertilizers)
universe eligibility:      NSE curated (India live universe · derived)
raw data:                  data/raw/india/GNFC.NS_D1.parquet (2026-08-06 to 2026-09-01)
news/context:              FinBERT news_sentiment.parquet (some coverage) + sector_news.json ("Chemicals": -0.209)
momentum:                  ensemble input · aegis.momentum.v1 score contributes
fundamentals:              feature_store joins fundamentals.parquet (yfinance ingest)
valuation:                 top_model: aegis.value.v1 score=0.9153  ← DOMINANT
research layers (multi-layer): NOT CONSUMED
ranking:                   rank=1
R2 ensemble score:         0.3216
R2 confidence:             0.3409
R2 action:                 STRONG BUY
entry/reference:           current_price=571.9 · entry_zone={"current": 571.9, "note": "hold · no entry"}
stop/target:               NONE (action is STRONG_BUY but note=hold · so entry_zone doesn't include stop_loss/target)
portfolio lifecycle:       Registry IND-R2-GNFC-20260806-03d0a7 · ACTIVE since 2026-08-06 · 26 days
Dynamic exit engine:       NOT INVOKED (dynamic_risk_v2 computed a stop but nobody reads it)
```

### USA · IT (Gartner · HOLD · R2 ACTIVE · flagged EXIT_STOP counterfactual)

```
ticker:                    IT (Gartner Inc)
universe eligibility:      S&P 500 (n=516 · sp500 label)
raw data:                  usa/data/raw/us/IT_D1.parquet (2026-08-10 to 2026-08-24)
news/context:              sector_news divergence proxy only · no USA FinBERT
momentum:                  aegis.momentum.v1 score=0.7105  ← STRONG
fundamentals:              (USA fundamentals path exists · unclear if it feeds R2)
valuation:                 aegis.growth.v1 score=0.5852
research layers:           NOT CONSUMED
ranking:                   in top-N (exact rank not shown in HOLD entry)
R2 action:                 HOLD
entry_zone:                {"current": 193.68, "note": "hold · no entry"}
stop/target:               NONE displayed for HOLD
portfolio lifecycle:       Registry USA-R2-IT-20260810-b5fd37 · ACTIVE since 2026-08-10 · 22 days
Dynamic exit engine:       NOT INVOKED
  - static 6% stop would trigger at 181.58 · current 179.46 · TRIGGERED 2026-08-12 (20d overdue)
  - dynamic_risk_v2 usa output does not exist (never runs for USA)
  - counterfactual column in workbook shows "EXIT_STOP (audit-only) · 2026-08-12"
```

**Both candidates confirm the pattern**: R2 ranks + acts via
model-factory ensemble → SSoT → institutional_optimization. Every
other engine we built either (a) is not consumed, (b) is displayed
only, or (c) is measurement-downstream of R2.

---

## 9 · Exit engine · specific audit (§9 rule: NO hardcoded stop)

**Established in `docs/AEGIS/R2_EXIT_CONTRACT_INVESTIGATION_v2_2026-09-01.md`**:

| Component | Type | Runs daily? | Fires close? |
|---|---|---|---|
| `evaluate_position` (STOP/TARGET/HORIZON) | Coded engine | NO · never called | Would · if called |
| `portfolio_manager._run_dynamic_cycle` | Orchestrator for evaluate_position | NO · never called | Would · if called |
| `dynamic_risk_v2.compute` | ATR / vol-scaled / trailing-lift stops | YES · new_opp_guard.py:347 | NO · JSON only · no consumer |
| `position_store` high-water + trailing | Daily update via mark_to_market | YES | NO · display only |
| `detail_xlsx.py:503` | STRONG_SELL → oreg.close | YES | YES · but only ensemble-driven |
| `mr_orphan_closer.py:204` | Housekeeping | YES | YES · ORPHAN_AUTO_CLOSE only |
| `apply_dynamic_exits.py` (this session · bridge) | Bridges evaluate_position → oreg.close | NO · manual · audit-only default | Would · in --enforce mode |

**Historical evidence (539 R2 CLOSED events all-time)**:
- 463 (85.9%) · ORPHAN_AUTO_CLOSE
- ~76 (~14.1%) · rotation-driven (ROTATION → NEW · +Xpp ALPHA)
- **0** · STOP / TARGET / HORIZON

**Documented threshold exists but is not enforced.** This is a defect ·
reported honestly. **No hardcoded stop introduced.**

Per-position status of the 3 flagged R2 positions:

| Position | Coded engine says (if invoked) | Actual production state |
|---|---|---|
| IND-R2-CHAMBLFERT-20260804 | Static 6% would EXIT_STOP 2026-08-28 · dynamic ATR (400.80) says HOLD | ACTIVE · pnl -8.58% |
| IND-R2-ITC-20260804 | Static 6% would EXIT_STOP 2026-08-19 · dynamic ATR (258.25) says HOLD | ACTIVE · pnl -7.00% |
| USA-R2-IT-20260810 | Static 6% would EXIT_STOP 2026-08-12 · no USA dynamic_risk output · defaults to static | ACTIVE · pnl -7.10% |

**Dynamic engine's verdict is more nuanced than a static stop would be.**
Under the dynamic ATR path, only USA IT would fire · India CHAMBLFERT
and ITC would be HELD because their volatility warrants wider stops.

---

## 10 · P&L / Portfolio / Exit trace (canonical lifecycle proof)

For the 3 flagged R2 positions the canonical chain is:

- **Entry**: Registry OPEN via `oreg.get_or_create` at `detail_xlsx.py:486`
  (proven for all 3 · position IDs exist)
- **Active position**: Registry ACTIVE for all 3 · included in current
  01_Portfolio (proven · in today's XLSX)
- **Mark-to-market**: parquet close read each day for display · position_store
  updates high_water (proven · runs daily)
- **Exit trigger evaluation**: **NOT EVALUATED** (this is the defect)
- **Exit event**: none for these 3 · none will be for these 3 unless
  ensemble emits STRONG_SELL or they become orphan-stale

**Anomalies checked**:
- Active negative P&L: yes · but explained (no exit enforcement)
- Missing P&L: 0 (verified via cert G13 · 100% Position ID coverage)
- Zero P&L in Exit History: 0 fabricated · all 0-values would be
  UNPRICED (renderer emits "—" not "0" for unpriced)
- Exits without investment: 0 (all Exit History rows come from Registry
  CLOSED events · every CLOSED had a prior ACTIVE)
- Positions without entry: 0
- Exits not removed from Portfolio: 0 (proven by C9)
- Portfolio positions that should have exited: **3** (per coded engine ·
  never invoked)
- Duplicate lifecycle instances: 0 (proven by C7)

**A `0 P&L` exit does not represent a non-invested signal in the current
workbook** · the renderer explicitly uses "—" / "UNAVAILABLE" for
non-computable cells (verified in `scripts/build_aegis_3sheet_workbook.py`
lines 175-190).

---

## 11 · Built but not wired (per §11 spec)

For each unwired component:

### `backend/portfolio/portfolio_manager.py` + `lifecycle_state_machine.py`
1. Why built: Phase 2 R006 · dynamic exit engine
2. Why not wired: comment `detail_xlsx.py:469` blames portfolio_manager for
   a NEW-every-day bug (Zydus / ONGC / HINDUNILVR appearing NEW every day)
3. Research-only? NO · designed for production
4. Data availability blocker? NO
5. Architecture blocker? Possibly (portfolio_ledger persistence layer never
   completed · `reports/portfolio_ledger/` doesn't exist)
6. Orchestration blocker? YES · removed from pipeline · nothing replaced it
7. Quality/reliability blocker? YES · the NEW-every-day bug was cited
8. Superseded? NO · no replacement engine exists
9. Simply forgotten? PARTIALLY (comment implies "we'll come back to it" ·
   nobody did)
10. Evidence: git blame on `detail_xlsx.py:469` shows 2026-08-20 commit
    context

### `backend/research/multi_layer/*` (7 modules · this session)
1. Why built: CEO directive · multi-layer research framework
2. Why not wired: not added to `scripts/aegis_daily_v2.py` STEPS
3. Research-only? YES (per CEO invariant "research never modifies R2")
4. Data availability blocker? NO · framework runs today
5. Architecture blocker? NO · fully additive
6. Orchestration blocker? YES · missing 5-6 lines in aegis_daily_v2.py
7. Quality/reliability blocker? NO · 13 golden tests pass
8. Superseded? NO
9. Simply forgotten? Not forgotten · deliberately not wired because CEO
   asked for research-only invariant to be preserved
10. Evidence: `docs/AEGIS/PRODUCTION_ENGINE_INTEGRATION_AUDIT.md` §19-I
    lists exact wiring lines needed

### `scripts/apply_dynamic_exits.py` (this session)
1. Why built: this session · to wire the existing dynamic exit engine
2. Why not wired: awaiting CEO decision on enforcement · currently `--audit-only`
3. Research-only? NO · designed as production bridge
4. Data availability blocker? NO
5. Architecture blocker? NO · bridge is fully additive
6. Orchestration blocker? YES · not added to STEPS
7. Quality/reliability blocker? NO · 13 golden tests pass · manual audit-only
   run today produced correct decisions
8. Superseded? NO
9. Simply forgotten? NO · intentionally held pending CEO decision
10. Evidence: this session's investigation reports

### All certification-only scripts (reconciler · sign-off · provenance · audits)
1. Why built: to verify system invariants
2. Why not wired: `REASON NOT ESTABLISHED — OWNER DECISION REQUIRED`
   (they could reasonably run daily but nobody has added them)
3. Research-only? NO · they're operations/quality
4. Data availability blocker? NO
5. Architecture blocker? NO
6. Orchestration blocker? YES
7. Quality/reliability blocker? NO
8. Superseded? NO
9. Simply forgotten? Likely · no explicit decision documented
10. Evidence: `scripts/aegis_daily_v2.py` STEPS list has no entry for
    reconciler / sign-off / provenance / audits

### `scripts/build_aegis_3sheet_workbook.py`
1. Why built: this session · CEO 3-sheet workbook spec
2. Why not wired: legacy telegram_command_center_send.py still emits the
   shipped XLSX · nobody swapped in the new renderer
3. Research-only? NO · designed to replace legacy renderer
4. Data availability blocker? NO
5. Architecture blocker? MEDIUM · replacing the Telegram delivery would
   require pointing `telegram_send_ux030` at the new file
6. Orchestration blocker? YES
7. Quality/reliability blocker? NO · cert 50/50 today
8. Superseded? Legacy renderer supersedes it in production despite being
   older architecturally
9. Simply forgotten? Not forgotten · not yet promoted
10. Evidence: STEP 46 telegram in aegis_daily_v2.py references legacy path

---

## 12 · Wired but ineffective (per §12 spec)

| Component | Wired to | Output ignored by | Classification |
|---|---|---|---|
| `dynamic_risk_v2.compute` | new_opp_guard.py daily | Nobody reads `reports/context/dynamic_risk_{market}.json` | GENERATES_UNUSED_OUTPUT |
| `position_store` trailing high-water | Daily via mark_to_market | Detail_xlsx reads for DISPLAY only · no exit consumer | GENERATES_UNUSED_OUTPUT (for exit purposes) |
| `sector_news` divergence proxy | detail_xlsx.py:1865 daily | Feeds investability but does not modify R2 ensemble | PARTIALLY_WIRED (feeds cosmetic layer only) |
| `repository_intelligence` | STEP 23 daily | Ops-only · nothing decision-affecting | PARTIALLY_WIRED (housekeeping) |
| `runner3_shadow` | STEP 48 daily | Isolated by design (Day-90 gate) · consumed by nothing | RESEARCH_ONLY |
| `consumer_audit` | STEP 21 daily | Reports · not consumed by decisions | PARTIALLY_WIRED (audit) |

---

## 13 · Actual production contribution measurement

For the R2 signal-critical PRODUCTION_WIRED components:

| Component | Candidates affected | Decisions changed | Ranking changes | Timing changes | Risk changes |
|---|---|---|---|---|---|
| model_factory ensemble | ALL (15 recs today) | ALL (source of action band) | ALL (rank comes from ensemble) | ✓ (entry timing via ensemble score) | ~ (via risk sizing) |
| institutional_optimization percentile | ALL (rebuilds action) | ALL (post-percentile action) | (preserves rank) | ~ | ~ |
| investability score (fed by news + divergence) | Displayed on every rec | Affects display band | ✗ (not primary rank) | ✗ | ✗ |
| capital_rotation | Up to 10 rotation proposals | Feeds STRONG_SELL exits | ~ | ~ (rotation timing) | ~ |
| dynamic_holding | Sets per-position horizon | Affects horizon display | ✗ | (horizon days) | ✗ |
| Multi-layer research | 0 · not consumed by R2 | 0 | 0 | 0 | 0 |
| Momentum ledger | 0 · not consumed by R2 | 0 | 0 | 0 | 0 |
| Crash resilience | 0 · not consumed by R2 | 0 | 0 | 0 | 0 |
| Dynamic exit engine | 0 · not invoked | 0 (0 EXIT_STOP events ever fired) | 0 | 0 | 0 |

`IMPACT NOT MEASURABLE FROM CURRENT DATA` applies to counterfactual
"how much would decisions change if X were wired" questions · we don't
have the counterfactual dataset.

---

## 14 · Production reality · the critical question answered

### A. Actually influencing R2

- All 12 ingestion + normalization steps (fii_dii · news_sentiment ·
  fundamentals · macro_summary · corporate_actions · backend_validation ·
  macro_intel · factor_library · market_intelligence)
- All 3 feature steps (feature_store · feature_intelligence)
- model_factory 11-model ensemble (including `aegis.momentum.v1` ·
  `aegis.value.v1` · `aegis.growth.v1` · `aegis.trend.v1` · etc.)
- recommendation_intelligence V3 + SSoT guard (recommendations.json ·
  KEYSTONE)
- institutional_optimization (percentile action rebuild · LOAD-BEARING)
- risk_engine + portfolio_engine
- capital_rotation (STRONG_SELL rotations)
- opportunity_cost
- dynamic_holding (per-position horizon)
- **investability** (fed by FinBERT news + sector divergence proxy)

### B. Running but not influencing R2

- dynamic_risk_v2 (writes JSON · no consumer)
- position_store trailing stop (display only)
- sector_news divergence proxy (feeds only investability score · not R2 ensemble input)
- consumer_audit (report only)
- repository_intelligence (report only)
- ops_check (health only)

### C. Research-only

- backend/research/multi_layer/* (7 modules)
- momentum_ledger + momentum_forward_outcomes
- stress_regime + crash_resilience
- runner3_shadow
- short_term_momentum (research)

### D. Implemented but not executed (in production)

- portfolio_manager
- lifecycle_state_machine
- apply_dynamic_exits (audit-only default)
- 3-sheet workbook renderer
- 6 certification-only scripts (reconciler · sign-off · provenance ·
  determinism · overlap · r1-audit)

### E. Broken / partially wired

- USA news_sentiment producer (path declared in canonical adapter · no producer)
- Legacy 8-sheet workbook contract (superseded)

### F. Unknown

- backend/decision_intelligence sub-modules that don't have obvious wiring
- backend/analytics/* (some are batch scripts · unclear cron cadence)
- backend/research/momentum_attribution (referenced in some paths ·
  daily cadence unclear)

### Critical question

**"Is today's R2 production decision genuinely multi-dimensional, or is
it effectively operating on a much smaller subset of the engines we
built?"**

**Answer**: R2 IS genuinely multi-dimensional in its signal side because
the model_factory ensemble has 11 heterogeneous models (momentum, value,
trend, growth, quality, mean-reversion, news, macro, sector, event,
AI hybrid) and feature_intelligence/feature_store aggregate a wide input
surface. The 11-model ensemble in production consumes essentially every
data source we ingest.

**However**, the EXIT side is dramatically narrower than intended:
- Exits fire only from ensemble STRONG_SELL or orphan-closer
- No stop-loss, target, horizon, ATR, trailing, regime-conditioned, or
  signal-reversal exit ever fires (539 CLOSED events · zero non-ensemble
  non-orphan exits)
- Multiple exit engines exist in code (portfolio_manager +
  lifecycle_state_machine + dynamic_risk_v2 + position_store trailing) ·
  none are invoked or consumed

**And the research side is minimal**:
- Multi-layer research, momentum ledger, stress regime, and crash
  resilience are ALL research-only · none feeds back into R2
- This is per CEO invariant ("research never modifies R2") · but it
  means R2 is effectively insulated from the new research capacity
  we've built

**Net verdict**: R2's SIGNAL side is genuinely multi-dimensional and
consumes most of what we've built. R2's EXIT side is a narrow slice of
the code (score-driven only). R2's RESEARCH-INFORMED side is essentially
zero (by design).

---

## 15 · Execution discipline compliance

- No code changed
- No commits
- No pushes
- No R2 modification
- No R2 scoring / entry / exit / weight change
- No filter added
- No R1 resurrection
- No workbook sheet added

**Deliverable**: this document + the prior audit + evidence files.

---

## Executive summary (bottom)

```
TOTAL COMPONENTS DISCOVERED:                    ~90
PRODUCTION_WIRED:                                48
PARTIALLY_WIRED:                                  4
RESEARCH_ONLY:                                    9
GENERATES_UNUSED_OUTPUT:                          6
UNREACHABLE:                                      3
DEPRECATED:                                       5
UNKNOWN — INVESTIGATION REQUIRED:                 3
```

```
INDIA PRODUCTION DEPTH:                          FULL (48 STEPS)
USA PRODUCTION DEPTH:                            REDUCED (own workflow · fewer steps)
DAILY NEWS:                                       PARTIAL (India FinBERT wired · USA not built · sector-news is price proxy)
MOMENTUM:                                         PARTIAL (aegis.momentum.v1 model wired · research momentum reporting-only)
MULTI-LAYER RESEARCH:                             RESEARCH_ONLY (scaffold · manual only)
FUNDAMENTALS:                                     WIRED (ingest_fundamentals → feature_store → ensemble)
RISK ENGINE:                                      WIRED (risk_engine STEP 24 · dynamic_risk_v2 partially wired)
DYNAMIC EXIT ENGINE:                              NOT WIRED (engine coded · never invoked)
PORTFOLIO LIFECYCLE:                              PARTIAL (open + score-driven close + orphan-close · no stop/target/horizon)
P&L:                                              WIRED (execution_simulator + morning_report + Telegram)
```

## Closure verdict

**`PRODUCTION PARTIALLY WIRED — GAPS REMAIN`**

Signal side: multi-dimensional and genuinely production-wired.
Exit side: narrow · dynamic exit engine coded but unused.
Research side: scaffolded but research-only (by design + orchestration gap).

The AEGIS built over the last 60 days is real and functional in its
signal chain. The exit + research + certification layers were built
mostly on the correct architecture but were not connected to the daily
production driver. The gap is a **discipline / orchestration gap** ·
not an architecture gap.

**End of audit. Awaiting CEO KEEP → WIRE → RESEARCH-ONLY → REMOVE →
REPAIR decisions per component.**
