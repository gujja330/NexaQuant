# MR v1 · CLOSE-OUT · Sprint M-R Research Phase

**Date:** 2026-08-27
**Governance:** [MR_V1_LOCK.md](MR_V1_LOCK.md) · [PRODUCTION_LOCK.md](../../PRODUCTION_LOCK.md)
**Status:** Foundation LOCKED · 3 focused shadow experiments ACTIVE · zero production changes.

---

## Executive summary (one page)

**Where we are, in three sentences:**

1. The measurement/research layer is complete and locked. 26 pipeline stages, 220 tests passing, `ALLOWED_WRITE_ROOT = reports/research` invariant enforced, and the delivery layer remains at the `3c4fa815` production baseline.
2. The month of historical AEGIS predictions produced real, statistically defensible signals · India R1 is weak, R2 rank_4_7 is the only positive cohort, stop-policy alternatives beat CURRENT, and a technical filter combining RSI + MA20 has significant WR spreads.
3. Nothing is production-safe today · 3 focused shadow experiments are ACTIVE_SHADOW and must accumulate N ≥ 100 forward observations before any promotion is considered.

**What was done at close-out:**

- Reduced 5 registered experiments → **3 focused ones** (per CEO ask)
- 5 old experiments marked `SUPERSEDED_BY` (4) or `ARCHIVED_LOW_PRIORITY` (1) · nothing deleted
- Added **X3 technical-filter rule** (RSI + MA20 evidence-backed edges)
- Ran the **fundamentals coverage gap check** · found India = 100%, USA = 0% (real gap · closure plan attached)
- All shadow rules fired against today's snapshot · **zero production side effects**

---

## The 3 focused shadow experiments · ACTIVE_SHADOW

| # | Experiment | Metric | Min N | Acceptance |
|---|---|---|---:|---|
| **X1** | India R1/R2 ranking (compound: confidence + top-3 slot filter) | shadow_5D_WR | 100 | WR ≥ prod + 5pp AND avg > prod + 0.3% |
| **X2** | India TIME_STOP_5D advisory (loss-control) | expectancy_gap_vs_current | 100 | Median advisory return + 0.3% AND cat-loss rate ≤ current |
| **X3** | Technical filter (RSI + MA20 evidence-backed) | positive_5D_WR − negative_5D_WR | 100 | ≥ 15pp WR spread between POSITIVE and NEGATIVE tags |

Each experiment's JSON at `reports/research/experiments/aegis_mr_experiment_20260827_x{1,2,3}_*.json` carries hypothesis · null_hypothesis · rejection_criteria · shadow_wire_up · safety_gate · promotion_gate · risk.

### Today's fires (day-0 shadow evidence)

| Experiment | n_rows | n_fired | Sample fire |
|---|---:|---:|---|
| X1 · R1/R2 ranking | 19 | 0 | Blocked by canonical schema (no rank/confidence) · resolves once schema extended |
| **X2 · TIME_STOP_5D** | 19 | **15** | BEL(23d), KOTAKBANK(23d), PERSISTENT(22d) all past 5-session hold |
| **X3 · Technical filter** | 19 | **9** | POSITIVE/NEGATIVE tags computed live from parquet-derived RSI + MA20 |

### 5 old experiments · reclassified

| Old | New status | Superseded by |
|---|---|---|
| india_confidence_anti_signal | SUPERSEDED_BY | X1 |
| india_top3_rank_inversion | SUPERSEDED_BY | X1 |
| india_negative_alpha | SUPERSEDED_BY | X1 |
| india_stop_policy | SUPERSEDED_BY | X2 |
| india_band_boundary | ARCHIVED_LOW_PRIORITY | — |

Old experiments continue to run their shadow rules for evidence continuity · marking them SUPERSEDED does NOT delete their shadow output.

---

## Fundamentals coverage gap

Explicitly measured today by [mr_fundamentals_gap_check.py](../../backend/research/mr_fundamentals_gap_check.py). See [FUNDAMENTALS_GAP_PLAN.md](FUNDAMENTALS_GAP_PLAN.md) for the full closure plan.

| Market | Fund parquet tickers | Universe | Daily-pred | **Coverage of daily preds** |
|---|---:|---:|---:|---:|
| **INDIA** | 228 | 230 | 41 | **100.00%** |
| **USA** | **0** | 908 | 498 | **0.00%** |

**India fundamentals are actually complete** for the daily prediction set (100% coverage · was misreported earlier). The gap is:

- **USA fundamentals parquet is empty (0 tickers).** All 498 USA daily-pred tickers are uncovered. Closure requires a yfinance batch pull for the S&P 500 universe under the same 8-column schema (`returnOnEquity`, `profitMargins`, `earningsGrowth`, `debtToEquity`, `trailingPE`, `priceToBook`, `next_earnings`, `quality_score`).
- USA fundamentals studies remain BLOCKED until coverage ≥ 95%.

Per-column India non-null coverage is 86-98% · adequate for ROE / PE / quality bucket studies going forward.

---

## Momentum · in daily measurement (per CEO ask)

- Day-0 corpus started 2026-08-27 · **India n=3 · USA n=106**
- Daily daemon `python -m backend.research.mr_walkforward_daemon --market both` appends today's Momentum picks under `reports/research/walkforward/{date}/momentum_{market}.jsonl`
- **No Momentum integration into production** · corpus accumulates until N ≥ 20 trading days · then first Momentum forward-validation study can run
- Momentum stays 🆕 new in the Daily Control Panel until then

---

## Decision table (unchanged · from earlier)

| Area | Improvement found? | Safe to integrate today? |
|---|---|---|
| R1 | YES · per-market weighting | **NO** |
| R2 | YES · rank_4_7 India positive cohort | **NO** |
| Momentum | UNKNOWN · data gap · corpus building | **NO** |
| Sectors | YES · India sector filter candidate | **NO** |
| Market cap | YES · USA MID tilt | **NO** |
| Technicals | YES · RSI + MA20 filters (now X3) | **NO** |
| Fundamentals | India covered · USA blocked by data gap | **NO** |
| Stop-loss | YES · TIME_STOP_5D (India) / TRAILING_10 (USA) | **NO** |
| AI research | Governance role · never auto-promotes | **NO by design** |

**0 of 9 safe to integrate today. This is the correct answer.**

---

## What runs daily

```bash
python -m backend.research.mr_v1_pipeline --market both      # 26 stages
```

Runs in this order:
1. Ingest history + join to forward outcomes (stages 1-15)
2. Automated walk-forward daemon captures canonical + Momentum (stage 16)
3. Conditional cohorts + master reports + dashboards (stages 17-22)
4. **Experiment consolidator flips statuses if needed** (stage 23)
5. **Shadow experiment runner fires 3 focused + 5 archived rules** (stage 24)
6. **Fundamentals gap check** (stage 25)
7. Daily control panel refresh (stage 26)

Idempotent · re-runs on the same day update the same files in place.

---

## Path from today to first possible production change

```
day 0  · today · all experiments ACTIVE_SHADOW · 0/100 forward evidence
   ↓
day 1-19 · daily daemon accumulates walk-forward evidence · panel shows accumulating
   ↓
day 20+ · first fwd_5d observations mature · panel transitions 🔬 → ⏳
   ↓
N ≥ 100 · walk-forward acceptance check runs · X1/X2/X3 either PASS or FAIL
   ↓
if PASS · CEO reviews experiment result + explicit override phrase
   ↓
new SPRINT_ID branch · config-toggle OFF by default · paper-trading 30 sessions
   ↓
production promotion under new SPRINT_ID · L4 evidence
```

**Minimum time-to-first-integration:** ~50 trading days from today. That's not a bug · that's the design.

---

## Compliance verbatim

- **Locked delivery layer** (R1 · R2 · Registry · xlsx_contract · xlsx_validator · canonical INVESTMENT_ACTIVE JSON · ensemble_weights_adaptive.yaml · model_registry.jsonl · scripts/telegram_command_center_send.py): **UNTOUCHED**
- **Locked MR v1 measurement layer**: **UNTOUCHED** since 92fbb16c commit
- **Old aegis_history.xlsx**: preserved as historical evidence · never deleted or overwritten
- **26/26** pipeline stages green
- **220/220** tests pass
- **3** focused experiments · ACTIVE_SHADOW · never auto-promoted
- **5** old experiments · SUPERSEDED / ARCHIVED · shadow output continues for continuity
- **0** production changes, 0 pushed since 92fbb16c, 0 committed in this close-out session
- **7-step promotion gate** applies to every candidate
- **Unlock phrase** required: `override the mr v1 lock` (research) · `override the production lock` (delivery)

---

## What NOT to do next

- Do NOT add more experiments (we consolidated to 3 for a reason)
- Do NOT modify production R1/R2/Registry/XLSX
- Do NOT delete the 5 old experiments' shadow output (evidence continuity)
- Do NOT auto-promote any candidate
- Do NOT delete `aegis_history.xlsx`
- Do NOT run speculative patches until the 3 experiments have accumulated forward evidence

## What TO do next

- Run the daemon daily (or wire into existing CI)
- After ~20 trading days, review the transition of the 3 experiments in the Daily Control Panel
- Fill the USA fundamentals coverage gap in parallel (data-side · yfinance batch pull)
- When N ≥ 100 forward per experiment, run acceptance evaluation
- Only then discuss promotion of the survivor(s)

---

## Files added / modified in this close-out

```
backend/research/
  mr_experiment_runner.py                  UPDATED · +3 X-rules, 8 total experiments wired
  mr_experiment_consolidator.py            NEW · 5→3 consolidation logic
  mr_fundamentals_gap_check.py             NEW · coverage measurement + closure plan
  mr_v1_pipeline.py                        UPDATED · 26 stages

tests/research/
  test_mr_x_rules.py                       NEW · 11 tests for X1/X2/X3 rules
  test_mr_experiment_runner.py             UPDATED · count check

reports/research/
  MR_V1_CLOSE_OUT.md                       NEW · this file
  FUNDAMENTALS_GAP_PLAN.md                 NEW · closure plan
  experiments/INDEX.json                   UPDATED · 8 total (3 ACTIVE, 4 SUPERSEDED, 1 ARCHIVED)
  experiments/aegis_mr_experiment_20260827_x1_india_r1_r2_ranking.json     NEW
  experiments/aegis_mr_experiment_20260827_x2_stop_loss_time_5d.json       NEW
  experiments/aegis_mr_experiment_20260827_x3_technical_filter.json        NEW
  experiments/aegis_mr_experiment_20260827_x1_india_r1_r2_ranking/2026-08-27/shadow.jsonl  NEW
  experiments/aegis_mr_experiment_20260827_x2_stop_loss_time_5d/2026-08-27/shadow.jsonl    NEW
  experiments/aegis_mr_experiment_20260827_x3_technical_filter/2026-08-27/shadow.jsonl     NEW
  mr_fundamentals_gap_india.json           NEW
  mr_fundamentals_gap_usa.json             NEW
```

**Not pushed. Awaiting your call.**
