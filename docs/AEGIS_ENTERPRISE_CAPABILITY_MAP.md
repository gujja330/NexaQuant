# AEGIS · Enterprise Capability Map
### 🔒 SEEDED 2026-07-27 · Wave 4 · D0 will complete full 65-capability population

**Purpose:** every capability in AEGIS, catalogued against the 20-field template locked in [`docs/AEGIS_WAVE_4_ARCHITECTURE_CONSOLIDATION.md`](AEGIS_WAVE_4_ARCHITECTURE_CONSOLIDATION.md). Any capability with an empty field is NOT production-ready.

**This turn (Wave 4 seed):** 20-field template + fully-populated pattern examples spanning all 10 domains (~18 capabilities). Full 65-capability population is Wave 4 · D0 scope.

**Status legend:**
- **Active** — currently produces artifacts on daily run · in target Wave-4 layout
- **Active-Legacy** — currently produces artifacts but slated for archive/consolidation in Wave 4
- **Missing** — referenced by operator/audit but does not exist in code
- **Planned** — Wave 4 NEW (Capital Rotation · Opportunity Cost · Portfolio Attribution)
- **Deprecated** — kept for reference only

---

## 20-Field Template Reference

```
Capability     : plain-language name
Owner          : target domain path
Input          : artifacts + external sources
Output         : artifacts produced (+ path)
Schema         : fingerprint + version
Consumers      : downstream engines that read the output
Tests          : path + count
Validator      : path in validation/ (mandatory)
Documentation  : path in docs/
Dashboard      : tile / route in SPA
Reports        : files emitted
Telegram       : integration point (or N/A)
Replay         : Y/N (replay driver present)
Benchmark      : Y/N (benchmarked)
AI Narration   : which narrator (or N/A)
Status         : Active / Active-Legacy / Missing / Planned / Deprecated
Version        : semver
Deprecated?    : Y/N
Replacement    : capability name if deprecated
Migration      : Wave-4 sub-wave + notes
```

---

## 01 · Market Intelligence

### 1.1 · Sector Engine (DEV018 · 13-dim)

- **Capability:** Sector composite scoring (13-dim: momentum · trend · rs_nifty · breadth · drawdown · flows · earnings · sentiment · volatility · liquidity · macro · industry · quality)
- **Owner:** `backend/01_market_intelligence/sector_engine/`
- **Input:** raw ticker parquets · `reports/global_context.json` · sector membership from `india/sectors.py` (to be consolidated into `10_shared/constants/sectors.py` in Wave 4)
- **Output:** `reports/sector_context.json` (list-shape · one entry per sector · fields `sector_key · display_name · status · score(0-100) · classification · confidence · n_constituents_used · top_drivers[] · top_detractors[] · weighting_version`)
- **Schema:** `ARCH017A v1.0-draft` · `weighting_version: ARCH018 v1.0-draft` · no fingerprint field yet (D0 must add)
- **Consumers:** `backend/canonical/adapters.adapt_flow_proxy` (post-C0 · list-aware) · `backend/macro_intel/sector_rotation.compute_sector_rotation` (post-C0 · list-aware) · `backend/factor_library` (sector rotation leader/laggard factors)
- **Tests:** `backend/tests/test_c0_silent_breakages.py::test_M_Sec1_*` (3) · no dedicated engine test suite yet (D0 flag)
- **Validator:** MISSING · to be created at `validation/sector_validation/sector_engine_validator.py` in D2 (must verify 13-dim contributions sum + score∈[0,100] + confidence∈[0,1] + list-shape stability)
- **Documentation:** partial in `docs/ARCH017A_INVESTMENT_PHILOSOPHY.md` · full spec pending D0
- **Dashboard:** Sector Radar tile · route `/sectors` in India SPA · USA equivalent MISSING
- **Reports:** `reports/sector_context.json` · `reports/industry_context.json` · `reports/company_context.json`
- **Telegram:** N/A (data feeds into Recommendation-domain senders)
- **Replay:** N (no headless driver at `backend/replay/engine_drivers.py` yet · D6 scope)
- **Benchmark:** N (no per-sector accuracy tracking · D6 scope)
- **AI Narration:** N/A (macro narrator covers sector context indirectly)
- **Status:** Active (list-shape now consumed correctly post C0)
- **Version:** 1.0.0 (schema `ARCH017A`)
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D2 · move to `backend/01_market_intelligence/sector_engine/` · schema fingerprint added · validator wired

### 1.2 · Global Engine

- **Capability:** Global macro-risk composite + posture classification
- **Owner:** `backend/01_market_intelligence/global_engine/`
- **Input:** `reports/macro_intelligence.json` · `reports/central_bank_state.json` · `reports/volatility_intelligence.json`
- **Output:** `reports/global_context.json` (posture: `Risk-On/Neutral/Risk-Off/Stress/Recession-Warning` · global_risk 0-100)
- **Schema:** informal · no `schema_fingerprint` (D0 flag)
- **Consumers:** `research/adaptive_rec_v2` · `research/risk_capital_v2` · Runner 1 legacy · Executive Dashboard
- **Tests:** covered indirectly in `backend/tests/test_sprint65.py`
- **Validator:** MISSING · `validation/macro_validation/global_engine_validator.py` (D2)
- **Documentation:** implicit in Sprint 6.5 report
- **Dashboard:** Global Posture tile
- **Reports:** `reports/global_context.json`
- **Telegram:** included in morning brief
- **Replay:** Y (driver exists via `backend/replay/engine_drivers.py::macro_intel`)
- **Benchmark:** N
- **AI Narration:** `ai_macro_narrative.json`
- **Status:** Active-Legacy (10-day stale mtime · producer disconnected from daily · Wave-4 D6 will restore)
- **Version:** 1.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D6 · restore daily production · move to `backend/01_market_intelligence/global_engine/`

---

## 02 · Feature Platform

### 2.1 · Technical Features

- **Capability:** Technical feature computation (RSI · MACD · ADX · ATR · SMA · returns · volatility · drawdown · 52W range · volume ratio)
- **Owner:** `backend/02_feature_platform/technical/` (currently `backend/feature_store/features/technical.py`)
- **Input:** `CanonicalBar` rows (via `backend/canonical/adapters.py::adapt_bars`)
- **Output:** feature rows in the Feature Store snapshot parquet
- **Schema:** `schema_fingerprint: b65ceb49a83a` (post-C0 stable · Wave 4 preserves)
- **Consumers:** `backend/model_factory/models/*` (11 models) · `backend/factor_library` · India `feature_engine.py`
- **Tests:** `backend/tests/test_sprint25.py` (12 tests) · `backend/tests/test_c0_silent_breakages.py` (11 tests · ATR/ADX regression added)
- **Validator:** MISSING · `validation/technical_validation/technical_features_validator.py` (D2 must add: scale sanity + RSI∈[0,100] + ATR>0 + ADX∈[0,100] + no NaN in required fields)
- **Documentation:** Sprint 2.5 report + inline docstrings
- **Dashboard:** feeds every SPA tile indirectly
- **Reports:** `reports/feature_store_summary.json` (aggregate) + snapshot parquet
- **Telegram:** N/A
- **Replay:** Y (via `backend/replay/engine_drivers.py`)
- **Benchmark:** N (individual features not benchmarked · aggregate feature quality tracked by Sprint B0)
- **AI Narration:** `reports/ai_feature_narrative.json`
- **Status:** Active (fixed C0 · ATR + ADX now consume real H/L)
- **Version:** 1.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D2 · move to `backend/02_feature_platform/technical/` · imports switch to `backend/10_shared/indicators/` in D1 (shared library first, then domain reorg)

### 2.2 · Fundamental Features

- **Capability:** ROE · D/E · PE · PB · margins · earnings growth · quality composite
- **Owner:** `backend/02_feature_platform/fundamental/`
- **Input:** `CanonicalFundamentals` (from yfinance latest snapshot)
- **Output:** fundamental feature rows
- **Schema:** part of `b65ceb49a83a` FS fingerprint
- **Consumers:** Value / Growth / Quality models
- **Tests:** covered in `test_sprint25.py`
- **Validator:** MISSING · `validation/fundamentals_validation/*` — must flag look-ahead: current impl broadcasts latest snapshot, breaks walk-forward for fundamentals
- **Documentation:** author-inline comment flags look-ahead issue explicitly
- **Dashboard:** fundamentals tile
- **Reports:** part of FS snapshot
- **Telegram:** N/A
- **Replay:** Y (with known look-ahead caveat)
- **Benchmark:** N
- **AI Narration:** via `ai_feature_narrative.json`
- **Status:** Active (with documented look-ahead limitation)
- **Version:** 1.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D2 · move · add as-of-aware fundamentals snapshot fetcher in Phase 4 backlog

---

## 03 · Model Platform

### 3.1 · Momentum Model

- **Capability:** Cross-sectional momentum score (5d · 20d · 60d returns + SMA position)
- **Owner:** `backend/03_model_platform/models/momentum/` (currently `backend/model_factory/models/momentum.py`)
- **Input:** feature rows from `02_feature_platform/technical/`
- **Output:** `ModelPrediction(score∈[-1,+1], confidence∈[0,1])` per ticker
- **Schema:** `ModelPrediction` dataclass · versioned in `model_factory/model_base.py`
- **Consumers:** `backend/model_factory/ensemble.py` · Recommendation Engine v3
- **Tests:** `backend/tests/test_sprint27.py` (14 tests · all 11 models)
- **Validator:** MISSING · `validation/model_validation/momentum_validator.py` — must verify: score∈[-1,+1] · deterministic under same inputs · rank-univ-dependency is documented explicit assumption (audit S5)
- **Documentation:** model docstring + Sprint 2.7 report
- **Dashboard:** model status tile
- **Reports:** `reports/model_factory.json` · `reports/model_metrics.json`
- **Telegram:** N/A
- **Replay:** Y
- **Benchmark:** N (per-model accuracy not tracked yet · Sprint 7.8 tracks ensemble only)
- **AI Narration:** `ai_model_narrative.json` (via Model Analyst)
- **Status:** Active
- **Version:** 1.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D3 · move · scoring-scale convention documented (audit S2 fix)

---

## 04 · Recommendation

### 4.1 · Recommendation Engine v3 (Runner 2)

- **Capability:** Ensemble → conflict → calibration → regime-adjust → classifier → bull/bear/risks
- **Owner:** `backend/04_recommendation/recommendation_engine/` (currently `backend/recommendation/`)
- **Input:** `Ensemble` output from Model Platform · Market Intelligence regime · Feature attribution
- **Output:** `reports/recommendations_v3.json` (+ `_conflicts.json` + `_summary.json`)
- **Schema:** `schema_fingerprint` present per rec (verified)
- **Consumers:** Risk Engine · Portfolio Engine · UX030 Telegram sender · Executive Dashboard (partial)
- **Tests:** `backend/tests/test_sprint3.py` (22 tests) — 100% green post-UTF-8-fix
- **Validator:** MISSING · `validation/recommendation_validation/rec_v3_validator.py` (D4) — must verify: `STRONG_BUY reachable in all regimes` (fix audit S4) · classifier if-else primary decision path · confidence chain lower bound audit
- **Documentation:** Sprint 3 report
- **Dashboard:** rec table tile
- **Reports:** `recommendations_v3.json` · `recommendations_v3_conflicts.json` · `recommendations_v3_summary.json`
- **Telegram:** feeds UX030 aggregator
- **Replay:** Y
- **Benchmark:** Y (Sprint 7.8 · currently n=0 due to 100% HOLD)
- **AI Narration:** `ai_recommendation_narrative.json`
- **Status:** Active (currently 100% HOLD · calibration cold-start)
- **Version:** 3.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D4 · move · MUST also produce `reports/recommendations.json` (keystone SSoT decision at D0)

### 4.2 · Recommendation Engine · Runner 1 (adaptive_rec_v2 legacy)

- **Capability:** HGB/LogReg learned rec model (Sprint DEV023 · legacy)
- **Owner:** `research/adaptive_rec_v2/` (SEALED · Active-Legacy)
- **Input:** `research/recommendations/run.py` output + `learning.parquet`
- **Output:** `reports/adaptive_rec_v2_signal.json`
- **Schema:** informal · no fingerprint
- **Consumers:** `research/fusion` engine
- **Tests:** `research/adaptive_rec_v2/tests/*`
- **Validator:** MISSING · `validation/recommendation_validation/runner1_v2_validator.py` (D4)
- **Documentation:** internal to `research/adaptive_rec_v2/`
- **Dashboard:** fed via fusion tile
- **Reports:** `adaptive_rec_v2_signal.json`
- **Telegram:** APOLLO diary sender (legacy)
- **Replay:** Y (Sprint 7.7 Runner 1 audit-trail)
- **Benchmark:** Y (Sprint 7.8 · n=10 · DIRECTIONAL_ONLY)
- **AI Narration:** N/A
- **Status:** Active-Legacy (SEALED)
- **Version:** 2.0.0
- **Deprecated?:** N (still primary source of active positions)
- **Replacement:** eventually superseded by Recommendation Engine v3 (Sprint 7.9 orchestrator merges them)
- **Migration:** UNTOUCHED in Wave 4 · consumer wrappers move under `04_recommendation/` but source stays sealed

### 4.3 · Capital Rotation Engine (Wave 4 · NEW)

- **Capability:** Rotate portfolio based on remaining-expected-upside vs alternative opportunities (not time-based). EXIT / TRIM / KEEP / ADD / ROTATE decisions.
- **Owner:** `backend/04_recommendation/capital_rotation/`
- **Input:** `reports/portfolio_v3.json` (current positions) · `reports/recommendations_v3.json` (candidate universe) · `reports/macro_regime.json` (gate) · `reports/sector_context.json` (post-C0 · usable now)
- **Output:** `reports/rotation_plan.json` · `reports/history/rotation_plan.parquet` · `reports/rotation_alerts.json`
- **Schema:** to be defined in D4 · will include `schema_fingerprint` from day one
- **Consumers:** Portfolio Engine (position updates) · Telegram (rotation alerts) · Dashboard (rotation tile)
- **Tests:** to be created at `tests/04_recommendation/capital_rotation/test_capital_rotation.py` in D4
- **Validator:** `validation/recommendation_validation/capital_rotation_validator.py` (D4) — must verify: `keep_score` and `candidate_score` bounded [-1,+1] · macro_gate ∈ {0.3, 0.5, 0.9, 1.0} · threshold logic monotonic
- **Documentation:** design spec in Wave 4 D4 section
- **Dashboard:** Capital Rotation tile
- **Reports:** as above
- **Telegram:** `rotation_alerts.json` → dedicated section in UX030 brief
- **Replay:** Y (built in D4)
- **Benchmark:** Y (N2 rotation frequency + N3 profit capture metrics)
- **AI Narration:** covered by `ai_recommendation_narrative.json` (extended in D4)
- **Status:** Planned (Wave 4 · D4)
- **Version:** 1.0.0 (target)
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** built new in D4 · 100% reuse of existing engines per Agent 4 design

### 4.4 · Opportunity Cost Engine (Wave 4 · NEW)

- **Capability:** Every HOLD must justify "why not rotate" · exposes next-best-candidate + expected alpha delta + reason-not-to-rotate
- **Owner:** `backend/04_recommendation/opportunity_cost/`
- **Input:** every HOLD from `recommendations_v3.json` · full candidate universe from Ranking layer
- **Output:** enrichment fields on `recommendations_v3.json`: `oc_next_best_ticker` · `oc_expected_alpha_delta` · `oc_reason_not_to_rotate`
- **Schema:** enriches existing rec schema · bump `schema_version` minor
- **Consumers:** Explainability layer · Telegram · Dashboard
- **Tests:** `tests/04_recommendation/opportunity_cost/`
- **Validator:** `validation/recommendation_validation/opportunity_cost_validator.py` — every HOLD in output has all 3 OC fields non-null
- **Documentation:** design spec in Wave 4 D4 section
- **Dashboard:** "Why HOLD" expander per rec
- **Reports:** enrichment path
- **Telegram:** "Why we're not rotating X" section
- **Replay:** Y
- **Benchmark:** N (measured indirectly via N4 · Missed alpha metric)
- **AI Narration:** covered by `ai_recommendation_narrative.json`
- **Status:** Planned (Wave 4 · D4)
- **Version:** 1.0.0 (target)
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** built new in D4 · depends on Capital Rotation ranking output

---

## 05 · Portfolio

### 5.1 · Portfolio Construction (v3)

- **Capability:** N-name portfolio builder + rebalance-diff + cash policy
- **Owner:** `backend/05_portfolio/construction/` (currently `backend/portfolio/`)
- **Input:** SizedPositions from Risk Engine
- **Output:** `reports/portfolio_v3.json` (currently 0 positions · Runner 2 100% HOLD chain)
- **Schema:** `schema_fingerprint: b65ceb49a83a` (verified)
- **Consumers:** Execution Simulator · Capital Rotation (D4) · Portfolio Attribution (D5) · Dashboard
- **Tests:** `backend/tests/test_sprint5.py`
- **Validator:** MISSING · `validation/portfolio_validation/construction_validator.py` (D5)
- **Documentation:** Sprint 5 report
- **Dashboard:** Portfolio tile
- **Reports:** `portfolio_v3.json` · `portfolio_diff.json` · `portfolio_state.json`
- **Telegram:** portfolio summary section
- **Replay:** Y
- **Benchmark:** N (portfolio-level metrics tracked separately)
- **AI Narration:** `ai_portfolio_narrative.json`
- **Status:** Active
- **Version:** 3.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D5 · move · resolve vs Runner-1 `portfolio.json` (SSoT decision)

### 5.2 · Risk Engine (Sprint 4)

- **Capability:** Kelly + fractional + caps + VaR/CVaR + concentration
- **Owner:** `backend/05_portfolio/risk/` (currently `backend/risk/`)
- **Input:** Recommendations from Rec Engine
- **Output:** `reports/sized_positions.json` · `reports/risk_report.json`
- **Schema:** SizedPosition dataclass · versioned
- **Consumers:** Portfolio Construction · Dashboard · Telegram
- **Tests:** `backend/tests/test_sprint4.py` (23 tests)
- **Validator:** MISSING · `validation/portfolio_validation/risk_validator.py` (D5)
- **Documentation:** Sprint 4 report
- **Dashboard:** Risk tile
- **Reports:** `sized_positions.json` · `risk_report.json` · `ai_risk_narrative.json`
- **Telegram:** risk summary section
- **Replay:** Y
- **Benchmark:** N
- **AI Narration:** `ai_risk_narrative.json`
- **Status:** Active (audit score 90/100 · healthiest engine)
- **Version:** 1.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D5 · move

### 5.3 · Portfolio Attribution (Wave 4 · NEW)

- **Capability:** Every position exposes contribution from Momentum · Value · Quality · Growth · Sector · Macro · Risk · Fundamentals · News · Corp Actions · Execution · Learning · Final Attribution
- **Owner:** `backend/05_portfolio/monitoring/attribution.py`
- **Input:** `portfolio_v3.json` positions + underlying model contributions + factor exposures
- **Output:** `reports/portfolio_attribution.json`
- **Schema:** new · fingerprinted from day one
- **Consumers:** Dashboard (attribution tile) · Explainability layer · Telegram (weekly attribution summary)
- **Tests:** `tests/05_portfolio/monitoring/test_attribution.py`
- **Validator:** `validation/portfolio_validation/attribution_validator.py` — sum-of-contributions matches total return within tolerance
- **Documentation:** design spec in Wave 4 D5 section
- **Dashboard:** per-position attribution expander
- **Reports:** `portfolio_attribution.json`
- **Telegram:** weekly attribution digest
- **Replay:** Y
- **Benchmark:** N (attribution is diagnostic, not scoring)
- **AI Narration:** extension of `ai_portfolio_narrative.json`
- **Status:** Planned (Wave 4 · D5)
- **Version:** 1.0.0 (target)
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** built new in D5

---

## 06 · Learning

### 6.1 · Adaptive Learning

- **Capability:** Outcome ledger + rec DNA feedback loop
- **Owner:** `backend/06_learning/adaptive_learning/`
- **Input:** closed trades from Execution Simulator · rec DNA from `research/recommendation_dna/`
- **Output:** `reports/feature_attribution.json` · `reports/learning.parquet` (currently 10-day stale)
- **Schema:** `learning.parquet` schema versioned
- **Consumers:** Winner Genome · Decision Attribution · Historical features
- **Tests:** `backend/tests/test_sprint6.py`
- **Validator:** MISSING · `validation/*/learning_validator.py`
- **Documentation:** Sprint 6 report
- **Dashboard:** Learning tile
- **Reports:** `learning.parquet` + summary JSONs
- **Telegram:** learning weekly digest
- **Replay:** Y
- **Benchmark:** N
- **AI Narration:** `ai_learning_narrative.json`
- **Status:** Active-Legacy (stale · Runner 2 chain not populating)
- **Version:** 1.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D6 · move · restore daily production via chain fix

### 6.2 · Replay Framework

- **Capability:** Historical backfill + deterministic replay + walk-forward
- **Owner:** `backend/06_learning/replay/`
- **Input:** raw ticker parquets · engine drivers
- **Output:** replayed feature/rec/risk/portfolio snapshots
- **Schema:** replay controller output · JSONL
- **Consumers:** Benchmark · Strategy Doctor · Institutional Acceptance suite
- **Tests:** `backend/tests/test_sprint76.py` + `test_sprint77.py` + `test_sprint77_runner1.py` (44 tests total)
- **Validator:** MISSING · `validation/replay_validation/*` — must add byte-equality regression test (audit Rep1)
- **Documentation:** Sprint 7.6/7.7 reports
- **Dashboard:** Replay Status tile
- **Reports:** `reports/backfill_summary.json` · `reports/walkforward_readiness.json`
- **Telegram:** N/A
- **Replay:** self
- **Benchmark:** N
- **AI Narration:** N/A
- **Status:** Active (functionally deterministic · byte-drift on timestamps · fix in D6)
- **Version:** 1.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D6 · move + add `--frozen-clock` mode (audit Rep2) + byte-equality regression test

### 6.3 · Champion Strategy

- **Capability:** Current-best strategy tracker (challenger promotion protocol)
- **Owner:** `backend/06_learning/champion/`
- **Input:** benchmark verdicts per strategy · challenger scores
- **Output:** `reports/champion_strategy.json`
- **Schema:** informal
- **Consumers:** Ops-check · Strategy selector · Executive Dashboard
- **Tests:** `champion_challenger/lib/drift.py` has drift tests; no production-runner tests
- **Validator:** MISSING · `validation/*/champion_validator.py` (D6)
- **Documentation:** Sprint 7 mentions
- **Dashboard:** Champion tile
- **Reports:** `champion_strategy.json` (currently 10 days stale · mtime 2026-07-17)
- **Telegram:** champion change alerts (currently silent · producer disconnected)
- **Replay:** N
- **Benchmark:** Y (indirectly)
- **AI Narration:** N/A
- **Status:** Active-Legacy (producer disconnected · hotfix `929be1d` loosened ops-check but didn't fix root)
- **Version:** 1.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D6 · move + reconnect producer + wire challenger promotion protocol

---

## 07 · Knowledge

### 7.1 · Knowledge Graph

- **Capability:** Entities · relationships · timeline nodes (Oil → Transport → Airlines chains)
- **Owner:** `backend/07_knowledge/knowledge_graph/`
- **Input:** `recommendations.json` (10 days stale) · macro state · news events
- **Output:** `reports/knowledge_graph.json` · `reports/stress_scenarios.json` · `reports/community_clusters.json`
- **Schema:** informal
- **Consumers:** Executive Dashboard · Institutional Memory
- **Tests:** covered in DEV024 modules
- **Validator:** MISSING · `validation/*/knowledge_graph_validator.py`
- **Documentation:** DEV024 module docstrings
- **Dashboard:** KG viz tile
- **Reports:** as above
- **Telegram:** N/A
- **Replay:** N
- **Benchmark:** N
- **AI Narration:** partial in macro narrator
- **Status:** Active-Legacy (upstream dep `recommendations.json` stale)
- **Version:** 1.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D6/D7 · move · unblocks when D4 fixes keystone

---

## 08 · Delivery

### 8.1 · Telegram Orchestrator

- **Capability:** Coordinate all Telegram sends · dedup · concurrency · retry
- **Owner:** `backend/08_delivery/telegram/orchestrator.py` (NEW · Wave 4 D7)
- **Input:** all rec/portfolio/risk/rotation outputs · rec-set hash · publish marker
- **Output:** delivery ledger `reports/telegram_delivery_*.jsonl` · dedup log
- **Schema:** to be defined in D7
- **Consumers:** legacy sealed `india/telegram_notify.py` (UNTOUCHED wrapper called from orchestrator) · UX030 script
- **Tests:** `tests/08_delivery/telegram/*` (D7)
- **Validator:** `validation/telegram_validation/*` — dedup key present · concurrency block enforced · publish marker order · retry semantics
- **Documentation:** design in Wave 4 D7 section
- **Dashboard:** Telegram Health tile
- **Reports:** `telegram_health_*.json` · delivery ledger
- **Telegram:** self
- **Replay:** N (delivery is idempotent-at-target · replay would resend)
- **Benchmark:** N
- **AI Narration:** N/A
- **Status:** Planned (Wave 4 · D7 · currently 6 senders no dedup)
- **Version:** 1.0.0 (target)
- **Deprecated?:** N
- **Replacement:** consolidates 6 senders behind one orchestrator
- **Migration:** D7 · add `concurrency:` block to `.github/workflows/aegis-daily.yml` (mirror `mon001-daily.yml:27-29`) · move `.published` marker BEFORE Telegram · add rec-set-hash dedup within 4h window

### 8.2 · Dashboard (India SPA)

- **Capability:** Static SPA reading from `reports/*.json` via fetch
- **Owner:** `backend/08_delivery/dashboard/` orchestration + `ux/dashboard/frontend/` static assets
- **Input:** `reports/*.json` (currently reads stale `recommendations.json` · will read SSoT after D4)
- **Output:** rendered HTML/JS in browser
- **Schema:** consumes producer schemas · no own schema
- **Consumers:** operator (browser)
- **Tests:** manual currently · headless-render smoke test to be added in D7
- **Validator:** `validation/dashboard_validation/*` — cache-bust present · SSoT alignment · schema compatibility per tile
- **Documentation:** partial
- **Dashboard:** self
- **Reports:** N/A (consumer only)
- **Telegram:** N/A
- **Replay:** N
- **Benchmark:** N
- **AI Narration:** consumes narratives from other engines
- **Status:** Active-Legacy (renders stale India `recommendations.json` per audit)
- **Version:** 1.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D7 · route consumption to SSoT post-D4

---

## 09 · Platform

### 9.1 · Persistence (Sprint 7.5 · `aegis.persistence.v1`)

- **Capability:** Append-only history writes with dedupe on (market, asof) + extra keys per family
- **Owner:** `backend/09_platform/persistence/` (currently `backend/persistence/`)
- **Input:** every engine's output
- **Output:** parquet histories at `reports/history/*` and `reports/*_history.parquet`
- **Schema:** Ledger schema versioned · dedup key documented per family
- **Consumers:** every engine that writes history
- **Tests:** `backend/tests/test_sprint75.py` (18 tests)
- **Validator:** `validation/*/persistence_validator.py` (D8) — dedup working · monotonic append · no clobber
- **Documentation:** Sprint 7.5 report
- **Dashboard:** persistence health tile
- **Reports:** `reports/persistence_errors.jsonl`
- **Telegram:** N/A
- **Replay:** self
- **Benchmark:** N
- **AI Narration:** N/A
- **Status:** Active (audit score 90/100 · one of two healthiest domains)
- **Version:** 1.0.0
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** D8 · move

### 9.2 · MON001 Sealed Monitoring

- **Capability:** Config-drift detection via SHA-256 fingerprint over baseline files + constants
- **Owner:** `backend/09_platform/monitoring/` (currently `india/monitoring/MON001_Forward_Validation/` · SEALED)
- **Input:** baseline files listed in `mon001.yaml` · sealed fingerprint at `reports/sealed_fingerprint.json`
- **Output:** MON001 daily reports · fingerprint diff on drift
- **Schema:** `mon001.yaml`
- **Consumers:** operator (via alerts) · ops-check
- **Tests:** `nexaquant/tests/test_regression.py::test_mon001_fingerprint_matches_seal`
- **Validator:** self (MON001 IS a validator)
- **Documentation:** in-module
- **Dashboard:** MON001 Alert tile
- **Reports:** `india/monitoring/MON001_Forward_Validation/reports/*`
- **Telegram:** drift alerts
- **Replay:** N
- **Benchmark:** N
- **AI Narration:** N/A
- **Status:** Active · SEALED · fingerprint `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf`
- **Version:** locked
- **Deprecated?:** N
- **Replacement:** —
- **Migration:** UNTOUCHED throughout Wave 4 · verify fingerprint at end of every sub-wave

---

## 10 · Shared

### 10.1 · Shared Indicator Library (Wave 4 · D1)

- **Capability:** ONE canonical implementation of RSI · ATR · ADX · MACD · EMA · SMA · volatility · beta · sharpe · sortino · calmar · momentum · drawdown · liquidity · Bollinger · correlation
- **Owner:** `backend/10_shared/indicators/`
- **Input:** OHLCV series (pandas)
- **Output:** float or Series per indicator
- **Schema:** function signatures documented + typed
- **Consumers:** every engine that computed indicators locally (4+ ATR sites · 3 RSI sites · 3 ADX sites collapse into 1 each)
- **Tests:** `tests/10_shared/indicators/test_*.py` — mathematical correctness suite
- **Validator:** `validation/indicator_validation/no_local_reimplementation.py` — grep-verify no `def rsi\|def atr\|def adx\|def macd` outside `backend/10_shared/indicators/`
- **Documentation:** module docstrings + `docs/capabilities/shared_indicators.md`
- **Dashboard:** N/A
- **Reports:** N/A
- **Telegram:** N/A
- **Replay:** N
- **Benchmark:** N
- **AI Narration:** N/A
- **Status:** Planned (Wave 4 · D1)
- **Version:** 1.0.0 (target)
- **Deprecated?:** N
- **Replacement:** consolidates 4+ ATR · 3 RSI · 3 ADX · multiple MACD reimplementations
- **Migration:** D1 · create canonical files · migrate `backend/feature_store/features/technical.py` first · legacy sites become thin re-exporters in D2

---

## Missing Capabilities (flagged by operator or audit)

### M.1 · Scanner Strategy

- **Capability:** Referenced by operator but does not exist in code (grep returns 0)
- **Status:** Missing
- **Migration:** D4 decision · build OR remove from operator lexicon

### M.2 · Income Strategy

- **Capability:** Referenced by operator but does not exist in code
- **Status:** Missing
- **Migration:** D4 decision · build OR remove from operator lexicon

### M.3 · Shield Strategy (currently embedded)

- **Capability:** Vol-tier profile embedded in `india/recommendation_generator.py:210-216`
- **Status:** Active-Legacy (embedded, not standalone)
- **Migration:** D6 decision · promote to first-class engine OR accept embedded

---

## Deprecated Capabilities (to be moved to archive/)

### D.1 · `research/recommendations/run.py`

- **Capability:** Legacy DEV023 rec runner · produces frozen `reports/recommendations.json`
- **Status:** Deprecated (per Sprint A1 audit)
- **Replacement:** Recommendation Engine v3 (Runner 2) via SSoT decision in D4
- **Migration:** archived in D4 or D8 · after 30 days verified no consumer references

---

## D0 Deliverables (Wave 4 · full completion)

- All 65 capabilities have all 20 fields populated
- `reports/research_engine_inventory.json` refreshed to match this map exactly
- Any capability with `Validator: MISSING` gets an issue opened tracked in D2..D8
- Sub-wave assignments finalized per capability in `Migration` field
- Executive Dashboard tile: "Capability Coverage: X / 65 fully populated"

---

**End of Enterprise Capability Map · SEEDED 2026-07-27 · D0 continues full population.**
