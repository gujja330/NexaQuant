# AEGIS · Wave 4 · Enterprise Architecture Consolidation
### 🔒 LOCKED 2026-07-27 · Last major structural sweep · Domain-centric · Post-cleanup → feature-evolution mode

**Reframe origin:** operator recognized mid-Wave-3 that C0/C1/C2/... labels are temporary implementation phases with no long-term meaning (same problem as Agent1/Agent2 naming). AEGIS is now an **institutional platform** — 59+ engines communicating through artifacts. Wave 4 organizes by **business capability**, not by cleanup sprint. This is the **last** structural sweep before AEGIS transitions to feature evolution.

**Supersedes:** Wave 3 phases C1..C7 (feature-centric). Wave 3 C0 stands — silent-breakage substrate fixes (ATR/ADX/sector schema) were required regardless of target architecture. The fixes that C1..C7 would have made (keystone gap · telegram concurrency · capital rotation · opportunity cost · portfolio attribution · institutional acceptance testing) still happen in Wave 4 but land inside the domain structure with proper capability records.

**Sequencing:** Wave 4 is 9 sub-waves (D0..D8). Each is a full end-to-end vertical slice per Implementation Mode · dual-market rule applies · sealed contracts UNTOUCHED · MON001 fingerprint preserved across every cutover.

---

## 0 · Guiding Principles

1. **Capability > File.** A capability is a thing the business does (Sector Rotation · Recommendation Ranking · Telegram Digest). A file is an implementation detail. Wave 4 catalogues capabilities, not files.
2. **One Home per Capability.** Every capability lives in exactly one domain folder. No cross-cutting "shared logic" ambiguity — either it's a domain capability or it's a `10_shared/` primitive.
3. **Producers own Schemas.** The engine that writes an artifact owns its schema. Consumers read via that schema. Schema drift = producer's problem.
4. **Every Engine has a Validator.** No engine ships without a validator in `validation/`. Validators run in CI.
5. **Sealed Contracts stay Sealed.** `india/telegram_notify.py` · `research/adaptive_rec_v2/` · `research/risk_capital_v2/` · MON001 fingerprint `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf` — untouched throughout Wave 4.
6. **Move via `git mv`.** Reorg preserves history. No delete+create.
7. **Coexistence during Migration.** New domain modules live alongside legacy paths until each cutover has proven byte-identical output. No big-bang.
8. **After Wave 4 = feature evolution only.** No more structural sprints. The 5-pillar authority (Phase 3/4/5/6 + Implementation Mode) + this Wave 4 seal becomes the sole architectural constitution.

---

## 1 · Target Repository Layout

### 1.1 Top-level Separation

```
aegis/
  backend/       business logic — the 10 domains below
  research/      experiments, DEV* prototypes, one-off studies (NEVER daily-wired)
  reports/       produced artifacts (output-only; no code)
  configs/       yaml configs · single source of tunables
  docs/          architecture · specs · roadmaps · closures
  tests/         mirrors backend/ + validation/
  scripts/       orchestrators + CLI entry points
  archive/       deprecated code kept for reference only
  validation/    per-engine validators (top-level · mirrors backend structure)
```

### 1.2 Backend · 10-Domain Model

```
backend/
  01_market_intelligence/
      global_engine/      global macro-risk + posture
      sector_engine/      sector-level composite (DEV018 · 13-dim)
      industry_engine/    industry decomposition of sector
      company_engine/     company-level intelligence

  02_feature_platform/
      technical/          RSI · MACD · ADX · ATR · EMA · SMA · Bollinger · momentum · returns · volatility · drawdown · position-in-range
      fundamental/        ROE · D/E · PE · PB · margins · growth · quality composites
      macro/              10Y · DXY · gold · WTI · VIX · MOVE · yield curve
      sector/             sector features per ticker (rank · leader/laggard flags)
      earnings/           days-to-next · surprise history · guidance change
      institutional/      inst-owned · insider net · FII/DII net
      news/               polarity · headline count · sentiment shift
      corporate_actions/  days-since-dividend · split ratio · buyback flag
      market_structure/   depth · liquidity · volume-ratio · gap detection

  03_model_platform/
      models/
          momentum/       trend/            value/
          growth/         quality/          mean_reversion/
          news_model/     macro_model/      sector_rotation/
          event_driven/   ai_hybrid/
      ensembles/          weighted combination · configurable weights
      calibration/        historical-precision multiplier · Platt/isotonic
      ranking/            cross-sectional rank-score · universe-aware
      scoring/            composite [-1,+1] and [0,100] converters

  04_recommendation/
      recommendation_engine/    Runner 2 v3 (backend/recommendation)
      confidence/               unified confidence scale (per Wave 4 · single source)
      explainability/           bull/bear/entry/exit/dimensions/delta-fields
      recommendation_dna/       DNA persist + feedback (from research/recommendation_dna)
      capital_rotation/         NEW · keep_score/candidate_score/rotate/exit/trim/add
      opportunity_cost/         NEW · every HOLD must justify "why not rotate"

  05_portfolio/
      construction/       N-name portfolio builder
      optimization/       Kelly + fractional + HRP
      monitoring/         attribution · drift · rebalance-diff
      risk/               VaR/CVaR/HHI/exposure caps/concentration/vol-adjust
      sizing/             per-position sizing rules
      execution/          simulator · fills · slippage · commission · equity curve

  06_learning/
      adaptive_learning/  outcome ledger · rec DNA feedback loop
      replay/             historical backfill · deterministic replay driver
      benchmark/          Wilson CI · normal-approx CI · sample-size verdicts
      strategy_doctor/    per-strategy diagnosis · why-underperformed
      champion/           current-champion strategy tracker
      challenger/         challenger promotion protocol

  07_knowledge/
      knowledge_graph/    entities · relationships · timeline nodes
      relationships/      Oil→Transport→Airlines→IndiGo→Margins chains
      institutional_memory/  recall · "have we seen this?"

  08_delivery/
      reports/            morning report · executive summary · sector brief
      dashboard/          India + USA SPA
      telegram/           SEALED sender + orchestration (concurrency + dedup at orch layer)
      api/                REST/OpenAPI (Phase 4 Module 18)

  09_platform/
      scheduler/          GH Actions + Windows tasks + cron
      orchestration/      aegis_daily_v2 · usa_daily · replay controller
      persistence/        append-only history (Sprint 7.5 aegis.persistence.v1)
      validation/         inline validation-during-pipeline (distinct from top-level validation/)
      contracts/          shared type definitions · sealed-fingerprint sentinel
      registry/           model registry · feature manifest · universe
      monitoring/         MON001 sealed · ops-check · fingerprint drift

  10_shared/
      indicators/         ONE rsi.py · atr.py · adx.py · macd.py · ema.py · sma.py · volatility.py · beta.py · sharpe.py · sortino.py
      utils/              math · date · io helpers
      constants/          MARKET_TZ · TRADING_DAYS_YEAR · ANNUALIZER
      schemas/            CanonicalBar · CanonicalDataset · SizedPosition · Recommendation
```

### 1.3 Validation Architecture (top-level `validation/`)

Mirrors backend structure — every capability has a validator.

```
validation/
  data_validation/            OHLC integrity · duplicates · NaN · delistings
  feature_validation/         mathematical correctness per feature
  factor_validation/          factor library null-rate · dispersion · monotonicity
  indicator_validation/       shared indicators: RSI/ATR/ADX/MACD/EMA/SMA/VOL/BETA
  fundamentals_validation/    latest-vs-as-of · look-ahead detection · sanity
  technical_validation/       feature-store technical output · scale sanity
  macro_validation/           regime coherence · symbol-map completeness
  sector_validation/          taxonomy · schema · rotation math
  model_validation/           determinism · rank/scale · confidence semantics
  recommendation_validation/  action classifier · calibration · disagreement handling
  portfolio_validation/       size limits · cash policy · turnover · concentration
  replay_validation/          byte-equality · frozen-clock · resume determinism
  benchmark_validation/       Wilson CI · sample-size gates · verdicts
  report_validation/          schema fingerprint · required fields · staleness
  telegram_validation/        dedup key · concurrency · retry semantics
  dashboard_validation/       data-source pinning · cache-bust · schema alignment
  workflow_validation/        cron collision · concurrency block · publish-marker order
  contract_validation/        sealed contracts UNTOUCHED · fingerprint preserved
  schema_validation/          producer-owner registry · consumer compatibility
  performance_validation/     per-step budget · memory · zero-caching audit
  integration_validation/     E2E chain integrity · 32-step India · 35-step USA
```

**Rule:** every engine in `backend/` has a corresponding validator in `validation/` at the same path depth. `backend/04_recommendation/capital_rotation/` → `validation/recommendation_validation/capital_rotation_validator.py`.

---

## 2 · Enterprise Capability Map · Master Spec

### 2.1 Twenty-Field Template (mandatory for every capability)

| # | Field | Purpose |
|---|-------|---------|
| 1 | Capability | Plain-language name |
| 2 | Owner | Target domain path (e.g. `04_recommendation/capital_rotation`) |
| 3 | Input | Artifacts consumed + external sources |
| 4 | Output | Artifacts produced |
| 5 | Schema | Fingerprint + schema version |
| 6 | Consumers | Downstream engines that read the output |
| 7 | Tests | Path + test count |
| 8 | Validator | Path in `validation/` |
| 9 | Documentation | Path in `docs/` |
| 10 | Dashboard | Tile / route in SPA |
| 11 | Reports | Files emitted |
| 12 | Telegram | Integration point (or N/A) |
| 13 | Replay | Replay-driver present (Y/N) |
| 14 | Benchmark | Benchmarked (Y/N) |
| 15 | AI Narration | Which narrator (or N/A) |
| 16 | Status | Active / Deprecated / Missing / Planned |
| 17 | Version | Semver |
| 18 | Deprecated? | Y/N |
| 19 | Replacement | Capability name if deprecated |
| 20 | Migration | Notes if being consolidated in Wave 4 |

**Rule:** any capability with an empty field is NOT production-ready. D0 populates all 20 fields for every Active engine.

### 2.2 Initial Roster (from Sprint A1 · 59 engines · full detail in D0)

Grouped by target domain. Populated fully in D0. Sprint A2 already produced `reports/research_engine_inventory.json` as the working substrate.

- **01_market_intelligence** (4): global_engine · sector_engine (DEV018) · industry_engine · company_engine
- **02_feature_platform** (9): technical · fundamental · macro · sector · earnings · institutional · news · corporate_actions · market_structure
- **03_model_platform** (11 models + ensemble/calibration/ranking/scoring): momentum · trend · value · growth · quality · mean_reversion · news_model · macro_model · sector_rotation · event_driven · ai_hybrid
- **04_recommendation** (6): recommendation_engine (v3 · Runner 2) · confidence · explainability · recommendation_dna · capital_rotation (NEW) · opportunity_cost (NEW)
- **05_portfolio** (6): construction · optimization · monitoring · risk · sizing · execution
- **06_learning** (6): adaptive_learning · replay · benchmark · strategy_doctor · champion · challenger
- **07_knowledge** (3): knowledge_graph · relationships · institutional_memory
- **08_delivery** (4): reports · dashboard · telegram · api
- **09_platform** (7): scheduler · orchestration · persistence · validation · contracts · registry · monitoring
- **10_shared** (indicators library — target: ONE canonical implementation of RSI/ATR/ADX/MACD/EMA/SMA/volatility/beta/sharpe/sortino)

Total: 59 core + 6 Wave-4 NEW = 65 capabilities in target catalog.

See [`docs/AEGIS_ENTERPRISE_CAPABILITY_MAP.md`](AEGIS_ENTERPRISE_CAPABILITY_MAP.md) for populated entries.

---

## 3 · Shared Library Consolidation (10_shared/indicators)

**Audit finding:** 4+ ATR · 3 RSI · 3 ADX implementations across `backend/feature_store` · `india/feature_engine.py` · `india/technical_factors.py` · `strategy/*.py` · `usa/research/recommendations/lib/entry_exit.py` · `research/edge_probe.py`. No shared library. Divergent conventions per engine.

**Wave 4 D1 target:**

```
backend/10_shared/indicators/
    __init__.py            re-exports the canonical set
    rsi.py                 Wilder EWM + simple-rolling variants documented explicitly
    atr.py                 true-range using real H/L/C
    adx.py                 textbook Wilder ADX using real H/L
    macd.py                12/26/9 default + parameterizable
    ema.py                 span + alpha parameterization
    sma.py                 rolling window
    volatility.py          daily · annualized · realized · GARCH-ready hooks
    bollinger.py           mean ± N·stdev
    beta.py                covariance/variance with rolling window
    correlation.py         Pearson rolling
    sharpe.py              annualized · configurable rf
    sortino.py             downside-deviation variant
    calmar.py              return / max drawdown
    momentum.py            k-day return + percentile
    drawdown.py            rolling max drawdown
    liquidity.py           volume ratio · turnover · dollar-volume
```

Every engine that computes any of the above imports from `backend.shared.indicators` — no local reimplementation permitted. Enforced by `validation/indicator_validation/no_local_reimplementation.py`.

---

## 4 · Wave 4 Sub-Waves (D0..D8)

Each sub-wave is a full end-to-end vertical slice per Implementation Mode. Sealed contracts UNTOUCHED. Dual-market rule applies. Every sub-wave ends with an update to the Executive Dashboard and the Enterprise Capability Map.

### D0 · Enterprise Capability Map · Full Population

**Scope:** every one of 65 capabilities has all 20 fields populated in [`docs/AEGIS_ENTERPRISE_CAPABILITY_MAP.md`](AEGIS_ENTERPRISE_CAPABILITY_MAP.md).

**Blockers cleared:** identify missing capabilities (Scanner · Income · Champion Producer) explicitly · classify Runner-1 engines as `Active-Legacy` (kept during migration) vs `Deprecated` (to be archived).

**Deliverable:** Cap Map fully populated + reports/research_engine_inventory.json refreshed to match.

### D1 · Shared Indicator Library

**Scope:** create `backend/10_shared/indicators/` with the ~16 canonical implementations · migrate `backend/feature_store/features/technical.py` to import from there · leave `india/technical_factors.py` and `india/feature_engine.py` as `Active-Legacy` importers until D2 (feature platform reorg) cuts them over.

**Deliverable:** grep `def rsi\|def atr\|def adx\|def macd` in `backend/` returns 1 hit each (in `10_shared/indicators/`). Old implementations become thin re-exports pending D2.

**Validator:** `validation/indicator_validation/*` — mathematical equivalence + no-local-reimplementation.

### D2 · Feature Platform Reorganization

**Scope:** `git mv backend/feature_store/features/* → backend/02_feature_platform/<category>/` · re-wire `feature_registry` imports · migrate `india/feature_engine.py` and `india/technical_factors.py` to import from `backend.02_feature_platform` (dropping local reimplementations) · every feature gets a validator in `validation/feature_validation/`.

**Deliverable:** feature_store consumers unchanged (backward-compatible re-export) · 81 features unchanged in count · schema fingerprint `b65ceb49a83a` preserved.

### D3 · Model Platform Reorganization

**Scope:** `git mv backend/model_factory/models/* → backend/03_model_platform/models/<name>/` · fix scoring-scale fragmentation (audit finding S1/S2 · unified confidence and score conventions documented in `03_model_platform/scoring/`) · fix STRONG_BUY-unreachable-in-stress bug (audit S4) · remove classifier dead-code `_MATRIX` (audit S7).

**Deliverable:** 11 models + ensemble under one domain · scoring layer explicit · calibration+ranking modules extracted · validators for every model.

### D4 · Recommendation Domain + Keystone SSoT + Capital Rotation + Opportunity Cost

**Scope (biggest sub-wave):**
- Fix keystone gap: `reports/recommendations.json` produced by ONE orchestrator step in `backend/04_recommendation/recommendation_engine/` — either wire Runner 2 v3 output into that path OR migrate 30+ consumers to `recommendations_v3.json`. Migration path chosen at D0 based on consumer count + churn.
- Build **Capital Rotation Engine** at `backend/04_recommendation/capital_rotation/`:
  - `keep_score(p) = 0.35·upside + 0.20·conf_Δ + 0.15·rank_Δ + 0.15·sector + 0.15·pnl`
  - `candidate_score(c) = (0.40·upside + 0.25·conf + 0.20·rank + 0.15·sector) × macro_gate`
  - Decision thresholds: EXIT `<-0.20` · TRIM `<+0.10` · ROTATE if edge `> +0.25`
  - Outputs: `reports/rotation_plan.json` + `_history.parquet` + `rotation_alerts.json`
- Build **Opportunity Cost Engine** at `backend/04_recommendation/opportunity_cost/`:
  - Every HOLD must expose `oc_next_best_ticker` · `oc_expected_alpha_delta` · `oc_reason_not_to_rotate`
- Add 5 delta/change fields to every recommendation (audit R2): `previous_rank` · `confidence_delta` · `sector_change` · `momentum_change` · `risk_change`
- Introduce Recommendation Lifecycle state machine per operator spec: `DISCOVERED · WATCHLIST · NEW BUY · ACTIVE · ADD · REDUCE · TRIM · PARTIAL EXIT · EXIT · ROTATED · ARCHIVED`

**Deliverable:** 9 previously-BROKEN India daily steps now consume fresh data · every rec is explainable · Capital Rotation is a first-class engine.

### D5 · Portfolio Domain + Portfolio Attribution

**Scope:**
- `git mv backend/{risk,portfolio,execution}/* → backend/05_portfolio/<subdomain>/`
- Build **Portfolio Attribution Engine** at `backend/05_portfolio/monitoring/attribution.py`:
  - Every position exposes contribution from: Momentum · Value · Quality · Growth · Sector · Macro · Risk · Fundamentals · News · Corporate Actions · Execution · Learning · Final Attribution
- Resolve Runner-1 `portfolio.json` vs Runner-2 `portfolio_v3.json` divergence: designate `portfolio_v3.json` as SSoT · move `portfolio.json` to `archive/` OR keep as historical-only under `06_learning/adaptive_learning/legacy_runner1_snapshots/`.

**Deliverable:** one portfolio SSoT · every position fully attributed · monitoring covers drift + rebalance-diff + attribution.

### D6 · Learning + Knowledge Domains

**Scope:**
- `git mv backend/{learning,replay,benchmark}/* → backend/06_learning/<subdomain>/`
- Reconnect **Champion Strategy** producer (audit Str1) — currently 10-day stale · reroute so `champion_strategy.json` writes on every daily run · integrate Challenger promotion protocol.
- Add **Replay Determinism regression test** (audit Rep1): replay a fixed window TWICE · hash-compare outputs · assert equal (with `norm_utc()` timestamp normalizer).
- Add `--frozen-clock` mode (audit Rep2): inject `asof_utc` instead of `date.today()` at `engine_drivers.py:304`.
- `git mv backend/knowledge_graph/* → backend/07_knowledge/knowledge_graph/`
- Move `institutional_memory` under `07_knowledge/institutional_memory/`.

**Deliverable:** determinism validated with byte-equality · Champion actively updated · Knowledge Graph in its proper domain.

### D7 · Delivery Domain + Telegram Concurrency + Dedup

**Scope:**
- Reorg `ux/dashboard/*` → `backend/08_delivery/dashboard/` (keeping SPA static assets under `ux/` but orchestration code under `backend/`)
- **Telegram concurrency + dedup at orchestration layer** (audit T1/T2/Sch1):
  - Add `concurrency:` block to `.github/workflows/aegis-daily.yml` (mirror `mon001-daily.yml:27-29`)
  - Move `.published` marker BEFORE Telegram in workflow
  - Add rec-set hash dedup key at `backend/08_delivery/telegram/orchestrator.py` — reject duplicate sends within 4h window
  - `india/telegram_notify.py` STAYS SEALED — only the ORCHESTRATOR wrapping it changes
- Dashboard: cache-bust confirmed · reads pinned to `recommendations_v3.json` (SSoT from D4)
- Report SSoT: designate morning report producer + benchmark consumer as single canonical path per market

**Deliverable:** zero duplicate Telegram sends · dashboard reads SSoT · delivery domain clean.

### D8 · Platform Hardening + Validation Architecture + Institutional Acceptance

**Scope:**
- `git mv backend/persistence/* → backend/09_platform/persistence/`
- `git mv backend/canonical/* → backend/09_platform/contracts/`
- `git mv backend/factor_library/* → backend/06_learning/factor_library/` (arguable — could be `09_platform/`; decided at D0 based on how it's consumed)
- **Wire top-level `validation/` into CI** — every validator runs on every push · surfaces a `validation_scorecard.json`
- Build **Institutional Acceptance Test Suite** at `tests/institutional_acceptance/`: 20 scenarios (Bull · Bear · Sideways · Crash · High-VIX · Low-VIX · Fed · RBI · Earnings · Corp Action · Gap Up · Gap Down · Delisting · Replay · Scheduler Restart · Telegram Failure · API Failure · Data Delay · Market Holiday · Cross-market Execution) — nothing should fail.
- **MON001 sealed_baseline_fingerprint.txt** now on disk · `ops_check.fingerprint.checked = true`
- Final SSoT enforcement pass — every artifact has one producer, verified by grep in CI.

**Deliverable:** production-ready platform · Wave 4 SEAL applied · AEGIS transitions to feature-evolution mode.

---

## 5 · Migration Safety Protocol

### 5.1 Sealed Contracts (UNTOUCHED throughout Wave 4)

| Contract | Location | Protection |
|----------|----------|------------|
| Telegram legacy sender | `india/telegram_notify.py` | Wrapped, not modified |
| Adaptive Rec v2 | `research/adaptive_rec_v2/*` | Bit-preserved · outputs unchanged |
| Risk Capital v2 | `research/risk_capital_v2/*` | Bit-preserved |
| MON001 sealed fingerprint | `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf` | Verified at end of every sub-wave |
| Feature Store schema | `b65ceb49a83a` | Verified at end of every sub-wave |

### 5.2 Cutover Rules

1. **New coexists with old.** For every domain reorg, new location is written first, tested green, THEN legacy path becomes a thin re-exporter, THEN legacy path is removed (in a separate final sub-wave under `archive/`).
2. **`git mv`, not delete+create.** History preserved.
3. **Byte-equality regression test before cutover.** For any capability being moved, run before/after with same inputs, hash outputs, assert equal.
4. **Per-sub-wave rollback branch.** Every sub-wave is on its own branch merged only after all Definition-of-Done items green.

### 5.3 Rollback Strategy

Every sub-wave that fails post-merge validation triggers a `git revert` of the sub-wave's merge commit (not individual commits). The revert restores state exactly. Post-revert, Wave 4 pauses until root cause is understood.

---

## 6 · Definition of Done · Wave 4 Seal

- [ ] Enterprise Capability Map: all 65 capabilities have all 20 fields populated (D0)
- [ ] `backend/10_shared/indicators/`: 16 canonical files · zero local reimplementations (grep `def rsi\|def atr\|def adx\|def macd\|def ema\|def sma` in `backend/` outside `10_shared/` returns 0) (D1)
- [ ] All 10 backend domains exist with the specified subdomains (D2-D8)
- [ ] Every domain has: one owner-doc · one config folder · one test folder · one validator folder (D2-D8)
- [ ] `validation/`: every engine has a validator running in CI (D8)
- [ ] Zero orphan artifacts: grep-verified producer/consumer for every `reports/*.json` and every `reports/*.parquet`
- [ ] Every artifact declares `schema_fingerprint` + `schema_version`
- [ ] Executive Dashboard shows domain-level status, not sprint-level
- [ ] MON001 fingerprint preserved across all cutovers
- [ ] All 280+ tests still green
- [ ] Institutional acceptance test suite: 20 scenarios pass (D8)
- [ ] Production Readiness Score recomputed against domain-model dimensions
- [ ] No `TODO` · no placeholder · no dead code in any `backend/` domain
- [ ] `archive/` contains all deprecated code with README explaining what replaces each item
- [ ] Frozen 5-pillar authority + Wave 4 seal is the sole architectural constitution going forward

---

## 7 · Naming Standards

- **Domains:** `NN_domain_name/` (numeric prefix for stable ordering)
- **Subdomains:** `snake_case/` (single word or hyphen-free compound)
- **Files:** `snake_case.py` matching primary export
- **Configs:** `configs/<domain>_<subdomain>_<capability>.yaml`
- **Reports:** `reports/<domain>/<capability>.json` (D0 decides whether to introduce `reports/<domain>/` subdirs or keep flat)
- **Tests:** `tests/<domain>/<subdomain>/test_<capability>.py`
- **Validators:** `validation/<capability>_validation/<engine>_validator.py`

---

## 8 · Versioning Standards

- **Schema versions:** semver in every artifact JSON at key `schema_version`
- **Engine versions:** semver in code at `<engine>.__version__`
- **Schema fingerprints:** SHA-256 of canonical schema JSON at key `schema_fingerprint`
- **Breaking changes:** major bump + migration doc in `docs/migrations/<engine>_<version>_migration.md`
- **Deprecation:** minor bump with `deprecated = True` flag · 2 sub-waves grace period before archive

---

## 9 · CI/CD Restructuring

- One workflow per top-level domain: `aegis-<domain>-ci.yml`
- Validators run on every push to `backend/<domain>/` OR `validation/<capability>_validation/`
- Full-repo regression only on `main` branch push
- Sealed-contract check runs on every workflow (MON001 fingerprint + FS schema fingerprint)

---

## 10 · Test Restructuring

- Mirror backend structure: `tests/<domain>/<subdomain>/test_<capability>.py`
- One test file per capability (not per sprint)
- Existing `test_sprint*.py` files migrate to their capability-matching location under `tests/legacy_sprint_shim/` and eventually archived
- New tests go to their capability home from day one

---

## 11 · Documentation Restructuring

- `docs/architecture/` — the 5-pillar authority + Wave 4 seal
- `docs/capabilities/<capability>.md` — per-capability spec (auto-generated from the Cap Map for consistency)
- `docs/migrations/<engine>_<version>_migration.md` — per breaking change
- `docs/decisions/<yyyy-mm-dd>_<title>.md` — ADRs (architecture decision records) · going forward standard

---

## 12 · Archive Strategy

- `archive/` contains all deprecated code
- Each archived module has a README explaining: what it did · what replaced it · when it was archived · why kept (typically for historical reference or replay of past states)
- Archived code is NOT imported by anything in `backend/`. Only reachable from `research/` for backtesting.

---

## 13 · Wave 4 Post-Seal Rules

After Wave 4 seal:
1. NO new top-level domains
2. NO new subdomains without an ADR in `docs/decisions/`
3. NO cross-domain imports except via `10_shared/`
4. Every feature evolution ships as a full end-to-end vertical slice per Implementation Mode
5. Every feature evolution updates its capability's row in the Enterprise Capability Map
6. Structural refactor requires an ADR + operator sign-off

---

## 14 · Wave 3 · What Persists · What Retires

**Persists (still valid):**
- Wave 3 C0 (silent-breakage fixes) — commit `6866f3b` · ATR/ADX/sector schema fixes stand
- v2.2 audit findings — 42 findings still the working substrate for Wave 4 (each Must-Fix is now scoped to a specific sub-wave)
- Production Readiness Score methodology — recomputed against domain-model dimensions at end of D8

**Retires (superseded):**
- Wave 3 C1..C7 phase labels — replaced by D0..D8 domain-centric sub-waves
- "Cleanup engineer" framing — replaced by "platform architect" framing
- File-centric duplicate hunting — replaced by capability-centric consolidation
- Sprint-based executive dashboard tiles — replaced by domain-level status

---

## 15 · Sequencing Summary

```
Wave 3 · C0  [SHIPPED · commit 6866f3b]
             ↓ substrate for any target architecture

Wave 4 · D0  Enterprise Capability Map · full population
       · D1  Shared Indicator Library
       · D2  Feature Platform reorg
       · D3  Model Platform reorg
       · D4  Recommendation + Keystone SSoT + Capital Rotation + Opp Cost
       · D5  Portfolio + Portfolio Attribution
       · D6  Learning + Knowledge + Replay determinism + Champion reconnect
       · D7  Delivery + Telegram concurrency
       · D8  Platform hardening + Validation architecture + Institutional Acceptance
             ↓
Wave 4 SEAL · AEGIS transitions to feature-evolution mode
             ↓
Phase 3/4/5/6 + Implementation Mode + Wave 4 seal = sole architectural constitution
Feature evolution only. No more structural sprints.
```

---

**End of Wave 4 · Enterprise Architecture Consolidation · LOCKED 2026-07-27.**

**Next execution step:** D0 · full Enterprise Capability Map population per 20-field template. Deliverable at [`docs/AEGIS_ENTERPRISE_CAPABILITY_MAP.md`](AEGIS_ENTERPRISE_CAPABILITY_MAP.md) (skeleton + pattern examples shipped this turn; full 65-capability population is D0 scope).
