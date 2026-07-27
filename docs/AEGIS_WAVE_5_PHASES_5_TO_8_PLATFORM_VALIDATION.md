# AEGIS · Wave 5 · Phases 5-8 · Platform Validation (Data · Feature · Model · Recommendation)
### 🔒 SHIPPED 2026-07-27 · consolidated per-platform validation · synthesizes v2.2 audit findings + Wave 3 C0 fixes + Phase 1/2 evidence

**Purpose:** produce the four platform-specific validation reports (Wave 5 Phases 5-8) in one consolidated doc. Each phase's findings + verdict + remediation path from v2.2 audit are re-classified under Constitution articles.

---

## Phase 5 · Data Platform Validation

**Scope:** raw data · canonical layer · feature store inputs · corporate actions · fundamentals · macro · alt data · history · incremental · append-only · no look-ahead · no survivorship bias · no stale · no dup rows · no schema drift.

**Evidence base:** v2.2 audit Phase 1 (Data Quality) · Sprint B0 (History Quality) · Wave 3 C0 (silent breakages).

### 5.1 · Data Integrity Matrix

| Check | India | USA | Verdict |
|---|:---:|:---:|:---:|
| NaN in OHLC | ✅ 0/314,062 | ✅ 0/42,671 | PASS |
| Duplicate-date rows | ✅ 0 | ✅ 0 | PASS |
| Invalid OHLC (open<low) | ⚠️ 13 bars / 13 tickers | ✅ 0 | **FAIL India** |
| Zero-volume days | ⚠️ VIX/idx concentrated | ⚠️ VIX only | ACCEPTED (indices) |
| Corp-action anomalies | ⚠️ VEDL 2026-04-30 -64.9% unrecorded | ⚠️ VIX regime change | **FAIL India VEDL** |
| Delistings (>60d stale) | ✅ 0 | ✅ 0 | PASS |
| Universe integrity (NIFTY200) | ⚠️ LTIM/PEL/TATAMOTORS missing | ✅ 30/30 Dow | **FAIL India** |
| Schema uniformity | ⚠️ 227 MT5 + 2 volume-only | ✅ uniform | PARTIAL |
| Delivery format | ✅ parquet | ✅ parquet | PASS |
| Freshness | ⚠️ mixed (5 keystone stale 7-10d) | ✅ fresh 2026-07-24 | **PARTIAL** |
| Append-only compliance | ✅ Sprint 7.5 | ✅ | PASS |
| No look-ahead (prices) | ✅ walk-forward safe | ✅ | PASS |
| No look-ahead (fundamentals) | ❌ snapshot broadcast | ❌ | **FAIL** |
| No survivorship bias | ✅ universe append-only | ✅ | PASS |

**Verdict Phase 5: DEGRADED · 6 Must-Fix items · 3 already-scoped fixes.**

**Article-level compliance:**
- Article 76 (research/ not daily-wired): 12 modules still in daily · PARTIAL
- Article 91 (byte-equality before cutover): PASS (C0 preserved fingerprint)

### 5.2 · Data Quality Report (5 Must-Fix items)

| ID | Finding | Location | Fix Phase |
|:-:|:---|:---|:-:|
| M-D1 | 13 India OHLC anomalies (open<low) | data/raw/india/{13 tickers}.parquet | Wave 4 D2 · ingest validator |
| M-D2 | VEDL 2026-04-30 unrecorded corporate action | data/raw/india/corporate_actions.parquet | Wave 4 D2 · CA validator + entry |
| M-D3 | NIFTY200 gap: LTIM/PEL/TATAMOTORS missing | data/raw/india/ | Wave 4 D2 · universe refresh |
| M-D4 | 161 reports missing schema_fingerprint | reports/*.json | Wave 5 Phase 3+ decorator |
| M-D5 | Fundamentals look-ahead (snapshot broadcast) | backend/feature_store/features/fundamental.py | Wave 4 D2 · as-of aware fetcher |

---

## Phase 6 · Feature Platform Validation

**Scope:** every feature mathematically verified (RSI · MACD · ADX · ATR · EMA · SMA · Bollinger · momentum · drawdown · volatility · liquidity · returns · fundamental ratios · macro · sector · institutional · news · corp actions).

**Evidence base:** v2.2 audit Phase 2 (Feature Engineering) · Wave 3 C0 (ATR + ADX fixes) · Phase 1 duplicate-indicator inventory.

### 6.1 · Feature Correctness Matrix (post-C0)

| Feature | Impl | Correctness | Duplication | Status |
|---|---|:---:|:---:|:---:|
| RSI-14 | `backend/feature_store/features/technical.py:_rsi` | ⚠️ simple rolling (not Wilder EWM) | 5 sites | PARTIAL |
| MACD (12,26,9) | `..._macd` | ✅ EWM correct | ≥3 sites | PARTIAL (dup) |
| ATR-14 | `..._atr` (POST-C0) | ✅ **FIXED · consumes real H/L** | 6 sites | PARTIAL (dup) |
| ADX-14 | `..._adx` (POST-C0) | ✅ **FIXED · textbook Wilder** | 4 sites | PARTIAL (dup) |
| EMA | inline | ✅ | many | PARTIAL (dup) |
| SMA (20/50/200) | inline | ✅ | many | PARTIAL (dup) |
| Volatility (20d/60d) | inline | ⚠️ NOT annualised in FS | 3 sites | PARTIAL |
| Momentum returns | `_returns_pct` | ✅ | many | PARTIAL |
| Drawdown (60d) | inline | ✅ correct rolling max | 2 sites | PARTIAL |
| Rel Strength (Nifty) | `technical_factors.py` | ✅ | 1 | PASS |
| Rel Strength vs S&P | `usa/lib/technicals.py` | ✅ | 1 | PASS |
| Liquidity (5v20 ratio) | inline | ✅ | 1 | PASS |
| Beta (Nifty) | `feature_engine.py` | ✅ 120d rolling | 1 | PASS |
| Fundamental (ROE/D_E/PE/PB) | `fundamental.py` | ⚠️ look-ahead (snapshot) | 1 | **FAIL walk-forward** |
| Macro features (10Y/DXY/gold/WTI/VIX/MOVE) | `macro.py` | ✅ pass-through | 1 | PASS (US-centric map) |
| Sector features (per ticker) | `sector.py` | ✅ post-C0 (list-shape handled) | 1 | PASS |
| Earnings features | `earnings.py` | ✅ | 1 | PASS |
| Institutional (insider/FII/DII) | `institutional.py` | ⚠️ hardcoded windows | 1 | PARTIAL |
| Corporate actions features | `corporate_actions.py` | ✅ | 1 | PASS |
| News features | `news.py` | ✅ | 1 | PASS |

**Verdict Phase 6: PARTIAL · 15+ duplicate indicator sites (Article 30 FAIL) · fundamentals look-ahead · vol not annualised.**

### 6.2 · Feature Validation Report (7 Must-Fix)

| ID | Finding | Fix Phase |
|:-:|:---|:-:|
| F1 | ATR was dead code | ✅ **SHIPPED C0** (commit 6866f3b) |
| F2 | ADX not real Wilder | ✅ **SHIPPED C0** |
| F3 | 3 RSI implementations | Wave 4 D1 · shared indicator lib |
| F4 | 6 ATR implementations | Wave 4 D1 |
| F5 | 4 ADX implementations | Wave 4 D1 |
| F6 | Volatility not annualised in FS | Wave 4 D2 |
| F7 | Fundamentals broadcast look-ahead | Wave 4 D2 · as-of fetcher |

---

## Phase 7 · Model Platform Validation

**Scope:** 11 models · ensemble · calibration · confidence · ranking · scoring · training · inference · determinism · performance · explainability · model registry · feature importance · historical performance · cold start · drift · bias · overfitting · underfitting · champion · challenger · promotion · rollback.

**Evidence base:** v2.2 audit Phase 3 (Scoring) · Sprint 2.7 tests · Sprint 3 tests · Sprint 7.8 benchmark.

### 7.1 · Model-Level Matrix

| # | Model | Score Range | Confidence | Det | Tests | Notes |
|:-:|---|:---:|:---:|:---:|:---:|---|
| 3.1 | Momentum | [-1,+1] | [0,1] | ✅ | s27 | rank-univ dependent |
| 3.2 | Trend | [-1,+1] | [0,1] | ✅ | s27 | |
| 3.3 | Value | [-1,+1] | [0,1] | ✅ | s27 | inv-PE + inv-PB |
| 3.4 | Growth | [-1,+1] | [0,1] | ✅ | s27 | earnings_growth + ROE only |
| 3.5 | Quality | [-1,+1] | [0,1] | ✅ | s27 | |
| 3.6 | Mean Reversion | [-1,+1] | [0,1] | ✅ | s27 | |
| 3.7 | News | [-1,+1] | [0,1] | ✅ | s27 | ranks already-normalised |
| 3.8 | Macro | [-1,+1] | 0.8 hardcoded | ✅ | s27 | magic constant |
| 3.9 | Sector Rotation | [-1,+1]? | [0,1] | ✅ | s27 | weights sum 0.8 not 1.0 |
| 3.10 | Event-Driven | [-1,+1] | [0,1] | ✅ | s27 | |
| 3.11 | AI Hybrid | [-1,+1] | [0,1] | ✅ | s27 | conf-weighted mean |
| 3.12 | Ensemble | [-1,+1] | [0,1] | ✅ | s27 | clips negative weights silently |

### 7.2 · Scoring Inconsistency Findings (from v2.2 audit S1-S11)

**11 inconsistencies documented in v2.2 audit.** Wave 5 target:
- S1 · Confidence scales fragmented (4 conventions) → Wave 4 D3 unify
- S2 · Score scales fragmented ([-1,+1] vs [0,100]) → Wave 4 D3
- S3 · `score` column collision → Wave 4 D3
- S4 · **STRONG_BUY unreachable in stress** → Wave 4 D3 calibration fix
- S5 · Rank univ-dependency → Wave 4 D3 documented
- S6 · Ensemble silently clips negatives → Wave 4 D3 fix
- S7 · Classifier `_MATRIX` dead code → Wave 4 D3 remove
- S8 · Dual pipelines (backend/recommendation vs adaptive_rec_v2) → Wave 4 D4
- S9 · Regime string coupling (`sideways` unknown) → Wave 4 D3
- S10 · MacroModel.confidence magic 0.8 → Wave 4 D3
- S11 · Sector rotation weights ≠1.0 → Wave 4 D3

**Verdict Phase 7: PARTIAL · 11 inconsistencies · all scoped to Wave 4 D3.**

---

## Phase 8 · Recommendation Platform Validation

**Scope:** Recommendation Engine · Confidence · Explainability · Recommendation DNA · Conflict resolution · Calibration · Bull/Bear case · Risk analysis · Opportunity ranking · Portfolio suitability · Lifecycle · Traceability · SSoT · Historical consistency · Deterministic.

**Evidence base:** v2.2 audit Phase 4 (Recommendation) · Sprint 3 tests · Sprint 7.8 benchmark · Wave 4 D4 keystone plan.

### 8.1 · Rec Engine Producers (from Sprint A1)

10 producers exist. Wave 5 target: ONE canonical (Runner 2 v3) + sealed legacy wrappers.

| # | Producer | Owner | Status | Wave 5 Action |
|:-:|---|---|:---:|---|
| 1 | Runner 1 legacy (`india/recommendation_generator.py`) | 04_R/rec_engine_r1 | L | Wave 4 D4 · keystone-migration decision |
| 2 | Runner 1 v2 (`research/adaptive_rec_v2`) | SEALED | L | UNTOUCHED |
| 3 | Fusion (`research/fusion`) | 04_R/fusion | L | Wave 4 D4 promotion |
| 4 | Runner 2 v3 (`backend/recommendation`) | 04_R/rec_engine | A | **PRIMARY · SSoT candidate** |
| 5 | DEV023 (`research/recommendations/run.py`) | archive | D | Wave 4 D4 archive · producer of frozen `recommendations.json` |
| 6 | USA legacy v1 (`usa/research/recommendations`) | 04_R/rec_engine_usa | L | Wave 4 D4 |
| 7-10 | Additional entry-points (adaptive · knowledge · winner_genome) | mixed | mixed | Wave 4 D4 |

### 8.2 · Keystone SSoT Fix (M-R1 · Wave 4 D4)

**Root cause:** `reports/recommendations.json` (frozen 2026-07-17) required by 6+ orchestrator steps, produced by ZERO. Only producer is deprecated `research/recommendations/run.py`.

**Fix decision:**
- **Option A:** wire deprecated `research/recommendations/run.py` back into daily until Runner 2 v3 calibrates
- **Option B:** migrate 30+ consumers to `recommendations_v3.json`
- **Recommendation (Phase 8):** Option B · single migration effort in Wave 4 D4 · consumers updated · legacy producer archived

### 8.3 · Rec Producer Schema Divergence (M-R2)

**Every rec producer missing 5 delta fields:** `previous_rank` · `confidence_delta` · `sector_change` · `momentum_change` · `risk_change`. Wave 4 D4 introduces delta-engine at `backend/04_recommendation/explainability/delta_engine.py`.

**Reason field style varies:**
- Runner 1: freetext `"Why"` column
- Runner 2 v3: freetext `bull_case`/`bear_case` + list `key_risks`/`exit_conditions`
- Fusion: structured `why_this[]`/`why_not_stronger[]`/`dimensions[]`
- DEV023: tag-list `reasons_for[]`/`reasons_against[]`

**Wave 4 D4 target:** canonical structured schema with backwards-compat wrappers.

### 8.4 · Recommendation Lifecycle (Wave 4 D4 · Sprint C1)

Per operator spec + v2.2 audit Phase 8 finding · Sprint C1 spec exists (`docs/AEGIS_PHASE3_TRADE_STATE_ENGINE_SPEC.md`) but zero code:

`DISCOVERED · WATCHLIST · NEW BUY · ACTIVE · ADD · REDUCE · TRIM · PARTIAL EXIT · EXIT · ROTATED · ARCHIVED`

**Verdict Phase 8: DEGRADED · keystone SSoT unfixed · 5 delta fields missing · lifecycle unbuilt · Runner 2 100% HOLD.**

### 8.5 · Rec Accuracy Benchmark (Sprint 7.8)

- Runner 1: n=10 · Wilson 95% CI `[23.66%, 76.34%]` · mean +0.0838% · win 50% · PF 1.0353 · max DD -17.44% · verdict `DIRECTIONAL_ONLY`
- Runner 2: n=0 · verdict `INSUFFICIENT_DATA`
- Comparison: `CANNOT_COMPARE_INSUFFICIENT_DATA` (need ≥30 closed each)

**Path to `STATISTICALLY_MEANINGFUL`:** corpus depth n ≥ 30 per runner · achieved either by Sprint 7.9 orchestrator kicking Runner 2 out of HOLD or by full-window replay expansion (B1 to `2025-01-01 → today`).

---

## Consolidated Phase 5-8 Verdict

| Platform | Compliance | Blockers |
|---|:---:|---|
| Phase 5 · Data | **DEGRADED** | 6 Must-Fix (13 OHLC · VEDL · NIFTY200 gap · schemas · staleness · fundamentals look-ahead) |
| Phase 6 · Feature | **PARTIAL** | 15+ dup sites (Article 30) · fundamentals look-ahead · vol not annualised |
| Phase 7 · Model | **PARTIAL** | 11 scoring inconsistencies (all scoped Wave 4 D3) |
| Phase 8 · Recommendation | **DEGRADED** | Keystone SSoT · 5 delta fields · lifecycle unbuilt · Runner 2 100% HOLD |

**Combined: NO-GO across all four platforms.** All Must-Fix items are scoped to Wave 4 D1..D4 with concrete fixes. Wave 5 · Phase 9+ continues execution.

**End of Wave 5 · Phases 5-8 · SHIPPED 2026-07-27.**
