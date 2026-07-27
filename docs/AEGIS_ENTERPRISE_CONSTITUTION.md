# AEGIS · Enterprise Constitution
### 🔒 LOCKED 2026-07-27 · Wave 4.5 · Apex Architectural Authority · Governs every implementation forever

This document is the **highest-priority architectural authority** for AEGIS. Every downstream document (Phase 3/4/5/6 roadmaps · Wave 4 spec · Capability Map · Implementation Mode · future sprints · future AI-generated code) is subordinate. Conflicts resolve in favor of this Constitution.

The Constitution is **amendable but not casually.** See Part XXIII — Amendment Process.

---

## Preamble

AEGIS is an **institutional AI investment platform** for dual-market (India NSE 200 + USA Dow 30) deployment. It is *advisory-only* — it never executes trades. It exists to produce daily, deterministic, explainable, auditable investment recommendations from raw market data through a chain of independent engines communicating via file-based artifacts.

This Constitution defines what AEGIS is, how it evolves, what can never change, and how disputes are resolved.

---

# PART I · IDENTITY

## Article 1 · Vision

To become the reference institutional investment platform where every recommendation is traceable to its evidence, every decision is explainable to a human, every result is reproducible bit-for-bit on replay, and every capability is owned by exactly one engine.

## Article 2 · Mission

Produce daily, deterministic, explainable, capital-efficient investment recommendations for institutional-grade dual-market portfolios (India NSE 200 + USA Dow 30), through a chain of independent engines communicating via file-based artifacts.

## Article 3 · What AEGIS IS

- An **institutional platform** of independent engines
- **Deterministic:** identical inputs → identical outputs, bit-for-bit
- **Advisory:** produces recommendations; never executes trades
- **File-based:** all state is in `reports/*.json`, `reports/*.parquet`, `data/aegis_*.csv` (no DB engine)
- **Append-only:** raw data is APPENDED, never re-downloaded
- **Walk-forward-safe:** every feature respects an as-of cutoff
- **Dual-market native:** every capability ships India + USA + global comparison
- **AI-augmented, not AI-driven:** AI explains and narrates; deterministic engines compute and decide
- **Audit-first:** every engine emits its own history for later replay and benchmarking

## Article 4 · What AEGIS is NOT

- **NOT** a trading system (no order routing, no exchange integration, no live executions)
- **NOT** a monolith (no god-modules, no shared mutable state)
- **NOT** a DB-backed application (persistence is file-based per Sprint 7.5)
- **NOT** a single-market product (India-only or USA-only additions violate Article 30)
- **NOT** an experimental research repo (`research/` is separate from `backend/`; research code is NEVER daily-wired)
- **NOT** a place where AI writes recommendations or portfolio decisions (Article 24)
- **NOT** a project where new AI agents can be added (Article 24.5)
- **NOT** governed by ad-hoc decisions (this Constitution supersedes)

## Article 5 · Fifteen Immutable Invariants (never-change)

1. AEGIS is advisory-only. Never executes trades.
2. `research/` is NEVER daily-wired. Research code lives in `research/`; production lives in `backend/`.
3. The **sealed contracts** are UNTOUCHABLE except by unanimous operator sign-off (see Appendix C):
   - `india/telegram_notify.py`
   - `research/adaptive_rec_v2/`
   - `research/risk_capital_v2/`
   - MON001 fingerprint `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf`
   - Feature Store schema fingerprint `b65ceb49a83a`
4. Six AI agents is the full set. No new AI agents (see Article 24.5 for the roster).
5. Every capability has exactly ONE canonical implementation.
6. Every artifact has exactly ONE producer.
7. Every capability has a validator in `validation/`.
8. Every sprint ships India + USA + `reports/global/<engine>_comparison.json` (Article 30).
9. Replay must be **byte-identical** across two runs of the same input window (Wave 4 · D6 test).
10. Sealed MON001 fingerprint is verified at the end of every sub-wave, every PR merge, every daily run.
11. Shared computation lives in `backend/10_shared/`. No local reimplementation of indicators.
12. AI outputs never modify production config, never emit recommendations, never execute anything.
13. Cross-domain communication is via published artifacts only. No cross-domain imports beyond `10_shared/`.
14. Every artifact declares `schema_fingerprint` + `schema_version`.
15. The Constitution is amendable only per Article 74 — never via silent PR.

---

# PART II · ENTERPRISE PRINCIPLES

## Article 6 · First Principles

- **Capability > File.** A capability is a thing the business does. A file is an implementation detail.
- **Producer owns Schema.** The engine that writes an artifact owns its schema.
- **Simpler beats Cleverer.** If a fix requires understanding 3 sealed contracts, redesign the fix.
- **Boring beats Novel.** No adopting new frameworks/libraries in a governance sprint.
- **Silence is not Success.** A missing check is a defect. Explicit failures beat silent fallbacks.

## Article 7 · Enterprise Principles

- **Reversibility First.** Prefer changes that can be reverted in one commit.
- **Coexistence Before Cutover.** New coexists with old until byte-equality is proven.
- **Fingerprint or Fabricate.** Every artifact declares its schema; if it doesn't, it's fabricated.
- **Grandfathering Is Bounded.** Existing engines get partial compliance when touched, not shotgun refactor — but the exception has an expiry date.
- **Wave Sealing.** Each Wave ends with a Definition-of-Done seal. Post-seal, that Wave's scope is closed.

## Article 8 · Architecture Principles

- **Ten Domains** — the backend has exactly 10 top-level domains (Article 10). No 11th without a full Constitution amendment.
- **Downward-Only Imports** — dependency direction is one-way (Article 45).
- **Single Source of Truth** — every rec / portfolio / risk / sector / macro state has ONE producer.
- **Artifact-First Communication** — engines talk via files, not shared memory.
- **Deterministic by Default** — anything non-deterministic requires explicit justification + `--frozen-clock` support.

---

# PART III · THE TEN DOMAINS

## Article 9 · Domain Ownership Rules

Every capability lives in exactly ONE domain. No capability crosses two domains. Cross-domain data flow is via published artifacts, not imports.

## Article 10 · The Ten-Domain Model (LOCKED)

```
backend/
  01_market_intelligence/   global · sector · industry · company engines
  02_feature_platform/      technical · fundamental · macro · sector · earnings · institutional · news · corp-actions · market-structure
  03_model_platform/        models · ensembles · calibration · ranking · scoring
  04_recommendation/        rec engine · confidence · explainability · rec DNA · capital rotation · opportunity cost
  05_portfolio/             construction · optimization · monitoring · risk · sizing · execution
  06_learning/              adaptive learning · replay · benchmark · strategy doctor · champion · challenger
  07_knowledge/             knowledge graph · relationships · institutional memory
  08_delivery/              reports · dashboard · telegram · api
  09_platform/              scheduler · orchestration · persistence · validation · contracts · registry · monitoring
  10_shared/                indicators · utils · constants · schemas
```

## Article 11 · The Ten-Layer Model (data flow)

```
Layer 0  Raw Data                    data/raw/india/*.parquet · usa/data/raw/us/*.parquet
Layer 1  Canonical Layer             backend/09_platform/contracts/ (typed dataclasses)
Layer 2  Feature Platform            backend/02_feature_platform/
Layer 3  Factor Platform             backend/06_learning/factor_library/ (D8 decides final home)
Layer 4  Model Platform              backend/03_model_platform/
Layer 5  Recommendation Platform     backend/04_recommendation/
Layer 6  Portfolio Platform          backend/05_portfolio/
Layer 7  Learning Platform           backend/06_learning/
Layer 8  Knowledge Platform          backend/07_knowledge/
Layer 9  Delivery Platform           backend/08_delivery/

Cross-cutting:
  Platform Services (09_platform/)   scheduler · orchestration · persistence · monitoring
  Shared Primitives (10_shared/)     indicators · utils · constants · schemas
```

**Data flows ONE WAY: Layer 0 → Layer 9.**

## Article 12 · Dependency Direction (import rules)

An engine at Layer N may import ONLY from Layers 0..N-1 plus `10_shared/`. It may NEVER import from Layers N+1..9.

### Article 12.1 · Forbidden Import Matrix (partial · authoritative in CI)

| Forbidden Import | Reason |
|------------------|--------|
| `02_feature_platform` importing `08_delivery` | Feature must not know about delivery |
| `04_recommendation` importing `08_delivery` | Rec must not know how it's delivered |
| `05_portfolio` importing `08_delivery` | Portfolio must not know about UI |
| `03_model_platform` importing `07_knowledge` | Model must not depend on knowledge graph |
| `10_shared` importing anything at Layer >0 | Shared is primitive · no upward deps |
| Any domain importing `research/` | Research is separate from production |
| Any domain importing `archive/` | Archive is deprecated |
| `01_market_intelligence` importing `05_portfolio` | Backward layer violation |
| Two domains importing each other | Circular dep — forbidden |

CI enforces via `validation/dependency_validation/import_direction_check.py` (D8 scope).

## Article 13 · Per-Domain Charter

Each domain's charter defines its **inputs · outputs · owned schemas · forbidden imports · replay obligations · benchmark obligations · dashboard tiles · telegram integration**. Charters are stored at `docs/domains/<NN_domain>.md` — one file per domain — populated in D0.

---

# PART IV · CAPABILITY GOVERNANCE

## Article 14 · Capability Definition

A **capability** is a discrete institutional function: e.g. "Sector Rotation Scoring" · "Capital Rotation Decision" · "Portfolio Attribution". A capability is NOT a file, NOT a function, NOT a class. It is a business action with:

- One owner (domain)
- One canonical implementation
- Zero or more consumers
- One validator
- One entry in the Enterprise Capability Map

## Article 15 · 20-Field Template Contract (mandatory)

Every capability record MUST populate all 20 fields:

`Capability · Owner · Input · Output · Schema · Consumers · Tests · Validator · Documentation · Dashboard · Reports · Telegram · Replay · Benchmark · AI Narration · Status · Version · Deprecated? · Replacement · Migration`

Any capability with an empty field is NOT production-ready. Enforced in CI at `validation/capability_validation/completeness_check.py` (D8 scope).

## Article 16 · Capability Lifecycle

```
Planned → Active → Deprecated → Archived
```

- **Planned:** designed, not yet shipped. Sits in the Cap Map with fields populated + `Status: Planned`.
- **Active:** shipped, tested, producing daily artifacts.
- **Deprecated:** replaced by another Active capability. Continues to run for 2 sub-waves (grace period).
- **Archived:** moved to `archive/` with a README explaining what replaced it.

## Article 17 · Adding a New Capability

1. Author writes a proposal in `docs/capabilities/proposals/<capability>.md` with all 20 fields.
2. Assigns to a domain per Article 9.
3. Reviews forbidden-imports check.
4. Ships end-to-end vertical slice per Implementation Mode.
5. Cap Map entry moves from `Planned` to `Active`.

## Article 18 · Modifying an Existing Capability

- **Non-breaking change:** minor version bump. Cap Map entry updated.
- **Breaking change:** major bump + migration doc at `docs/migrations/`. Consumers get 2 sub-waves grace period.
- **Deprecation:** minor bump with `deprecated = True` flag. Replacement named. 2 sub-waves grace. Then archive.

## Article 19 · Engine Ownership

Every engine has exactly ONE code-owner (a subdomain within a domain). Cross-engine changes require the owning subdomain's approval in the PR.

---

# PART V · ARTIFACT & SCHEMA GOVERNANCE

## Article 20 · Producer Owns Schema

The engine that writes an artifact owns its schema. Consumers read via that schema. Schema drift is the producer's problem to resolve, not the consumer's.

## Article 21 · Schema Fingerprint Requirement

Every artifact JSON declares:
```json
{
  "schema_version": "1.0.0",
  "schema_fingerprint": "b65ceb49a83a"
}
```

Fingerprint is SHA-256 of the canonical schema JSON. Any producer that ships without these two fields fails CI at `validation/schema_validation/fingerprint_required.py`.

## Article 22 · Artifact Naming Convention

- Production reports: `reports/<capability>.json` or `reports/<domain>/<capability>.json` (D0 decides flat vs nested)
- History parquets: `reports/history/<capability>.parquet` or `reports/<capability>_history.parquet`
- Ledgers: `reports/<capability>_ledger.jsonl` (append-only)
- Global-comparison: `reports/global/<capability>_comparison.json`
- USA equivalents: `usa/reports/<capability>.json`

## Article 23 · Consumer Compatibility Guarantee

- **Major bump (X.y.z):** consumers may break. Producer must provide migration doc.
- **Minor bump (x.Y.z):** consumers must NOT break. New optional fields only.
- **Patch bump (x.y.Z):** bug fixes only. Same schema, same field semantics.

## Article 24 · Deprecating an Artifact

1. Producer emits a `deprecated: true` flag in the artifact JSON.
2. Producer continues emitting for 2 sub-waves.
3. Consumers migrate.
4. Producer stops emitting. Artifact removed. History parquet moves to `archive/`.

---

# PART VI · VALIDATION CONSTITUTION

## Article 25 · Every Capability Has a Validator

Non-negotiable. No engine ships without a validator in `validation/`. Enforced at merge.

## Article 26 · Validator Location Convention

```
validation/
  <domain>_validation/
    <engine>_validator.py
```

E.g. `validation/recommendation_validation/capital_rotation_validator.py`.

## Article 27 · Validator Coverage Categories

Each validator covers as many of these as apply:
- **Data:** input shape · null-rate · range · dtype
- **Schema:** fingerprint present · schema_version parseable
- **Behavior:** deterministic under same inputs · monotonicity properties
- **Integration:** downstream consumers can parse the output
- **Performance:** runs within per-step budget
- **Security:** no secrets in output

## Article 28 · Validator Failure = Merge Block

Any validator failure blocks the merge. No `-n` / no `--skip-checks` / no `-c commit.gpgsign=false`. If a validator is wrong, fix the validator FIRST, then the code.

## Article 29 · Runs in CI

Every validator runs in CI on every push. Locally-runnable via `python -m validation.<domain>_validation.<engine>_validator`.

---

# PART VII · SHARED LIBRARY CONSTITUTION

## Article 30 · Single Canonical Implementation

For every primitive that multiple engines need (RSI · ATR · ADX · MACD · EMA · SMA · volatility · beta · sharpe · sortino · calmar · momentum · drawdown · liquidity · Bollinger · correlation), there is ONE implementation at `backend/10_shared/indicators/<name>.py`. Local reimplementations are forbidden.

## Article 31 · Shared Layer Cannot Depend Upward

`backend/10_shared/` may import ONLY from Python stdlib, `pandas`, `numpy`, and other `10_shared/` modules. Any import from Layer >0 fails CI at `validation/dependency_validation/shared_no_upward.py`.

## Article 32 · Utility Library Policy

`backend/10_shared/utils/` contains only pure functions — no I/O, no state, no side effects. Utilities requiring I/O belong in `backend/09_platform/`.

## Article 33 · Constants Library Policy

`backend/10_shared/constants/` contains only literals and their derivations. E.g. `TRADING_DAYS_YEAR = 252` · `MARKET_TZ_IST = "Asia/Kolkata"`. No functions.

## Article 34 · Schema Library Policy

`backend/10_shared/schemas/` contains canonical dataclasses (CanonicalBar · CanonicalDataset · SizedPosition · Recommendation). These are the ONLY types allowed to cross domain boundaries.

---

# PART VIII · AI USAGE BOUNDARIES

## Article 35 · AI EXPLAINS, Deterministic Engines DECIDE

AI narrators produce human-readable explanations of deterministic engine outputs. AI does NOT:
- compute scores
- rank recommendations
- size positions
- decide capital rotation
- modify configs
- promote strategies
- execute anything

## Article 36 · AI Output Must Be Replayable

Every AI output is a function of deterministic inputs. Given the same inputs, the AI narrator must return semantically equivalent output. AI variance is allowed in phrasing; NOT in claim.

## Article 37 · The Six AI Agents (LOCKED SET · Immutable Invariant #4)

```
1. Market Analyst        → reports/ai_market_narrative.json
2. Learning Analyst      → reports/ai_learning_narrative.json
3. Macro Analyst         → reports/ai_macro_narrative.json
4. Portfolio Analyst     → reports/ai_portfolio_narrative.json
5. Recommendation Analyst → reports/ai_recommendation_narrative.json
6. Risk Analyst          → reports/ai_risk_narrative.json
```

**No new AI agents.** Ever. Additional AI-driven capabilities are added by enriching the data feeding existing agents, not by adding a 7th agent.

## Article 38 · AI Prompt Governance

- Every AI narrator has a versioned prompt template at `backend/ai/prompts/<narrator>_v<N>.md`.
- Prompt changes = minor bump for the narrator.
- Prompt template is included in the narrator's schema_fingerprint calculation.

---

# PART IX · TESTING CONSTITUTION

## Article 39 · Testing Pyramid

```
Institutional Acceptance Suite (20 scenarios)          ← D8 target
E2E Chain Integrity (32 India + 35 USA daily steps)    ← D8 target
Domain Integration (per-domain flow tests)             ← per D2..D8
Capability Unit Tests (per-capability)                 ← always
Shared Primitive Tests (indicator math correctness)    ← D1
```

## Article 40 · Test Location Convention

Mirror backend structure:
```
tests/<domain>/<subdomain>/test_<capability>.py
```

Existing `test_sprint*.py` files migrate to their capability-matching location in a dedicated D8 shim sub-wave.

## Article 41 · Regression Suite

- `nexaquant/tests/test_regression.py` remains the pre-commit gate (invariance guards + fingerprint).
- Cumulative 280+ tests must always be green. A merge that drops the count is a merge-blocker.

## Article 42 · Institutional Acceptance Suite (20 scenarios · D8)

```
Bull · Bear · Sideways · Crash · High-VIX · Low-VIX
Fed · RBI · Earnings · Corporate Action
Gap Up · Gap Down · Delisting
Replay · Scheduler Restart
Telegram Failure · API Failure · Data Delay
Market Holiday · Cross-market Execution
```

All 20 must pass before Wave 4 seal (D8 exit criteria).

## Article 43 · Test Failure Handling

- Fix the code, not the test — unless the test is provably wrong.
- Never `pytest.skip`, `xfail`, or comment out a test to unblock a merge.
- Flaky tests get investigated within 24h — not silenced.

---

# PART X · CI/CD CONSTITUTION

## Article 44 · Workflow Per Domain

One CI workflow per top-level domain: `aegis-<domain>-ci.yml`. Runs on push to `backend/<domain>/` OR `validation/<domain>_validation/`.

## Article 45 · Concurrency Rule

Every workflow that touches shared state (daily orchestrator, mon001, telegram) declares a `concurrency:` block. No exceptions. Mirror `mon001-daily.yml:27-29` for the pattern.

## Article 46 · Sealed Contract Check

Every workflow verifies sealed fingerprints at end:
- MON001 fingerprint `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf`
- Feature Store fingerprint `b65ceb49a83a`
- (Any additional sealed fingerprints added over time)

## Article 47 · Merge Rules

- Green CI required.
- Every merge is a NEW commit (no `--amend` on published commits).
- No `--no-verify`, no `--no-gpg-sign`, no bypass flags.
- Rebase (not merge) preferred to keep linear history.

## Article 48 · Rollback Protocol

Every sub-wave is on its own branch. Failure post-merge triggers `git revert` of the sub-wave's merge commit. Wave 4 pauses until root cause is documented.

---

# PART XI · DEPENDENCY & IMPORT CONSTITUTION

## Article 49 · Downward-Only Imports (see also Article 12)

Enforced by CI at `validation/dependency_validation/import_direction_check.py`. Any import that violates the layer direction fails the merge.

## Article 50 · Cross-Domain Via `10_shared/` Only

Two domains at the same layer NEVER import each other. If they need shared logic, that logic moves to `10_shared/`.

## Article 51 · Circular-Dep Detection

CI runs `pydeps` or equivalent to detect cycles. Zero cycles allowed.

## Article 52 · Third-Party Dep Policy

- New third-party dependencies require an ADR at `docs/decisions/`.
- Existing deps: `pandas`, `numpy`, `pyarrow`, `yfinance`, `pyyaml`, `requests`, `sklearn`, `scipy`. Others require ADR.
- Version pins in `requirements.txt` — no floating majors.

## Article 53 · Layer Isolation Test

Every domain has a `tests/<domain>/test_isolation.py` verifying that no unauthorized upward import exists.

---

# PART XII · PERFORMANCE CONSTITUTION

## Article 54 · Per-Step Budget

Daily orchestrator step budgets:
- Standard step: ≤ 30s
- Ingest step (network): ≤ 120s
- Full daily pipeline: ≤ 300s per market

Steps exceeding budget generate a `perf_warning` in the ledger. Steps 2× over budget block the merge that introduced them.

## Article 55 · Zero Caching Where Freshness Matters

Cache-bust required for:
- Dashboard fetches (`?t=Date.now()` or `cache: 'no-store'`)
- Ops-check artifact reads
- Fingerprint verification reads

Caching allowed for:
- Third-party API responses (yfinance) — with TTL
- Feature-store snapshots — via schema fingerprint

## Article 56 · Retry Semantics

- Daily orchestrator steps: NO auto-retry (fail-fast with `--continue` to skip)
- Telegram delivery: exponential backoff, max 3 attempts (already in `scripts/telegram_send_with_retry.py`)
- Ingest: no retry within a single run (retried by cron on next slot)

## Article 57 · Timeout Policy

Every `subprocess.run` declares an explicit `timeout=`. Default 600s. Never omit.

---

# PART XIII · SECURITY & SECRETS

## Article 58 · Secrets Never in Code

- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` in `.env.telegram` (operator directive · never asked again)
- Any other credential in `.env.*` files listed in `.gitignore`
- No secrets in git history, no secrets in config YAML, no secrets in report JSON

## Article 59 · Read-Only Producer Access

Downstream consumers of `reports/*.json` open with `mode="r"`. No writes to another engine's artifact — ever.

## Article 60 · Sealed Fingerprint Protection

Sealed fingerprints in Article 5 Immutable #3 are cryptographic; changing the underlying files changes the fingerprint. A drift alert is a merge-blocker.

## Article 61 · Dependency Vulnerability

`safety check` or equivalent runs weekly. Critical CVEs in dependencies trigger a hotfix sub-wave.

---

# PART XIV · DUAL-MARKET CONSTITUTION

## Article 62 · Every Sprint Ships India + USA

Non-negotiable per operator directive `feedback_dual_market_parallel`. India-only or USA-only sprints are NOT COMPLETE.

## Article 63 · `reports/global/<engine>_comparison.json` Rule

Every dual-market engine produces a global comparison artifact showing India vs USA delta. Missing = merge-blocker.

## Article 64 · Currency Handling

- India: INR (₹) — displayed as ₹X or Rs.X
- USA: USD ($) — displayed as $X
- No cross-currency arithmetic without explicit FX conversion via `10_shared/utils/fx.py`

## Article 65 · Timezone Handling

- India: `Asia/Kolkata` (IST) — trading hours 09:15-15:30 IST
- USA: `America/New_York` (ET) — trading hours 09:30-16:00 ET
- All timestamps in artifacts are ISO 8601 UTC. Local-time renders only in Dashboard/Telegram.

## Article 66 · Universe Independence

- India NSE 200 (from `india.data_nse.NIFTY200`)
- USA Dow 30 (from `usa/reports/universe.json`)
- No engine assumes ticker overlap. Each market has its own universe object.

---

# PART XV · NAMING, FOLDER, CODE CONVENTIONS

## Article 67 · Directory Naming

- Domains: `NN_domain_name/` (numeric prefix for stable ordering)
- Subdomains: `snake_case/` (single word or underscore-joined)
- Test files: `test_<capability>.py`
- Validator files: `<engine>_validator.py`
- Config files: `<domain>_<engine>.yaml`
- Report files: `<capability>.json` or `<capability>.parquet`

## Article 68 · Code Conventions

- Python 3.12+
- `from __future__ import annotations` at top of every file
- Type hints on every public function signature
- Dataclasses (frozen where possible) over dicts for cross-boundary types
- No mutable default arguments
- No wildcard imports outside `__init__.py`
- No `print()` for observability — use stdlib `logging`

## Article 69 · JSON Schema Conventions

Every artifact JSON has these top-level keys at minimum:
```json
{
  "engine": "aegis.<domain>.<capability>.v<N>",
  "version": "1.0.0",
  "schema_version": "1.0.0",
  "schema_fingerprint": "<sha256>",
  "market": "india" | "usa" | "global",
  "asof": "YYYY-MM-DD",
  "run_utc": "YYYY-MM-DDTHH:MM:SS+00:00",
  "model_stamp": { ... },
  ...capability-specific fields...
}
```

## Article 70 · Database Conventions

No DB engine. State is file-based:
- Snapshots: `reports/*.json`, `reports/*.parquet` (mutable)
- History: `reports/*_history.parquet` (append-only)
- Ledgers: `reports/*_ledger.jsonl` (append-only)
- Registries: `data/*.csv` (append-only unless explicitly rewritten)

If a future ADR justifies a DB (e.g. DuckDB embedded per Phase 3 ARCH022+), it lives at `backend/09_platform/persistence/duckdb_engine.py` and coexists with file-based state, not replacing it.

## Article 71 · Logging Conventions

- stdlib `logging` module (never `print` in production paths)
- Log levels: DEBUG · INFO · WARNING · ERROR · CRITICAL
- Structured log records: `{ts, level, engine, capability, msg, ctx}`
- Rotated logs at `logs/<engine>.log`
- Ledger emits (JSONL) at `reports/<engine>_ledger.jsonl` — separate from logs

---

# PART XVI · CONFIGURATION CONSTITUTION

## Article 72 · `configs/` is the Single Tunable Source

All engine tunables (weights, thresholds, universe lists, model hyperparams) live in `configs/*.yaml`. Hardcoded magic numbers in code are Article 72 violations.

## Article 73 · YAML Only

Configs are YAML. Not JSON (JSON is for machine-produced artifacts). Not TOML. Not INI.

## Article 74 · Config Owner Per File

Every config file has an owning subdomain declared in its frontmatter:
```yaml
# owner: backend/04_recommendation/capital_rotation
# version: 1.0.0
```

## Article 75 · Config Change = Version Bump

Any config change bumps the file's version and appends to a changelog at `configs/CHANGELOG.md`.

---

# PART XVII · RESEARCH vs PRODUCTION SEPARATION

## Article 76 · `research/` is NEVER Daily-Wired

`research/` contains experiments, DEV* prototypes, one-off studies. It is NEVER imported by `backend/`. It is NEVER referenced in `.github/workflows/*.yml`.

## Article 77 · Promotion Path (research → validation → backend)

1. Author prototypes in `research/<capability>/`.
2. Publishes benchmark evidence at `research/<capability>/results.md`.
3. Writes a promotion proposal at `docs/capabilities/proposals/<capability>.md`.
4. Ships end-to-end vertical slice into `backend/<domain>/<capability>/`.
5. Cap Map entry moves from `Planned` to `Active`.
6. Old research module either archived OR retained for continuous R&D.

## Article 78 · Sealed Research Modules

Certain `research/` modules are sealed (`research/adaptive_rec_v2/`, `research/risk_capital_v2/`) — see Appendix C. Their outputs are consumed by production wrappers, but the modules themselves are UNTOUCHABLE.

---

# PART XVIII · ARCHIVE & DEPRECATION

## Article 79 · Deprecation Path

`Active → Deprecated → Archived`. Grace period 2 sub-waves at each stage.

## Article 80 · `archive/` Structure

```
archive/
  YYYY/
    NN_<capability>/
      README.md    what it did · what replaced it · when archived · why kept
      <original files>
```

## Article 81 · Historical Access Only

Archived code is NOT imported by `backend/`. It may be referenced from `research/` for historical backtests.

## Article 82 · Deletion Requires ADR

Never delete archived code without an ADR at `docs/decisions/<date>_delete_<capability>.md`.

---

# PART XIX · LOGGING, MONITORING, OBSERVABILITY

## Article 83 · Structured Logging (stdlib `logging`)

Every module uses `logging.getLogger(__name__)`. No `print()` in production paths.

## Article 84 · Ledger Convention

Every long-running orchestrator writes a JSONL ledger:
```
reports/<engine>_history.jsonl
{
  "run_utc": "...",
  "n_steps": N,
  "n_success": M,
  "n_failure": K,
  "total_elapsed_s": T,
  "steps": [ { "name": ..., "verdict": ..., "elapsed_s": ..., "returncode": ..., "produced": [...], "stdout_tail": ..., "stderr_tail": ... }, ... ]
}
```

## Article 85 · MON001 Fingerprint Sentinel

MON001 is the config-drift detector. Its sealed baseline lives at `india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json`. The current fingerprint is:
```
e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf
```

Verified at end of every sub-wave, every PR merge, every daily run.

## Article 86 · Ops-Check Aggregator

`scripts/aegis_ops_check.py` reads 23 required artifacts + 14 schemas → emits `reports/ops_check.json` with verdict GREEN / DEGRADED / CRITICAL. Any CRITICAL blocks the operator from shipping.

---

# PART XX · ERROR HANDLING, ROLLBACK, MIGRATION

## Article 87 · Fail-Fast at Boundaries

At API/user/network boundaries: validate inputs, fail fast with clear error message. Never `except Exception: pass` at a boundary.

## Article 88 · Graceful Degradation Internal

Between internal engines: an upstream failure emits a partial artifact with `verdict: PARTIAL` + `errors: [...]` so downstream can continue in degraded mode. Never silently emit an empty artifact.

## Article 89 · Rollback Branch Per Sub-Wave

Every sub-wave is on `wave4-d<N>` branch. Rollback = `git revert` of the sub-wave's merge commit.

## Article 90 · Migration = New Coexists with Old, Then Cutover

- **Phase 1:** new module written alongside legacy · both produce artifacts
- **Phase 2:** byte-equality verified · legacy becomes thin re-exporter
- **Phase 3:** legacy removed to `archive/` in a dedicated final sub-wave

## Article 91 · Byte-Equality Before Cutover

For any capability being moved, run before-vs-after with identical inputs, hash outputs (after `norm_utc()` timestamp normalization), assert equal. No cutover without this proof.

---

# PART XXI · DEFINITION OF DONE

## Article 92 · Every Sprint DoD Checklist (14 items · MANDATORY)

- [ ] Implementation summary
- [ ] Static analysis (import direction · layer isolation · no forbidden imports)
- [ ] Unit tests green
- [ ] Integration tests green
- [ ] Runtime output with real numbers
- [ ] Artifacts declared with `schema_fingerprint` + `schema_version`
- [ ] Validation table (per Article 27 categories)
- [ ] Before/after evidence
- [ ] Limitations documented
- [ ] Next-dependent check
- [ ] Acceptance checklist
- [ ] Scorecard
- [ ] Executive Dashboard updated
- [ ] Sealed fingerprints verified

Per `aegis_mandatory_validation_rules` invariant.

## Article 93 · Every Capability DoD (20 fields per Article 15)

## Article 94 · Every Domain DoD

- One owner-doc at `docs/domains/<NN_domain>.md`
- One config folder at `configs/<domain>/`
- One test folder at `tests/<domain>/`
- One validator folder at `validation/<domain>_validation/`
- Every subdomain enumerated + capability-linked

## Article 95 · Wave Seal DoD

Waves close with a Closure Report at `docs/AEGIS_WAVE_<N>_CLOSURE_REPORT.md` classifying every finding per Wave Closure Mode (Must-Fix / Accepted Debt / Environment / Expected Future).

---

# PART XXII · INSTITUTIONAL ACCEPTANCE CHECKLIST (D8 exit)

Per Article 42 · these 20 scenarios must pass:

```
1.  Bull market run — expected: positive breadth, momentum leaders promoted
2.  Bear market run — expected: caps kicked in, defensive positions preferred
3.  Sideways market — expected: HOLD dominates, no forced trades
4.  Crash (>-5% intraday) — expected: risk_off regime detected, VaR breach flagged
5.  High-VIX (>30) — expected: confidence dampener applied, position sizes reduced
6.  Low-VIX (<12) — expected: standard sizing, no complacency alerts
7.  Fed hike surprise — expected: macro regime shifts, sector rotation triggers
8.  RBI hold — expected: no false signal, macro narrator explains
9.  Earnings season — expected: earn_days_to_next drives position hold vs trim
10. Corporate action (split) — expected: recorded in corporate_actions.parquet + price series adjusted
11. Gap Up open — expected: momentum score updated, no false BUY on stale close
12. Gap Down open — expected: risk trigger fires, position review flagged
13. Delisting — expected: universe updated, existing position exit path
14. Full-window replay 2025-01-01 → today — expected: byte-identical to prior replay
15. Scheduler restart mid-run — expected: resume from last checkpoint, no duplicate work
16. Telegram failure — expected: retry with backoff, no duplicate on retry-success
17. yfinance API failure — expected: partial artifact with verdict=PARTIAL, downstream degraded gracefully
18. Data delay (fresh > 24h stale) — expected: freshness SLA flag in ops-check
19. Market holiday — expected: no false-alarm on absent bars, next trading day resumes
20. Cross-market run (India morning + USA evening) — expected: no state collision, both markets ship
```

All 20 pass = Wave 4 SEAL granted.

---

# PART XXIII · FUTURE EXTENSIBILITY

## Article 96 · Adding a Domain

Requires:
- ADR at `docs/decisions/<date>_add_domain_<name>.md`
- Constitution amendment
- Operator sign-off
- Update to Article 10 domain list
- Full migration plan

Bar is DELIBERATELY high. Prefer expanding an existing domain.

## Article 97 · Adding a Layer

Bar is even higher. Requires full Wave sprint. Prefer expressing as a domain within existing layers.

## Article 98 · Adding a Cross-Domain Utility

- Author writes utility at `backend/10_shared/utils/<utility>.py`
- Validator at `validation/shared_validation/`
- Docs at `docs/capabilities/shared_<utility>.md`
- No consumer-side reimplementation permitted (grep-verified)

## Article 99 · Amendment Process

The Constitution is amended via:
1. Author writes proposal at `docs/constitutional_amendments/<date>_<title>.md`
2. Impact analysis: which articles change, which cascade
3. Migration plan for affected code
4. Operator sign-off (recorded in the amendment doc)
5. Version bump: this document at top gets `Constitutional Version: N`
6. All downstream docs updated to reference the new article numbers

Silent amendment (editing an article without a proposal doc) is a Constitutional violation.

---

# PART XXIV · THE SIXTEEN IMMUTABLE INVARIANTS (extended)

Extending Article 5, these 16 hold forever:

1. AEGIS is advisory-only (Article 3)
2. `research/` is never daily-wired (Article 76)
3. Sealed contracts are UNTOUCHABLE (Article 5, Appendix C)
4. Six AI agents is the full set (Article 37)
5. One canonical implementation per capability (Article 14)
6. One producer per artifact (Article 20)
7. Every capability has a validator (Article 25)
8. Every sprint dual-market (Article 62)
9. Replay must be byte-identical (Article 91)
10. MON001 fingerprint verified at every seal (Article 85)
11. Shared computation in `10_shared/` (Article 30)
12. AI never emits recommendations (Article 35)
13. Cross-domain communication via artifacts only (Article 50)
14. Every artifact carries schema_fingerprint + schema_version (Article 21)
15. Constitution amendment requires Article 99 process
16. Downward-only imports (Article 12)

Any change that violates any invariant is a Constitutional violation. Blocking issue. Not shippable.

---

# APPENDICES

## Appendix A · The 10-Layer Model (visual)

```
Layer 9  Delivery Platform         ──→ operator (browser · telegram · report)
                ↑
Layer 8  Knowledge Platform         KG · relationships · institutional memory
                ↑
Layer 7  Learning Platform          adaptive · replay · benchmark · champion
                ↑
Layer 6  Portfolio Platform         construction · optimization · risk · sizing · execution
                ↑
Layer 5  Recommendation Platform    rec engine · confidence · explainability · capital rotation · opp cost
                ↑
Layer 4  Model Platform             11 models + ensemble + calibration + ranking + scoring
                ↑
Layer 3  Factor Platform            factor library (macro factors + composite)
                ↑
Layer 2  Feature Platform           technical · fundamental · macro · sector · earnings · institutional · news · corp-actions · market-structure
                ↑
Layer 1  Canonical Layer            typed dataclasses (CanonicalBar · CanonicalDataset · SizedPosition · Recommendation)
                ↑
Layer 0  Raw Data                   MT5 parquets + yfinance CSV + news RSS

Cross-cutting:
  Platform Services (09_platform)   scheduler · orchestration · persistence · monitoring
  Shared Primitives (10_shared)     indicators · utils · constants · schemas

  Data flow: Layer 0 → Layer 9 · never reverse · never lateral except via 10_shared
```

## Appendix B · Import Rules Matrix (authoritative — CI-enforced in D8)

| From ↓ / To → | 01_MI | 02_FP | 03_MP | 04_R | 05_P | 06_L | 07_K | 08_D | 09_PL | 10_SH |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 01_market_intelligence | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 02_feature_platform | ✅ | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 03_model_platform | ✅ | ✅ | — | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 04_recommendation | ✅ | ✅ | ✅ | — | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 05_portfolio | ✅ | ✅ | ✅ | ✅ | — | ❌ | ❌ | ❌ | ✅ | ✅ |
| 06_learning | ✅ | ✅ | ✅ | ✅ | ✅ | — | ❌ | ❌ | ✅ | ✅ |
| 07_knowledge | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ❌ | ✅ | ✅ |
| 08_delivery | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ |
| 09_platform | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | — | ✅ |
| 10_shared | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | — |

Legend: ✅ allowed · ❌ forbidden · — self · `09_platform` is cross-cutting (its runners in `scripts/` may import from anywhere, but its library code stays isolated).

## Appendix C · Sealed Contracts Registry

| Contract | Path | Fingerprint | Amendment Path |
|----------|------|-------------|----------------|
| Telegram legacy sender | `india/telegram_notify.py` | (source-of-truth · byte-hash pinned in test) | Operator sign-off only |
| Adaptive Rec v2 | `research/adaptive_rec_v2/` | (module-level lock) | Amendment only after Sprint 7.9 orchestrator supersedes |
| Risk Capital v2 | `research/risk_capital_v2/` | (module-level lock) | Amendment only after Sprint 7.9 orchestrator supersedes |
| MON001 sealed fingerprint | `india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json` | `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf` | Any change is a MAJOR event — full audit + operator sign-off |
| Feature Store schema | `backend/feature_store/feature_versioning.py` | `b65ceb49a83a` | Minor bump per new-feature addition · major bump breaks consumers |

## Appendix D · The Six AI Agents

Per Article 37 · immutable set.

| # | Agent | Owner Domain | Input | Output | Prompt Template |
|---|-------|--------------|-------|--------|-----------------|
| 1 | Market Analyst | 01_market_intelligence | market_intelligence.json | ai_market_narrative.json | `backend/ai/prompts/market_analyst_v1.md` |
| 2 | Learning Analyst | 06_learning | feature_attribution.json + learning.parquet | ai_learning_narrative.json | `backend/ai/prompts/learning_analyst_v1.md` |
| 3 | Macro Analyst | 01_market_intelligence | macro_regime.json + macro_intelligence.json | ai_macro_narrative.json | `backend/ai/prompts/macro_analyst_v1.md` |
| 4 | Portfolio Analyst | 05_portfolio | portfolio_v3.json + risk_report.json | ai_portfolio_narrative.json | `backend/ai/prompts/portfolio_analyst_v1.md` |
| 5 | Recommendation Analyst | 04_recommendation | recommendations_v3.json + conflicts.json | ai_recommendation_narrative.json | `backend/ai/prompts/rec_analyst_v1.md` |
| 6 | Risk Analyst | 05_portfolio | risk_report.json + sized_positions.json | ai_risk_narrative.json | `backend/ai/prompts/risk_analyst_v1.md` |

## Appendix E · Cap Map Cross-Reference

Full 65-capability inventory maintained at [`docs/AEGIS_ENTERPRISE_CAPABILITY_MAP.md`](AEGIS_ENTERPRISE_CAPABILITY_MAP.md). This Constitution defines the *rules*; the Cap Map defines the *instances*.

---

## Constitutional Version

**Version 1.0.0 · LOCKED 2026-07-27**

Amendment history (future updates recorded here):
- 1.0.0 · 2026-07-27 · Initial ratification · locks Wave 4.5 authority · governs all future implementation

---

## Ratification

This Constitution is the apex architectural authority for AEGIS/NexaQuant. Every existing document (Phase 3/4/5/6 roadmaps · Wave 4 spec · Capability Map · Implementation Mode · v2.2 audit) is subordinate. Every future document is subordinate.

**Sequencing:**
```
1. This Constitution ratified              [SHIPPED 2026-07-27]
2. Architecture frozen                     [effective 2026-07-27]
3. Wave 4 · D0..D8 execute AGAINST it     [next]
4. After D8 · repository structurally frozen
5. From then on · feature evolution only  [permanent]
```

**End of Constitution · v1.0.0 · LOCKED 2026-07-27.**
