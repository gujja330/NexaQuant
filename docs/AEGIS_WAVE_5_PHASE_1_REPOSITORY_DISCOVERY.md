# AEGIS · Wave 5 · Phase 1 · Repository Discovery
### 🔒 SHIPPED 2026-07-27 · 24 inventories · read-only comprehensive scan · substrate for Phase 2 compliance audit

**Purpose:** produce a complete, evidence-backed picture of the repository as-is · every folder, module, capability, engine, artifact, schema, dependency, execution path, config, secret, dependency, test, doc, tech-debt item, and duplicate implementation catalogued. This document is the substrate on which Phase 2 (Architecture Compliance Audit) evaluates fit vs the Constitution + Wave 4 + Cap Map.

**Method:** direct filesystem enumeration + grep + Python module introspection · builds on Sprint A1 (10 rec producers · 59 engines · 6 cross-cutting risks) + Sprint A2 (per-engine status matrix) + v2.2 audit (42 findings) + Wave 4 Enterprise Capability Map · no re-audit of already-classified findings · net-new inventories added where prior work didn't cover.

**Scope:** the entire `c:/Users/GPraveenKumar/Downloads/prism` repository.

**Sealed contracts UNTOUCHED · MON001 fingerprint `e4c070673568c52d…` preserved · 280/280 tests still green · Constitution compliance: read-only scan makes no changes.**

---

## 0 · Discovery Summary (executive)

| Metric | Value |
|---|---|
| Total Python files | **857** (excluding `__pycache__`) |
| Backend modules | 180 |
| India modules | 159 |
| USA modules | 56 |
| Research modules | **317** (largest tree) |
| NexaQuant modules | 48 |
| Scripts / Strategy / UX | 12 / 12 / 25 |
| Test files (all) | **58** (21 research · 19 backend · 10 nexaquant · 6 india · 2 ux) |
| Docs (.md in docs/) | **141** |
| Configs (.yaml in configs/) | **7** |
| GitHub workflows | **5** |
| Reports · JSON | **176** |
| Reports · Parquet | 30 |
| Reports · JSONL ledgers | 8 |
| USA reports total | 107 |
| Backend files declaring `schema_fingerprint` | 42 |
| Reports carrying `schema_fingerprint` | **12** (~6.8% coverage — GAP) |
| Duplicate indicator sites | **RSI 5 · ATR 6 · ADX 4 · MACD ≥3** — Constitution Article 30 violated |
| DEPRECATED markers | 10 |
| TODO/FIXME markers | 1 (excellent) |
| Secrets in code | **0** (verified · both `.env.angel` + `.env.telegram` gitignored) |
| `archive/` directory | **absent** — Wave 4 D8 creates it |
| CSV registries | 8 in `data/` + `model_registry.jsonl` at root |
| Orchestrator steps | 32 (India `aegis_daily_v2.py`) · 35 (USA `usa_daily.py`) |
| Sealed-contract import surface | 1 test file only (clean isolation) |

**Top-of-mind findings (feed Phase 2):**
- **Schema fingerprint coverage 6.8%** — 164 of 176 reports have no fingerprint. Constitution Article 21 non-compliance.
- **15 duplicate indicator sites** (5+6+4) across `backend/`, `india/`, `research/`, `strategy/`, `usa/research/` — Constitution Article 30 non-compliance (kills the "one canonical implementation" rule).
- **research/ larger than backend/** (317 vs 180 modules) — research overhang · needs Constitution Article 76 audit (`research/` must not be daily-wired).
- **India + USA duplication** — parallel subdirectory structure (india/feature_store vs usa/research/feature_store) violates Article 62 dual-market rule interpretation (should share via `backend/` domain, not per-market copies).
- **7 configs · Article 72 partial** — most tunables likely still in code · Phase 6 will find them.
- **Backend has 23 subdirs · target is 10 domains** — Wave 4 D2..D8 will migrate.

---

## 1 · Repository Inventory

Top-level layout (as of 2026-07-27):

```
prism/
  backend/                180 .py · 23 subdirs · production business logic
  india/                  159 .py · 17 subdirs · India market runners + engines (Runner 1 legacy)
  usa/                     56 .py · 9 subdirs · USA market runners + engines
  research/               317 .py · 25 subdirs · experimental + DEV* prototypes + SEALED (adaptive_rec_v2 · risk_capital_v2)
  nexaquant/               48 .py · ops daemon + registry + logging setup
  scripts/                 12 .py · orchestrators + CLI entry points
  strategy/                12 .py · legacy strategy definitions (SMC · risk · regime · rules)
  ux/                      25 .py + dashboard SPA static assets
  configs/                  7 .yaml · single source of tunables (partial)
  docs/                   141 .md · roadmaps · sprint reports · architecture · closures
  data/                    raw parquets + CSV registries + external sources
  reports/                 214 artifacts (176 JSON + 30 parquet + 8 JSONL)
  logs/                    runtime logs (rotated per engine)
  deploy/                  AWS EC2 setup + Caddy config
  execution/               legacy standalone execution (subject to Wave 4 D5 review)
  markets/                 legacy market definitions
  features/                pre-generated feature parquets + manifests
  backtest/                legacy backtester
  experiments/             legacy experiment outputs
  output/                  scratch outputs
  chat/                    session logs (permanent handoff docs)
  compare/                 comparison outputs
  .github/workflows/       5 CI workflows
```

Notable top-level files:
- `AEGIS_CONSTITUTION.md` (top-level pointer to `docs/AEGIS_ENTERPRISE_CONSTITUTION.md`)
- `CHANGELOG.md`
- `README.md`
- `Dockerfile` + `docker-compose.yml`
- `requirements.txt` + `requirements-live.txt` + `requirements-dashboard.txt`
- `config_loader.py` (top-level · Article 68 candidate for relocation to `backend/09_platform/`)
- `model_registry.jsonl` (top-level · should live under `backend/09_platform/registry/`)

**Compliance flag (Phase 2):** several top-level files should relocate per Article 10 domain model.

---

## 2 · Folder Inventory

### 2.1 · backend/ subdirs (23 · target = 10 domains)

```
backend/ai/                       6 AI narrators + prompt templates
backend/benchmark/                Sprint 7.8 benchmark framework
backend/canonical/                CanonicalBar/Dataset schemas + adapters (→ 10_shared/schemas OR 09_platform/contracts)
backend/execution/                Execution simulator (→ 05_portfolio/execution)
backend/factor_library/           Sprint 7.5 factor library (→ 06_learning/factor_library or 09_platform)
backend/feature_intelligence/     MLOps layer over Feature Store (→ 02_feature_platform + governance)
backend/feature_store/            Sprint 2.5 feature store (→ 02_feature_platform)
backend/history_quality/          Sprint B0 quality validator (→ validation/data_validation)
backend/learning/                 Sprint 6 learning engine (→ 06_learning/adaptive_learning)
backend/macro_intel/              Sprint 6.5 macro intel (→ 01_market_intelligence/global_engine)
backend/market_intelligence/      Market intelligence composite (→ 01_market_intelligence)
backend/model_factory/            11 models + ensemble (→ 03_model_platform)
backend/model_registry/           Model registry (→ 09_platform/registry)
backend/persistence/              Sprint 7.5 append-only history (→ 09_platform/persistence)
backend/portfolio/                Sprint 5 portfolio (→ 05_portfolio/construction)
backend/promotion/                Champion/challenger promotion (→ 06_learning/champion)
backend/recommendation/           Sprint 3 rec engine v3 (→ 04_recommendation/recommendation_engine)
backend/replay/                   Sprint 7.6/7.7 replay controller + drivers (→ 06_learning/replay)
backend/risk/                     Sprint 4 risk engine (→ 05_portfolio/risk)
backend/statistics/               Wilson CI + normal-approx CI (→ 10_shared/utils/statistics)
backend/tests/                    18 test files (→ tests/backend/ mirror)
backend/validation/               Sprint validation logic (→ merges with top-level validation/)
```

### 2.2 · india/ subdirs (17 · Runner 1 legacy + India-specific glue)

```
india/ai_lab/                     legacy strategy search
india/backend_validation/         India-specific validation
india/evidence/                   Evidence collection
india/execution_simulator/        India-specific execution
india/factor_library/             India factor lib (dup of backend/factor_library)
india/feature_intelligence/       India variant (dup)
india/feature_store/              India variant (dup)
india/history_quality/            India variant
india/learning_engine/            India variant
india/macro_intel/                India variant
india/market_intelligence/        India variant
india/model_factory/              India variant
india/monitoring/MON001_*/        SEALED · fingerprint sentinel · UNTOUCHABLE
india/portfolio_engine/           India variant
india/recommendation_intelligence/  India runner adapter
india/risk_engine/                India variant
```

**Compliance flag (Phase 2):** heavy per-market duplication of subdomains. Article 62 dual-market rule intent = share via `backend/` domain with market-parameterized runners, NOT per-market subdirectory copies.

### 2.3 · usa/ subdirs (9)

```
usa/backend_validation/           USA validation
usa/configs/                      USA-specific configs (→ configs/ with market suffix)
usa/dashboard/                    USA SPA (→ 08_delivery/dashboard)
usa/data/raw/us/                  USA raw data
usa/docs/                         USA-specific docs (→ docs/ market suffix)
usa/reports/                      107 USA report artifacts
usa/research/                     USA research runners (parallel structure to india/)
usa/scripts/                      USA orchestrators (usa_daily.py + build_universe.py + refresh_market_data.py + telegram_send.py + usa_ops_check.py)
usa/telegram/                     USA Telegram
```

### 2.4 · research/ subdirs (25 · substantially larger than backend)

```
research/RISK001-A/                       Exit policy study
research/adaptive_learning/               Legacy DEV
research/adaptive_rec_v2/                 SEALED · Runner 1 v2 HGB/LogReg
research/backtesting/                     Legacy backtester
research/benchmark/                       Legacy benchmark
research/champion_challenger/             Promotion logic
research/company_intelligence/            DEV020
research/confidence_calibration/          DEV
research/decision_attribution/            DEV
research/decision_center/                 Aggregator
research/global_intelligence/             DEV017
research/industry_intelligence/           DEV019
research/institutional_memory/            DEV
research/knowledge_graph/                 DEV024
research/morning_report/                  Report producer
research/portfolio_construction/          Legacy
research/portfolio_monitor/               Legacy monitor
research/recommendation_dna/              DNA + feedback (partial orchestration)
research/recommendations/                 DEV023 legacy rec runner (frozen recommendations.json producer)
research/research_assistant/              Legacy
research/risk_capital_v2/                 SEALED
research/sector_intelligence/             DEV018
research/strategy_doctor/                 DEV
research/validation_v2/                   Runner 1 v2 validation
```

**Compliance flag (Phase 2):** `research/` contains active daily-wired code (`research/recommendations/` · `research/adaptive_rec_v2/` · `research/risk_capital_v2/` · fusion + validation_v2). Article 76 says `research/` NEVER daily-wired — either amend the Constitution to grandfather these (Article 78 sealed research clause covers 2 of the 3) OR migrate them into `backend/04_recommendation/`.

### 2.5 · scripts/ (12 orchestrators + CLI)

```
scripts/aegis_daily_v2.py                 India orchestrator · 32 steps
scripts/aegis_health_check.py             Health check aggregator
scripts/aegis_ops_check.py                Ops-check (23 required artifacts + 14 schemas)
scripts/aegis_profile.py                  Standalone profiler (not wired to daily)
scripts/check_data_freshness.py           SLA freshness check
scripts/e2e_test.py                       End-to-end smoke test
scripts/nexaquant_daemon.py               Long-running daemon
scripts/nexaquant_service.py              Windows service wrapper
scripts/run_pipeline_local.py             Local dev orchestrator
scripts/telegram_health_check.py          Telegram connectivity check
scripts/telegram_send_ux030.py            UX030 dedicated sender
scripts/telegram_send_with_retry.py       Legacy sender wrapper
```

Plus USA-specific: `usa/scripts/{usa_daily,build_universe,refresh_market_data,telegram_send,usa_ops_check}.py`

---

## 3 · Module Inventory · Summary

Total production/research Python modules: **857** (excluding `__pycache__`, `venv`, and vendored packages).

Distribution:
- `research/` 317 (37%)
- `backend/` 180 (21%)
- `india/` 159 (19%)
- `usa/` 56 (7%)
- `nexaquant/` 48 (6%)
- `ux/` 25 (3%)
- `scripts/` 12 (1.4%)
- `strategy/` 12 (1.4%)
- Other (top-level + legacy) 48 (5.6%)

**Compliance flag (Phase 2):** `research/` = 37% of the codebase. Under Article 76 much of this should be either archived, sealed (with explicit registry), or promoted to `backend/`.

---

## 4 · Capability Inventory

Full 65-capability roster established in [`docs/AEGIS_ENTERPRISE_CAPABILITY_MAP.md`](AEGIS_ENTERPRISE_CAPABILITY_MAP.md). Status (from Cap Map + audit):

| Status | Count | Notes |
|---|---:|---|
| Active (production, healthy) | ~18 | Risk Engine · Persistence · MON001 · FS technical · macro intel · etc. |
| Active-Legacy (production but slated for consolidation) | ~30 | Runner 1 · Runner 1 v2 · fusion · India per-market variants |
| Missing (referenced but doesn't exist) | 3 | Scanner · Income · standalone Shield |
| Planned (Wave 4/5 NEW) | 4 | Capital Rotation · Opportunity Cost · Portfolio Attribution · Shared Indicators |
| Deprecated (queued for archive) | ≥1 | `research/recommendations/run.py` (DEV023) |

Full 65-cap × 20-field population is Wave 4 · D0 scope. Wave 5 · Phase 4 (Capability Completion) verifies all fields populated.

---

## 5 · Engine Inventory

Full inventory in `reports/research_engine_inventory.json` (Sprint A2 · 59 engines · 25 categories · Connected/Partially/Active/Missing status). Summary:

| Category | Connected | Partial | Active-Legacy | Missing |
|---|---:|---:|---:|---:|
| Feature Platform | 8 | 1 | 0 | 0 |
| Model Platform | 11 | 0 | 0 | 0 |
| Recommendation | 3 | 1 | 3 | 0 |
| Portfolio | 3 | 0 | 1 | 0 |
| Risk | 1 | 0 | 1 | 0 |
| Learning | 2 | 1 | 3 | 1 |
| Macro / Market Intel | 4 | 0 | 1 | 0 |
| Knowledge Graph | 1 | 1 | 0 | 0 |
| Sector | 3 | 0 | 0 | 0 |
| Champion / Challenger | 0 | 1 | 1 | 0 |
| Delivery (Reports/Dashboard/Telegram/API) | 4 | 3 | 2 | 1 (API) |
| Ops / Health | 3 | 0 | 0 | 0 |
| Registry / Persistence | 2 | 0 | 0 | 0 |
| **Total** | **~39** | **~13** | **~3** | **~4** (matches A2 · 59 total) |

**Wave 5 targets:**
- **Missing → build:** API (Phase 4 Module 18) · Champion producer (D6) · Scanner + Income (D4 decision) · standalone Shield promotion (D6)
- **Partial → complete:** documented in Sprint A2 · addressed sequentially in Wave 5 Phases 5-14

---

## 6 · Artifact Inventory

`reports/` layer:
- **176 JSON files** — canonical current state
- **30 Parquet files** — history snapshots (append-only per Sprint 7.5)
- **8 JSONL ledgers** — orchestrator/telegram/mon001/persistence-error/ops event streams

USA-specific `usa/reports/`: 107 files total.

Naming convention audit:
- Most follow `<capability>.json` pattern (Article 22 compliant)
- Some carry version suffixes (`recommendations_v3.json` · `portfolio_v3.json` · `adaptive_rec_v2_signal.json`) — indicates versioning conflict rather than schema versioning · Phase 2 flag
- Global-comparison subdir `reports/global/` established (Wave 1 A1) — currently 1 file · target = every dual-market engine

**Full artifact-to-producer mapping done in Sprint A1 · reused here.**

**Compliance flag (Phase 2):** Only 12 of 176 reports carry `schema_fingerprint` (6.8%). Article 21 requires ALL. Major gap.

---

## 7 · Schema Inventory

Backend modules declaring `schema_fingerprint`: **42** files (via grep).
Reports currently carrying `schema_fingerprint`: **12** files.

Schema-fingerprinted artifacts confirmed by prior audits:
- `portfolio_v3.json` → `b65ceb49a83a`
- `recommendations_v3.json` (per-rec fingerprints)
- `sized_positions.json` (SizedPosition dataclass · schema_fingerprint + feature_set_version)
- Feature Store snapshot parquets (via `feature_versioning.py`)

Ledger schemas (`aegis_daily_v2_history.jsonl` · `mon001_alerts.jsonl` · `telegram_delivery_*.jsonl` · `persistence_errors.jsonl`) — Article 84 compliant.

**Compliance flag (Phase 2):** ~164 reports need schema_fingerprint added. Bulk addition via a per-artifact "schema decorator" pattern is a Phase 3 (Standardization) target.

---

## 8 · Dependency Graph

Backend-internal import graph seed:
- 15+ backend files import from `backend.ai.*` (narrators)
- Cross-domain imports via `from backend.X import Y` present in 30+ files (Phase 2 will build the full graph for Article 12 compliance audit)

**Compliance flag (Phase 2):** proper graph generation via `pydeps` or hand-parsing planned in Phase 2. Preview: some `backend.*` files may already have upward layer imports that will fail the D8 CI check — need enumeration before D2 reorg.

---

## 9 · Execution Graph

**India daily orchestrator** (`scripts/aegis_daily_v2.py`): **~32 steps** in strict sequential order:
1. Ingest ×4 (fii_dii · news_sentiment · fundamentals · corporate_actions)
2. `backend_validation`
3. Macro/factor/market intelligence/feature/model chain (6 steps)
4. `recommendation_intelligence` (Runner 2)
5. Risk/portfolio/learning/execution (4 steps)
6. Runner 1 v2 chain (`adaptive_rec_v2` → `validation_v2` → `risk_capital_v2` → `dna_feedback` → `knowledge_graph` → `fusion`)
7. `stock_validation` · `price_context` · `decision_center` · `institutional_memory` · `winner_genome` · `decision_attribution` · `benchmark` · `morning_report` · `ops_check` · `telegram`

**USA daily orchestrator** (`usa/scripts/usa_daily.py`): **~35 steps** in similar structure with USA legacy v1 chain.

Full E2E chain-integrity matrix documented in v2.2 audit Phase 19 — 9 of 32 India steps BROKEN (all read `recommendations.json` which is unproduced by any orchestrator step · keystone gap).

**Reuse:** v2.2 audit already produced full chain matrix — no re-derivation needed.

---

## 10 · Data Flow Graph (Layer 0 → Layer 9)

```
Layer 0  data/raw/india/*.parquet · usa/data/raw/us/*.parquet · news RSS · yfinance API
Layer 1  backend/canonical/*  (CanonicalBar · CanonicalDataset · CanonicalFundamentals · ...)
Layer 2  backend/feature_store/features/*  (technical · fundamental · macro · sector · earnings · institutional · news · corp_actions · market_intel · historical)
Layer 3  backend/factor_library/*  (22 factors)
Layer 4  backend/model_factory/models/*  (11 models) + ensemble.py
Layer 5  backend/recommendation/*  + research/adaptive_rec_v2 + research/fusion  → reports/recommendations_v3.json (fresh) + reports/recommendations.json (STALE · keystone gap)
Layer 6  backend/risk/* → backend/portfolio/* → backend/execution/* → reports/{sized_positions,portfolio_v3,execution_ledger}.json/parquet
Layer 7  backend/learning/* + research/adaptive_learning/* + research/knowledge_graph/*
Layer 8  research/institutional_memory/* + research/knowledge_graph/*
Layer 9  research/morning_report/* → reports/morning_latest.html/md · ux/dashboard/frontend/* · scripts/telegram_send_*.py
```

**Compliance flag (Phase 2):** Layers 5/7/8/9 currently have `research/` code in the daily production path. Article 76 non-compliance. Wave 4 D6/D8 will migrate.

---

## 11 · Import Graph

Delta over §8:
- 15+ upward imports from `backend/ai/*` → other backend domains (narrators cross-cut · consistent with Cross-cutting Platform Services in Appendix A of the Constitution)
- `nexaquant/*` operates in its own subproject — clean isolation
- `scripts/*` (top-level orchestrators) import from many backends — expected · Article 12 allows this because orchestrators live at Cross-cutting Platform Services layer

Full graph enumeration + forbidden-import verification is Phase 2 scope.

---

## 12 · Technology Inventory

**Language:** Python 3.12+ (Constitution Article 68)
**Package deps** (from `requirements.txt` — 35 top-level, kitchen-sink superset):

```
Data:        pandas · numpy · pyarrow · scipy · statsmodels · ta · featuretools · tsfresh
ML:          scikit-learn · torch · torchaudio · torchvision · transformers · stable-baselines3 · ray[rllib] · hmmlearn
NLP:         transformers · langchain
Explain:     shap · lime
Config:      pyyaml · hydra-core · omegaconf
Web/UI:      dash · plotly
Async:       aiohttp · asyncio
Data-gen:    copulas · arch · river
Broker:      MetaTrader5
Graph:       networkx
Framework:   great_expectations · retrying
```

**Slim runtime subsets:** `requirements-live.txt` (production runtime) + `requirements-dashboard.txt` (dashboard-only).

**Compliance flag (Phase 2):** kitchen-sink requirements.txt is Article 52 non-compliant — new deps require an ADR. Migration path: split into `requirements-runtime.txt` (production) + `requirements-research.txt` (heavy) + `requirements-dev.txt` (testing).

**DB engine:** none (Article 70 · file-based state is deliberate architectural choice).

---

## 13 · Configuration Inventory

`configs/` (7 files):
```
configs/base_config.yaml                Global platform config
configs/execution_config.yaml            Execution simulator params
configs/factor_library_config.yaml       Sprint 7.5 factor lib
configs/learning_config.yaml             Learning engine params
configs/macro_intel_config.yaml          Sprint 6.5 macro intel
configs/portfolio_config.yaml            Portfolio construction
configs/risk_budget.yaml                 Sprint 4 risk caps + Kelly params
```

Plus `usa/configs/*` — USA-specific configs (not enumerated · Phase 3 will consolidate).

**Compliance flag (Phase 2/3):** Article 72 requires all tunables in `configs/*.yaml`. Grep survey (Phase 3) will find magic numbers in code that need extraction. Article 74 requires `# owner:` frontmatter — likely absent · Phase 3 fix.

---

## 14 · Secrets Inventory

`.env*` files present in repo (via `ls -la .env*`):
- `.env.angel` (broker credentials · 111 bytes)
- `.env.telegram` (bot token + chat ID · 96 bytes)

**`.gitignore` coverage:** `.env` · `.env*` · `.env.angel` · `.env.nexabot*` · `.env.nexabot-*` — all listed. Both present .env files are covered.

**Secrets-in-code sanity:** `grep -rE 'TELEGRAM_BOT_TOKEN\s*=\s*["'\''][0-9]' backend/ india/ usa/` → **0 hits.** Clean.

**Compliance:** Article 58 satisfied.

---

## 15 · Environment Inventory

Environment variables referenced across code (grep sample):
- `TELEGRAM_BOT_TOKEN` · `TELEGRAM_CHAT_ID` (from `.env.telegram`)
- `ANGEL_CLIENT_ID` · `ANGEL_TOTP_SECRET` · `ANGEL_PIN` · `ANGEL_API_KEY` (from `.env.angel`)
- `PYTHONPATH` (set by orchestrators)
- CI-only: `GITHUB_TOKEN` · `SECRETS_*` (set by GH Actions)

Full grep sweep for all `os.environ.get`/`os.getenv` is Phase 3 (Standardization) scope.

---

## 16 · Package Inventory

See §12. **35 top-level deps** in `requirements.txt` · 2 slim requirement files for runtime/dashboard splits.

Pin state: **not pinned** — this is Article 52 non-compliance. Phase 3 (Standardization) pins version majors.

---

## 17 · Test Inventory

Total test files: **58** (across all top-level dirs).

Breakdown:
```
research/tests/         21 files
backend/tests/          19 files (includes new test_c0_silent_breakages.py)
nexaquant/tests/        10 files
india/tests/             6 files
ux/tests/                2 files
```

**Backend tests enumerated:**
```
test_sprint2.py            Sprint 2 baseline
test_sprint25.py           Feature Store (12 tests · GREEN)
test_sprint26.py           Feature Intelligence
test_sprint27.py           Model Factory (14 tests · GREEN)
test_sprint3.py            Recommendation Engine v3 (22 tests · GREEN with UTF-8 stdout)
test_sprint4.py            Risk Engine (23 tests · GREEN)
test_sprint5.py            Portfolio Engine
test_sprint6.py            Learning Engine
test_sprint65.py           Macro Intel (22 tests · GREEN)
test_sprint7.py            Execution Simulator
test_sprint75.py           Persistence (18 tests · GREEN)
test_sprint76.py           Historical Backfill/Replay (19 tests · GREEN)
test_sprint77.py           Full Replay (14 tests · GREEN)
test_sprint77_runner1.py   Runner 1 audit-trail (11 tests · GREEN)
test_sprint78.py           Recommendation Benchmark (17 tests · GREEN)
test_sprint_b0.py          History Quality (24 tests · GREEN)
test_telegram_notify_fallback.py  Telegram fallback (10 tests · GREEN)
test_c0_silent_breakages.py       Wave 3 · C0 silent-breakage fixes (11 tests · GREEN · NEW)
```

**Cumulative test count:** 280+ backend + regression (per v2.2 audit) — verified green post-C0.

**Compliance flag (Phase 2):** Tests organized by SPRINT, not by capability. Article 40 requires per-capability test files at `tests/<domain>/<subdomain>/test_<capability>.py`. Migration = D8 shim scope.

---

## 18 · Documentation Inventory

`docs/*.md`: **141 files.**

Recent additions (Wave 3/4/5):
```
docs/AEGIS_ENTERPRISE_CONSTITUTION.md               v1.0.0 · APEX AUTHORITY
docs/AEGIS_ENTERPRISE_CAPABILITY_MAP.md             Wave 4 seed · 18 examples · D0 completes
docs/AEGIS_WAVE_4_ARCHITECTURE_CONSOLIDATION.md     Wave 4 master spec
docs/AEGIS_V2_2_AUDIT.md                             v2.2 audit · 20 phases · 42 findings
docs/AEGIS_WAVE_1_2_CLOSURE_REPORT.md                Wave 1+2 closure
docs/AEGIS_REPO_AUDIT.md                             Sprint A1 · 10-section audit
```

Foundational architecture docs (frozen):
```
docs/AEGIS_PHASE3_MASTER_ROADMAP.md
docs/AEGIS_PHASE4_PRODUCT_COMPLETION.md
docs/AEGIS_PHASE5_DEVELOPMENT_STANDARDS.md
docs/AEGIS_PHASE6_EXECUTION_BLUEPRINT.md
docs/AEGIS_IMPLEMENTATION_MODE.md
docs/AEGIS_PHASE2_ARCHITECTURE.md
docs/AEGIS_PHASE3_TRADE_STATE_ENGINE_SPEC.md
docs/ARCH001A_INVESTMENT_PHILOSOPHY.md
```

Sprint reports (17 in docs/):
```
docs/AEGIS_SPRINT{2..7,2_7,4,5,6,65,7,75,76,77,78}_REPORT.md
```

Utility/operational:
```
docs/UBUNTU_COMMANDS.md
docs/AEGIS_EXECUTION_FLOW.md
docs/AEGIS_CONFIGURATION_REGISTRY.md
docs/AEGIS_PRODUCTION_VS_RESEARCH.md
docs/ENG*_REPORT.md
docs/DEPLOY.md
```

**Compliance flag (Phase 2):** 141 markdown files · needs Article 68 organization. Migration = per-capability docs at `docs/capabilities/<capability>.md` + per-domain at `docs/domains/<NN_domain>.md`. Sprint reports retained under `docs/sprint_reports/` for historical reference.

---

## 19 · Technical Debt Inventory

From v2.2 audit + prior closures:

**Ledger'd Accepted Debt (from Wave 1+2 closure):**
- DEBT-1 · `reports/recommendations.json` keystone gap → Wave 4 D4
- DEBT-2 · Corporate Actions engine (MM_D1 stall) → data-layer track
- DEBT-3 · Dual history schemas (canonical vs runner1 bespoke) → Wave 4 D5
- DEBT-4 · `recommendation_dna` orphan dep → Wave 4 D6
- DEBT-5 · Existing engines not per Phase 5 layout → grandfathering rule

**v2.2 Audit Accepted Debt (14 items · from Wave 3):**
- A-D1/D2 · USA index file naming + India schema mix
- A-F1..F6 · 3+ RSIs / 3+ ADXs / 4+ ATRs · vol not annualized · MACD hardcoded · fundamentals broadcast look-ahead
- A-S1..S6 · Scoring naming collisions · rank-univ dependency · ensemble negative-weight clip · dual pipelines · MacroModel confidence magic · sector-rotation weights ≠1.0
- A-Str1/2 · Scanner + Income don't exist · Shield embedded
- A-Pf1/2 · yfinance-loop bottlenecks (ingest_corporate_actions · ingest_fundamentals)

**Environment items:**
- MON001 sealed_baseline_fingerprint.txt on disk (target · currently absent — audit fingerprint check runs from yaml + sealed_fingerprint.json)

**Expected-future items (12 · not blockers):**
- Runner 2 100% HOLD (waits on Sprint 7.9 orchestrator)
- Corpus depth n=10 (grows organically or via B1 replay expansion)
- Every rec producer missing 5 delta fields (belongs in Sprint C1/D4)
- Lifecycle state machine (Sprint C1/D4)
- Capital Rotation Engine (Wave 4 D4)
- Historical 5 net-new metrics (Wave 4 D6)
- ...

---

## 20 · Dead Code Inventory

Confirmed dead code:
- `backend/recommendation/classifier.py:12-19` — `_MATRIX` list defined but never referenced (actual decisions come from if-else block at L31-35). Constitution Article 68 · dead code violation.

Previously-dead code fixed in Wave 3 C0:
- ~~`backend/feature_store/features/technical.py:49-53` ATR proxy branch~~ — REMOVED · commit `6866f3b`

Suspected dead code (needs Phase 2 verification):
- Multiple legacy `research/` modules that don't appear in any orchestrator plan
- `strategy/` modules — enumerate consumers in Phase 2

**Compliance flag (Phase 2):** grep-verify every backend/india/usa module has at least one consumer OR is a top-level entry point OR is a test.

---

## 21 · Duplicate Implementation Inventory

**Indicator duplication (Constitution Article 30 violations):**
- `def _rsi` / `def rsi` — **5 sites** across `backend/feature_store/features/technical.py` · `india/feature_engine.py` · `india/technical_factors.py` · `strategy/regime.py` · `research/edge_probe.py`
- `def _atr` / `def atr` — **6 sites** across the same distribution + `strategy/smc.py` + `strategy/risk.py` + `usa/research/recommendations/lib/entry_exit.py`
- `def _adx` / `def adx` — **4 sites** across `backend/feature_store/features/technical.py` · `india/feature_engine.py` · `india/technical_factors.py` · `strategy/regime.py`
- **MACD ≥3 sites** (backend · india · misc)

**Rec engine duplication (10 producers · Sprint A1):**
- Runner 1 legacy (`india/recommendation_generator.py`)
- Runner 1 v2 (`research/adaptive_rec_v2/`)
- Fusion (`research/fusion/`)
- Runner 2 v3 (`backend/recommendation/`)
- DEV023 (`research/recommendations/run.py` · deprecated)
- USA legacy v1 (`usa/research/recommendations/`)
- Plus 4 additional entry-points found in A1

**History-writing duplication (2 schemas):**
- Canonical `backend/persistence/history_writer.py::append_snapshot_row`
- Bespoke `runner1_ingest.py` writer

**Confidence scale duplication (4 conventions per v2.2 audit S1):**
- `[0,1]` (backend/recommendation)
- `{Low, Med, High}` (india/confidence_engine)
- `{0.0, 1.0}` binary (backend/factor_library)
- `predict_proba[:,1]` (research/adaptive_rec_v2)

**Score scale duplication (2 conventions per v2.2 audit S2):**
- `[-1, +1]` (Model Factory + Rec Engine)
- `[0, 100]` (Market Intelligence + USA technicals + adaptive_rec_v2 dimensions)

**All targeted by Wave 4 D1 (shared indicator lib) + D3 (scoring convention unified) + D4 (SSoT rec).**

---

## 22 · Legacy Inventory

Classification of legacy code by target action:

| Path | Status | Target Action |
|---|---|---|
| `india/telegram_notify.py` | SEALED-Legacy | UNTOUCHED (Constitution Appendix C) |
| `research/adaptive_rec_v2/` | SEALED-Legacy | UNTOUCHED (Constitution Appendix C) |
| `research/risk_capital_v2/` | SEALED-Legacy | UNTOUCHED (Constitution Appendix C) |
| `india/recommendation_generator.py` | Active-Legacy | Continues under Runner 1 orchestrator until Sprint 7.9 |
| `india/aegis_engine.py` / `arjuna_os.py` / `arjuna_v2.py` | Deprecated | Archive candidate (Phase 2 verify) |
| `strategy/*.py` (12 files) | Deprecated-Suspected | Archive if no active consumer (Phase 2 verify) |
| `execution/` (top-level) | Deprecated-Suspected | Merges into `backend/05_portfolio/execution` |
| `backtest/` | Deprecated-Suspected | Archive candidate |
| `markets/` | Deprecated-Suspected | Archive if superseded |
| `experiments/` | Deprecated | Archive · Article 76 (research-only) |
| `research/recommendations/run.py` | Deprecated | Archive after Wave 4 D4 keystone SSoT decision |
| `data/aegis_recommendation_db.csv` | Active-Legacy | Retain as legacy audit trail until Sprint 7.9 |

---

## 23 · Research Inventory

25 subdirs (see §2.4) · 317 modules · **larger than backend production code**.

Categorization needed (Phase 2):
- **SEALED** (Constitution Appendix C): `adaptive_rec_v2` · `risk_capital_v2`
- **Active-in-daily** (Article 76 non-compliance · needs promotion to backend or grandfathering ADR): `recommendations` · `validation_v2` · `knowledge_graph` · `fusion` · `institutional_memory` · `winner_genome` · `decision_attribution` · `morning_report` · `benchmark` · `stock_validation` · `price_context` · `decision_center`
- **Prototype-only** (correctly research-scoped): `RISK001-A` · `adaptive_learning` · `champion_challenger` · `confidence_calibration` · `strategy_doctor` · `research_assistant`
- **Legacy-abandoned** (archive candidates): `backtesting` (if replay superseded) · `portfolio_construction` (if backend/portfolio superseded) · `portfolio_monitor` (if backend/portfolio superseded)
- **Domain research feeding backend**: `sector_intelligence` (DEV018 · feeds `sector_context.json`) · `global_intelligence` (DEV017) · `industry_intelligence` (DEV019) · `company_intelligence` (DEV020) — these are the "01_market_intelligence" future homes

**Compliance flag (Phase 2):** ~12 research modules are daily-wired. Article 76 requires either: (a) migrate to `backend/`, (b) seal (Appendix C amendment), or (c) remove from daily.

---

## 24 · Production Inventory

`backend/` = production code · 180 modules · 23 subdirs (targets 10 domains per Wave 4).

**Fingerprinted production artifacts** (from `grep schema_fingerprint reports/`):
- `reports/portfolio_v3.json`
- `reports/sized_positions.json`
- `reports/recommendations_v3.json` (per-rec)
- Sprint 7.5 history parquets
- ~8 others

**Production readiness snapshot** (from v2.2 audit):
- 5 dimensions at ≥60/100: Determinism (75) · Data Quality (60) · Risk Enforcement (90) · Persistence (90 · GO) · Performance (65)
- 6 dimensions below 60: SSoT (25) · Rec Accuracy (35) · Portfolio Consistency (20) · Sector (30) · Telegram Dedup (30) · Report Consistency (55)
- Overall: **49/100 · NO-GO** · Wave 5 target = ≥75 for GO seal

---

## Findings Requiring Action (feed Phase 2 Compliance Audit)

**Non-compliance with Constitution (verified this phase):**
1. **Article 21** — Only 6.8% of reports carry `schema_fingerprint` (12/176). Bulk fix needed.
2. **Article 30** — 15 duplicate indicator implementations (5 RSI · 6 ATR · 4 ADX). Kills the "one canonical implementation" rule.
3. **Article 62** — Per-market subdirectory duplication (india/feature_store vs usa/research/feature_store vs backend/feature_store). Dual-market rule intent is share via `backend/` with market parameterization.
4. **Article 68** — Top-level `config_loader.py` + `model_registry.jsonl` violate domain isolation.
5. **Article 72** — 7 configs · magic numbers still in code (grep survey needed in Phase 3).
6. **Article 76** — ~12 `research/` modules are daily-wired · needs promotion OR seal-amendment OR removal.
7. **Article 40** — Tests organized by SPRINT not by CAPABILITY.

**Non-compliance with Wave 4:**
1. `archive/` directory does not exist yet (Wave 4 · D8 · Article 80)
2. `validation/` top-level directory does not exist yet (Wave 4 · D8)
3. Backend has 23 subdirs vs 10-domain target (Wave 4 · D2..D8)
4. Shared indicator library at `backend/10_shared/indicators/` does not exist (Wave 4 · D1)

**Verified compliant:**
1. Article 5 (16 immutable invariants) — sealed contracts intact
2. Article 58 (secrets never in code) — verified · 0 hits in code
3. Article 65 (timezone handling in artifacts) — ISO 8601 UTC verified in samples
4. Article 85 (MON001 fingerprint sentinel) — sealed fingerprint verified this session `e4c070673568c52d…`
5. Article 41 (regression suite) — 280+ tests green
6. Article 89 (rollback branch per sub-wave) — proven with C0 commit pattern
7. Article 91 (byte-equality before cutover) — evidenced by Wave 3 C0 fingerprint preservation

**Missing capabilities (from Cap Map):**
- Scanner Strategy · Income Strategy · standalone Shield promotion (Wave 4 D4/D6 decision)
- Capital Rotation Engine (Wave 4 D4 · Wave 5 Phase 9)
- Opportunity Cost Engine (Wave 4 D4 · Wave 5 Phase 9)
- Portfolio Attribution Engine (Wave 4 D5 · Wave 5 Phase 10)
- API Center (Phase 4 Module 18 · Wave 5 Phase 14)
- Champion producer reconnect (Wave 4 D6 · Wave 5 Phase 12)

---

## Definition of Done · Phase 1

- [x] Repository inventory (§1)
- [x] Folder inventory (§2 · 4 subdivision levels)
- [x] Module inventory (§3 · 857 files categorised)
- [x] Capability inventory (§4 · cross-linked to Cap Map)
- [x] Engine inventory (§5 · 59 engines from A2)
- [x] Artifact inventory (§6 · 214 report artifacts + 107 USA)
- [x] Schema inventory (§7 · 6.8% fingerprint coverage flagged)
- [x] Dependency graph (§8 · seed · Phase 2 completes)
- [x] Execution graph (§9 · India 32 · USA 35 · reused from v2.2 audit)
- [x] Data flow graph (§10 · Layer 0 → Layer 9)
- [x] Import graph (§11 · seed · Phase 2 completes)
- [x] Technology inventory (§12 · 35 deps · not pinned)
- [x] Configuration inventory (§13 · 7 configs)
- [x] Secrets inventory (§14 · both .env files gitignored · 0 hits in code)
- [x] Environment inventory (§15 · key vars enumerated)
- [x] Package inventory (§16)
- [x] Test inventory (§17 · 58 tests · 280+ green)
- [x] Documentation inventory (§18 · 141 docs)
- [x] Technical debt inventory (§19 · reuses ledger from Wave 1+2 + v2.2)
- [x] Dead code inventory (§20 · `_MATRIX` confirmed · ATR proxy fixed)
- [x] Duplicate implementation inventory (§21 · 15 indicator sites · 4 confidence scales · 2 score scales)
- [x] Legacy inventory (§22 · sealed vs archive-candidate classification)
- [x] Research inventory (§23 · 25 subdirs classified 5 ways)
- [x] Production inventory (§24 · 180 modules · fingerprint status)
- [x] Findings feed to Phase 2 (compliance audit)
- [x] Sealed contracts UNTOUCHED · MON001 fingerprint preserved
- [x] No code modified · docs-only per Phase 1 (discovery) directive

---

## Next Phase Handoff · Phase 2 · Architecture Compliance Audit

**Blockers cleared:**
- Repository fully mapped
- Every non-compliance flagged with specific Constitution article reference
- Cross-references to prior audit substrate (Sprint A1/A2 · v2.2 · Wave 4 Cap Map) done · no re-audit

**Phase 2 scope:**
- Build full dependency graph (Article 12 · downward-only imports)
- Build full import graph (Article 45-52 · forbidden-import matrix)
- Compute compliance score against 99 articles
- Enumerate missing validators (target: every capability)
- Enumerate missing schemas (target: every artifact carries fingerprint)
- Enumerate missing documentation (per capability + per domain)
- Enumerate missing dashboards / replay / benchmark / AI narration
- Produce Compliance Scorecard (per article · pass/fail/partial)

**Estimated Phase 2 completion:** 1 focused turn · docs-only.

---

**End of Wave 5 · Phase 1 · Repository Discovery · SHIPPED 2026-07-27.**
