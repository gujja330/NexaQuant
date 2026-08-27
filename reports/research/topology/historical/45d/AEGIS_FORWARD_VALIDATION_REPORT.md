# AEGIS_FORWARD_VALIDATION_REPORT

_Sprint M-R · Forward Validation Engine v1 · sandbox_

**Generated:** 2026-08-27T09:15:39+00:00  
**Engine:** `aegis.mr_forward_validation_report.v1.0`  
**Status:** FOUNDATION COMPLETE · INTEGRATION DEFERRED  
**Locked layers:** UNTOUCHED · zero production changes.

---

## 1 · Executive summary

| | INDIA | USA |
|---|---:|---:|
| Predictions ingested | 551 | 1088 |
| fwd_1d WR | 21.60% | 39.52% |
| fwd_1d avg | -0.137% | 0.221% |
| fwd_5d WR | 25.77% | 41.67% |
| fwd_5d avg | -0.729% | -0.338% |
| fwd_10d WR | 27.80% | 75.00% |
| fwd_10d avg | -1.534% | 2.276% |
| fwd_20d WR | — | — |
| fwd_20d avg | — | — |
| Universe-baseline 5D WR | 32.25% | 38.98% |
| **AEGIS alpha (5D WR)** | **-6.48pp** | **2.69pp** |

**Headline:** 
India AEGIS is currently **BELOW** random-universe baseline (-6.48pp). 
USA AEGIS is **ABOVE** baseline (+2.69pp, small positive edge).


---

## 2 · R1 Runner


### INDIA · R1
| Bucket | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| R1 | 314 | 20.81% | -0.984% | -1.86% | 0.726% | -1.952% | 13.49% |

### USA · R1
| Bucket | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| R1 | 80 | 54.55% | +0.183% | 2.58% | 0.870% | -0.729% | 10.00% |

---

## 3 · R2 Runner


### INDIA · R2
| Bucket | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| R2 | 237 | 32.16% | -0.399% | -1.16% | 1.737% | -2.525% | 21.94% |

### USA · R2
| Bucket | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| R2 | 1008 | 40.88% | -0.37% | 1.77% | 0.942% | -0.823% | 16.00% |

---

## 4 · Momentum

**DATA GAP:** No historical Momentum snapshots exist. Momentum recommendations were not captured into `aegis_history.xlsx` beyond the current-day feed. Walk-forward capture starts today · `python -m backend.research.mr_walkforward_snapshot --snapshot --market both` needs to run daily from now on to build the corpus. First actionable measurement expected after 20 trading days.

---

## 5 · Sector analysis


### INDIA
| Sector | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| Industrials | 16 | 80.0% | +1.434% | 3.02% | 1.652% | -0.392% | 50.00% |
| Power | 31 | 30.0% | -0.297% | -0.84% | 1.042% | -1.118% | 3.23% |
| Chemicals | 14 | 22.22% | -0.43% | -0.15% | 0.881% | -1.128% | 28.57% |
| Transport | 16 | 20.0% | -2.571% | -5.39% | 0.354% | -3.003% | 37.50% |
| Pharma | 31 | 15.79% | -1.934% | -4.38% | 0.396% | -2.377% | 6.45% |
| FMCG | 33 | 14.29% | -1.586% | -3.78% | 0.456% | -2.354% | 21.21% |
| Metal | 15 | 11.11% | -0.917% | -2.29% | 0.219% | -1.468% | 6.67% |
| Financials | 21 | 7.14% | -0.872% | -0.78% | 0.636% | -1.298% | 0.00% |
| Energy | 14 | 0.0% | -0.663% | -1.89% | 0.260% | -1.321% | 0.00% |

### USA
| Sector | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| — | 60 | 42.86% | -1.253% | 2.58% | 0.676% | -0.895% | 10.00% |
| Large-Cap | 995 | 41.11% | -0.282% | — | 0.962% | -0.801% | — |

---

## 6 · Market cap


### INDIA
| Cap | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| LARGE | 459 | 25.45% | -0.697% | -1.45% | 1.081% | -2.071% | 15.33% |
| MID | 92 | 27.42% | -0.9% | -2.03% | 1.559% | -2.836% | 26.37% |

### USA
| Cap | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| LARGE | 459 | 35.96% | -0.841% | 0.36% | 1.051% | -1.036% | 13.56% |
| MID | 622 | 46.6% | +0.096% | 5.46% | 0.861% | -0.664% | 7.69% |

---

## 7 · Winners (fwd_5d > +0.5%)


### INDIA · n=101
- Runner mix: `{'R2': {'n': 55, 'pct': 54.46}, 'R1': {'n': 46, 'pct': 45.54}}`
- Band mix: `{'MARGINAL': {'n': 47, 'pct': 46.53}, 'QUALITY': {'n': 24, 'pct': 23.76}, 'OK': {'n': 16, 'pct': 15.84}, 'AVOID': {'n': 14, 'pct': 13.86}}`
- Confidence avg: 51.40%  (range 21.5-90.0)
- Avg MFE: 4.175%  ·  Avg MAE: -0.962%
- Stop-hit rate: 6.19%

### USA · n=80
- Runner mix: `{'R2': {'n': 74, 'pct': 92.5}, 'R1': {'n': 6, 'pct': 7.5}}`
- Band mix: `{'PENDING': {'n': 49, 'pct': 61.25}, 'OK': {'n': 16, 'pct': 20.0}, 'MARGINAL': {'n': 8, 'pct': 10.0}, 'AVOID': {'n': 5, 'pct': 6.25}, 'QUALITY': {'n': 2, 'pct': 2.5}}`
- Confidence avg: 78.38%  (range 30.0-100.0)
- Avg MFE: 5.143%  ·  Avg MAE: -1.465%
- Stop-hit rate: 0.00%

---

## 8 · Losers (fwd_5d < -0.5%)


### INDIA · n=247
- Runner mix: `{'R1': {'n': 143, 'pct': 57.89}, 'R2': {'n': 104, 'pct': 42.11}}`
- Band mix: `{'MARGINAL': {'n': 97, 'pct': 39.27}, 'OK': {'n': 69, 'pct': 27.94}, 'AVOID': {'n': 45, 'pct': 18.22}, 'QUALITY': {'n': 36, 'pct': 14.57}}`
- Confidence avg: 57.94%  (range 21.5-90.0)
- Avg MFE: 0.467%  ·  Avg MAE: -3.825%
- Stop-hit rate: 30.86%
- Loss rate: 48.46%  ·  Preventable: 86.89%
- Classification: `{'PREVENTABLE_STOP_WIDE': 17, 'PREVENTABLE_HIGH_CONF': 43, 'PREVENTABLE_MODERATE': 169, 'PREVENTABLE_TIMING': 3, 'UNAVOIDABLE': 7, 'MARKET_WIDE': 28}`

### USA · n=86
- Runner mix: `{'R2': {'n': 82, 'pct': 95.35}, 'R1': {'n': 4, 'pct': 4.65}}`
- Band mix: `{'PENDING': {'n': 58, 'pct': 67.44}, 'OK': {'n': 18, 'pct': 20.93}, 'MARGINAL': {'n': 7, 'pct': 8.14}, 'QUALITY': {'n': 2, 'pct': 2.33}, 'AVOID': {'n': 1, 'pct': 1.16}}`
- Confidence avg: 78.20%  (range 35.0-100.0)
- Avg MFE: 2.041%  ·  Avg MAE: -4.991%
- Stop-hit rate: 83.33%
- Loss rate: 11.67%  ·  Preventable: 66.14%
- Classification: `{'UNAVOIDABLE': 43, 'PREVENTABLE_MODERATE': 47, 'PREVENTABLE_HIGH_CONF': 10, 'PREVENTABLE_TIMING': 7, 'PREVENTABLE_STOP_WIDE': 20}`

---

## 9 · Stop-loss policy sweep


### INDIA
| Policy | n | WR | avg% | median% | PF | stop-hit% | cat>10%% | worst% | days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CURRENT | 490 | 26.53% | -0.886 | -0.907 | 0.43 | 18.57 | 0.2 | -10.476 | 7.34 |
| FIXED_3 | 500 | 26.4% | -0.933 | -1.043 | 0.41 | 32.4 | 0.2 | -10.476 | 6.66 |
| FIXED_5 | 500 | 27.4% | -0.96 | -0.84 | 0.42 | 13.8 | 0.2 | -10.476 | 7.80 |
| FIXED_7_5 | 500 | 27.8% | -0.93 | -0.786 | 0.43 | 3.6 | 0.2 | -10.476 | 8.41 |
| FIXED_10 | 500 | 27.8% | -0.918 | -0.786 | 0.43 | 0.2 | 0.2 | -10.476 | 8.50 |
| ATR_2X | 500 | 26.0% | -0.925 | -1.289 | 0.42 | 41.0 | 0.2 | -10.476 | 6.17 |
| ATR_3X | 500 | 27.6% | -0.915 | -0.817 | 0.43 | 22.6 | 0.2 | -10.476 | 7.33 |
| VOL_ADAPTIVE | 500 | 27.4% | -0.934 | -0.84 | 0.42 | 11.8 | 0.2 | -10.476 | 7.91 |
| TRAILING_5 | 500 | 26.8% | -0.972 | -0.851 | 0.40 | 17.6 | 0.2 | -10.476 | 7.56 |
| TRAILING_10 | 500 | 27.0% | -0.965 | -0.825 | 0.41 | 1.2 | 0.2 | -10.476 | 8.43 |
| TIME_STOP_5D | 500 | 24.8% | -0.613 | -0.771 | 0.52 | 0.0 | 0.0 | -9.069 | 4.45 |
| TIME_STOP_10D | 500 | 28.0% | -0.961 | -0.79 | 0.41 | 0.0 | 0.0 | -9.682 | 7.44 |

### USA
| Policy | n | WR | avg% | median% | PF | stop-hit% | cat>10%% | worst% | days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CURRENT | 39 | 35.9% | -0.63 | -0.341 | 0.65 | 25.64 | 0.0 | -7.097 | 3.03 |
| FIXED_3 | 625 | 38.72% | +0.055 | -0.031 | 1.05 | 17.12 | 0.0 | -7.474 | 2.76 |
| FIXED_5 | 625 | 41.28% | +0.23 | +0.111 | 1.23 | 6.72 | 0.0 | -8.618 | 3.13 |
| FIXED_7_5 | 625 | 41.92% | +0.28 | +0.14 | 1.29 | 2.4 | 0.0 | -9.96 | 3.28 |
| FIXED_10 | 625 | 41.92% | +0.271 | +0.14 | 1.28 | 0.8 | 0.8 | -13.91 | 3.33 |
| ATR_2X | 625 | 41.28% | +0.19 | +0.111 | 1.18 | 8.0 | 0.32 | -13.91 | 3.13 |
| ATR_3X | 625 | 41.92% | +0.253 | +0.14 | 1.26 | 3.36 | 0.48 | -13.91 | 3.27 |
| VOL_ADAPTIVE | 625 | 41.92% | +0.271 | +0.14 | 1.28 | 2.72 | 0.48 | -13.91 | 3.29 |
| TRAILING_5 | 625 | 40.32% | +0.175 | +0.091 | 1.18 | 12.0 | 0.0 | -8.618 | 2.93 |
| TRAILING_10 | 625 | 42.08% | +0.291 | +0.143 | 1.31 | 2.56 | 0.64 | -12.882 | 3.30 |
| TIME_STOP_5D | 625 | 39.36% | +0.026 | +0.07 | 1.03 | 0.0 | 0.32 | -12.876 | 2.27 |
| TIME_STOP_10D | 625 | 41.92% | +0.267 | +0.14 | 1.28 | 0.0 | 0.8 | -13.91 | 3.35 |

---

## 10 · MFE / MAE distribution


### INDIA
- Avg MFE: **1.161%**
- Avg MAE: **-2.199%**
- Stop-hit rate: 17.19%
- Reward:risk (MFE/|MAE|): **0.53**

### USA
- Avg MFE: **0.937%**
- Avg MAE: **-0.816%**
- Stop-hit rate: 11.76%
- Reward:risk (MFE/|MAE|): **1.15**

---

## 11 · Technical factors


### INDIA

**rsi_bucket**
| Bucket | n | 5D WR | 5D avg |
|---|---:|---:|---:|
| NEUTRAL_45_55 | 139 | 26.26% | -0.547% |
| OVERBOUGHT_ge70 | 14 | 14.29% | -1.381% |
| OVERSOLD_lt30 | 28 | 43.75% | +0.303% |
| STRONG_55_70 | 164 | 32.54% | -0.618% |
| WEAK_30_45 | 206 | 18.25% | -1.017% |

**trend**
| Bucket | n | 5D WR | 5D avg |
|---|---:|---:|---:|
| ABOVE_MA200 | 204 | 21.38% | -0.905% |
| BELOW_MA200 | 347 | 28.34% | -0.626% |

**vol_bucket**
| Bucket | n | 5D WR | 5D avg |
|---|---:|---:|---:|
| high_2_3 | 67 | 32.56% | -0.086% |
| low_lt1 | 135 | 24.0% | -0.683% |
| mid_1_2 | 348 | 24.91% | -0.863% |
| vhigh_3_4 | 1 | 100.0% | +4.907% |

**ma20_dist_bucket**
| Bucket | n | 5D WR | 5D avg |
|---|---:|---:|---:|
| above_+1_+5 | 149 | 37.17% | -0.467% |
| below_-5_-1 | 195 | 17.97% | -0.958% |
| deep_below_lt-5 | 40 | 21.43% | -0.856% |
| far_above_ge+5 | 48 | 27.27% | -0.806% |
| near_-1_+1 | 119 | 22.78% | -0.644% |

**momentum_20d_bucket**
| Bucket | n | 5D WR | 5D avg |
|---|---:|---:|---:|
| falling_lt-5 | 97 | 30.16% | -0.575% |
| flat_0_+5 | 145 | 23.81% | -1.007% |
| strong_+5_+10 | 78 | 34.33% | +0.141% |
| surge_ge+10 | 38 | 23.33% | -1.75% |
| weak_-5_0 | 193 | 21.26% | -0.793% |

### USA

**rsi_bucket**
| Bucket | n | 5D WR | 5D avg |
|---|---:|---:|---:|
| NEUTRAL_45_55 | 316 | 47.54% | +0.153% |
| OVERBOUGHT_ge70 | 112 | 41.38% | +0.168% |
| OVERSOLD_lt30 | 15 | 50.0% | -0.635% |
| STRONG_55_70 | 453 | 34.25% | -1.062% |
| WEAK_30_45 | 187 | 48.15% | -0.013% |

**trend**
| Bucket | n | 5D WR | 5D avg |
|---|---:|---:|---:|
| ABOVE_MA200 | 793 | 37.06% | -0.401% |
| BELOW_MA200 | 290 | 55.1% | -0.154% |

**vol_bucket**
| Bucket | n | 5D WR | 5D avg |
|---|---:|---:|---:|
| high_2_3 | 367 | 39.73% | -0.898% |
| low_lt1 | 33 | 33.33% | -0.031% |
| mid_1_2 | 443 | 48.68% | +0.663% |
| vhigh_3_4 | 130 | 33.33% | -1.786% |
| xhigh_ge4 | 114 | 31.58% | -0.918% |

**ma20_dist_bucket**
| Bucket | n | 5D WR | 5D avg |
|---|---:|---:|---:|
| above_+1_+5 | 306 | 27.5% | -1.111% |
| below_-5_-1 | 217 | 51.06% | +0.527% |
| deep_below_lt-5 | 67 | 33.33% | -0.7% |
| far_above_ge+5 | 325 | 39.71% | -0.883% |
| near_-1_+1 | 172 | 51.61% | +0.612% |

**momentum_20d_bucket**
| Bucket | n | 5D WR | 5D avg |
|---|---:|---:|---:|
| falling_lt-5 | 166 | 41.67% | -0.727% |
| flat_0_+5 | 227 | 43.18% | +0.103% |
| strong_+5_+10 | 191 | 39.29% | -0.842% |
| surge_ge+10 | 315 | 41.27% | -0.376% |
| weak_-5_0 | 186 | 42.42% | -0.144% |

---

## 12 · Fundamental factors


### INDIA
_(fundamentals parquet coverage gap · no bucket qualifies)_

### USA
_(fundamentals parquet coverage gap · no bucket qualifies)_

---

## 13 · Quality / Investability / Urgency validation


### INDIA
| Score | expected | actual | WR spread | **VERDICT** |
|---|---|---|---:|---|
| investability_band | MONOTONIC_UP | MIXED_UP | 16.90pp | **KEEP_WARN** |
| confidence_pct | MONOTONIC_UP | MIXED_DOWN | 23.88pp | **KEEP_WARN** |

**INDIA · investability_band bucket detail:**

| Bucket | n | 5D WR | 5D avg | 10D WR | 10D avg |
|---|---:|---:|---:|---:|---:|
| AVOID | 108 | 19.18% | -0.879% | 16.22% | -1.617% |
| OK | 119 | 17.39% | -1.314% | 24.56% | -2.132% |
| MARGINAL | 224 | 29.94% | -0.800% | 27.78% | -2.129% |
| QUALITY | 100 | 34.29% | 0.357% | 43.59% | 0.793% |

**INDIA · confidence_pct bucket detail:**

| Bucket | n | 5D WR | 5D avg | 10D WR | 10D avg |
|---|---:|---:|---:|---:|---:|
| conf_lt30 | 39 | 37.04% | -0.385% | 26.67% | -1.707% |
| conf_30_50 | 181 | 33.83% | -0.187% | 38.55% | -0.732% |
| conf_50_70 | 180 | 22.95% | -1.079% | 27.42% | -2.143% |
| conf_70_85 | 103 | 13.16% | -1.193% | 15.56% | -2.130% |
| conf_ge85 | 48 | 23.53% | -0.825% | 11.11% | -1.502% |

### USA
| Score | expected | actual | WR spread | **VERDICT** |
|---|---|---|---:|---|
| investability_band | MONOTONIC_UP | UNDEFINED | — | **NO_DATA** |
| confidence_pct | MONOTONIC_UP | MONOTONIC_DOWN | 9.78pp | **ANTI_SIGNAL_WEAK** |

**USA · investability_band bucket detail:**

| Bucket | n | 5D WR | 5D avg | 10D WR | 10D avg |
|---|---:|---:|---:|---:|---:|
| AVOID | 6 | 83.33% | 1.577% | — | — |
| OK | 39 | 44.44% | -0.549% | 50.00% | 0.285% |
| MARGINAL | 18 | 44.44% | -0.353% | — | — |
| QUALITY | 5 | 40.00% | 0.876% | 100.00% | 0.675% |

**USA · confidence_pct bucket detail:**

| Bucket | n | 5D WR | 5D avg | 10D WR | 10D avg |
|---|---:|---:|---:|---:|---:|
| conf_30_50 | 61 | 50.00% | 0.358% | — | — |
| conf_50_70 | 208 | 43.75% | -1.079% | 75.00% | 2.276% |
| conf_70_85 | 355 | 41.07% | -0.662% | — | — |
| conf_ge85 | 464 | 40.22% | 0.026% | — | — |

---

## 14 · Regime analysis


### INDIA
- Regime distribution across window: `{'BULL': 700, 'BEAR': 316, 'HIGH_VOL': 280, 'NEUTRAL': 176}`

| Regime | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| BEAR | 52 | 34.62% | -0.486% | — | 1.049% | -1.507% | 11.54% |
| BULL | 303 | 23.76% | -0.821% | -1.53% | 1.654% | -3.229% | 25.94% |
| UNKNOWN | 62 | 29.73% | -0.318% | — | 0.642% | -1.211% | 6.45% |

### USA
- Regime distribution across window: `{'BULL': 599, 'BEAR': 202, 'HIGH_VOL': 294, 'NEUTRAL': 99}`

| Regime | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| BULL | 1021 | 40.43% | -0.408% | 2.28% | 0.976% | -0.856% | 30.77% |
| UNKNOWN | 67 | 100.0% | +2.922% | — | 0.352% | -0.215% | 3.39% |

---

## 15 · Failure patterns (anti-signals at entry)


### INDIA · n_losses=267
| Anti-signal at entry | count |
|---|---:|
| BELOW_MA200 | 160 |
| INDIA_TOP3_RANK_INVERSION | 83 |
| BAND_OK | 75 |
| INDIA_CONFIDENCE_ANTI_SIGNAL_70_85 | 58 |
| BAND_AVOID | 48 |
| DEEP_BELOW_MA20 | 20 |
| RSI_OVERBOUGHT | 12 |

### USA · n_losses=127
| Anti-signal at entry | count |
|---|---:|
| HIGH_VOL_GE3PCT | 32 |
| BELOW_MA200 | 29 |
| BAND_OK | 24 |
| RSI_OVERBOUGHT | 18 |
| DEEP_BELOW_MA20 | 4 |
| BAND_AVOID | 2 |

---

## 16 · Candidate improvements (DRAFT tickets · never auto-applied)


Top 5 candidates ranked by severity×3 + verdict×2 + evidence×1 + preventability×2:

| Rank | Score | Market | Severity | Verdict | n_evid | Title |
|---:|---:|---|---|---|---:|---|
| 1 | 25 | INDIA | HIGH | PRODUCTION_CANDIDATE | 551 | India confidence_pct is anti-correlated with forward return |
| 2 | 24 | INDIA | HIGH | PRODUCTION_CANDIDATE | 141 | India top-3 rank slot underperforms rank_4_7 (ranker inversion) |
| 3 | 24 | INDIA | CRITICAL | PRODUCTION_CANDIDATE | 2747 | India AEGIS produces -6.48pp NEGATIVE alpha vs universe |
| 4 | 22 | INDIA | MEDIUM | PRODUCTION_CANDIDATE | 551 | India OK band underperforms AVOID · boundary miscalibrated |
| 5 | 22 | INDIA | MEDIUM | PRODUCTION_CANDIDATE | 500 | India TIME_STOP_5D beats CURRENT by 0.273% expectancy |

---

## 17 · Out-of-sample validation


**Forward-captured days so far:** 1

- `2026-08-27` 
  - `india.jsonl` · n_predictions=19
  - `momentum_india.jsonl` · n_predictions=3
  - `momentum_usa.jsonl` · n_predictions=106

**Registered walk-forward experiments (from candidate improvements):**

| Experiment | Metric | Min N | Window | Status |
|---|---|---:|---:|---|
| `aegis_mr_experiment_20260827_india_confidence_anti_signal` | shadow_5D_WR | 100 | 30d | **NOT_STARTED** |
| `aegis_mr_experiment_20260827_india_top3_rank_inversion` | shadow_top3_5D_WR | 100 | 30d | **NOT_STARTED** |
| `aegis_mr_experiment_20260827_india_negative_alpha` | shadow_alpha_vs_universe | 100 | 30d | **NOT_STARTED** |
| `aegis_mr_experiment_20260827_india_band_boundary` | band_ordering_monotonicity | 100 | 30d | **NOT_STARTED** |
| `aegis_mr_experiment_20260827_india_stop_policy` | expectancy_gap_vs_current | 100 | 30d | **NOT_STARTED** |

**Status:** IN_PROGRESS · walk-forward corpus needs ≥20 trading days before any experiment can conclude. Daily snapshot capture must run from today forward. Every experiment stays `NOT_STARTED` until CEO enables it.

---

## 18 · Recommendations for production


**Current recommendation:** *No production changes.*


Every candidate improvement from §16 is `status: DRAFT`. Every walk-forward experiment from §17 is `status: NOT_STARTED`. The 7-step promotion gate applies verbatim to each:

- 1. Research Ticket accepted by CEO
- 2. Walk-forward test on N ≥ 100 forward predictions
- 3. Full regression pass on locked delivery invariants (BLOCK == 0)
- 4. CEO explicit approval + lock-override phrase
- 5. Config-toggle OFF by default in a new SPRINT_ID branch
- 6. Paper-trading period ≥ 30 sessions with green metrics
- 7. Production promotion under new SPRINT_ID with L4 evidence

**Locked layers · verbatim untouched:** R1 runner, R2 runner, Registry, `backend/delivery/xlsx_contract.py`, `backend/delivery/xlsx_validator.py`, `scripts/telegram_command_center_send.py` canonical JSON emit, `configs/ensemble_weights_adaptive.yaml`, `model_registry.jsonl`.


**Data gaps to close before promotion:**
- Momentum historical snapshots (start forward capture now)
- USA investability shadow file (94% PENDING band)
- Fundamentals parquet coverage (India 228 tickers only)
- Walk-forward corpus depth (day-0 captured today only)


---

## Appendix · files consumed

- `reports/research/mr_prediction_autopsy_{market}.jsonl`
- `reports/research/mr_prediction_autopsy_{market}_enriched.jsonl`
- `reports/research/mr_prediction_autopsy_{market}_summary.json`
- `reports/research/mr_studies_{market}.json`
- `reports/research/mr_stop_loss_sweep_{market}.json`
- `reports/research/mr_loss_prevention_{market}.json`
- `reports/research/mr_control_cohort_{market}.json`
- `reports/research/mr_missed_winners_{market}.json`
- `reports/research/mr_market_regime_{market}.json`
- `reports/research/mr_feature_ranking_{market}.json`
- `reports/research/mr_score_usefulness_{market}.json`
- `reports/research/mr_winner_loser_genome_{market}.json`
- `reports/research/mr_hypothesis_shortlist.json`
- `reports/research/tickets/INDEX.json + 5 DRAFT tickets`
- `reports/research/experiments/INDEX.json + 5 NOT_STARTED experiments`
- `reports/research/walkforward/{date}/{market}.jsonl (day-0 captures)`

## Reproduce

```bash
python -m backend.research.mr_v1_pipeline --market both
python -m backend.research.mr_forward_validation_report
pytest tests/research/ -q
```
