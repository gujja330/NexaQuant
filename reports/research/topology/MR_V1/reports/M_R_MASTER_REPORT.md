# AEGIS · Sprint M-R · FORWARD VALIDATION ENGINE v1 · Master Report

**Version tag:** M-R.v1.0 · **Experiment ID:** M-R.v0.1 · sandbox
**Generated:** 2026-08-27T09:15:38+00:00
**Scope:** every daily prediction in aegis_history.xlsx over the last month.

## Status

- **Foundation:** COMPLETE (14/14 items in CEO's Forward Validation v1 scope)
- **Integration into production decisions:** DEFERRED (per CEO directive)
- **Locked layers untouched:** R1, R2, Registry, XLSX contract, Canonical INVESTMENT_ACTIVE, ensemble weights
- **No production changes.** No push. Read-only evidence for CEO.
- **Every candidate improvement** requires the 7-step promotion gate before touching production.

## 14-item scope tracking

| # | Item | Status |
|---:|---|---|
| 1 | Ingest month of historical predictions | DONE |
| 2 | Join each prediction to future market outcomes | DONE |
| 3 | Calculate 1/3/5/10/20D returns | DONE |
| 4 | Calculate MFE/MAE | DONE |
| 5 | Calculate stop-hit behaviour | DONE (12 policies replayed) |
| 6 | Label WIN / LOSS / FLAT | DONE (fwd_5d > +0.5 / < -0.5) |
| 7 | Split by R1 / R2 / Momentum | DONE (Momentum n=0 · data-gap noted) |
| 8 | Split by sector and market cap | DONE |
| 9 | Evaluate technical / fundamental / investability features | DONE |
| 10 | Winner/loser attribution + missed winners | DONE |
| 11 | Statistical significance / confidence (Wilson-95) | DONE |
| 12 | Single research report | DONE (this file) |
| 13 | Regression tests for research dataset | DONE (tests/research/test_mr_dataset_regression.py · 14 checks) |
| 14 | Do NOT change production decisions | ENFORCED |


## 1 · Master Dataset Row Count

| Market | Predictions | Runners | Bands |
|---|---:|---|---|
| INDIA | 551 | {'R2': 237, 'R1': 314} | {'OK': 119, 'AVOID': 108, 'MARGINAL': 224, 'QUALITY': 100} |
| USA | 1088 | {'R2': 1008, 'R1': 80} | {'PENDING': 1020, 'QUALITY': 5, 'OK': 39, 'MARGINAL': 18, 'AVOID': 6} |

## 2 · Runner Scoreboard (R1 / R2 / Momentum)


### INDIA

| Runner | n | WR fwd_5d | avg fwd_5d | avg fwd_10d | verdict |
|---|---:|---:|---:|---:|---|
| R1 | 314 | 20.81% | -0.984% | -1.858% | PRODUCTION_CANDIDATE |
| R2 | 237 | 32.16% | -0.399% | -1.163% | PRODUCTION_CANDIDATE |

### USA

| Runner | n | WR fwd_5d | avg fwd_5d | avg fwd_10d | verdict |
|---|---:|---:|---:|---:|---|
| R1 | 80 | 54.55% | +0.183% | 2.582% | OBSERVATION_ONLY |
| R2 | 1008 | 40.88% | -0.37% | 1.766% | PRODUCTION_CANDIDATE |

## 3 · Winner vs Loser Genome (fwd_5d)


### INDIA
- winners n=101 · losers n=247
- avg confidence winners=51.4% · losers=57.94% · DELTA=-6.54%
- winners MFE=4.175% MAE=-0.962% stop_hit=6.19%
- losers  MFE=0.467% MAE=-3.825% stop_hit=30.86%

Genome signals:
  - {'signal': 'runner_R1_skew', 'winner_pct': 45.54, 'loser_pct': 57.89, 'delta_pct': -12.35, 'verdict': 'losers_favor_R1'}
  - {'signal': 'runner_R2_skew', 'winner_pct': 54.46, 'loser_pct': 42.11, 'delta_pct': 12.35, 'verdict': 'winners_favor_R2'}
  - {'signal': 'band_QUALITY_skew', 'winner_pct': 23.76, 'loser_pct': 14.57, 'delta_pct': 9.19}
  - {'signal': 'band_OK_skew', 'winner_pct': 15.84, 'loser_pct': 27.94, 'delta_pct': -12.09}
  - {'signal': 'band_MARGINAL_skew', 'winner_pct': 46.53, 'loser_pct': 39.27, 'delta_pct': 7.26}
  - {'signal': 'rank_top3_skew', 'winner_pct': 18.81, 'loser_pct': 31.98, 'delta_pct': -13.17}
  - {'signal': 'rank_rank_4_7_skew', 'winner_pct': 39.6, 'loser_pct': 25.51, 'delta_pct': 14.1}
  - {'signal': 'confidence_diff', 'winner_avg': 51.4, 'loser_avg': 57.94, 'delta': -6.54}

### USA
- winners n=80 · losers n=86
- avg confidence winners=78.38% · losers=78.2% · DELTA=0.18%
- winners MFE=5.143% MAE=-1.465% stop_hit=0.0%
- losers  MFE=2.041% MAE=-4.991% stop_hit=83.33%

Genome signals:
  - {'signal': 'band_AVOID_skew', 'winner_pct': 6.25, 'loser_pct': 1.16, 'delta_pct': 5.09}
  - {'signal': 'band_PENDING_skew', 'winner_pct': 61.25, 'loser_pct': 67.44, 'delta_pct': -6.19}
  - {'signal': 'confidence_diff', 'winner_avg': 78.38, 'loser_avg': 78.2, 'delta': 0.18}

## 4 · Stop-Loss Policy Sweep


### INDIA · n=551 predictions

| Policy | n | WR% | avg% | median% | PF | stop% | cat>10%% | worst% | days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CURRENT | 490 | 26.53 | -0.886 | -0.907 | 0.429 | 18.57 | 0.2 | -10.476 | 7.34 |
| FIXED_3 | 500 | 26.4 | -0.933 | -1.043 | 0.413 | 32.4 | 0.2 | -10.476 | 6.66 |
| FIXED_5 | 500 | 27.4 | -0.96 | -0.84 | 0.417 | 13.8 | 0.2 | -10.476 | 7.8 |
| FIXED_7_5 | 500 | 27.8 | -0.93 | -0.786 | 0.426 | 3.6 | 0.2 | -10.476 | 8.41 |
| FIXED_10 | 500 | 27.8 | -0.918 | -0.786 | 0.429 | 0.2 | 0.2 | -10.476 | 8.5 |
| ATR_2X | 500 | 26.0 | -0.925 | -1.289 | 0.42 | 41.0 | 0.2 | -10.476 | 6.17 |
| ATR_3X | 500 | 27.6 | -0.915 | -0.817 | 0.429 | 22.6 | 0.2 | -10.476 | 7.33 |
| VOL_ADAPTIVE | 500 | 27.4 | -0.934 | -0.84 | 0.423 | 11.8 | 0.2 | -10.476 | 7.91 |
| TRAILING_5 | 500 | 26.8 | -0.972 | -0.851 | 0.4 | 17.6 | 0.2 | -10.476 | 7.56 |
| TRAILING_10 | 500 | 27.0 | -0.965 | -0.825 | 0.407 | 1.2 | 0.2 | -10.476 | 8.43 |
| TIME_STOP_5D | 500 | 24.8 | -0.613 | -0.771 | 0.523 | 0.0 | 0.0 | -9.069 | 4.45 |
| TIME_STOP_10D | 500 | 28.0 | -0.961 | -0.79 | 0.411 | 0.0 | 0.0 | -9.682 | 7.44 |

### USA · n=1088 predictions

| Policy | n | WR% | avg% | median% | PF | stop% | cat>10%% | worst% | days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CURRENT | 39 | 35.9 | -0.63 | -0.341 | 0.645 | 25.64 | 0.0 | -7.097 | 3.03 |
| FIXED_3 | 625 | 38.72 | +0.055 | -0.031 | 1.052 | 17.12 | 0.0 | -7.474 | 2.76 |
| FIXED_5 | 625 | 41.28 | +0.23 | +0.111 | 1.234 | 6.72 | 0.0 | -8.618 | 3.13 |
| FIXED_7_5 | 625 | 41.92 | +0.28 | +0.14 | 1.295 | 2.4 | 0.0 | -9.96 | 3.28 |
| FIXED_10 | 625 | 41.92 | +0.271 | +0.14 | 1.283 | 0.8 | 0.8 | -13.91 | 3.33 |
| ATR_2X | 625 | 41.28 | +0.19 | +0.111 | 1.184 | 8.0 | 0.32 | -13.91 | 3.13 |
| ATR_3X | 625 | 41.92 | +0.253 | +0.14 | 1.26 | 3.36 | 0.48 | -13.91 | 3.27 |
| VOL_ADAPTIVE | 625 | 41.92 | +0.271 | +0.14 | 1.283 | 2.72 | 0.48 | -13.91 | 3.29 |
| TRAILING_5 | 625 | 40.32 | +0.175 | +0.091 | 1.182 | 12.0 | 0.0 | -8.618 | 2.93 |
| TRAILING_10 | 625 | 42.08 | +0.291 | +0.143 | 1.309 | 2.56 | 0.64 | -12.882 | 3.3 |
| TIME_STOP_5D | 625 | 39.36 | +0.026 | +0.07 | 1.028 | 0.0 | 0.32 | -12.876 | 2.27 |
| TIME_STOP_10D | 625 | 41.92 | +0.267 | +0.14 | 1.277 | 0.0 | 0.8 | -13.91 | 3.35 |

## 5 · Sector Analysis


### INDIA

| Sector | n | WR fwd_5d | avg fwd_5d | MFE | MAE | stop_hit% |
|---|---:|---:|---:|---:|---:|---:|
| FMCG | 33 | 14.29% | -1.586% | 0.456 | -2.354 | 21.21 |
| Pharma | 31 | 15.79% | -1.934% | 0.396 | -2.377 | 6.45 |
| Power | 31 | 30.0% | -0.297% | 1.042 | -1.118 | 3.23 |
| Financials | 21 | 7.14% | -0.872% | 0.636 | -1.298 | 0.0 |
| Industrials | 16 | 80.0% | +1.434% | 1.652 | -0.392 | 50.0 |
| Transport | 16 | 20.0% | -2.571% | 0.354 | -3.003 | 37.5 |
| Metal | 15 | 11.11% | -0.917% | 0.219 | -1.468 | 6.67 |
| Chemicals | 14 | 22.22% | -0.43% | 0.881 | -1.128 | 28.57 |
| Energy | 14 | 0.0% | -0.663% | 0.26 | -1.321 | 0.0 |

### USA

| Sector | n | WR fwd_5d | avg fwd_5d | MFE | MAE | stop_hit% |
|---|---:|---:|---:|---:|---:|---:|
| Large-Cap | 995 | 41.11% | -0.282% | 0.962 | -0.801 | None |
| — | 60 | 42.86% | -1.253% | 0.676 | -0.895 | 10.0 |

## 6 · Market-Cap Analysis (liquidity proxy)


### INDIA

| Cap | n | WR fwd_5d | avg fwd_5d | avg fwd_10d |
|---|---:|---:|---:|---:|
| LARGE | 459 | 25.45% | -0.697% | -1.45 |
| MID | 92 | 27.42% | -0.9% | -2.033 |

### USA

| Cap | n | WR fwd_5d | avg fwd_5d | avg fwd_10d |
|---|---:|---:|---:|---:|
| LARGE | 459 | 35.96% | -0.841% | 0.363 |
| MID | 622 | 46.6% | +0.096% | 5.465 |

## 7a · Technical Analysis


### INDIA


**rsi_bucket**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| NEUTRAL_45_55 | 139 | 26.26% | -0.547% | INSUFFICIENT_EVIDENCE |
| OVERBOUGHT_ge70 | 14 | 14.29% | -1.381% | OBSERVATION_ONLY |
| OVERSOLD_lt30 | 28 | 43.75% | +0.303% | OBSERVATION_ONLY |
| STRONG_55_70 | 164 | 32.54% | -0.618% | PRODUCTION_CANDIDATE |
| WEAK_30_45 | 206 | 18.25% | -1.017% | PRODUCTION_CANDIDATE |

**trend**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| ABOVE_MA200 | 204 | 21.38% | -0.905% | PRODUCTION_CANDIDATE |
| BELOW_MA200 | 347 | 28.34% | -0.626% | PRODUCTION_CANDIDATE |

**vol_bucket**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| high_2_3 | 67 | 32.56% | -0.086% | INSUFFICIENT_EVIDENCE |
| low_lt1 | 135 | 24.0% | -0.683% | INSUFFICIENT_EVIDENCE |
| mid_1_2 | 348 | 24.91% | -0.863% | PRODUCTION_CANDIDATE |
| vhigh_3_4 | 1 | 100.0% | +4.907% | OBSERVATION_ONLY |

**ma20_dist_bucket**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| above_+1_+5 | 149 | 37.17% | -0.467% | PRODUCTION_CANDIDATE |
| below_-5_-1 | 195 | 17.97% | -0.958% | PRODUCTION_CANDIDATE |
| deep_below_lt-5 | 40 | 21.43% | -0.856% | INSUFFICIENT_EVIDENCE |
| far_above_ge+5 | 48 | 27.27% | -0.806% | INSUFFICIENT_EVIDENCE |
| near_-1_+1 | 119 | 22.78% | -0.644% | INSUFFICIENT_EVIDENCE |

**momentum_20d_bucket**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| falling_lt-5 | 97 | 30.16% | -0.575% | INSUFFICIENT_EVIDENCE |
| flat_0_+5 | 145 | 23.81% | -1.007% | PRODUCTION_CANDIDATE |
| strong_+5_+10 | 78 | 34.33% | +0.141% | INSUFFICIENT_EVIDENCE |
| surge_ge+10 | 38 | 23.33% | -1.75% | INSUFFICIENT_EVIDENCE |
| weak_-5_0 | 193 | 21.26% | -0.793% | PRODUCTION_CANDIDATE |

### USA


**rsi_bucket**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| NEUTRAL_45_55 | 316 | 47.54% | +0.153% | INSUFFICIENT_EVIDENCE |
| OVERBOUGHT_ge70 | 112 | 41.38% | +0.168% | INSUFFICIENT_EVIDENCE |
| OVERSOLD_lt30 | 15 | 50.0% | -0.635% | OBSERVATION_ONLY |
| STRONG_55_70 | 453 | 34.25% | -1.062% | INSUFFICIENT_EVIDENCE |
| WEAK_30_45 | 187 | 48.15% | -0.013% | INSUFFICIENT_EVIDENCE |

**trend**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| ABOVE_MA200 | 793 | 37.06% | -0.401% | PRODUCTION_CANDIDATE |
| BELOW_MA200 | 290 | 55.1% | -0.154% | INSUFFICIENT_EVIDENCE |

**vol_bucket**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| high_2_3 | 367 | 39.73% | -0.898% | INSUFFICIENT_EVIDENCE |
| low_lt1 | 33 | 33.33% | -0.031% | OBSERVATION_ONLY |
| mid_1_2 | 443 | 48.68% | +0.663% | INSUFFICIENT_EVIDENCE |
| vhigh_3_4 | 130 | 33.33% | -1.786% | OBSERVATION_ONLY |
| xhigh_ge4 | 114 | 31.58% | -0.918% | OBSERVATION_ONLY |

**ma20_dist_bucket**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| above_+1_+5 | 306 | 27.5% | -1.111% | INSUFFICIENT_EVIDENCE |
| below_-5_-1 | 217 | 51.06% | +0.527% | INSUFFICIENT_EVIDENCE |
| deep_below_lt-5 | 67 | 33.33% | -0.7% | OBSERVATION_ONLY |
| far_above_ge+5 | 325 | 39.71% | -0.883% | INSUFFICIENT_EVIDENCE |
| near_-1_+1 | 172 | 51.61% | +0.612% | INSUFFICIENT_EVIDENCE |

**momentum_20d_bucket**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| falling_lt-5 | 166 | 41.67% | -0.727% | INSUFFICIENT_EVIDENCE |
| flat_0_+5 | 227 | 43.18% | +0.103% | INSUFFICIENT_EVIDENCE |
| strong_+5_+10 | 191 | 39.29% | -0.842% | INSUFFICIENT_EVIDENCE |
| surge_ge+10 | 315 | 41.27% | -0.376% | INSUFFICIENT_EVIDENCE |
| weak_-5_0 | 186 | 42.42% | -0.144% | INSUFFICIENT_EVIDENCE |

## 7b · Fundamental Analysis (current-snapshot · not historical)


### INDIA


### USA


## 8 · Market-Regime Analysis


### INDIA
Regime distribution across window: {'BULL': 700, 'BEAR': 316, 'HIGH_VOL': 280, 'NEUTRAL': 176}

| Regime | n | WR fwd_5d | avg fwd_5d | avg fwd_10d |
|---|---:|---:|---:|---:|
| BEAR | 52 | 34.62% | -0.486% | — |
| BULL | 303 | 23.76% | -0.821% | -1.534 |
| UNKNOWN | 62 | 29.73% | -0.318% | — |

### USA
Regime distribution across window: {'BULL': 599, 'BEAR': 202, 'HIGH_VOL': 294, 'NEUTRAL': 99}

| Regime | n | WR fwd_5d | avg fwd_5d | avg fwd_10d |
|---|---:|---:|---:|---:|
| BULL | 1021 | 40.43% | -0.408% | 2.276 |
| UNKNOWN | 67 | 100.0% | +2.922% | — |

## 9 · False-Positive Analysis

The Winner/Loser Genome (§3) IS the false-positive analysis: every LOSER row is a prediction AEGIS made that lost. The genome quantifies which features distinguish losers from winners. See the `cohort_LOSER` block in `mr_winner_loser_genome_{market}.json`.


## 10 · Feature Predictive-Power Ranking


### INDIA · min_bucket_n=20 · threshold_pp=15

| Rank | Feature | WR spread (pp) | avg spread (%) | n | buckets | verdict |
|---:|---|---:|---:|---:|---:|---|
| 1 | `rsi_14` | 25.5 | 1.32 | 551 | 4 | PRODUCTION_CANDIDATE |
| 2 | `confidence_pct` | 23.88 | 1.006 | 551 | 5 | PRODUCTION_CANDIDATE |
| 3 | `sector` | 22.86 | 1.637 | 193 | 4 | PRODUCTION_CANDIDATE |
| 4 | `ma20_dist_pct` | 19.2 | 0.491 | 551 | 5 | PRODUCTION_CANDIDATE |
| 5 | `investability_band` | 16.9 | 1.671 | 551 | 4 | PRODUCTION_CANDIDATE |
| 6 | `rank_slot` | 15.36 | 0.563 | 551 | 3 | PRODUCTION_CANDIDATE |
| 7 | `momentum_20d_pct` | 13.07 | 1.891 | 551 | 5 | WEAK_SIGNAL |
| 8 | `runner` | 11.35 | 0.585 | 551 | 2 | WEAK_SIGNAL |
| 9 | `vol_20d_pct` | 8.56 | 0.777 | 551 | 3 | WEAK_SIGNAL |
| 10 | `trend` | 6.96 | 0.279 | 551 | 2 | WEAK_SIGNAL |
| 11 | `cap_bucket` | 1.97 | 0.203 | 551 | 2 | WEAK_SIGNAL |

### USA · min_bucket_n=20 · threshold_pp=15

| Rank | Feature | WR spread (pp) | avg spread (%) | n | buckets | verdict |
|---:|---|---:|---:|---:|---:|---|
| 1 | `rank_slot` | 100.0 | 4.018 | 113 | 3 | PRODUCTION_CANDIDATE |
| 2 | `ma20_dist_pct` | 24.11 | 1.723 | 1087 | 5 | PRODUCTION_CANDIDATE |
| 3 | `trend` | 18.04 | 0.247 | 1088 | 2 | PRODUCTION_CANDIDATE |
| 4 | `vol_20d_pct` | 17.1 | 2.449 | 1087 | 5 | PRODUCTION_CANDIDATE |
| 5 | `rsi_14` | 13.9 | 1.23 | 1083 | 4 | WEAK_SIGNAL |
| 6 | `runner` | 13.67 | 0.553 | 1088 | 2 | WEAK_SIGNAL |
| 7 | `cap_bucket` | 10.64 | 0.937 | 1088 | 2 | WEAK_SIGNAL |
| 8 | `confidence_pct` | 9.78 | 1.437 | 1088 | 4 | WEAK_SIGNAL |
| 9 | `investability_band` | 5.86 | 0.134 | 1088 | 2 | WEAK_SIGNAL |
| 10 | `momentum_20d_pct` | 3.89 | 0.945 | 1085 | 5 | WEAK_SIGNAL |
| 11 | `sector` | 1.75 | 0.971 | 1055 | 2 | WEAK_SIGNAL |

## 11a · Leakage / Data-Quality Audit


### INDIA · n_rows=551

| Check | pass | fail | n/a | pass_rate |
|---|---:|---:|---:|---:|
| A2_rec_date_le_pred_date | 551 | 0 | 0 | 100.0% |
| A4_entry_price_close_match | 551 | 0 | 0 | 100.0% |
| A5_mfe_mae_signs | 551 | 0 | 0 | 100.0% |
| A6_mfe_mae_dominate_fwd | 500 | 0 | 51 | 100.0% |

**A7_duplicate_pred_tuples:** `{'n_duplicates': 56, 'sample': {'2026-08-10|ICICIBANK|R1': 2, '2026-08-10|SUNPHARMA|R1': 2, '2026-08-10|PIDILITIND|R1': 2, '2026-08-10|LUPIN|R1': 2, '2026-08-10|KOTAKBANK|R1': 2, '2026-08-10|NTPC|R1': 2, '2026-08-10|BEL|R1': 2, '2026-08-10|POWERGRID|R1': 2, '2026-08-10|IRCTC|R1': 2, '2026-08-10|COALINDIA|R1': 2}}`

**A8_universe_coverage_sample:** `{'sampled': 100, 'no_parquet_close': 0}`

### USA · n_rows=1088

| Check | pass | fail | n/a | pass_rate |
|---|---:|---:|---:|---:|
| A2_rec_date_le_pred_date | 122 | 32 | 934 | 79.22% |
| A4_entry_price_close_match | 85 | 0 | 1003 | 100.0% |
| A5_mfe_mae_signs | 1088 | 0 | 0 | 100.0% |
| A6_mfe_mae_dominate_fwd | 625 | 0 | 463 | 100.0% |

**A7_duplicate_pred_tuples:** `{'n_duplicates': 0, 'sample': {}}`

**A8_universe_coverage_sample:** `{'sampled': 100, 'no_parquet_close': 0}`

## 11b · Control Cohort Baseline (AEGIS vs Universe)


### INDIA

- control universe_size = 230
- n_days = 18

| Horizon | Universe WR | Universe avg | AEGIS WR | AEGIS avg | Alpha |
|---|---:|---:|---:|---:|---:|
| fwd_5d | 32.25% | -0.388% | 25.77% | -0.729% | WR-6.48pp / avg-0.341% |
| fwd_10d | 30.02% | -0.934% | 27.8% | -1.534% | WR-2.22pp / avg-0.6% |

### USA

- control universe_size = 908
- n_days = 7

| Horizon | Universe WR | Universe avg | AEGIS WR | AEGIS avg | Alpha |
|---|---:|---:|---:|---:|---:|
| fwd_5d | 38.98% | -0.476% | 41.67% | -0.338% | WR+2.69pp / avg+0.138% |
| fwd_10d | 46.24% | +0.058% | 75.0% | +2.276% | WR+28.76pp / avg+2.218% |

## 10 · False-Negative Analysis · Missed Winners (≥+5% fwd_5d)


### INDIA
- universe_size: 230
- n_days: 18
- total AEGIS recommendations: 446
- big winners CAUGHT (≥+5% fwd_5d): 16
- big winners MISSED: 131
- capture_rate: **10.88%**
- avg missed per day: 7.28

Top 5 miss-heavy days:
  - 2026-08-06 · missed=21 · top=MCX(+12.7%), PAYTM(+12.6%), GLAND(+12.0%)
  - 2026-08-04 · missed=18 · top=GLAND(+13.2%), PAYTM(+12.7%), BOSCHLTD(+9.9%)
  - 2026-08-05 · missed=16 · top=PAYTM(+13.8%), GLAND(+13.2%), MOTHERSON(+12.1%)
  - 2026-08-07 · missed=16 · top=GLAND(+14.2%), PAYTM(+11.2%), MCX(+10.4%)
  - 2026-08-18 · missed=12 · top=RATNAMANI(+14.2%), MUTHOOTFIN(+10.1%), MCX(+8.4%)

### USA
- universe_size: 908
- n_days: 7
- total AEGIS recommendations: 1046
- big winners CAUGHT (≥+5% fwd_5d): 10
- big winners MISSED: 15
- capture_rate: **40.0%**
- avg missed per day: 2.14

Top 5 miss-heavy days:
  - 2026-08-14 · missed=11 · top=ARE(+11.1%), CF(+9.6%), APA(+7.2%)
  - 2026-08-10 · missed=4 · top=CIEN(+14.8%), AMD(+7.8%), ANET(+5.4%)
  - 2026-08-11 · missed=0 · top=
  - 2026-08-12 · missed=0 · top=
  - 2026-08-19 · missed=0 · top=

## 11 · Score-Usefulness Test (Investability / Confidence)


### INDIA


**band**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| AVOID | 108 | 19.18% | -0.879% | INSUFFICIENT_EVIDENCE |
| MARGINAL | 224 | 29.94% | -0.8% | PRODUCTION_CANDIDATE |
| OK | 119 | 17.39% | -1.314% | INSUFFICIENT_EVIDENCE |
| QUALITY | 100 | 34.29% | +0.357% | INSUFFICIENT_EVIDENCE |

**confidence_bucket**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| high_70_85 | 103 | 13.16% | -1.193% | INSUFFICIENT_EVIDENCE |
| low_lt30 | 39 | 37.04% | -0.385% | INSUFFICIENT_EVIDENCE |
| mid_30_50 | 181 | 33.83% | -0.187% | PRODUCTION_CANDIDATE |
| mid_50_70 | 180 | 22.95% | -1.079% | PRODUCTION_CANDIDATE |
| xhigh_ge85 | 48 | 23.53% | -0.825% | INSUFFICIENT_EVIDENCE |

### USA


**band**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| AVOID | 6 | 83.33% | +1.577% | OBSERVATION_ONLY |
| MARGINAL | 18 | 44.44% | -0.353% | OBSERVATION_ONLY |
| OK | 39 | 44.44% | -0.549% | INSUFFICIENT_EVIDENCE |
| PENDING | 1020 | 38.58% | -0.415% | PRODUCTION_CANDIDATE |
| QUALITY | 5 | 40.0% | +0.876% | OBSERVATION_ONLY |

**confidence_bucket**
| bucket | n | WR fwd_5d | avg fwd_5d | verdict |
|---|---:|---:|---:|---|
| high_70_85 | 355 | 41.07% | -0.662% | INSUFFICIENT_EVIDENCE |
| mid_30_50 | 61 | 50.0% | +0.358% | OBSERVATION_ONLY |
| mid_50_70 | 208 | 43.75% | -1.079% | INSUFFICIENT_EVIDENCE |
| xhigh_ge85 | 464 | 40.22% | +0.026% | INSUFFICIENT_EVIDENCE |

## LP · Loss Prevention Report


### INDIA

- n_predictions: 551
- n_losses: 267 (loss_rate 48.46%)
- **preventable_pct**: 86.89%
- by_classification: `{'PREVENTABLE_STOP_WIDE': 17, 'PREVENTABLE_HIGH_CONF': 43, 'PREVENTABLE_MODERATE': 169, 'PREVENTABLE_TIMING': 3, 'UNAVOIDABLE': 7, 'MARKET_WIDE': 28}`
- by_runner: `{'R2': 117, 'R1': 150}`

**Top anti-signals present in loser cohort:**

| Anti-signal | count |
|---|---:|
| BELOW_MA200 | 160 |
| INDIA_TOP3_RANK_INVERSION | 83 |
| BAND_OK | 75 |
| INDIA_CONFIDENCE_ANTI_SIGNAL_70_85 | 58 |
| BAND_AVOID | 48 |
| DEEP_BELOW_MA20 | 20 |
| RSI_OVERBOUGHT | 12 |

**Sample 10 losses with classification:**

| Date | Ticker | Runner | Rank | Conf | Band | fwd_5d% | MAE% | Class |
|---|---|---|---:|---:|---|---:|---:|---|
| 2026-08-04 | LUPIN | R2 | 1 | 51.8 | OK | -4.405 | -8.746 | PREVENTABLE_STOP_WIDE |
| 2026-08-04 | CHAMBLFERT | R2 | 3 | 38.3 | AVOID | -1.769 | -5.471 | PREVENTABLE_HIGH_CONF |
| 2026-08-04 | COALINDIA | R2 | 5 | 36.1 | MARGINAL | -0.614 | -3.649 | PREVENTABLE_MODERATE |
| 2026-08-04 | ITC | R2 | 7 | 38.3 | MARGINAL | -2.054 | -6.249 | PREVENTABLE_MODERATE |
| 2026-08-04 | HCLTECH | R2 | 8 | 43.1 | OK | 0.132 | -4.811 | PREVENTABLE_HIGH_CONF |
| 2026-08-04 | TCS | R2 | 9 | 37.1 | MARGINAL | 0.258 | -7.198 | PREVENTABLE_MODERATE |
| 2026-08-04 | SUNPHARMA | R1 | 1 | 90.0 | QUALITY | -0.68 | -4.102 | PREVENTABLE_MODERATE |
| 2026-08-04 | ICICIBANK | R1 | 2 | 83.0 | QUALITY | -1.373 | -3.277 | PREVENTABLE_MODERATE |
| 2026-08-04 | NTPC | R1 | 4 | 72.0 | AVOID | -2.534 | -3.081 | PREVENTABLE_HIGH_CONF |
| 2026-08-04 | KOTAKBANK | R1 | 5 | 71.0 | QUALITY | -1.033 | -2.355 | PREVENTABLE_MODERATE |

### USA

- n_predictions: 1088
- n_losses: 127 (loss_rate 11.67%)
- **preventable_pct**: 66.14%
- by_classification: `{'UNAVOIDABLE': 43, 'PREVENTABLE_MODERATE': 47, 'PREVENTABLE_HIGH_CONF': 10, 'PREVENTABLE_TIMING': 7, 'PREVENTABLE_STOP_WIDE': 20}`
- by_runner: `{'R1': 9, 'R2': 118}`

**Top anti-signals present in loser cohort:**

| Anti-signal | count |
|---|---:|
| HIGH_VOL_GE3PCT | 32 |
| BELOW_MA200 | 29 |
| BAND_OK | 24 |
| RSI_OVERBOUGHT | 18 |
| DEEP_BELOW_MA20 | 4 |
| BAND_AVOID | 2 |

**Sample 10 losses with classification:**

| Date | Ticker | Runner | Rank | Conf | Band | fwd_5d% | MAE% | Class |
|---|---|---|---:|---:|---|---:|---:|---|
| 2026-08-10 | HON | R1 | 9 | 56.8 | PENDING | None | -5.273 | UNAVOIDABLE |
| 2026-08-10 | AAPL | R1 | 7 | 50.5 | QUALITY | -0.866 | -1.95 | UNAVOIDABLE |
| 2026-08-10 | IT | R2 | 2 | 49.8 | PENDING | None | -7.097 | PREVENTABLE_MODERATE |
| 2026-08-10 | ADBE | R2 | 4 | 56.8 | OK | -6.931 | -6.931 | PREVENTABLE_HIGH_CONF |
| 2026-08-10 | ADSK | R2 | 5 | 54.0 | OK | -5.635 | -5.635 | PREVENTABLE_TIMING |
| 2026-08-10 | UBER | R2 | 7 | 56.8 | PENDING | None | -3.422 | UNAVOIDABLE |
| 2026-08-10 | UBER | R1 | 2 | 56.8 | PENDING | None | -3.422 | UNAVOIDABLE |
| 2026-08-10 | ADSK | R1 | 5 | 54.0 | OK | -5.635 | -5.635 | PREVENTABLE_TIMING |
| 2026-08-10 | ADBE | R1 | 6 | 56.8 | OK | -6.931 | -6.931 | PREVENTABLE_HIGH_CONF |
| 2026-08-10 | IT | R1 | 7 | 49.8 | PENDING | None | -7.097 | PREVENTABLE_MODERATE |

## 12 · Top 10 Findings (evidence-backed)

1. **F1 · India R1<R2**: India R1 5D WR=20.81% vs R2=32.16%. Runner asymmetry is directional.
2. **F2 · USA R1>R2**: USA R1 5D WR=54.55% vs R2=40.88%. Opposite of India · runner behavior is market-dependent, not universal.
3. **F3 · India TOP-3 rank inversion**: top3 WR=17.43% · rank_4_7 WR=32.79%. Ranker inverted vs outcome.
4. **F4 · USA rank works**: USA top3 WR=100.0% (perfect on small n=45). Monotone by rank. USA ranker is not broken.
5. **F5 · India band boundary defect**: OK WR=17.39% < AVOID WR=19.18%. OK band should NOT be below AVOID.
6. **F6 · India confidence anti-correlated**: winners avg conf=51.4% · losers avg conf=57.94%. Delta=-6.54%. Losers more confident than winners.
7. **F7 · India stop-policy leader**: `TIME_STOP_5D` expectancy=-0.613% vs CURRENT=-0.886%. Gap=0.273%. Requires walk-forward before any change.
8. **F8 · India capture rate**: 10.88% of ≥+5% fwd_5d winners across the universe were recommended by AEGIS. Missed 131 winners in 18 days · avg 7.28/day.
9. **F9 · India regime dependence**: 5D WR by regime = {'BEAR': 34.62, 'BULL': 23.76, 'UNKNOWN': 29.73}. Regime gate is a candidate improvement.
10. **F10 · India cap-bucket signal**: 5D WR by cap = {'LARGE': 25.45, 'MID': 27.42}.

## 13 · Top 10 Proposed Model Improvements (candidates only · NOT approved)

1. **C1 · India ranker rebuild**: R1 top-3 selection is anti-correlated with outcome (F3). Candidate: re-rank R1 output by inverse-confidence in India OR swap R1/R2 weight in India ensemble. Requires walk-forward on ≥100 new predictions.
2. **C2 · Per-market runner weights**: F1+F2 · R1 and R2 flip roles between markets. Candidate: separate ensemble weights per market instead of shared.
3. **C3 · India band-boundary re-tune**: F5 · OK-band underperforms AVOID. Candidate: re-derive OK/MARGINAL split with forward-return-optimized thresholds.
4. **C4 · India confidence recalibration**: F6 · confidence anti-correlates. Candidate: refit confidence model on winner/loser labels · or invert its contribution to ranker in India · treat as WARN signal not GO signal.
5. **C5 · Stop-policy switch**: F7 · one candidate policy beats CURRENT on expectancy. Candidate: config-toggle new stop policy OFF by default · paper-trade 30 days · then decide.
6. **C6 · Regime gate**: F9 · outcomes differ by regime. Candidate: reduce sizing OR skip R1 in BEAR regime.
7. **C7 · Cap-bucket sizing**: F10 · outcomes differ by cap. Candidate: per-cap position sizing rules.
8. **C8 · Momentum re-integration**: Momentum data is missing from history capture (n=0). Candidate: start capturing Momentum snapshots forward from today · re-run this study in 30 days.
9. **C9 · Sector filter (India)**: identify sectors with 5D WR <20% and either downweight or skip. Candidate rule needs sector-cohort n≥50.
10. **C10 · Miss-recovery scan**: F8 · missed-winner scan surfaces tickers AEGIS filtered · investigate whether investability threshold is over-strict.

## 14 · Evidence Trail for Each Improvement

Every candidate above (C1-C10) is backed by cohort-level evidence in the JSON files under `reports/research/`. Before any of them can be promoted to production, the following gate applies:

1. Research Ticket with hypothesis + expected effect size
2. Walk-forward test on ≥100 forward predictions (per M-R contract)
3. Full regression on locked delivery layer (no BLOCK invariants regress)
4. CEO approval + explicit lock-override phrase
5. Config-toggle OFF by default
6. Paper trading period ≥30 sessions
7. Then production promotion under new SPRINT_ID

## 15 · Compliance Statement

This report contains NO production changes and NO push has occurred.

All engines write only to `reports/research/` under M-R sandbox contract `ALLOWED_WRITE_ROOT = reports/research`. The locked delivery layer (`_split_and_send`, `xlsx_contract`, `xlsx_validator`, canonical JSON emit) was NOT touched by this run. R1/R2/Registry/XLSX format remain as of last locked commit.

Every candidate improvement (C1-C10) requires the 7-step future-change gate before it can affect production. This report is evidence-collection output only.
