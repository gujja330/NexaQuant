# MR v1 · Experiments FROZEN · CEO Final

**Locked date:** 2026-08-27
**Locked by:** CEO explicit directive · "Lock the research baseline now and stop changing it."
**Sentinel:** `MR_V1_EXPERIMENTS_FROZEN.v1.0`

---

## The 3 focused experiments · FROZEN

**Do not reshuffle. Do not rename. Do not add a 4th.** The next event that touches this set is the promotion-gate acceptance evaluation after N ≥ 100 forward observations, or an explicit rejection.

### E1 · India R1 filter

- **experiment_id:** `aegis_mr_experiment_20260827_e1_india_r1_filter`
- **Market:** INDIA
- **Rule:** For India R1 rows, reject when either
  - top-3 slot AND `ma20_dist` outside +1..+5 (14.5% WR historical cohort), OR
  - confidence 70-85 anti-signal band (13.16% WR historical cohort)
- **Historical evidence:** 82 top3 + 103 anti-signal band = 185 R1 rows out of 314
- **Acceptance:** filtered R1 5D WR ≥ production R1 + 5pp on **n ≥ 100 forward**
- **Rejection:** filtered R1 5D WR < production R1 − 3pp

### E2 · India R2 rank_4_7 + RSI STRONG positive-boost

- **experiment_id:** `aegis_mr_experiment_20260827_e2_india_r2_rank_4_7_boost`
- **Market:** INDIA
- **Rule:** For India R2 rows with rank in [4,7] AND RSI in [55,70), tag `BOOST_R2_STRONG`
- **Historical evidence:** conditional 3-way `R2 · rank_4_7 · rsi=STRONG` → **72.73% 5D WR (n=22, +46.96pp edge, Wilson-95 significant)**
- **Acceptance:** boost cohort 5D WR ≥ 55% on **n ≥ 100 forward** AND avg > 0.5%
- **Rejection:** boost cohort 5D WR < 40% (regime overfit)

### E3 · Stop-loss cross-market

- **experiment_id:** `aegis_mr_experiment_20260827_e3_stop_loss_cross_market`
- **Market:** CROSS_MARKET (India + USA · fires on both snapshots)
- **Rule (INDIA):** TIME_STOP_5D advisory when position aged ≥ 5 sessions
- **Rule (USA):** TRAILING_10 armed advisory (walk-forward scorer computes retrospective trailing outcome)
- **Historical evidence:** India TIME_STOP_5D expectancy +0.273% + 0.00% catastrophic on n=500 · USA TRAILING_10 expectancy +0.921% PF 1.309 on n=625
- **Acceptance (INDIA):** advisory median return ≥ CURRENT median + 0.3% AND cat-loss ≤ CURRENT on **n ≥ 100** advisory events
- **Acceptance (USA):** advisory net of TRAILING_10 exit ≥ CURRENT + 0.5% expectancy on **n ≥ 100**
- **Rejection:** MFE-captured drops by more than 0.5% vs CURRENT

---

## Retired · not in the focused set

| Old ID | Status | Reason |
|---|---|---|
| aegis_mr_experiment_20260827_x1_india_r1_r2_ranking | SUPERSEDED_BY E1 | E1 is a cleaner narrower filter |
| aegis_mr_experiment_20260827_x2_stop_loss_time_5d | SUPERSEDED_BY E3 | E3 folds India + USA together |
| aegis_mr_experiment_20260827_x3_usa_mid_cap_tilt | ARCHIVED_FOR_LATER | not in CEO's top 3 · shadow output continues for continuity |
| aegis_mr_experiment_20260827_x3_technical_filter | ARCHIVED_FOR_LATER | not in CEO's top 3 |
| aegis_mr_experiment_20260827_india_confidence_anti_signal | SUPERSEDED_BY E1 | folded into E1 |
| aegis_mr_experiment_20260827_india_top3_rank_inversion | SUPERSEDED_BY E1 | folded into E1 |
| aegis_mr_experiment_20260827_india_negative_alpha | SUPERSEDED_BY E1 | folded into E1 |
| aegis_mr_experiment_20260827_india_stop_policy | SUPERSEDED_BY E3 | folded into E3 |
| aegis_mr_experiment_20260827_india_band_boundary | ARCHIVED_LOW_PRIORITY | no successor · not in CEO's top 3 |

**Retired experiments continue to fire their shadow rules for evidence continuity.** They just don't count as focused walk-forward candidates. Nothing is deleted.

---

## What CANNOT change without CEO explicit override

- The 3 experiment IDs above
- Their rules
- Their acceptance / rejection criteria
- Their N ≥ 100 sample requirement
- Any field of any existing experiment JSON marked `ceo_final_status: FROZEN in MR_V1_EXPERIMENTS_FROZEN.md`

Override phrase (verbatim required): **`override the mr v1 experiments frozen lock`**

Any other phrasing does NOT unlock. This is separate from the MR_V1_LOCK and PRODUCTION_LOCK unlock phrases.

---

## What CAN change without an unlock phrase

- Adding daily walk-forward data to existing experiments (that's the whole point)
- Fixing bugs in a rule's implementation (bug fixes preserve behavior)
- Recording new attempts / days_of_evidence counters
- Reading the shadow output for analysis
- Producing daily reports and dashboards from the accumulated data

---

## Parallel work · outside the frozen set

- **Momentum daily capture** · continues via daemon · not being evaluated yet
- **Fundamentals coverage** · USA parquet needs a yfinance batch pull to reach ≥ 95% (India already 100%)

Both are DATA-side work · they do not touch this frozen experiment set.

---

## Path from today to first promotion decision

```
day 0    (today · 2026-08-27) · E1/E2/E3 ACTIVE_SHADOW · 0/100 forward each
   ↓
day 20+  · first fwd_5d observations mature · scorer labels WIN/LOSS + MFE/MAE + stop_hit
   ↓
~ day 40 · N ≥ 100 forward per experiment (rough estimate · depends on daily rec-count)
   ↓
acceptance evaluation runs · each of E1/E2/E3 either PASSES or FAILS acceptance
   ↓
if PASS · CEO reviews · new SPRINT_ID branch built · paper trade 30 sessions
   ↓
if paper-trade PASSES · production promotion under new SPRINT_ID with L4 evidence
```

**Minimum time-to-first-integration:** ~ 70 trading days from today. That's the design.

---

## Compliance verbatim

- Delivery layer: LOCKED (PRODUCTION_LOCK.md)
- Research foundation: LOCKED (MR_V1_LOCK.md)
- Experiment set: LOCKED (this file)
- Momentum & Fundamentals: parallel data-side work · not touching this set
- Zero production changes at freeze time
- 226/226 tests pass
- No push has occurred since the 92fbb16c research-foundation commit
