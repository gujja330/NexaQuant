# AEGIS · M-R1 Forward Validation · First Evidence Report

**Experiment:** M-R.v0.1 · Sprint M Research Runner (sandbox, measurement-only)
**Generated:** 2026-08-27
**Scope:** Every daily prediction in `aegis_history.xlsx` AEGIS Daily sheet · **NOT** current-portfolio survivors.
**Population:** India n=551 · USA n=1088 predictions.
**Locked layers untouched:** R1, R2, Registry, XLSX contract, Canonical INVESTMENT_ACTIVE.

---

## Reading key

- `WR` = 5-day forward win rate (return > +0.5%)
- `avg` = mean forward-5d percent change
- `CI` = Wilson-95 confidence interval on WR
- `conf` = average AEGIS-reported confidence score at prediction time
- Winner = fwd_5d > +0.5% · Loser = fwd_5d < -0.5% · Neutral = between

Statistical discipline: any bucket with n < 20 is OBSERVATION-ONLY. n < 100 is INSUFFICIENT_EVIDENCE. n ≥ 100 is PRODUCTION_CANDIDATE evidence (per M-R contract).

---

## 🚨 India Headline · Predictions net-lose across all horizons

| Horizon | n | WR % | avg % | median % |
|---|---:|---:|---:|---:|
| fwd_1d | 500 | 21.60 | -0.14 | -0.04 |
| fwd_3d | 444 | 22.97 | -0.46 | -0.64 |
| fwd_5d | 392 | 25.77 | -0.73 | -1.19 |
| fwd_10d | 223 | 27.80 | -1.53 | -1.97 |

- avg_MFE = **+1.16%** · avg_MAE = **-2.20%** · stop_hit_rate_20d = **17.19%**
- Median NEGATIVE at every horizon.
- This 30-day window is dominated by a market drawdown context · absolute WR must be read together with a market-benchmark cohort (**follow-up task**).

## 🚨 Finding 1 · India R1 Top-3 mechanism identified

The Ranker Autopsy exposes what fills the top-3 slot:

| Bucket | n | WR % | CI | avg % | avg conf | Band mix |
|---|---:|---:|---:|---:|---:|---|
| **R1 · top3** | **82** | **14.52** | 7.83 – 25.34 | **-1.18** | **83.13** | **QUALITY 57% · OK 40% · AVOID 2%** |
| R1 · rank_4_7 | 122 | 26.19 | 17.98 – 36.49 | -0.74 | 69.25 | AVOID 49% · MARGINAL 20% · QUALITY 16% · OK 14% |
| R1 · rank_8_15 | 110 | 20.00 | 12.51 – 30.41 | -1.10 | 66.58 | MARGINAL 88% · AVOID 12% |
| **R2 · top3** | 59 | 21.28 | 11.99 – 34.90 | -0.54 | 42.45 | **OK 59% · QUALITY 27% · MARGINAL 12% · AVOID 2%** |
| **R2 · rank_4_7** | **56** | **47.37** | 32.48 – 62.74 | **+0.53** | 36.75 | **MARGINAL 66% · QUALITY 30% · OK 4%** |
| R2 · rank_8_15 | 122 | 31.40 | 22.56 – 41.82 | -0.74 | 33.63 | MARGINAL 48% · OK 26% · AVOID 26% |

### What this proves

1. **`R2 · rank_4_7`** is the ONLY India cohort with a positive average · **+0.53%, 47% WR**. This is where India's real edge lives · MARGINAL/QUALITY blend with a rank-4-through-7 filter.
2. **`R1 · top3`** is failing on high-confidence QUALITY(57%) + OK(40%) picks. When R1 says "high confidence + top rank", it loses 85% of the time. The very tokens that should predict success are anti-correlated with outcome.
3. **`R2 · top3`** is 59% OK-band. OK band by itself only has 17.4% WR (below AVOID). R2's top-3 selection over-weights the worst-performing investability band.

## 🚨 Finding 2 · India confidence is INVERTED

| Cohort | avg confidence |
|---|---:|
| Winners (fwd_5d > +0.5%) | **51.4%** |
| Losers (fwd_5d < -0.5%) | **57.94%** |
| **Delta (winners − losers)** | **-6.54%** |

Losers arrive with HIGHER confidence than winners. The confidence score is not merely uninformative · it is **anti-correlated** with outcome by 6.5 points across n=101 winners vs n=247 losers.

## 🚨 Finding 3 · India band boundary defect · OK worse than AVOID

| Band | n | WR % | avg % | avg conf | Where they sit by rank |
|---|---:|---:|---:|---:|---|
| **QUALITY** | 100 | **34.29** | **+0.36** | 66.69 | top3=63 · 4_7=37 · 8_15=0 |
| MARGINAL | 224 | 29.94 | -0.80 | 51.54 | top3=7 · 4_7=62 · 8_15=155 |
| AVOID | 108 | 19.18 | -0.88 | 57.11 | top3=3 · 4_7=60 · 8_15=45 |
| **OK** | **119** | **17.39** | **-1.31** | 57.75 | **top3=68** · 4_7=19 · 8_15=32 |

**QUALITY works · then MARGINAL · then AVOID · with OK dead last.** The OK-band population is 57% top-3 · so its poor performance is entangled with the R1 top-3 defect. Untangling requires:

- Band-only cohort at fixed rank (need larger n via time)
- Confidence-only cohort at fixed rank

## Finding 4 · R1 vs R2 flips between markets

| Runner | India n | India 5D WR | India 5D avg | USA n | USA 5D WR | USA 5D avg |
|---|---:|---:|---:|---:|---:|---:|
| R1 | 314 | 20.81% | -0.98% | 80 | 54.55% | +0.18% |
| R2 | 237 | 32.16% | -0.40% | 1008 | 40.88% | -0.37% |

**India: R2 wins. USA: R1 wins.** We have been treating R1/R2 as market-agnostic · they behave oppositely. Any future rebalance of ensemble weights must be per-market.

## Finding 5 · USA Top-3 rank IS a genuine edge

| Bucket | n | 5D WR | 5D avg |
|---|---:|---:|---:|
| USA R1 · top3 | 24 | **100.00%** | +2.19% |
| USA R2 · top3 | 21 | **100.00%** | +1.11% |
| USA R1 · rank_4_7 | 32 | 55.56% | +0.26% |
| USA R2 · rank_4_7 | 11 | 33.33% | -2.53% |
| USA R1 · rank_8_15 | 24 | 0.00% | -2.55% |

USA ranker is **monotone in the right direction**. Small n on top-3 (n=45 combined) means CI is wide but the direction is unambiguous. India ranker is broken. USA ranker is not.

Caveat: 94% of USA rows fall in `PENDING` band because the USA investability shadow file is under-populated. Band signal on USA cannot be read from this run · **follow-up task**.

---

## What must NOT happen next

Per M-R contract + `PRODUCTION_LOCK.md`:

- **No** modification to R1 / R2 / Registry / XLSX contract / Canonical JSON.
- **No** ensemble weight change.
- **No** confidence-score rebuild.
- **No** ranker replacement.
- **No** production feature-flag flip.

The evidence is 30 days old. WR is not yet market-benchmark normalized. Winner cohorts are n<250. Every production candidate rule needs walk-forward validation on FRESH days.

## What should happen next · in order of value

### Immediate (this week · sandbox only)

1. **Enrich autopsy rows with historical features** at prediction time · sector · market cap · RSI · MA-distance · volatility · momentum score · fundamentals. Currently we only have runner, rank, confidence, band, sector, entry price, stop. Need the full genome.

2. **India R1 top-3 deep dive** · pick 20 losing top-3 predictions and reconstruct why R1 ranked them 1-3. Which features drove the top-3 slot vs the rank_4-7 slot on that same day?

3. **Band boundary study at fixed rank** · isolate whether OK-band is bad universally or only because it clusters at top-3.

4. **USA investability shadow gap** · fix the shadow file so we can read USA bands properly.

5. **Market-benchmark cohort** · compare India predictions vs NIFTY over same 5D window · is the -0.73% avg an alpha problem or a beta problem?

### Follow-up (next 2 weeks · sandbox only)

6. **Stop-loss policy sweep** · replay historical predictions under {current, 5%, 7.5%, 10%, ATR-based, sector/regime-adaptive} · compare win rate, avg winner, avg loser, profit factor, expectancy, max DD, premature-stop rate, catastrophic-loss rate, MFE captured.

7. **Sector × Cap × Runner × Regime matrix** for both markets.

8. **Momentum dedicated cohort** · reconstruct every Momentum recommendation and evaluate WATCH vs EMERGING vs SKIP forward returns · currently blocked by absence of historical Momentum snapshots. May need a walk-forward capture starting today.

9. **Opportunity discovery** · for each historical day, list top-N ex-post 10-day winners AEGIS did NOT recommend. Diagnose the filter that excluded them.

### Only after items 1-9 · production-candidate rules

10. Any proposed change to R1/R2/ranker/ensemble/confidence goes through:
    - Research Ticket with hypothesis + expected effect size
    - Walk-forward test on N ≥ 100 forward predictions
    - Full regression pass
    - CEO approval
    - Config-toggle OFF by default
    - Paper trading period
    - Then production

---

## Files emitted

- [reports/research/mr_prediction_autopsy_india.jsonl](reports/research/mr_prediction_autopsy_india.jsonl) · one row per prediction
- [reports/research/mr_prediction_autopsy_india_summary.json](reports/research/mr_prediction_autopsy_india_summary.json)
- [reports/research/mr_prediction_autopsy_usa.jsonl](reports/research/mr_prediction_autopsy_usa.jsonl)
- [reports/research/mr_prediction_autopsy_usa_summary.json](reports/research/mr_prediction_autopsy_usa_summary.json)
- [reports/research/mr_winner_loser_genome_india.json](reports/research/mr_winner_loser_genome_india.json)
- [reports/research/mr_winner_loser_genome_usa.json](reports/research/mr_winner_loser_genome_usa.json)

## Engines

- [backend/research/mr_prediction_autopsy.py](backend/research/mr_prediction_autopsy.py) · `aegis.mr_prediction_autopsy.v0.1`
- [backend/research/mr_winner_loser_genome.py](backend/research/mr_winner_loser_genome.py) · `aegis.mr_winner_loser_genome.v0.1`
- [backend/research/mr_runner.py](backend/research/mr_runner.py) · sandbox host · `M-R.v0.1`

## Reproducibility

```bash
PYTHONIOENCODING=utf-8 python -m backend.research.mr_prediction_autopsy --market both
PYTHONIOENCODING=utf-8 python -m backend.research.mr_winner_loser_genome --market both
```

No production side effects. Reads locked canonical inputs · writes only to `reports/research/`.
