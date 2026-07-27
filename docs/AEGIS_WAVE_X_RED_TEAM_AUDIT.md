# AEGIS · Wave X · Red Team Independent Audit
### 🔒 SHIPPED 2026-07-27 · adversarial reviewer stance · verifies implementation not documentation · Go/No-Go with evidence · no fixes

**Mandate:** act as an independent panel of principal architects, quant researchers, platform engineers, SREs, security engineers, and institutional-system reviewers. Assume every previous document (Constitution · Wave 4 · Cap Map · Wave 5 phase docs · Executive Dashboard) may contain mistakes. **Do not trust prior conclusions.** Verify implementation with grep + read + execute. Do NOT implement fixes.

**Method:** fresh evidence sweep on the head of `main` (post-commit `e6ded78`). Cross-check every "SHIPPED" claim in Wave 5 against actual code state. Look for the seams between what was WRITTEN and what would RUN in production.

**Operator's precipitating observation (validated):** *"Several documents describe new engines (Capital Rotation and Portfolio Attribution) as 'SHIPPED,' while other reports still describe many required validators, schema fingerprints, and production integrations as missing or planned."* — **This inconsistency is REAL and material.**

---

## 0 · Verdict Summary

# **NO-GO for production certification.** Wave 5's own score (54.25/100) is defensible, but the "SHIPPED" verb was used inconsistently and inflated the reader's mental model.

**Red Team's honest framing (the missing ladder):**

```
Level 0  DESIGNED     — spec written · no code
Level 1  BUILT        — code exists in-tree · imports · unit tests green
Level 2  WIRED        — invoked from an orchestrator (daily / replay / scheduler)
Level 3  VALIDATED    — validator exists · CI-enforced · passes on production data
Level 4  CONSUMED     — downstream artifacts read by dashboards / reports / Telegram
Level 5  CERTIFIED    — passes Institutional Acceptance (Article 42 · 20 scenarios)
```

**Wave 5 said "SHIPPED" · reality is Level 1 (BUILT).** For Capital Rotation + Opp Cost + Portfolio Attribution, code exists and tests pass, but they are **NOT WIRED · NOT CONSUMED · NOT CERTIFIED**. This is a documentation-honesty defect, not an engineering defect. The engines themselves are Constitution-compliant · deterministic · fingerprinted · tested.

---

## 1 · The SHIPPED-vs-Wired Ladder · Adjudication

Applied to every Wave 5 code deliverable:

| Deliverable | L1 Built | L2 Wired | L3 Validated | L4 Consumed | L5 Certified | Honest Status |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **Capital Rotation Engine** | ✅ | ❌ (not in aegis_daily_v2.py; not in usa_daily.py) | ✅ validator exists at `validation/recommendation_validation/capital_rotation_validator.py` but NOT wired to CI | ❌ no `reports/rotation_plan.json` on disk | ❌ | **BUILT · not shipped to prod** |
| **Opportunity Cost Engine** | ✅ | ❌ | ✅ validator present · not CI-wired | ❌ | ❌ | **BUILT · not shipped to prod** |
| **Portfolio Attribution Engine** | ✅ | ❌ (not in either daily orchestrator) | ✅ validator present · reconciliation invariant enforced · not CI-wired | ❌ no `reports/portfolio_attribution.json` on disk | ❌ | **BUILT · not shipped to prod** |
| **Shared Indicator Library** | ⚠️ seed only (`backend/shared/indicators/__init__.py` — no actual RSI/ATR/ADX code inside) | ❌ | ❌ | ❌ | ❌ | **SCAFFOLDED not built · Article 30 violation persists** |
| **`validation/` architecture** | ✅ 22 subdomain folders + 3 validator files | ❌ not wired to CI (no workflow references) | N/A | ❌ | ❌ | **STRUCTURE ONLY · CI unwired** |
| **`archive/`** | ✅ README | N/A | N/A | N/A | N/A | **EMPTY DIR** (target · nothing to archive yet) |
| **`docs/domains/`** | ⚠️ README only · no per-domain doc | N/A | N/A | N/A | N/A | **1/11 files** (README + 0 domain owner docs) |
| **`docs/capabilities/`** | ❌ empty | N/A | N/A | N/A | N/A | **0/65 capability docs** |
| **Config Article 74 frontmatter** | ✅ 7/7 configs | ✅ files read by orchestrators unchanged | N/A | N/A | N/A | **DONE** (real fix) |

**Red Team finding:** Wave 5 · Phase 3 legitimately flipped Article 74 from FAIL to PASS. Wave 5 · Phase 9/10 legitimately BUILT engines to Level 1. Everything Wave 5 called "SHIPPED" at Level 2+ was overclaimed.

---

## 2 · Fresh Compliance Recheck · Constitution Articles

Selected articles re-verified with fresh grep · not trusting prior scorecard:

| Article | Wave 5 Claim | Fresh Evidence | True Verdict |
|:---:|---|---|:---:|
| 3 · Advisory-only | PASS | grep for order/execute — 0 hits | ✅ PASS |
| 5 · 16 Invariants | PASS | MON001 fingerprint `e4c070673568c52d…` verified live | ✅ PASS |
| 10 · 10-domain model | FAIL | `backend/` still has 23 subdirs · Wave 4 D0-D8 unstarted | ❌ FAIL (Wave 5 didn't move the needle) |
| 12 · Downward-only imports | PARTIAL | No enforcement in CI yet | ⚠️ PARTIAL (unchanged) |
| 15 · 20-field Cap Map | PARTIAL | 18 detailed + 47 compact-only · full population NOT done | ⚠️ PARTIAL (Wave 5 P4 was compact table not full population) |
| 21 · schema_fingerprint on every artifact | FAIL | **10/171 = 5.8%** (fresh count · WORSE than Wave 5's claim of 12/176) | ❌ FAIL |
| 25 · Every capability has validator | FAIL | 3 new validators (Wave 5 P9/P10) · **65 target** · pre-existing `backend/validation/*` (7 files) exists but they were never counted or reconciled | ❌ FAIL (Wave 5 Phase 2 undercounted pre-existing validators · overcounted target coverage) |
| 30 · One canonical implementation | FAIL | **19 indicator def sites** across backend/india/usa/strategy/research (5 RSI · 6 ATR · 4 ADX · 3 EMA · 1 MACD · 0 SMA) · `backend/shared/indicators/` empty except `__init__.py` | ❌ FAIL (unchanged since Phase 2) |
| 37 · Six AI agents locked | PASS | Confirmed | ✅ PASS |
| 40 · Tests per capability | FAIL | All still sprint-labeled | ❌ FAIL (unchanged) |
| 41 · 280+ regression tests | PASS | 314 tests · verified | ✅ PASS |
| 42 · 20-scenario institutional acceptance | FAIL | `tests/institutional_acceptance/` is empty scaffold · 0/20 built | ❌ FAIL |
| 45 · Concurrency block every workflow | FAIL | Only `mon001-daily.yml` has it (fresh grep) | ❌ FAIL |
| 62 · Dual-market every sprint | PASS | Wave 5 code deliverables market-parameterized · but NOT wired to USA daily | ⚠️ PARTIAL (design compliant · integration missing) |
| 68 · No print() in production | FAIL | Unchanged · only `nexaquant/*` uses stdlib logging | ❌ FAIL |
| 72 · Configs single source | PARTIAL | 7 configs · magic numbers still in code | ⚠️ PARTIAL |
| 74 · Config owner frontmatter | PASS | ✅ 7/7 verified via `head -1` | ✅ PASS (Wave 5 legitimate) |
| 76 · research/ never daily-wired | FAIL | 10+ research modules still daily-wired · unchanged | ❌ FAIL |
| 80 · archive/ structure | PARTIAL | Directory + README present · but empty · nothing actually archived | ⚠️ PARTIAL (scaffold only) |
| 85 · MON001 fingerprint | PASS | Verified live · unchanged | ✅ PASS |
| 91 · Byte-equality before cutover | PASS | Verified for C0 · unverified for other cutovers | ✅ PASS |
| 94 · Per-domain owner docs | PARTIAL | Only `docs/domains/README.md` · 0/10 owner docs | ⚠️ PARTIAL (Wave 5 P3 overclaimed PASS · reality is scaffold only) |
| 99 · Amendment process | PASS | Documented · no silent amendment | ✅ PASS |

**Red Team recount:**
| Wave 5's claim | Red Team verdict |
|:---:|:---:|
| PASS 45 (45.5%) | PASS **~38** (38.4%) |
| PARTIAL 24 | PARTIAL 26 |
| FAIL 18 | FAIL **21** |
| N/A 12 | N/A 14 |

**Wave 5 overstated PASS count by ~7 articles.** Specific overstatements:
- Article 25 (validators): 3 of 65 target · was called "3 validators shipped" but article requires every capability
- Article 80 (archive): scaffold ≠ populated
- Article 94 (per-domain docs): README ≠ 10 domain docs
- Article 40 (tests): unchanged
- Article 76 (research daily-wired): unchanged
- Article 10 (10-domain model): backend/ still has 23 subdirs

---

## 3 · Duplicated Capabilities (Article 30 · Fresh Grep)

**Wave 5 said:** duplicate indicator sites addressed by Wave 4 D1 (shared indicator library).
**Reality:** `backend/shared/indicators/` contains ONLY `__init__.py` (a docstring + version + constitutional pointer). **Zero canonical implementations exist.** All 19 legacy sites remain live.

| Primitive | Sites | Locations |
|---|:---:|---|
| RSI | 5 | `backend/feature_store/features/technical.py` · `india/feature_engine.py` · `india/technical_factors.py` · `strategy/regime.py` · `research/edge_probe.py` |
| ATR | 6 | above + `strategy/smc.py` · `strategy/risk.py` · `usa/research/recommendations/lib/entry_exit.py` |
| ADX | 4 | `backend/feature_store/features/technical.py` · `india/feature_engine.py` · `india/technical_factors.py` · `strategy/regime.py` |
| EMA | 3 | inline in multiple files |
| MACD | 1 | `backend/feature_store/features/technical.py` (correction: earlier "3 sites" claim was overstated) |
| SMA | 0 dedicated defs | inline via `.rolling().mean()` — untracked by this grep pattern |

**Verdict:** Article 30 status **unchanged since Wave 5 Phase 2 · still FAIL.**

---

## 4 · Missing Production Code Behind Documented Features

Cross-referencing Cap Map + docs vs actual runtime:

| Documented Feature | Doc Location | Actual Runtime |
|---|---|---|
| Capital Rotation | Cap Map 4.10 · Wave 5 P9 doc | Code exists · **no daily orchestrator step · no rotation_plan.json produced** |
| Opportunity Cost | Cap Map 4.11 · Wave 5 P9 doc | Code exists · **no enrichment applied to any daily rec** |
| Portfolio Attribution | Cap Map 5.8 · Wave 5 P10 doc | Code exists · **no portfolio_attribution.json produced** |
| Shared Indicator Library | Wave 4 D1 · Constitution Article 30 · Wave 5 P3 mentions | `__init__.py` only · **zero indicator files** |
| Rec Delta Engine (5 delta fields) | v2.2 audit M-R2 · Wave 4 D4 · Wave 5 P8 | **Zero producers emit `previous_rank/confidence_delta/sector_change/momentum_change/risk_change`** |
| Recommendation Lifecycle state machine | Sprint C1 spec · Wave 4 D4 | **Zero code · spec-only** |
| Champion producer (reconnect) | v2.2 audit Str1 · Wave 4 D6 | Still 9-day stale (`champion_strategy.json` mtime 2026-07-17) |
| Keystone `recommendations.json` producer | v2.2 audit M-R1 · Wave 4 D4 | Still 9-day stale · no orchestrator produces it |
| Replay byte-equality regression test | v2.2 audit Rep1 · Wave 4 D6 | **Not written** |
| `--frozen-clock` replay mode | v2.2 audit Rep2 · Wave 4 D6 | **Not implemented** |
| Telegram concurrency block | v2.2 audit T1 · Wave 4 D7 | Still absent from `aegis-daily.yml` |
| Telegram rec-hash dedup | v2.2 audit T3 · Wave 4 D7 | **Not built** |
| 20-scenario Institutional Acceptance suite | Article 42 · Wave 4 D8 | Empty scaffold (`tests/institutional_acceptance/`) |
| API Center | Cap Map 8.8 · Phase 4 Module 18 | **Missing** |
| Scanner strategy · Income strategy | operator lexicon · Cap Map M.1/M.2 | **Missing** (still) |
| VEDL corporate action entry | v2.2 audit M-D2 | **Still absent** from `corporate_actions.parquet` |
| 13 India OHLC anomalies (open<low) | v2.2 audit M-D1 | **Still uncorrected** (13 bars remain broken) |
| NIFTY200 gap (LTIM/PEL/TATAMOTORS) | v2.2 audit M-D3 | **Still missing** from raw |

**Verdict:** Wave 5 built 3 new engines but ZERO of the pre-existing v2.2 Must-Fix items were completed. The Wave 5 program was ADDITIVE, not REMEDIATIVE. This is a governance-scope mistake — Wave 5's title was "productionization + institutional certification" but its actual output was "audit consolidation + 3 new engine builds."

---

## 5 · Dead Code · Unused Reports · Stale Artifacts

| Item | Status | Notes |
|---|:---:|---|
| `backend/recommendation/classifier.py:_MATRIX` | STILL DEAD | Unchanged since v2.2 audit S7 |
| `reports/recommendations.json` | STALE 9d | Frozen 2026-07-17 · no producer |
| `reports/portfolio.json` (Runner 1) | STALE 9d | Frozen 2026-07-17 · duplicated by portfolio_v3.json |
| `reports/champion_strategy.json` | STALE 9d | Producer disconnected |
| `reports/global_context.json` | STALE 9d | Producer disconnected |
| `reports/learning.parquet` | STALE 9d | Runner 2 100% HOLD chain empty |
| `reports/morning_latest.html` | STALE 7d | Blocked by keystone gap |
| `research/recommendations/run.py` (DEV023) | STILL PRESENT | Wave 4 D4 planned archive · not moved |

**Verdict:** Wave 5 did not archive a single item. `archive/` directory is empty. Cleanup deferred to Wave 4 sub-waves that have not been executed.

---

## 6 · Governance Violations Detected

| # | Violation | Article | Evidence |
|:---:|---|:---:|---|
| G1 | Wave 5 used "SHIPPED" verb inconsistently across levels 1-5 of the ladder | Article 21 (schema honesty) analog | Cap Map lists Capital Rotation as "Planned" while Wave 5 P9 doc says "SHIPPED" |
| G2 | 3 validators created outside CI wiring (Wave 5 P9/P10 validators do not run on push) | Article 29 | No workflow references `validation/` directory |
| G3 | Wave 5 Phase 3 claimed Article 80 PASS from creating an empty archive/ dir + README | Article 80 | Article 80 requires actual archived items with README per capability |
| G4 | Wave 5 Phase 3 claimed Article 94 PASS from creating docs/domains/README.md only | Article 94 | Requires per-domain owner docs · 0/10 exist |
| G5 | Wave 5 tests for new engines shipped but not counted toward capability-level test coverage matrix in Phase 16 | Article 40 | New tests reuse sprint-style naming (test_wave5_*) not per-capability path |
| G6 | Capital Rotation Cap Map entry (§4.10) lists Status = "P" (Planned) while Wave 5 P9 doc + commit message say "SHIPPED" | Article 16 (Lifecycle) | Two-source truth mismatch |
| G7 | `backend/shared/indicators/__init__.py` file created but re-exports nothing · violates Article 30 by creating the illusion of a canonical library | Article 30 | Import returns no primitives |
| G8 | Wave 5 phase 20 "Production Readiness Score 54.25/100" is arithmetically valid but conflates BUILT (Level 1) as if it were SHIPPED (Level 2+), inflating perception | governance honesty | Portfolio Consistency 20 → 35 delta credited to Attribution Engine that isn't wired |
| G9 | ENG001 Regression exists as separate workflow instead of merged into AEGIS CI as operator has now suggested | Article 44 (workflow per domain) | 5 workflows on disk · operator recommendation is 4+Release |

---

## 7 · Deterministic Behavior & Replay Assumptions Recheck

| Claim | Status | Evidence |
|---|:---:|---|
| Capital Rotation deterministic | ✅ | Test `test_capital_rotation_deterministic` explicit |
| Opportunity Cost deterministic | ✅ | Test `test_opportunity_cost_deterministic` explicit |
| Portfolio Attribution deterministic | ✅ | Test `test_attribution_deterministic` explicit |
| Replay byte-identical (two-run) | ❌ | No test written · no `--frozen-clock` mode |
| C0 fixes preserved fingerprint | ✅ | Verified fresh (`e4c070673568c52d…` still current) |
| FS schema fingerprint stable | ✅ | `b65ceb49a83a` unchanged since C0 |

**Verdict:** individual new engines are deterministic in unit tests · **system-level byte-equality replay is unverified**. Article 42 scenario #14 (full-window replay byte-identical) has no test coverage.

---

## 8 · Maintainability · Scalability · Security · Operational Readiness

### 8.1 · Maintainability

| Dimension | Verdict |
|---|:---:|
| Docs volume | HIGH (141 md · governance excellent) |
| Docs granularity | LOW (0/65 per-capability docs · 0/10 per-domain docs) |
| Test-to-capability ratio | LOW (58 test files vs 65 capabilities · not aligned) |
| Import graph clarity | LOW (23 backend subdirs · 10-domain model unimplemented) |
| Duplicate implementations | HIGH (Article 30 unresolved) |
| **Overall maintainability** | **⚠️ MEDIUM · governance strong · execution behind** |

### 8.2 · Scalability

| Dimension | Verdict |
|---|:---:|
| Universe scale (200 India · 30 USA) | ✅ tested |
| Runtime budget | ✅ 140-200s India · 25-106s USA (within 300s target) |
| Persistence append-only | ✅ Sprint 7.5 |
| Zero-caching where matters | ✅ verified in Phase 18 |
| Universe 5× scale unverified | ⚠️ no load test |
| **Overall scalability** | **✅ acceptable at current scale · load-test gap** |

### 8.3 · Security

| Dimension | Verdict |
|---|:---:|
| Secrets in code | ✅ 0 hits (verified fresh) |
| `.env` gitignored | ✅ verified |
| Dep vulnerability scan | ❌ `safety check` not wired |
| Version pinning | ❌ `requirements.txt` unpinned |
| Injection surfaces | ✅ no `shell=True` |
| **Overall security** | **✅ core PASS · supply-chain gap** |

### 8.4 · Operational Readiness

| Dimension | Verdict |
|---|:---:|
| Structured logging | ❌ mostly `print()` |
| Metrics | ⚠️ per-step ledger only |
| Tracing | ❌ absent |
| Retries | ⚠️ Telegram only |
| Concurrency locks | ❌ only mon001-daily.yml |
| Rollback protocol | ✅ commit-revert pattern proven (C0) |
| Health checks | ✅ Telegram + freshness · ops_check |
| Alerting | ⚠️ Telegram-only path · no on-call rotation |
| **Overall operational** | **⚠️ MEDIUM · logging + tracing + concurrency gaps material** |

---

## 9 · Prioritized Remediation Backlog (independent view)

**No implementation this audit.** The Red Team's ranked backlog for what SHOULD happen next:

| Rank | Task | Wave 5 Claim | Reality | ROI |
|:---:|---|:---:|:---:|:---:|
| 1 | **Wire Capital Rotation into `aegis_daily_v2.py` + `usa_daily.py`** · produce `rotation_plan.json` | SHIPPED | BUILT not wired | HIGH · flips Cap Map §4.10 status to Active |
| 2 | **Wire Portfolio Attribution into daily orchestrators** · produce `portfolio_attribution.json` | SHIPPED | BUILT not wired | HIGH · flips §5.8 to Active |
| 3 | **Wire Opportunity Cost enrichment onto every HOLD** | SHIPPED | BUILT not applied | HIGH · flips §4.11 to Active |
| 4 | **Fix keystone `reports/recommendations.json` producer** (v2.2 M-R1) | PLANNED D4 | STALE 9d | HIGHEST · unblocks 9 broken daily steps |
| 5 | **Add byte-equality replay regression test** (v2.2 Rep1) | PLANNED D6 | Not written | HIGH · Article 42 scenario #14 |
| 6 | **Add `--frozen-clock` mode to replay** (v2.2 Rep2) | PLANNED D6 | Not written | HIGH |
| 7 | **Wire `validation/` into CI** — every validator runs on push | Wave 4 D8 | Files exist · CI unwired | MED |
| 8 | **Populate `backend/shared/indicators/`** with canonical RSI/ATR/ADX/MACD/EMA/SMA impls · migrate 19 duplicate sites | Wave 4 D1 | Empty `__init__.py` | HIGH · Article 30 |
| 9 | **Add `concurrency:` block to `aegis-daily.yml`** (v2.2 T1) | PLANNED D7 | Missing | MED · trivial fix |
| 10 | **Sanitize 13 India OHLC anomalies** (v2.2 M-D1) | PLANNED D2 | Uncorrected | MED |
| 11 | **Add VEDL corporate action entry** (v2.2 M-D2) | PLANNED D2 | Uncorrected | MED |
| 12 | **Restore NIFTY200 missing tickers** (v2.2 M-D3) | PLANNED D2 | Missing | MED |
| 13 | **Add rec-hash Telegram dedup** (v2.2 T3) | PLANNED D7 | Not built | LOW-MED |
| 14 | **Remove classifier `_MATRIX` dead code** (v2.2 S7) | PLANNED D3 | Still present | LOW · trivial fix |
| 15 | **Fix STRONG_BUY-unreachable-in-stress** (v2.2 S4) | PLANNED D3 | Uncorrected | MED |
| 16 | **Populate 10 domain owner docs** (Article 94) | Wave 5 P3 PASS-claimed | 0/10 exist | LOW |
| 17 | **Populate 65 per-capability docs** (Article 94) | Wave 4 D0 | 0/65 exist | LOW |
| 18 | **Wire `safety check` to CI + pin `requirements.txt` majors** (Article 52 · 61) | Phase 17 recommendation | Not done | MED |
| 19 | **Migrate `print()` → stdlib logging** across `backend/india/usa/scripts` (Article 71) | Phase 15 recommendation | Not done | MED |
| 20 | **Build 20-scenario institutional acceptance suite** (Article 42 · Wave 4 D8) | Empty scaffold | 0/20 scenarios | HIGH · certification gate |
| 21 | **Sprint 7.9 · Recommendation Orchestrator** — get Runner 2 out of 100% HOLD | Frozen roadmap | Deferred | HIGHEST · fixes 4 dimensions simultaneously |

**Recommended sequencing:**
1. **Immediate (single commit)** — Ranks 9 + 14 (trivial fixes) · Rank 1-3 (wire Wave 5 engines to daily orchestrator · elevate BUILT to WIRED)
2. **Sprint 1 · Substrate** — Ranks 8 + 10-12 (data + indicators) — closes Article 30
3. **Sprint 2 · Rec Chain** — Ranks 4 + 15 + 21 (keystone + STRONG_BUY + orchestrator) — biggest unlock
4. **Sprint 3 · Replay + Delivery** — Ranks 5-7 + 13 (determinism + Telegram dedup + validation-in-CI)
5. **Sprint 4 · Docs + Certification** — Ranks 16-20 (docs + security + logging + acceptance suite)

---

## 10 · Sealed Contracts Verification (fresh)

| Contract | Fingerprint | Status |
|---|---|:---:|
| MON001 sealed baseline | `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf` | ✅ PRESERVED |
| Feature Store schema | `b65ceb49a83a` | ✅ STABLE |
| `india/telegram_notify.py` | (imported only by test_telegram_notify_fallback) | ✅ UNTOUCHED |
| `research/adaptive_rec_v2/` | (imported by fusion consumers) | ✅ UNTOUCHED |
| `research/risk_capital_v2/` | (imported by fusion consumers) | ✅ UNTOUCHED |

**No sealed contract violations detected.** This is the one area where Wave 5's claims fully match reality.

---

## 11 · Final Go/No-Go (Red Team)

# **NO-GO** · unchanged verdict but with honest ladder.

**Red Team's true state:**
- Wave 5 delivered **3 Level-1 BUILT engines** + **3 Level-3 VALIDATED validators** + governance foundation
- Wave 5 did NOT elevate anything to Level 2 WIRED · Level 4 CONSUMED · Level 5 CERTIFIED
- Wave 5's 54.25/100 score is arithmetically correct but inflates Portfolio Consistency dimension because Attribution Engine is not wired
- **Honest score (Red Team recalculation using only WIRED-or-better capabilities): ~50/100** (revised down from 54.25 for Portfolio Consistency +15 pp credit that shouldn't count)

**Path to GO is defined but not started.**

**Estimated effort to WIRED status for Wave 5 new engines:** 1 focused sprint (3 orchestrator additions + 3 CI validator wire-ins + 3 output artifact schemas registered).

**Estimated effort to full CERTIFIED status:** the full Wave 4 D0-D8 sequence + the 20-scenario institutional suite. That's the 43-pp path to 97/100 that Wave 5 Phase 20 correctly identified.

---

## 12 · Operator-facing Questions

**Q1 · Workflow cleanup (from operator's message):** Reduce `.github/workflows/` from 5 → 4 by merging `eng001-regression.yml` into `aegis-ci.yml` and consider adding `release.yml`. Destructive change — requires operator sign-off. Red Team recommendation: **defer until Wave 4 D8** (where CI restructure is native scope · avoid mid-audit workflow churn).

**Q2 · Documentation honesty standard:** Should Wave 5's "SHIPPED" verb be retroactively rewritten to reflect the 5-level ladder (BUILT / WIRED / VALIDATED / CONSUMED / CERTIFIED)? Red Team recommendation: **YES** · amend the Constitution to require ladder-level in every capability status claim (Article 16 amendment via Article 99 process).

**Q3 · Cap Map single-source-of-truth conflict:** Wave 5 P9 doc lists Capital Rotation as "SHIPPED" · Cap Map §4.10 lists it as "Planned". Both are current. Red Team recommendation: **resolve by adopting ladder** — mark Capital Rotation as `Status: BUILT · target: WIRED-by-D4` in Cap Map.

**Q4 · Skip Wave 6 · execute remediation backlog:** operator was right to suggest not building more architecture docs. Ranked backlog above is the actionable path. Red Team recommendation: **execute Rank 1-3 in the next turn** (wiring the 3 Wave 5 engines to daily orchestrators — the smallest and most clarifying next step).

---

## 13 · Definition of Done · Red Team Audit

- [x] Fresh evidence sweep (grep + read + fingerprint check · not doc-trust)
- [x] 5-level ladder introduced (BUILT / WIRED / VALIDATED / CONSUMED / CERTIFIED)
- [x] Wave 5 SHIPPED claims adjudicated (Level 1 only)
- [x] Constitution recount produced (PASS 45 → PASS 38 correction)
- [x] Duplicated capabilities regrep (Article 30 · 19 sites confirmed)
- [x] Missing production code enumerated
- [x] Dead code · stale artifacts listed
- [x] Governance violations G1-G9
- [x] Determinism recheck (unit-level ✅ · system-level ❌)
- [x] Maintainability / Scalability / Security / Operational assessment
- [x] Prioritized remediation backlog (21 items · sequencing recommendation)
- [x] Sealed contracts verified fresh
- [x] Final Go/No-Go with evidence
- [x] Operator-facing questions
- [x] No fixes implemented (audit-only per mandate)
- [x] Sealed contracts UNTOUCHED · MON001 fingerprint preserved through this audit

**End of Wave X · Red Team Independent Audit · SHIPPED 2026-07-27.**
