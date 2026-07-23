# AEGIS · Sprint 7.8 · Recommendation Benchmark Report
### 13-Section Validation Report

**Sprint status:** ✅ MODULE SHIPPED · framework complete, initial dataset intentionally small
**Date:** 2026-07-21
**Engine ID:** `aegis.benchmark.v1`
**Version:** 1.0.0
**Placement:** Inserted between Sprint 7.7 (Full Historical Replay) and any Recommendation Orchestrator work, per operator directive of 2026-07-21.

---

## 1 · Rationale (why this sprint had to come before any orchestrator)

Prior work landed a Runner 1 walk-forward with 10 closed trades and a "PASS" verdict. The operator correctly pushed back:

> Ten closed trades over a 4-week window is directionally interesting but NOT statistically conclusive. Winners aren't sufficiently outweighing losers. Win rate alone is misleading. Build a proper benchmark before comparing runners.

Sprint 7.8 delivers exactly that — a comprehensive metric panel with **explicit statistical-significance gates** so a small-sample "PASS" can never masquerade as institutional evidence.

---

## 2 · Modules Delivered

| # | Module | Purpose |
|---|---|---|
| 1 | `backend/benchmark/__init__.py` | Public API |
| 2 | `backend/benchmark/statistical_significance.py` | Wilson score CI for proportions · normal-approx CI for means · sample-size verdict bands |
| 3 | `backend/benchmark/report.py` | Full metric panel + `build_comparison()` for side-by-side runners |
| 4 | `backend/tests/test_sprint78.py` | 17 tests (all green) |

---

## 3 · Metric Panel (per operator's exact list)

Overall + segmented (by action, sector, confidence bucket, macro regime):

- **Core returns:** total · mean · median · stdev · 95% CI on mean
- **Win/loss decomposition:** win rate + Wilson 95% CI · avg_win · avg_loss · largest_win · largest_loss
- **Institutional edge metrics:** profit factor · expectancy per trade · reward/risk ratio
- **Risk / drawdown:** Sharpe (annualised) · Sortino · Calmar · max drawdown · max consecutive losses/wins
- **Behavioural:** avg holding period
- **Segment-specific:**
  - `by_action` — STRONG_BUY vs BUY vs SELL vs STRONG_SELL
  - `by_sector` — per-sector slice with own metrics + CIs
  - `by_confidence_bucket` — ≤0.50 · 0.50-0.60 · 0.60-0.70 · 0.70-0.80 · 0.80-0.90 · 0.90-1.00
  - `by_regime` — bull / bear / neutral / RISK_ON / RISK_OFF / etc.
- **STRONG_BUY vs BUY discrimination test** — mean-return edge · win-rate edge · verdict gated on n≥30

---

## 4 · Statistical Discipline (the core design decision)

Every quantitative claim carries its uncertainty:

- **Win rate → Wilson score 95% CI** (robust for small n; naive p̂ ± 1.96·σ collapses to `[0.5, 0.5]` at n=10, which is a lie)
- **Mean return → normal-approx 95% CI** (with sample-size caveat flagged separately)
- **Sample-size verdict bands:**
  - `INSUFFICIENT_DATA` (n < 5) — cannot draw any conclusion
  - `DIRECTIONAL_ONLY` (5 ≤ n < 30) — pattern suggestive but not statistically proven
  - `STATISTICALLY_MEANINGFUL` (30 ≤ n < 100)
  - `INSTITUTIONAL_GRADE` (n ≥ 100)
- **Verdicts are structural, never "good/bad"** — the operator interprets, the module measures.
- **`build_comparison()` refuses to name a winner** unless both runners have ≥30 closed positions — matches operator directive verbatim.

---

## 5 · Live Runtime Output — Runner 1 · India · 2026-07-21

**Overall (10 closed positions)**

| Metric | Value | 95% CI | Verdict |
|---|---:|---:|---|
| Sample size | 10 | | **DIRECTIONAL_ONLY** — pattern suggestive but not statistically proven |
| Mean return | **+0.08%** | **[-3.70%, +3.87%]** | CI straddles zero — cannot conclude positive edge |
| Win rate | **50.0%** | **[23.66%, 76.34%]** | CI straddles "terrible" and "great" |
| Expectancy/trade | +0.08% | | |
| Profit factor | 1.04 | | Barely positive |
| Reward/risk ratio | 1.04 | | Winners barely outweigh losers |
| Avg winner | +4.91% | | |
| Avg loser | -4.74% | | |
| Max drawdown | -17.4% | | |
| Max consecutive losses | 3 | | |

**STRONG_BUY vs BUY**

| | STRONG_BUY | BUY | Edge |
|---|---:|---:|---:|
| n | 6 | 4 | |
| Mean return | +0.85% | -1.07% | **+1.92%** |
| Win rate | 66.67% | 25.00% | **+41.67 pp** |
| **Verdict** | | | **DIRECTIONAL_ONLY** (smallest group = 4 trades) |

The **direction** is striking — STRONG_BUY massively outperforms BUY on both mean-return and win-rate — but with only 4 BUY trades the module correctly refuses to confirm it. Institutional discipline.

**Comparison Runner 1 vs Runner 2**

```
verdict: CANNOT_COMPARE_INSUFFICIENT_DATA
reason:  Runner 1: 10 closed · Runner 2: 0 closed · need >= 30 each to compare
```

---

## 6 · What This Sprint Deliberately Does NOT Do

- **Does not name a winner** between Runner 1 and Runner 2 — sample too small.
- **Does not build an orchestrator** — the operator explicitly asked me to wait for benchmark evidence first.
- **Does not extend the Runner 1 audit trail** to 2025-01-01 — the CSV `data/aegis_recommendation_db.csv` is only 4 weeks deep, and reconstructing older Runner 1 output would require refactoring the legacy `india/recommendation_generator.py`, which violates the "legacy engines untouched" invariant.
- **Does not backfill Runner 2's actionable calls** — Runner 2 (Rec Engine v3) emitted 100% HOLD across all 203 Sprint 7.7 replay dates due to the cold-start calibration issue. That's a Rec-engine issue, not a benchmark issue.

---

## 7 · Contracts Enforced

| Contract | Status |
|---|---|
| Free-stack only (pandas + numpy) | ✅ |
| Read-only over history parquets (never mutates corpus) | ✅ |
| Deterministic (same input corpus → same report) | ✅ |
| Every metric carries sample size + verdict | ✅ tested |
| No "good/bad" claims — only structural verdicts | ✅ |
| Comparison refuses to name a winner below n=30 each | ✅ tested |
| No new AI agents · no new recommendation engines | ✅ |
| Legacy engines untouched | ✅ |
| Sealed OPS001/MON001 files untouched | ✅ |
| Fingerprint b65ceb49a83a preserved | ✅ |

---

## 8 · Regression Suite

```
======================================================================
  SPRINT 7.8 · Recommendation Benchmark Report · Regression Tests
======================================================================
  [OK] wilson CI is WIDE for small n
  [OK] wilson CI tightens as n grows
  [OK] wilson CI handles n=0 safely
  [OK] mean CI is wide for small n
  [OK] sample-size verdict bands (INSUFF/DIR/STAT/INST)
  [OK] confidence buckets partition 0.5-1.0 correctly
  [OK] consecutive streaks: basic W/L walk
  [OK] consecutive streaks: empty series safe
  [OK] metrics on empty slice → INSUFFICIENT_DATA
  [OK] metrics compute win rate + CI + expectancy + R/R
  [OK] metrics compute max drawdown honoring order
  [OK] STRONG_BUY vs BUY = DIRECTIONAL_ONLY when small
  [OK] STRONG_BUY vs BUY produces outcome verdict when large
  [OK] build_report: no corpus → empty + caveat
  [OK] build_report: writes JSON + INSUFFICIENT_DATA caveat
  [OK] build_report: segments by action/sector/conf-bucket/regime
  [OK] comparison refuses verdict when either runner < 30 closed

  17 passed, 0 failed of 17
```

No regression on Sprint 7.6 (19/19), Sprint 7.7 (14/14), Sprint 7.7 Runner 1 (11/11).

---

## 9 · Integration

| Integration point | Change |
|---|---|
| `.github/workflows/aegis-ci.yml` | Sprint 7.7 Runner 1 + Sprint 7.8 tests wired |
| `reports/benchmark_runner1_india.json` | Real Runner 1 benchmark on 10 trades |
| `reports/benchmark_compare.json` | Verdict: `CANNOT_COMPARE_INSUFFICIENT_DATA` — honest |
| `docs/AEGIS_SPRINT78_REPORT.md` | This report |
| `reports/EXECUTIVE_DASHBOARD.md` | Refreshed with 7.8 status + real numbers |

---

## 10 · Cumulative Test Health

```
Sprint 1..6.5 + 7 + 7.5 + 7.6      224/224   ✅
Sprint 7.7 (replay + WF + guard)    14/14    ✅
Sprint 7.7 Runner 1 (legacy audit)  11/11    ✅
Sprint 7.8 (benchmark report)       17/17    ✅  ← NEW
Telegram HTTP 400 fallback          10/10    ✅
─────────────────────────────────────────────────
TOTAL                              276/276   ✅
```

---

## 11 · Known Limits (honest scoping — matches operator's "10 trades ≠ conclusion" mandate)

- **Runner 1 corpus depth = 10 closed trades.** All headline metrics are DIRECTIONAL_ONLY.
- **Runner 2 corpus depth = 0 closed trades** (rec engine emits 100% HOLD due to cold-start calibration).
- **Confidence-bucket analysis** works but every bucket is sub-5 samples on Runner 1's ledger → the segmented view will only produce meaningful signal once the ledger grows.
- **Per-macro-regime slices** exist but are noise-level on 10 trades.

---

## 12 · NEXT — What Actually Unblocks Institutional Comparison

Two paths, both mechanical:

1. **Grow Runner 1's audit trail organically** — the daily pipeline continues appending to `data/aegis_recommendation_db.csv`. Re-run the ingest weekly. Reaches STATISTICALLY_MEANINGFUL (n≥30) in roughly 6-8 more weeks at current rate (~12 closed trades / 4 weeks).

2. **Fix Runner 2's cold-start calibration** so it actually emits BUY/SELL calls that can close on horizons — enables Runner 2 to accumulate a corpus too. This is a Rec-engine change (Sprint 3), not a benchmark change.

**Only when both runners cross n=30 closed positions each** should the Recommendation Orchestrator (deferred Sprint 7.9) start weighting them.

---

## 13 · NEXT BOTTLENECK

**Corpus depth** for both runners. The framework is now complete — win-rate CIs, expectancy, R/R, profit factor, drawdowns, streaks, per-sector, per-regime, per-confidence-bucket, STRONG_BUY vs BUY discrimination — all measured. What's missing is **data**, and data grows one trading day at a time.

Every daily run now enriches the corpus automatically (Sprint 7.5 wired the histories · Sprint 7.7 wired the outcome computation · Sprint 7.8 wired the metric panel). Institutional comparison arrives when the ledger crosses 30 closed positions per runner.

---

**End of Sprint 7.8 · Recommendation Benchmark Report**
