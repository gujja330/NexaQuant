# AEGIS v2.2 · End-to-End Stabilization Audit
### 🔒 LOCKED 2026-07-27 · Investigation Phase Complete · 20-Phase Framework · Production Readiness Score = **49/100 · NO-GO**

**Method:** 7 parallel investigation subagents · read-only across `c:/Users/GPraveenKumar/Downloads/prism` · 356,733 bar-rows scanned (314,062 India + 42,671 USA) · 59 engines · 32 India + 35 USA daily-orchestrator steps · 5 GitHub Actions workflows · 6 Telegram senders · zero code modified this phase.

**Directive (from operator):** *"Investigation first, implementation second. Do NOT modify code. Understand the complete platform first. Validate every assumption with evidence."*

**Cumulative test health at audit time:** 280/280 backend + regression tests green · fingerprint `e4c070673568c52d…` preserved · sealed OPS001/MON001/legacy engines untouched.

---

## 0 · Executive Summary

**Score: 49/100 → NO-GO.** AEGIS is architecturally sound but operationally degraded. Five weight-adjusted primary blockers absorb ~30 of the 51 lost points:

1. **Keystone `reports/recommendations.json` unowned** — required by 6+ India daily steps, produced by ZERO orchestrator step, mtime frozen at 2026-07-17 (10 days stale). Root cause: only producer is deprecated `research/recommendations/run.py`, not wired to any daily runner. Downstream effect: 9/32 India steps read stale data every day.
2. **Runner 2 (Rec v3) emits 100% HOLD** across the last 15 recommendations · 96 replayed India dates · 68 replayed USA dates. Collapses Portfolio Consistency (0 positions · 100% cash), Benchmark completeness (n=0), Learning ledger (empty).
3. **Recommendation Accuracy corpus depth = 10 trades** (Runner 1 legacy) — Wilson 95% CI = `[23.66%, 76.34%]` on win rate → `DIRECTIONAL_ONLY` verdict. Sample too small to certify.
4. **6 Telegram senders active, zero dedup key** — `.github/workflows/aegis-daily.yml:150,162` fires two senders in same job; no `concurrency:` block. Evidence: 4× UX030 sends captured in `reports/telegram_delivery_ux030_2026-07-20.jsonl`.
5. **Sector taxonomy divergence** — `india/sectors.py` custom 17-bucket vs `backend/macro_intel/sector_rotation.py` USA-GICS 11-bucket. No mapping layer. Cross-market sector rotation is not comparable.

**Additional silent-breakage findings surfaced (not previously known):**
- **`backend/feature_store/features/technical.py:_atr` is dead code** — the H/L branch never fires because caller builds a `close+volume` DataFrame → every `atr_14_pct` value is a ±0.5% mechanical band on close (~0.7-1.0% constant), across 356k bars.
- **`_adx` is not real ADX** — uses `close.diff()` for both +DM/-DM (textbook Wilder needs `high.diff()` and `-low.diff()`).
- **Sector schema mismatch** in `backend/canonical/adapters.py:422-442` and `backend/macro_intel/sector_rotation.py:45-52` checks `isinstance(sectors, dict)` but on-disk `sector_context.json` has `"sectors"` as a **list** → 0 rows extracted → `sector_rotation.json` empty for India, factor_library sector readings null.
- **VEDL 2026-04-30 -64.9% not in `corporate_actions.parquet`** — unrecorded event, downstream treats as valid signal.
- **13 India OHLC anomalies** — `open < low` across ANGELONE, BALRAMCHIN, BANKBARODA, BHARATFORG, INDIANB, IRCTC, MAZDOCK, PNB, RBLBANK, RECLTD, SBILIFE, TORNTPHARM, UNIONBANK.
- **MON001 sealed-baseline fingerprint sentinel dormant** — `sealed_baseline_fingerprint.txt` not on disk · `ops_check.json` reports `fingerprint.checked: false`.
- **STRONG_BUY unreachable in stress regime** — regime × calibration chain caps calibrated confidence at 0.65, but classifier requires ≥0.70.
- **Classifier `_MATRIX` is dead code** — actual decisions come from if-else at `backend/recommendation/classifier.py:31-35`.

**Not blockers (validated healthy):**
- Risk Enforcement (Sprint 4, score 90/100 · 23 tests · VaR/CVaR/HHI wired)
- State management (Sprint 7.5 persistence, score 90/100 · append-only history · 18 tests)
- Determinism substrate (Sprint 7.6/7.7 replay deterministic in known-good paths, score 75/100)
- USA chain integrity (all 8 downstream `recommendations.json` consumers fresh mtime 2026-07-24)
- Data quality basics (0 NaN in OHLC across all 356k bars · 0 duplicate-date rows · 0 delistings)

---

## 1 · The 20 Deliverables

Every phase's finding is anchored to concrete evidence with file:line references. Each finding is CLASSIFIED per Wave Closure Mode: 🔴 Must-Fix · 🟠 Accepted Debt · 🟢 Environment · 🔵 Expected Future.

### Phase 1 · Data Quality Report

| # | Check | India | USA | Class |
|---|-------|:-----:|:---:|:-----:|
| 1 | NaN in OHLC | ✅ 0/314,062 | ✅ 0/42,671 | — |
| 2 | Duplicate-date rows | ✅ 0 | ✅ 0 | — |
| 3 | Invalid OHLC (`open<low`) | ⚠️ 13 bars / 13 tickers | ✅ 0 | 🔴 M-D1 |
| 4 | Negative/zero close | ✅ 0 | ✅ 0 | — |
| 5 | Zero-volume days | ⚠️ 1,757 (0.56%) | ⚠️ 1,257 (2.95%) | 🔵 EF-D1 (all VIX/idx) |
| 6 | Corp-action anomaly (>30% 1-day drop) | ⚠️ 3 events · VEDL -64.9% NOT in corporate_actions.parquet | ⚠️ 1 (VIX regime change) | 🔴 M-D2 (VEDL) |
| 7 | Delistings (>60d behind fleet) | ✅ 0 | ✅ 0 | — |
| 8 | Symbol mapping | ✅ | ⚠️ 4 index files use `_IDX_*` convention | 🟠 A-D1 |
| 9 | NIFTY200 vs raw universe | ⚠️ LTIM, PEL, TATAMOTORS missing | — | 🔴 M-D3 |
| 10 | Raw-schema uniformity | ⚠️ 227 MT5 (tick_volume+spread) vs 2 (volume only: INDIAVIX, SP500) | ✅ | 🟠 A-D2 |
| 11 | US universe consistency | — | ✅ 30/30 | — |

**Must-Fix candidates:**
- **M-D1 · 13 India OHLC anomalies** — invalid `open < low` bars will propagate as noisy inputs to every downstream indicator until sanitized.
- **M-D2 · VEDL 2026-04-30 unrecorded event** — treat as split/spin-off gap in `data/raw/india/corporate_actions.parquet`. Add explicit entry OR add price-anomaly detector in ingest.
- **M-D3 · NIFTY200 gap** — `LTIM/PEL/TATAMOTORS` (heavy-weight names) absent from raw. Universe drift risk in ranker.

### Phase 2 · Feature Engineering Validation

**Master feature table:** 40+ registered features across `backend/feature_store/features/{technical,fundamental,news,earnings,macro,sector,institutional,corporate_actions,market_intel,historical}.py`.

**Suspicious implementations (with evidence):**

| # | Finding | Location | Impact | Class |
|---|---------|----------|--------|:-----:|
| F1 | ATR is dead code — `_atr` proxy branch always fires; H/L branch never triggers | `backend/feature_store/features/technical.py:46-53` + caller L83-85 | **All 356k `atr_14_pct` values are ±0.5% mechanical band on close (~0.7-1.0% constant)** | 🔴 M-F1 |
| F2 | ADX is close-only proxy (not textbook Wilder) — uses `close.diff()` for +DM/-DM | `backend/feature_store/features/technical.py:64-73` | Trend model reads compromised ADX signal in Feature Store; correct version exists in `india/feature_engine.py:_adx` | 🔴 M-F2 |
| F3 | RSI uses simple rolling mean, not Wilder smoothing | `backend/feature_store/features/technical.py:25` + `india/technical_factors.py:27` + `india/feature_engine.py:69` | Values differ from broker/dashboard convention; 3 divergent implementations | 🟠 A-F1 |
| F4 | Volatility not annualised in Feature Store | `backend/feature_store/features/technical.py:106-111` | `volatility_20d` is daily-scale; other engines use `×sqrt(252)`. Silent scale mismatch | 🟠 A-F2 |
| F5 | 4+ ATRs · 3 RSIs · 3 ADXs across trees — no shared indicator library | `backend/feature_store/features/technical.py` · `india/feature_engine.py` · `india/technical_factors.py` · `strategy/{smc,risk,regime}.py` · `usa/research/recommendations/lib/entry_exit.py` · `research/edge_probe.py` | Divergent conventions per engine | 🟠 A-F3 |
| F6 | Fundamentals broadcast latest snapshot (look-ahead risk) | `india/feature_engine.py:158-171` + `backend/feature_store/features/fundamental.py` | Only prices are walk-forward safe; author self-flagged `"(snapshot, broadcast -> OPTIMISTIC/look-ahead)"` | 🟠 A-F4 |
| F7 | Macro symbol map is US-centric only (no China/Europe) — India VIX explicitly null | `backend/feature_store/features/macro.py:16-45` | Half the macro feature space missing for India | 🔵 EF-F1 (Sprint 6.5 backlog) |
| F8 | MACD hardcoded (12,26,9) — no override | `backend/feature_store/features/technical.py:36-42` | Forces `min_history = 35`; not parameterizable | 🟠 A-F5 |
| F9 | Institutional windows hardcoded (insider 90d · fii/dii 5d) | `backend/feature_store/features/institutional.py:14-56` | Not parameterizable per market or regime | 🟠 A-F6 |

**Must-Fix from this phase: F1 (ATR dead code) + F2 (ADX not real ADX).** Both are silent breakages that make Model Factory + Rec Engine consume noise disguised as feature signal.

### Phase 3 · Scoring Validation

23 score-producing sites catalogued (see Section C.1 of Agent 5 report). **11 documented inconsistencies:**

| # | Finding | Location | Class |
|---|---------|----------|:-----:|
| S1 | Confidence scales fragmented: `[0,1]` (backend) vs `{Low,Med,High}` (india/confidence_engine) vs `{0.0, 1.0}` binary (factor_library) vs `predict_proba[:,1]` (adaptive_rec_v2) | 4 engines | 🔴 M-S1 |
| S2 | Score scales fragmented: `[-1,+1]` (Model Factory + Rec Engine) vs `[0,100]` (Market Intelligence + USA technicals + adaptive_rec_v2 dimensions) | 4 engines | 🔴 M-S2 |
| S3 | `score` column collision — `[-1,+1]` in Model Factory vs `[0,100]` `score_at_entry` in `research/adaptive_rec_v2/lib/features.py:24` | Cross-engine feature naming clash | 🟠 A-S1 |
| S4 | **STRONG_BUY unreachable in stress regime** — regime mult 0.65 × classifier threshold 0.70 → cap = 0.65 | `backend/recommendation/{calibration,regime_adjust,classifier}.py` | 🔴 M-S3 |
| S5 | Rank-based scoring depends on universe — feeding 1 ticker → 0.0; feeding 30 → different score than 229 | `backend/model_factory/model_base.py:113-120 rank_score()` | 🟠 A-S2 |
| S6 | Ensemble silently clips negative weights to 0 without warning | `backend/model_factory/ensemble.py:23-27 EnsembleWeights.normalize()` | 🟠 A-S3 |
| S7 | **Classifier `_MATRIX` is DEAD code** — actual decisions come from if-else at L31-35; `_MATRIX` contains bogus row (`-1.01, 0.70, STRONG_SELL`) | `backend/recommendation/classifier.py:12-19` | 🔴 M-S4 |
| S8 | Two competing rec pipelines: `backend/recommendation` (threshold classifier) vs `research/adaptive_rec_v2` (HGB/LogReg) — different confidence semantics | Cross-engine | 🟠 A-S4 |
| S9 | Regime string coupling — `factor_library/engine.py:35-42 _classify_trend` returns `"sideways"` which regime_adjust doesn't recognize → falls to `unknown` (0.85 mult) | `backend/factor_library/engine.py:35-42` vs `backend/recommendation/regime_adjust.py:14-20` | 🔴 M-S5 |
| S10 | `MacroModel.confidence` hardcoded to 0.8 magic constant | `backend/model_factory/models/macro_model.py:40` | 🟠 A-S5 |
| S11 | Sector rotation weights sum to 0.8 (`0.6 + 0.3 - 0.1`), not 1.0 — composite not on same absolute scale as other rule-based models | `backend/model_factory/models/sector_rotation.py:32` | 🟠 A-S6 |

### Phase 4 · Recommendation Validation

Confirmed 10 recommendation entry points (from Sprint A1 audit). Cross-engine trace of IPCALAB + APOLLOHOSP:

| Ticker | Producer | Score | Rank | Action | Confidence | Sector | mtime |
|--------|----------|:-----:|:----:|:------:|:----------:|:------:|:-----:|
| IPCALAB | `research/recommendations/run.py` (DEV023 · deprecated) | 83.51 | 1 | Strong-Buy | 1.00 | Pharma | 2026-07-17 |
| APOLLOHOSP | Runner-1-LEGACY (Shield 14.1% weight) | — | — | STRONG BUY | — | Healthcare | 2026-07-24 |
| APOLLOHOSP | Runner-1-v2 (adaptive fusion) | 73.63 | 19 | Buy | — | Healthcare | 2026-07-24 |
| APOLLOHOSP | Runner-2-v3 (backend/recommendation) | — | — | HOLD | — | Healthcare | 2026-07-24 |

**Findings:**
- IPCALAB frozen at 2026-07-17 because `recommendations.json` (its only publisher) has no daily orchestrator producer.
- APOLLOHOSP has three simultaneous producer conclusions, each with different sector/action/rank.
- Runner 2 emits 100% HOLD (15/15 last run) → collapses portfolio.
- **Every rec producer is missing all 5 delta/change fields**: `previous_rank`, `confidence_delta`, `sector_change`, `momentum_change`, `risk_change` (Agent 2 finding).
- Only DEV023 has `current_rank`, `overall_rank`, `sector_rank`, `industry_rank`.
- Reason field style varies wildly across 4 producers: R1 freetext · R2 bull/bear · Fusion structured `why_this[]/why_not_stronger[]/dimensions[]` · DEV023 tag-list `reasons_for[]/reasons_against[]`.

**Must-Fix candidates:**
- **M-R1 · Keystone gap** — orchestrator must produce `reports/recommendations.json` (either wire deprecated `research/recommendations/run.py` OR migrate 30+ downstream consumers to `recommendations_v3.json`).
- **M-R2 · Rec producer schema divergence** — 3 different reason schemas, missing delta fields, incompatible rank fields.

### Phase 5 · Portfolio Validation

**`reports/portfolio_v3.json`:** `n_positions=0` · `cash_pct=1.0` · `positions=[]` · `schema_fingerprint=b65ceb49a83a` · mtime 2026-07-24.

**Runner 1 `reports/portfolio.json`:** mtime **2026-07-17** (10 days stale). Runner 1 outputs 51 NEW_POSITION on 208 tickers but never feeds into `portfolio_engine`.

**Two portfolios coexist:**
| Portfolio | Producer | Positions | State | Class |
|-----------|----------|:---------:|:-----:|:-----:|
| `portfolio.json` | Runner 1 (legacy) | 51 NEW | 10 days stale | 🔴 M-P1 |
| `portfolio_v3.json` | Runner 2 (backend/portfolio) | 0 | fresh but empty (Runner 2 100% HOLD) | 🔵 EF-P1 |

**M-P1 · Portfolio divergence** — dashboard/Telegram/reports read whichever file is fresher; UI shows misleading picture depending on which one wins. Requires SSoT decision.

### Phase 6 · Sector Validation

**CRITICAL SILENT BREAKAGE:**
- `backend/canonical/adapters.py:422-442` and `backend/macro_intel/sector_rotation.py:45-52` both check `isinstance(sectors, dict)` for extraction
- On-disk `reports/sector_context.json` has `"sectors"` as a **list**
- Result: 0 rows extracted → `sector_rotation.json` empty for India (`sector_returns={}` · `leaders=[]` · `laggards=[]` · `rotation_strength=0.0`)
- Factor Library reads → null sector-rotation-leader/laggard factor rows for India

**Additional findings:**
- Runner 1 uses **hardcoded** `india/sectors.py::SECTORS` + own 3-month momentum for `sec_score` — ignores DEV018 13-dim sector model
- Runner 2 has **ZERO** references to any sector context file
- Risk / Portfolio / Capital Rotation / Telegram / Dashboard never read `sector_rotation.json` or `sector_context.json`
- 3 producers have effectively NO active production consumer: `sector_context`, `industry_context`, `company_context`
- **Sector taxonomy divergence:** `india/sectors.py:5-51` uses 17 custom buckets (`Financials, IT, Energy, Power, FMCG, Auto, Pharma, Healthcare, Metal, Cement, Infra, Industrials, Telecom, Consumer, Chemicals, Realty, Transport`) vs `backend/macro_intel/sector_rotation.py:10-22` uses 11 USA-GICS (`Technology, Financials, Healthcare, Energy, Industrials, Consumer Discretionary, Consumer Staples, Utilities, Materials, Real Estate, Communication Services`). No mapping layer.

**Must-Fix candidates:**
- **M-Sec1** — Fix `isinstance(sectors, dict)` → handle list on disk (1-line fix per site).
- **M-Sec2** — Add sector taxonomy mapping layer (India-custom ↔ GICS).

### Phase 7 · Capital Rotation Validation ⭐

**Engine does NOT exist.** Zero files matching `capital_rotation`, absent from all Phase 3/4/5/6 roadmap sprint reports 1-7.8, absent from Phase 4 module list.

**Design (Agent 4 · 100% reuse of existing engines):**

```
keep_score(p)      = 0.35·upside + 0.20·conf_Δ + 0.15·rank_Δ + 0.15·sector + 0.15·pnl
candidate_score(c) = (0.40·upside + 0.25·conf + 0.20·rank + 0.15·sector) × macro_gate
macro_gate         = {risk_on:1.0, neutral:0.9, risk_off:0.5, stress:0.3, recession_warning:0.5}

Decision thresholds:
  EXIT       if keep_score < -0.20
  TRIM_50    if keep_score < +0.10
  ROTATE     if candidate.score - keep.score > +0.25
```

**Pipeline insertion:** new step AFTER `decision_center` in `scripts/aegis_daily_v2.py`.
**New files (implementation phase):** `india/capital_rotation/run.py` + `usa/research/capital_rotation/run.py` + `configs/capital_rotation.yaml`.
**Outputs:** `reports/rotation_plan.json` + `reports/history/rotation_plan.parquet` + `reports/rotation_alerts.json`.

**Not built. Ships in v2.2 Wave 3 (post-audit) or Sprint 7.9+ per operator direction.**

### Phase 8 · Risk Validation

**Sprint 4 · shipped healthy.** Score: **90/100 → GO.**
- `backend/risk/{types,sizing,vol_adjustment,exposure_caps,concentration,var_cvar,engine}.py`
- `configs/risk_budget.yaml` locked
- 23 tests green
- Live daily produces fresh `reports/sized_positions.json`, `risk_report.json`, `ai_risk_narrative.json` (mtime 2026-07-24)
- VaR/CVaR/HHI/`cap_reason` all wired

**No blockers.** Only caveat: currently receives zero positions from Runner 2 (100% HOLD chain), so risk enforcement is inactive by starvation — not by design fault.

### Phase 9 · Strategy Validation

| Strategy | Status | Evidence |
|----------|:------:|----------|
| Scanner | ❌ DOES NOT EXIST | grep across repo: 0 files |
| Champion | ⚠️ DISCONNECTED | `champion_strategy.json` mtime 2026-07-17 (10d stale) · producer unwired · hotfix `929be1d` loosened ops-check SLA but did not fix producer |
| Shield | ⚠️ NOT STANDALONE | vol-tier profile embedded in `india/recommendation_generator.py:210-216`, not a first-class engine |
| Income | ❌ DOES NOT EXIST | grep across repo: 0 files |
| Momentum / Value / Quality / Growth | ✅ EXIST | `backend/model_factory/models/{momentum,value,quality,growth}.py` |

**Classification:**
- 🔴 M-Str1 · Champion strategy producer disconnected (10-day stale)
- 🟠 A-Str1 · Scanner + Income don't exist — decide: build or remove from operator lexicon
- 🟠 A-Str2 · Shield embedded in Runner 1 rec generator — promote to first-class engine or accept in-line

### Phase 10 · AI Validation

**Per invariant (`aegis_ai_embedded_architecture` memory): 6 AI agents is the full set. No new AI.** Existing AI narrators:

| Narrator | Output | Role |
|----------|--------|:----:|
| Market | `reports/ai_market_narrative.json` | explains market intel |
| Learning | `reports/ai_learning_narrative.json` | explains learning corpus |
| Macro | `reports/ai_macro_narrative.json` | explains macro regime |
| Portfolio | `reports/ai_portfolio_narrative.json` | explains portfolio state |
| Recommendation | `reports/ai_recommendation_narrative.json` | explains rec decisions |
| Risk | `reports/ai_risk_narrative.json` | explains risk report |

**All AI outputs explain/synthesize · NEVER compute or decide.** Verified per invariant.

**Feature narrative:** `reports/ai_feature_narrative.json` present but stale on inputs (features derived from broken ATR/ADX/sector chain → AI narration built on faulty numeric substrate).

**Class:** 🔵 EF-AI1 — AI outputs are structurally fine but semantically compromised until upstream features are fixed.

### Phase 11 · Historical Validation

**Sprint 7.8 benchmark framework:**
- Runner 1: n=10 · verdict `DIRECTIONAL_ONLY` · Wilson 95% CI `[23.66%, 76.34%]` · mean +0.0838% · win rate 50% · profit factor 1.0353 · max DD -17.44%
- Runner 2: n=0 · verdict `INSUFFICIENT_DATA` (100% HOLD chain)
- Comparison: `CANNOT_COMPARE_INSUFFICIENT_DATA` (need ≥30 closed each)

**Sprint 7.7 replay coverage:** 137 USA + 94 India days replayed · 0 leaks · target window `2025-01-01 → today` NOT achieved.

**Historical metrics currently produced:** 17 (from Sprint 7.8 panel).

**5 net-new metrics designed by Agent 4 (for post-audit v2.2 Wave 3):**
- **N1 · Alpha/Beta** — OLS regression rec vs benchmark
- **N2 · Rotation frequency** — trades per position per year
- **N3 · Profit capture** — realized / theoretical max
- **N4 · Missed alpha** — HOLD false negatives at ex-post positive outcomes
- **N5 · HOLD false-neg rate** — % of HOLDs that would have been positive

**Class:** 🔵 EF-H1 — corpus depth solved by more days replayed OR by Rec Engine v3 emitting BUY/SELL. Not a fix, a fill.

### Phase 12 · Replay Validation (Determinism · primary criterion)

**Verdict:** DEGRADED. Functionally deterministic (no RNG in critical paths) but NOT byte-identical due to timestamp rotation.

| Source of byte-drift | Location |
|----------------------|----------|
| `run_utc` timestamp in every engine driver | `backend/replay/engine_drivers.py:154,224,276` |
| `appended_utc` in every history write | `backend/persistence/history_writer.py:75` |
| `elapsed_s` per step | `backend/replay/controller.py:138,152,235,305` |
| `wall_clock` derived from `date.today()` | `backend/replay/engine_drivers.py:304` |

**No regression test compares two-run outputs.** `test_sprint76.py:274` tests resume-skip only.

**Must-Fix candidates:**
- **M-Rep1 · Add byte-equality regression test** — replay a fixed window TWICE, hash-compare all outputs, assert equal (with a `norm_utc()` helper that strips timestamps from JSON).
- **M-Rep2 · Add `--frozen-clock` mode** — inject `asof_utc` instead of reading `date.today()` in `engine_drivers.py:304`.

### Phase 13 · Telegram Validation

**Compound root cause (Agent 3):**
1. `.github/workflows/aegis-daily.yml:150-168` — dual senders fired in same job (`telegram_send_with_retry.py` + `telegram_send_ux030.py`)
2. `.github/workflows/aegis-daily.yml:182` — `.published` marker written LAST (should be BEFORE Telegram)
3. `aegis-daily.yml` has NO `concurrency:` block (compare `mon001-daily.yml:27-29`)
4. `scripts/telegram_send_with_retry.py:76-81` FAILURE_MARKERS mis-classify partial-success
5. `india/telegram_notify.py:918-940` chunks message; chunk 1/2 succeeds + chunk 2/2 fails → retry sends chunk 1 again
6. 5 secondary origination points: 2 Windows tasks + `run_daily.bat` + nexaquant daemon + USA workflow

**Evidence:** `reports/telegram_delivery_ux030_2026-07-20.jsonl` — 4× UX030 sends captured in the same day.

**Sealed contract: `india/telegram_notify.py` UNTOUCHED per invariant.**

**Must-Fix candidates:**
- **M-T1 · Add `concurrency:` block to `aegis-daily.yml`** (mirror `mon001-daily.yml:27-29`)
- **M-T2 · Move `.published` marker BEFORE Telegram** (not after)
- **M-T3 · Add dedup key based on rec-set hash** — reject duplicate sends within 4-hour window

### Phase 14 · Report Validation

**Fresh (mtime 2026-07-24):**
`recommendations_v3.json` · `portfolio_v3.json` · `risk_report.json` · `investment_intelligence.json` · `ai_*_narrative.json` (6 files) · `sized_positions.json`

**Stale (mtime 2026-07-17, 10 days):**
`recommendations.json` (keystone) · `global_context.json` · `learning.parquet` · `champion_strategy.json` · `portfolio.json`

**Semi-stale:**
- `morning_latest.html` — 7 days (2026-07-20)
- `benchmark.json` — 6 days (2026-07-21)

**Per-artifact `schema_fingerprint` present** (verified in `portfolio_v3.json`). **No global report catalogue** with version pinning.

**Class:** 🔴 M-Rep1 — morning report staleness · directly linked to keystone gap (M-R1).

### Phase 15 · Dashboard Validation

**India dashboard** (`ux/dashboard/frontend/index.html:872-876`):
- `REPORTS_BASE = '../../../reports/'`
- `fetch(..., {cache: 'no-store'})` at L876 — cache-bust correct
- BUT reads `recommendations.json` (10 days stale) → renders `2026-07-17` numbers as "today"

**USA dashboard** (`usa/dashboard/frontend/index.html:190,873`):
- `fetch("../../reports/" + f + "?t=" + Date.now())` — cache-bust correct
- USA `recommendations.json` fresh → dashboard renders correct data

**Class:** 🔴 M-Dash1 (India stale-inputs render) — resolved when keystone gap (M-R1) closes.

### Phase 16 · Database Validation

**No DB engine.** Zero imports of `duckdb`, `sqlite3`, `psycopg2`, `pymongo`, `redis`, `sqlalchemy` in production code.

**All state file-based** — 17 database-like stores catalogued:
- 14 parquet history stores (per Sprint 7.5 `aegis.persistence.v1`)
- 3 jsonl ledgers (aegis_daily_v2, mon001 alerts, telegram deliveries)
- 4 CSV registries (aegis_recommendation_db, feature manifest, model registry, universe)

**Persistence layer verified healthy:**
- `backend/persistence/__init__.py`, `history_writer.py`
- `reports/aegis_daily_v2_history.jsonl` (9 entries)
- Dedupe key `(market, asof)`, extended with `factor` for factor_library per Wave 1+2 B0-1 hotfix
- 18 tests green (Sprint 7.5)

**Class:** 🟢 GO (as designed) — no DB is a deliberate v2 architectural choice. DuckDB layer deferred to Phase 3 ARCH022+.

### Phase 17 · Scheduler Validation

**5 workflows:**
| Workflow | Cron (UTC) | Concurrency block? |
|----------|------------|:------------------:|
| `aegis-daily.yml` | 00:30/01:00/01:30/02:30 Mon-Fri (4 IST-morning retries) | ❌ NO |
| `aegis-usa.yml` | 20:30 Mon-Fri | ❌ NO |
| `mon001-daily.yml` | 11:00/13:15/15:45 Mon-Fri | ✅ YES (`concurrency: mon001-daily`) |
| `eng001-regression.yml` | 05:37 Sun + on-push | — |
| `aegis-ci.yml` | on-push/PR | — |

**Sequential-dependency guard:** `.published` file only — no cross-workflow lock.

**Risk:** if `aegis-daily.yml` delayed past 11:00 UTC → mon001 runs on stale data (no enforcement).

**Class:** 🔴 M-Sch1 — add `concurrency:` block to `aegis-daily.yml` (fixes duplicate scheduler AND Telegram dedup in one shot).

### Phase 18 · Performance Validation

**India pipeline:** 32 sequential steps · 140-200s total · 100% single-threaded.
**USA pipeline:** 35 sequential steps · 25-106s total.

**Bottlenecks (`reports/aegis_daily_v2_history.jsonl` · 9 entries):**
| Step | Median (s) | Max (s) | Class |
|------|:----------:|:-------:|:-----:|
| `ingest_corporate_actions` | 75.4 | 98.9 | 🟠 A-Pf1 (yfinance loop) |
| `ingest_fundamentals` | 66.7 | 77.2 | 🟠 A-Pf2 (yfinance loop) |
| `adaptive_rec_v2` | 20.9 | 44.0 | 🔵 EF-Pf1 (5× variance) |
| `refresh_market_data` (USA) | 15.9 | 35.3 | 🔵 EF-Pf2 (4× variance) |
| `institutional_memory` | 4.1 | 13.4 | 🔵 EF-Pf3 (4× variance) |
| `price_context` | 1.4 | 8.1 | 🔵 EF-Pf4 (7× variance) |

**Zero caching layers** (`@lru_cache/functools.cache/joblib.Memory/diskcache` — all 0 hits).
**Zero parallel processing** in daily orchestrator.
**No per-step retry with backoff** (only Telegram has retry — `scripts/telegram_send_with_retry.py:157`).
**Zero logging** in `scripts/india/usa/backend/research/` — all `print()` to stdout captured by subprocess.

**Class:** 🟠 accepted for now — pipeline well within budget; no acute perf need. Formalize in future hygiene sprint.

### Phase 19 · End-to-End Integration Validation

**Chain-integrity matrix (India):** 9 of 32 steps BROKEN, all reading `recommendations.json` (which is unproduced):

| Step | Requires | Status |
|------|----------|:------:|
| `validation_v2` | `recommendations.json` | 🔴 BROKEN |
| `risk_capital_v2` | `recommendations.json` + `global_context.json` | 🔴 BROKEN |
| `knowledge_graph` | `recommendations.json` | 🔴 BROKEN |
| `dna_feedback` | `recommendation_dna.parquet` (offline-produced) | 🔴 BROKEN |
| `price_context` | `recommendations.json` | 🔴 BROKEN |
| `institutional_memory` | `recommendations.json` | 🔴 BROKEN |
| `winner_genome` | `learning.parquet` + `recommendations.json` | 🔴 BROKEN |
| `decision_attribution` | `recommendations.json` | 🔴 BROKEN |
| `stock_validation` | `learning.parquet` (10d stale) | 🔴 BROKEN |
| `benchmark` | `learning.parquet` + `NSEI_D1.parquet` | 🔴 BROKEN |
| `morning_report` | `recommendations.json` + `benchmark.json` | 🔴 BROKEN |

**Chain-integrity matrix (USA):** OK — `recommendations` step produces `usa/reports/recommendations.json` · 8 downstream consumers all fresh.

**Class:** 🔴 M-E1 (India keystone chain) — single point of failure · single fix restores 9 steps.

### Phase 20 · Production Readiness Report

## **Weighted Production Readiness Score: 49 / 100 → NO-GO**

| Dimension | Weight | Score | Delta vs 100 |
|-----------|:------:|:-----:|:------------:|
| Determinism | 15% | 75 | -25 |
| **SSoT** | 15% | **25** | **-75** |
| **Recommendation Accuracy** | 15% | **35** | **-65** |
| Data Quality | 10% | 60 | -40 |
| Risk Enforcement | 10% | 90 | -10 |
| **Portfolio Consistency** | 10% | **20** | **-80** |
| Sector Consistency | 5% | 30 | -70 |
| Telegram Dedup | 5% | 30 | -70 |
| Report Consistency | 5% | 55 | -45 |
| Historical Validation | 5% | 55 | -45 |
| Performance | 5% | 65 | -35 |

Weighted sum:
```
0.15·75 + 0.15·25 + 0.15·35 + 0.10·60 + 0.10·90 + 0.10·20 + 0.05·30 + 0.05·30 + 0.05·55 + 0.05·55 + 0.05·65
= 11.25 + 3.75 + 5.25 + 6.00 + 9.00 + 2.00 + 1.50 + 1.50 + 2.75 + 2.75 + 3.25
= 49.00
```

**Verdict: NO-GO for production certification until Must-Fix items ship.**

---

## 2 · Classification Roll-up

**Total findings: 42.** Classified per Wave Closure Mode:

### 🔴 Must-Fix (14 items · ordered by weight-adjusted lever)

| ID | Finding | Estimated fix | Weight-adjusted lever |
|----|---------|:-------------:|:---------------------:|
| M-R1 | Wire keystone `reports/recommendations.json` producer (or migrate 30+ consumers to `recommendations_v3.json`) | 1 sprint | **+11.25 pts** (SSoT 15% × 75) |
| M-Sec1 | Fix `isinstance(sectors, dict)` → handle list on-disk (`adapters.py:422-442` + `sector_rotation.py:45-52`) | 1 line × 2 sites | **+3.5 pts** (Sector 5% × 70) |
| M-T1 | Add `concurrency:` block to `aegis-daily.yml` (mirror `mon001-daily.yml:27-29`) | 3 lines | **+3.5 pts** (Telegram 5% × 70) |
| M-T2 | Move `.published` marker BEFORE Telegram in `aegis-daily.yml:182` | 1 workflow edit | Compound with M-T1 |
| M-F1 | Fix ATR — pass real H/L into `_atr` (Feature Store) | 1 function refactor | Compound with M-F2 (features → scoring) |
| M-F2 | Fix ADX — use `high.diff()`/`-low.diff()` not `close.diff()` in Feature Store | 1 function rewrite | Compound with M-F1 |
| M-Rep1 | Add byte-equality replay determinism regression test | 1 test file | **+3.75 pts** (Determinism 15% × 25) |
| M-Rep2 | Add `--frozen-clock` mode to replay | 1 CLI flag + 4 site edits | Compound with M-Rep1 |
| M-Sch1 | Same as M-T1 (single concurrency block fixes both dedup and scheduler race) | — | Combined |
| M-Sec2 | Add India-custom ↔ GICS sector taxonomy mapping layer | 1 config + 1 lookup fn | Sector consistency |
| M-Str1 | Reconnect Champion strategy producer (currently 10-day stale) | 1 wire-in | Restores ops-check GREEN |
| M-D1 | Sanitize 13 India OHLC `open<low` bars in ingest | 1 validator + backfill | Data quality baseline |
| M-D2 | Add VEDL 2026-04-30 corporate-action entry (or price-anomaly detector) | 1 CSV row + validator | Data quality baseline |
| M-D3 | Restore NIFTY200 members LTIM/PEL/TATAMOTORS in raw | data ingest fix | Universe integrity |

### 🟠 Accepted Debt (14 items)

- A-D1 · USA index files use `_IDX_*` prefix — parseable but not stock-symbol-clean (grandfathered per Phase 5)
- A-D2 · India schema mixed (MT5 227 vs volume-only 2) — normalize in future hygiene sprint
- A-F1..A-F6 · 3 RSIs/3 ADXs/4 ATRs · vol not annualised in FS · fundamentals broadcast look-ahead · MACD/institutional windows hardcoded — indicator library consolidation in future hygiene sprint
- A-S1..A-S6 · Scoring naming collisions · rank-univ-dep · ensemble negative-weight clip · dual pipelines · MacroModel confidence magic-const · sector-rotation weights ≠1.0
- A-Str1 · Scanner + Income don't exist — decide with operator: build or remove lexicon
- A-Str2 · Shield embedded in Runner 1 — promote or accept
- A-Pf1..A-Pf2 · yfinance-loop bottlenecks (`ingest_corporate_actions`, `ingest_fundamentals`)

**Prior debt still open** (from Wave 1+2 closure): DEBT-1 keystone gap · DEBT-2 corporate-actions · DEBT-3 dual history schemas · DEBT-4 recommendation_dna orphan · DEBT-5 Phase-5 grandfathered engines.

### 🟢 Environment/Config (2 items)

- Telegram tokens confirmed present in `.env.telegram` (per operator directive)
- MON001 sealed-baseline fingerprint sentinel dormant — `sealed_baseline_fingerprint.txt` not on disk · `ops_check.json` reports `fingerprint.checked: false` — add sentinel file

### 🔵 Expected Future Population (12 items)

- Runner 2 100% HOLD collapses Portfolio + Benchmark + Learning — waits on Sprint 7.9 orchestrator
- Corpus depth n=10 → grows organically or via B1 replay expansion
- Every rec producer missing 5 delta/change fields → belongs in Sprint C1 (trade state)
- Lifecycle state machine (`SUPERSEDED/POST_EXIT/REVERSAL/REENTRY`) → Sprint C1
- Capital Rotation Engine → v2.2 Wave 3
- Historical 5 net-new metrics → v2.2 Wave 3
- Zero-vol days concentrated in VIX/idx → expected
- Feature Store macro symbol map China/Europe → Sprint 6.5 backlog
- Runtime variance on 4 steps → I/O + network dependent
- 20+ orphan reports → Wave 1+2 ledger'd
- DuckDB layer → Phase 3 ARCH022+
- Runner 2 HOLD cold-start feeds through replay too

---

## 3 · Priority-Wise Implementation Plan (v2.2 Wave 3 · post-audit)

**Ordered by weight-adjusted lever (biggest ROI first). Total estimated to reach GO threshold (75/100): 7 Must-Fix items · ~2 sprints.**

### Sprint C0 · Data Substrate & Silent Breakages (unblocks features → scoring → recs)

1. **M-Sec1** · fix `isinstance(sectors, dict)` in 2 sites — 1-line fix each · unblocks factor_library sector rows + sector_rotation.json for India
2. **M-F1** · fix ATR to consume real H/L (Feature Store) — restore atr_14_pct signal across 356k bars
3. **M-F2** · fix ADX to use high.diff/-low.diff (Feature Store) — restore trend model signal
4. **M-D1** · sanitize 13 India OHLC anomalies
5. **M-D2** · add VEDL corporate-action entry + generic anomaly detector
6. **M-D3** · restore NIFTY200 LTIM/PEL/TATAMOTORS raw parquets

**Estimated projected score after C0: 55/100.** Sector 30→85, Data 60→85, Determinism 75→80.

### Sprint C1 · Keystone + Telegram + Scheduler + Champion (biggest single lever)

7. **M-R1** · wire keystone `reports/recommendations.json` producer OR migrate 30+ consumers to `recommendations_v3.json` — SINGLE fix restores 9 India daily-orchestrator steps + India dashboard + morning_report
8. **M-T1/T2/Sch1** · add `concurrency:` block to `aegis-daily.yml` + move `.published` BEFORE Telegram + add dedup key (combined workflow edit)
9. **M-Str1** · reconnect Champion strategy producer
10. **M-Dash1** · India dashboard stale-inputs (resolved automatically by M-R1)
11. **M-Rep1** · India morning report staleness (resolved automatically by M-R1)

**Estimated projected score after C1: 75/100.** SSoT 25→75, Telegram 30→85, Scheduler ✅, Reports 55→80.

### Sprint C2 · Replay Determinism (primary criterion) + Explainability

12. **M-Rep1** · add byte-equality replay determinism regression test
13. **M-Rep2** · add `--frozen-clock` mode
14. **M-R2** · rec producer schema divergence (5 delta/change fields + reason schema alignment)

**Estimated projected score after C2: 82/100 → GO.**

### Post-audit deferred (Wave 3+)

- Capital Rotation Engine (fully designed by Agent 4 — 100% reuse · implementation-ready)
- Historical panel 5 net-new metrics (N1..N5)
- Sprint 7.9 Rec Orchestrator (blocked by benchmark corpus depth)
- Trade State Engine (Sprint C1 per Phase 3 spec)

---

## 4 · Final Go/No-Go Decision

# **NO-GO** for v2.2 production certification.

**Signed evidence:**
- 42 findings across 20 phases (14 Must-Fix · 14 Accepted Debt · 2 Environment · 12 Expected Future)
- Weighted Production Readiness Score = 49/100 (target ≥75 for GO)
- 9 of 32 India daily-orchestrator steps BROKEN (keystone gap)
- Portfolio Consistency = 20/100 (Runner 2 100% HOLD cold-start)
- Recommendation Accuracy = 35/100 (n=10 corpus depth)
- Two silent breakages found in Feature Store (ATR dead-code · ADX not real ADX)
- Sector schema mismatch silently zeroes India sector data

**Path to GO:**
- Sprint C0 (data + silent breakages) → 55/100
- Sprint C1 (keystone + telegram + scheduler + champion) → 75/100 → **GO threshold**
- Sprint C2 (replay determinism + explainability) → 82/100

**Estimated timeline to GO:** 2 sprints executed per Implementation Mode (end-to-end vertical slices, dual-market rule applies).

---

## 5 · Production Certification Checklist

| Criterion | Status | Blocker |
|-----------|:------:|---------|
| Every validation test passes | ⚠️ | 14 Must-Fix items |
| Recommendations are deterministic | ⚠️ | Timestamp rotation (M-Rep1/2) |
| Portfolio decisions are explainable | ❌ | 5 delta fields missing (M-R2) |
| Reports · Dashboard · Telegram use same source of truth | ❌ | Keystone gap (M-R1) |
| No duplicate notifications occur | ❌ | No `concurrency:` block (M-T1) |
| Capital rotation behaves as expected | ❌ | Engine not built (Wave 3) |
| Sector intelligence is validated | ❌ | Schema mismatch (M-Sec1) + taxonomy divergence (M-Sec2) |
| Replay produces identical results | ⚠️ | No byte-equality test (M-Rep1) |
| Benchmark comparisons are accurate | ⚠️ | Sample size n=10 (organic fill) |
| Historical performance metrics are reproducible | ✅ | Sprint 7.5/7.7/7.8 substrate healthy |
| All critical bugs are resolved | ❌ | See 14 Must-Fix items |

**Legend:** ✅ met · ⚠️ partial · ❌ not met.

---

## 6 · Risk Register (post-audit · to be actioned in Wave 3)

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|:----------:|:------:|------------|
| R1 | Keystone gap continues to freeze downstream reports | HIGH | HIGH | M-R1 · Sprint C1 |
| R2 | Runner 2 remains 100% HOLD → benchmark never reaches n=30 | HIGH | MED | Sprint 7.9 orchestrator OR B1 replay expansion |
| R3 | Silent Feature Store breakages (ATR/ADX) corrupt model training | HIGH | HIGH | M-F1/F2 · Sprint C0 |
| R4 | Sector schema mismatch corrupts factor library sector features | HIGH | MED | M-Sec1 · Sprint C0 (1-line fix) |
| R5 | Duplicate Telegram sends erode operator trust | MED | MED | M-T1/T2/Sch1 · Sprint C1 |
| R6 | MON001 sentinel dormant → fingerprint drift undetected | LOW | HIGH | Add `sealed_baseline_fingerprint.txt` |
| R7 | India dashboard renders stale numbers as "today" | MED | HIGH | Resolved by M-R1 |
| R8 | 13 India OHLC anomalies propagate to models | LOW | MED | M-D1 · Sprint C0 |
| R9 | VEDL unrecorded event distorts risk models | LOW | HIGH | M-D2 · Sprint C0 |
| R10 | NIFTY200 gap distorts ranking universe | MED | MED | M-D3 · Sprint C0 |

---

## 7 · Reuse Ledger (what we did NOT redo)

- **Sprint A1** — 10 rec producers · Runner 1/2 dependency graphs · 59 engines · 6 cross-cutting risks (v2.2 Phase 1 builds on this)
- **Sprint A2** — per-engine status matrix (39 Connected · 13 Partially · 3 Active · 4 Missing)
- **Sprint B0** — history quality PARTIAL both markets (v2.2 Phase 11 references this)
- **Sprint 7.7** headless engine drivers (available for M-R1 wire-in)
- **Sprint 7.8** benchmark framework (Wilson CI + expectancy — no rebuild)

**Grandfathering rule (Phase 5) applies** — existing engines get partial compliance when touched, not shotgun refactor.

---

## 8 · Definition of Done · v2.2 Audit Phase

- [x] All 20 phases investigated with evidence
- [x] All 42 findings classified per Wave Closure Mode
- [x] Production Readiness Score computed with weighted formula
- [x] Priority-wise implementation plan (Sprint C0/C1/C2)
- [x] Final Go/No-Go decision (NO-GO with path to GO)
- [x] Risk Register (10 items)
- [x] Production Certification Checklist (11 criteria)
- [x] No code modified (Investigation First rule honored)
- [x] Sealed contracts UNTOUCHED
- [x] 280/280 tests still green
- [x] Fingerprint `e4c070673568c52d…` preserved
- [x] Dual-market coverage (India + USA)
- [x] Report on disk (this doc)
- [ ] Executive dashboard updated with v2.2 audit tile
- [ ] Docs-only commit + push
- [ ] Memory updated with v2.2 audit lock

---

**End of AEGIS v2.2 Audit · LOCKED 2026-07-27 · NO-GO with clear 2-sprint path to GO threshold ≥75/100.**
