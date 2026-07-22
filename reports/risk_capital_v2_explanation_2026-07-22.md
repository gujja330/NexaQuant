# Risk & Capital Engine · v2.0 · 2026-07-22

_Generated 2026-07-22T04:02:01.962741+00:00Z · regime **Neutral**_

## Portfolio-level risk

- Portfolio annualised vol: **0.1919**
- VaR 95%: **0.3156** · VaR 99%: **0.4464**
- CVaR 95%: **0.3958**
- Verdict: **WARNING**

### Budget utilisation

- `total_portfolio_vol` : 0.1919
- `budget_total_vol` : 0.2
- `total_budget_utilisation` : 0.9594
- `per_position_budget` : 0.05
- `per_sector_budget` : 0.3

### Risk alerts

- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `EXIDEIND` — EXIDEIND contributes 0.0534 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `GLAND` — GLAND contributes 0.0542 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `GODREJPROP` — GODREJPROP contributes 0.0612 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `IPCALAB` — IPCALAB contributes 0.0831 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `KALYANKJIL` — KALYANKJIL contributes 0.0869 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `LODHA` — LODHA contributes 0.0831 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `NYKAA` — NYKAA contributes 0.0800 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `RADICO` — RADICO contributes 0.0751 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `RELAXO` — RELAXO contributes 0.0725 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `SONACOMS` — SONACOMS contributes 0.0831 exceeding per-position budget 0.05

### Per-sector variance contribution

| Sector | VaR Contribution | Budget Utilisation |
|--------|------------------:|---------------------:|
| Pharma | 0.2787 | 0.9288 |
| Realty | 0.1849 | 0.6164 |
| Auto | 0.1753 | 0.5845 |
| Consumption | 0.1593 | 0.5311 |
| IT | 0.08 | 0.2667 |
| FMCG | 0.0751 | 0.2503 |
| Healthcare | 0.0466 | 0.1554 |

## Position sizing (top-10 by target weight)

For each position, why the size is what it is — and what would
have to change for the size to become 4% or 12% instead.

### `RADICO` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.247 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `APOLLOHOSP` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 0.920 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.161 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `NYKAA` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.261 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `SONACOMS` · target **9.68%** · verdict **PASS**

target 9.68% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.291 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.291  —  annualised vol 0.271 vs reference 0.35 -> factor 1.291 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.936x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.936x). Change ratio: 1.24x on the current stack.

### `IPCALAB` · target **9.40%** · verdict **PASS**

target 9.40% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.2534 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.2534  —  annualised vol 0.279 vs reference 0.35 -> factor 1.253 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.880x). Change ratio: 0.43x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.880x). Change ratio: 1.28x on the current stack.

### `LODHA` · target **7.04%** · verdict **PASS**

target 7.04% = base 5% × (confidence=1.5 · regime=1.0 · volatility=0.9392 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 0.9392  —  annualised vol 0.373 vs reference 0.35 -> factor 0.939 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.409x). Change ratio: 0.57x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.409x). Change ratio: 1.70x on the current stack.

### `GODREJPROP` · target **6.09%** · verdict **PASS**

target 6.09% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.0618 · sector_concentration=0.7652) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.0618  —  annualised vol 0.330 vs reference 0.35 -> factor 1.062 (bounded [0.6, 1.3])
- `sector_concentration` = 0.7652  —  sector share 7.04% of cap 30% -> factor 0.765

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.219x). Change ratio: 0.66x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.219x). Change ratio: 1.97x on the current stack.

### `PHOENIXLTD` · target **5.48%** · verdict **PASS**

target 5.48% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=0.5621) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.253 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 0.5621  —  sector share 13.14% of cap 30% -> factor 0.562

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.096x). Change ratio: 0.73x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.096x). Change ratio: 2.19x on the current stack.

### `ZYDUSLIFE` · target **5.42%** · verdict **PASS**

target 5.42% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=0.5559) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.250 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 0.5559  —  sector share 13.32% of cap 30% -> factor 0.556

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.084x). Change ratio: 0.74x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.084x). Change ratio: 2.21x on the current stack.

### `BHARATFORG` · target **5.07%** · verdict **PASS**

target 5.07% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=0.5196) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.262 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 0.5196  —  sector share 14.41% of cap 30% -> factor 0.520

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.013x). Change ratio: 0.79x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.013x). Change ratio: 2.37x on the current stack.


## Governance

> Advisory only. This is a target allocation, not an execution instruction.