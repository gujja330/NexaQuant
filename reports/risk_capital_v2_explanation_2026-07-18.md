# Risk & Capital Engine · v2.0 · 2026-07-18

_Generated 2026-07-18T02:53:57.602195+00:00Z · regime **Neutral**_

## Portfolio-level risk

- Portfolio annualised vol: **0.1926**
- VaR 95%: **0.3168** · VaR 99%: **0.4481**
- CVaR 95%: **0.3973**
- Verdict: **WARNING**

### Budget utilisation

- `total_portfolio_vol` : 0.1926
- `budget_total_vol` : 0.2
- `total_budget_utilisation` : 0.9631
- `per_position_budget` : 0.05
- `per_sector_budget` : 0.3

### Risk alerts

- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `EXIDEIND` — EXIDEIND contributes 0.0536 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `GLAND` — GLAND contributes 0.0530 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `GODREJPROP` — GODREJPROP contributes 0.0610 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `IPCALAB` — IPCALAB contributes 0.0821 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `KALYANKJIL` — KALYANKJIL contributes 0.0873 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `LODHA` — LODHA contributes 0.0827 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `NYKAA` — NYKAA contributes 0.0816 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `RADICO` — RADICO contributes 0.0827 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `RELAXO` — RELAXO contributes 0.0687 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `SONACOMS` — SONACOMS contributes 0.0827 exceeding per-position budget 0.05

### Per-sector variance contribution

| Sector | VaR Contribution | Budget Utilisation |
|--------|------------------:|---------------------:|
| Pharma | 0.2734 | 0.9114 |
| Realty | 0.1844 | 0.6148 |
| Auto | 0.1739 | 0.5798 |
| Consumption | 0.1559 | 0.5198 |
| FMCG | 0.0827 | 0.2757 |
| IT | 0.0816 | 0.272 |
| Healthcare | 0.048 | 0.1598 |

## Position sizing (top-10 by target weight)

For each position, why the size is what it is — and what would
have to change for the size to become 4% or 12% instead.

### `IPCALAB` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.268 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `APOLLOHOSP` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 0.920 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.166 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `NYKAA` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.266 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `RADICO` · target **9.53%** · verdict **PASS**

target 9.53% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.2708 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.2708  —  annualised vol 0.275 vs reference 0.35 -> factor 1.271 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.906x). Change ratio: 0.42x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.906x). Change ratio: 1.26x on the current stack.

### `SONACOMS` · target **9.52%** · verdict **PASS**

target 9.52% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.2697 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.2697  —  annualised vol 0.276 vs reference 0.35 -> factor 1.270 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.905x). Change ratio: 0.42x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.905x). Change ratio: 1.26x on the current stack.

### `LODHA` · target **7.01%** · verdict **PASS**

target 7.01% = base 5% × (confidence=1.5 · regime=1.0 · volatility=0.935 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 0.935  —  annualised vol 0.374 vs reference 0.35 -> factor 0.935 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.403x). Change ratio: 0.57x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.403x). Change ratio: 1.71x on the current stack.

### `GODREJPROP` · target **6.12%** · verdict **PASS**

target 6.12% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.0645 · sector_concentration=0.7662) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.0645  —  annualised vol 0.329 vs reference 0.35 -> factor 1.065 (bounded [0.6, 1.3])
- `sector_concentration` = 0.7662  —  sector share 7.01% of cap 30% -> factor 0.766

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.223x). Change ratio: 0.65x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.223x). Change ratio: 1.96x on the current stack.

### `PHOENIXLTD` · target **5.48%** · verdict **PASS**

target 5.48% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=0.5623) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.254 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 0.5623  —  sector share 13.13% of cap 30% -> factor 0.562

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.096x). Change ratio: 0.73x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.096x). Change ratio: 2.19x on the current stack.

### `ZYDUSLIFE` · target **5.33%** · verdict **PASS**

target 5.33% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=0.547) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.247 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 0.547  —  sector share 13.59% of cap 30% -> factor 0.547

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.067x). Change ratio: 0.75x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.067x). Change ratio: 2.25x on the current stack.

### `BHARATFORG` · target **5.10%** · verdict **PASS**

target 5.10% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=0.5233) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.254 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 0.5233  —  sector share 14.30% of cap 30% -> factor 0.523

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.020x). Change ratio: 0.78x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.020x). Change ratio: 2.35x on the current stack.


## Governance

> Advisory only. This is a target allocation, not an execution instruction.