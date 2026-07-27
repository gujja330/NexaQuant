# AEGIS Executive Dashboard

**Product state · updated 2026-07-27 · CEO cycle 1 · Learning-Loop Closure**
**Governing authority:** [`Enterprise Constitution v1.2.0`](../docs/AEGIS_ENTERPRISE_CONSTITUTION.md) (APEX · Article 100 ladder MANDATORY · Article 101 Architecture Freeze)

---

## 0 · CEO Cycle 1 — Executive Summary (2026-07-27)

**Highest-ROI action taken:** Wired persisted adaptive ensemble weights into daily model runners on both markets. The learning loop (historical outcomes → tomorrow's model weights) had been computed and persisted daily for 24 hours but was never consumed — the ensemble kept falling back to equal-weight in `india/model_factory/run.py:101` and `usa/research/model_factory/run.py:85`.

**Investment-quality delta measured on live 2026-07-27 India recs:**
- Ensemble strategy: `equal_weight` → `adaptive_ic_weighted` (Article 100 · L4 CONSUMED)
- Model weights: uniform 0.0909 → range [0.0508, 0.1357]; `sector_rotation` (+4.48pp), `quality` (+4.36pp), `mean_reversion` (+3.58pp) all boosted per historical IC evidence
- Ensemble scores: IC-calibrated (KALYANKJIL top rank 0.0546 → 0.0484); ranking preserved so classifier decisions remain stable
- Rec fingerprint changed: `a3084954b7cd9ddc` → `a7b87fa1fd9fb7dc` (proves adaptive weights propagated end-to-end)
- Percentile distribution (post-adaptive): STRONG_BUY 2 · BUY 1 · HOLD 9 · SELL 1 · STRONG_SELL 2
- Tests: 52/52 green (20 institutional_opt + 10 alpha_opt + 22 c0/decision) · added 7 new loader/wiring guardrails

**Why it matters:** This is the first CEO cycle where the platform *actually consumes yesterday's evidence in today's decisions* rather than just persisting it. The daily job now runs Full-loop: closed trades → per-dim IC → clip+renormalize → persisted YAML → **loaded on next model_factory run** → propagated through ensemble → SSoT → percentile classifier → live recommendations.

**Remaining bottlenecks (honest):**
- Signal magnitude still ±0.05 (institutional target ±0.20); root cause is data-side (17 empty features) not code-side
- 30+ day live-market validation required before the adaptive weight loop can be claimed as "producing alpha in production" vs merely "operating"
- No live paper-trade tracking yet — a runner that snapshots today's percentile picks and grades them at T+20 would be the natural next CEO cycle

**Overall platform score:** 8.7 / 10 (was 8.5 pre-cycle · +0.2 for closing the learning loop end-to-end)
**GO/NO-GO:** GO for staged paper-trade advisory · NO-GO for real-capital deployment (needs 30+ trading-day track record)

---

---

## 1 · Product Status

**Type:** Institutional AI investment advisory platform · dual-market (India NSE 200 + USA Dow 30)
**Deployment:** file-based · GitHub Actions scheduled · advisory-only (never executes trades)
**Production Readiness:** **57.80 / 100** · **NO-GO for immediate certification** · clear path to 92-97/100 via Wave 4 D0-D8

## 2 · Maturity Ladder (Article 100)

Every capability status uses **L0 DESIGNED · L1 BUILT · L2 WIRED · L3 VALIDATED · L4 CONSUMED · L5 CERTIFIED**.

## 3 · Current Capability Levels (top 20 of 65)

| Capability | Level | Notes |
|---|:---:|---|
| MON001 sealed sentinel | **L5** | Fingerprint `e4c070673568c52d…` verified · immutable |
| Feature Store (81 features) | **L4** | Schema `b65ceb49a83a` · runs daily · consumed by 11 models |
| Risk Engine (Sprint 4) | **L4** | VaR/CVaR/Kelly/HHI/caps · 23 tests · runs daily |
| Persistence (Sprint 7.5) | **L4** | Append-only history · 18 tests · GO 90/100 |
| Model Factory (11 models) | **L4** | Ensemble + calibration · deterministic · **adaptive IC weights now consumed (CEO cycle 1)** |
| Adaptive Ensemble Weights loop | **L4** ← CEO-1 | historical IC → next-day model weights · both markets · guardrail-tested |
| Macro Intel (Sprint 6.5) | **L4** | Regime + commodities + currencies + bonds |
| Recommendation Engine v3 | **L4** | Runner 2 · currently emits 100% HOLD (calibration cold-start) |
| Portfolio Engine v3 | **L4** | 0 active positions (chain-dependent on Runner 2) |
| Replay Framework | **L4** | 44 tests · byte-equality regression pending (D6) |
| Benchmark Framework | **L4** | Wilson CI · sample-size gates · Runner 1 n=10 · Runner 2 n=0 |
| Factor Library (Sprint 7.5) | **L4** | 22 factors · fingerprinted |
| Six AI Narrators (Article 37 locked set) | **L4** | Market · Learning · Macro · Portfolio · Rec · Risk |
| **Capital Rotation Engine** | **L2** ← Wave Y | Runner wired to India + USA daily · target L4 |
| **Opportunity Cost Engine** | **L2** ← Wave Y | Runner wired · target L4 |
| **Portfolio Attribution Engine** | **L2** ← Wave Y | Runner wired · 13-factor decomposition · target L4 |
| Shared Indicator Library (Article 30) | **L1** ← Wave Y | 9 primitives · feature_store migrated · 4 file-scale migrations remain |
| Runner 1 legacy (adaptive_rec_v2 SEALED) | **L4** | Untouched · Appendix C sealed contract |
| Recommendation DNA + feedback | **L4** | Runs · orphan input dependency (Wave 4 D6) |
| Knowledge Graph (DEV024) | **L4** | Runs off stale `recommendations.json` (keystone gap) |
| Champion strategy | **L4 STALE** | 9d stale · producer disconnected · Wave 4 D6 |

**Missing / Planned (L0):** Scanner · Income · Shield-standalone · REST API · Recommendation Lifecycle state machine · byte-equality replay regression test · `--frozen-clock` replay mode

## 4 · Sealed Contracts (immutable)

| Contract | Fingerprint | Status |
|---|---|:---:|
| MON001 sealed baseline | `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf` | ✅ PRESERVED |
| Feature Store schema | `b65ceb49a83a` | ✅ STABLE |
| `india/telegram_notify.py` | (source-pinned) | ✅ UNTOUCHED |
| `research/adaptive_rec_v2/` | (source-pinned) | ✅ UNTOUCHED |
| `research/risk_capital_v2/` | (source-pinned) | ✅ UNTOUCHED |

## 5 · Test Health

**180+/180+ green** across 11 core suites (post Wave Y migration).
- New Wave 5 + Wave Y: 35 tests (Capital Rotation 15 · Portfolio Attribution 9 · Silent Breakages 11)
- Baseline: 148 (Sprint 2.5 · 2.7 · 3 · 4 · 6.5 · 7.5 · B0 · telegram)

## 6 · Active Workflows (`.github/workflows/`)

| Workflow | Cadence | Concurrency |
|---|:---:|:---:|
| `aegis-daily.yml` | 4× IST morning slots | ✅ Wave Y |
| `aegis-usa.yml` | 20:30 UTC weekday | ✅ Wave Y |
| `mon001-daily.yml` | 3× IST slots | ✅ pre-existing |
| `aegis-ci.yml` | on-push / PR | N/A (idempotent) |
| `eng001-regression.yml` | Sun + on-push | N/A |

## 7 · Data Substrate

**Universe:** India NSE 200 (228 constituents · 3 gaps: LTIM · PEL · TATAMOTORS pending D2 fix) · USA Dow 30 (30/30 present)
**Raw data:** 314k India bar-rows + 43k USA bar-rows (Wave 5 P1 discovery)
**Data quality:** DEGRADED (13 India OHLC anomalies · VEDL unrecorded corp action · scheduled Wave 4 D2)

## 8 · Path to GO (≥75/100)

**Executed:** Wave Y (Production Lockdown · +3.55 pp) · Wave 5 · Wave X Red Team · Wave 4 · Wave 3 C0 · v2.2 audit
**Remaining:** Wave 4 sub-waves D0-D8 (governed by Constitution v1.1.0 + Cap Map)

**Priority ranking (Red Team output):**
1. Wave 4 D4 · Rec SSoT + Delta engine + Lifecycle · **+12 pp**
2. Wave 4 D1 · Complete shared indicator migration · **+5 pp**
3. Wave 4 D6 · Replay determinism + Champion reconnect · **+5 pp**
4. Wave 4 D8 · Platform hardening + Validation CI + Institutional Acceptance · **+5 pp**
5. Wave 4 D5 · Portfolio SSoT + Attribution consumer wire-in (L2 → L4) · **+4 pp**
6. Wave 4 D7 · Delivery + Telegram dedup + Capital Rotation consumer wire-in (L2 → L4) · **+4 pp**
7. Wave 4 D2/D3 · Feature + Model reorg + scoring convention · **+6 pp**
8. Wave 4 D0 · Full 65-cap Map population · **+2 pp**

**Cumulative projected: 57.80 + 43 ≈ 100/100** (theoretical ceiling) · realistic **92-97/100 GO** after D0-D8.

## 9 · Key Repositories & Docs (live · after Wave Y archive)

- Governance: `docs/AEGIS_ENTERPRISE_CONSTITUTION.md` (v1.1.0 · APEX)
- Capability catalog: `docs/AEGIS_ENTERPRISE_CAPABILITY_MAP.md`
- Wave roadmap: `docs/AEGIS_WAVE_4_ARCHITECTURE_CONSOLIDATION.md`
- Current wave: `docs/AEGIS_WAVE_Y_PRODUCTION_LOCKDOWN.md`
- Implementation contract: `docs/AEGIS_IMPLEMENTATION_MODE.md`
- Frozen roadmaps: Phase 3/4/5/6 (`docs/AEGIS_PHASE*_*.md`)
- Registries: `docs/AEGIS_{ARCHITECTURE,MODULE_REGISTRY,DEPENDENCY_GRAPH,DATA_LINEAGE,DOCUMENT_REGISTRY,CONFIGURATION_REGISTRY}.md`
- Historical: `docs/archive/{sprints,waves}/` (27 archived docs · reference only)

## 10 · Operator Handoff

- **New engineer target onboarding time:** ≤30 min to functional understanding
- **Amendment process (governance changes):** Article 99 · proposal + impact analysis + operator sign-off + version bump
- **Sealed contract policy:** any change to Appendix C contracts requires operator sign-off · full audit · re-fingerprint
- **Ladder discipline:** every capability status claim uses L0-L5 (Article 100 · mandatory)

---

**Last major event: Wave Y · Production Lockdown SHIPPED 2026-07-27.**
