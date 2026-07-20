# Risk & Capital Engine · v2.0 · 2026-07-20

_Generated 2026-07-20T04:15:22.765663+00:00Z · regime **Neutral**_

## Portfolio-level risk

- Portfolio annualised vol: **0.1938**
- VaR 95%: **0.3188** · VaR 99%: **0.4508**
- CVaR 95%: **0.3997**
- Verdict: **WARNING**

### Budget utilisation

- `total_portfolio_vol` : 0.1938
- `budget_total_vol` : 0.2
- `total_budget_utilisation` : 0.969
- `per_position_budget` : 0.05
- `per_sector_budget` : 0.3

### Risk alerts

- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `EXIDEIND` — EXIDEIND contributes 0.0533 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `GLAND` — GLAND contributes 0.0526 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `GODREJPROP` — GODREJPROP contributes 0.0606 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `IPCALAB` — IPCALAB contributes 0.0812 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `KALYANKJIL` — KALYANKJIL contributes 0.0870 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `LODHA` — LODHA contributes 0.0821 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `NYKAA` — NYKAA contributes 0.0796 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `RADICO` — RADICO contributes 0.0791 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `RELAXO` — RELAXO contributes 0.0792 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `SONACOMS` — SONACOMS contributes 0.0821 exceeding per-position budget 0.05

### Per-sector variance contribution

| Sector | VaR Contribution | Budget Utilisation |
|--------|------------------:|---------------------:|
| Pharma | 0.2705 | 0.9017 |
| Realty | 0.1832 | 0.6106 |
| Auto | 0.1747 | 0.5824 |
| Consumption | 0.1661 | 0.5538 |
| IT | 0.0796 | 0.2655 |
| FMCG | 0.0791 | 0.2636 |
| Healthcare | 0.0467 | 0.1557 |

## Position sizing (top-10 by target weight)

For each position, why the size is what it is — and what would
have to change for the size to become 4% or 12% instead.

### `IPCALAB` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.266 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `RADICO` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.261 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `APOLLOHOSP` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 0.920 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.163 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `NYKAA` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.262 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `SONACOMS` · target **9.50%** · verdict **PASS**

target 9.50% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.2669 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.2669  —  annualised vol 0.276 vs reference 0.35 -> factor 1.267 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.900x). Change ratio: 0.42x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.900x). Change ratio: 1.26x on the current stack.

### `LODHA` · target **7.01%** · verdict **PASS**

target 7.01% = base 5% × (confidence=1.5 · regime=1.0 · volatility=0.9346 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 0.9346  —  annualised vol 0.374 vs reference 0.35 -> factor 0.935 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.402x). Change ratio: 0.57x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.402x). Change ratio: 1.71x on the current stack.

### `GODREJPROP` · target **6.14%** · verdict **PASS**

target 6.14% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.0688 · sector_concentration=0.7663) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.0688  —  annualised vol 0.327 vs reference 0.35 -> factor 1.069 (bounded [0.6, 1.3])
- `sector_concentration` = 0.7663  —  sector share 7.01% of cap 30% -> factor 0.766

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.229x). Change ratio: 0.65x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.229x). Change ratio: 1.95x on the current stack.

### `PHOENIXLTD` · target **5.48%** · verdict **PASS**

target 5.48% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=0.5616) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.255 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 0.5616  —  sector share 13.15% of cap 30% -> factor 0.562

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.095x). Change ratio: 0.73x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.095x). Change ratio: 2.19x on the current stack.

### `ZYDUSLIFE` · target **5.32%** · verdict **PASS**

target 5.32% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=0.5459) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.247 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 0.5459  —  sector share 13.62% of cap 30% -> factor 0.546

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.065x). Change ratio: 0.75x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.065x). Change ratio: 2.25x on the current stack.

### `BHARATFORG` · target **5.12%** · verdict **PASS**

target 5.12% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=0.525) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.265 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 0.525  —  sector share 14.25% of cap 30% -> factor 0.525

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.024x). Change ratio: 0.78x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.024x). Change ratio: 2.34x on the current stack.


## Governance

> Advisory only. This is a target allocation, not an execution instruction.