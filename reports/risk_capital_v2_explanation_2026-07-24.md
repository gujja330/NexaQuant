# Risk & Capital Engine · v2.0 · 2026-07-24

_Generated 2026-07-24T03:56:47.300419+00:00Z · regime **Neutral**_

## Portfolio-level risk

- Portfolio annualised vol: **0.1919**
- VaR 95%: **0.3157** · VaR 99%: **0.4465**
- CVaR 95%: **0.3959**
- Verdict: **WARNING**

### Budget utilisation

- `total_portfolio_vol` : 0.1919
- `budget_total_vol` : 0.2
- `total_budget_utilisation` : 0.9596
- `per_position_budget` : 0.05
- `per_sector_budget` : 0.3

### Risk alerts

- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `EXIDEIND` — EXIDEIND contributes 0.0534 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `GLAND` — GLAND contributes 0.0542 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `GODREJPROP` — GODREJPROP contributes 0.0611 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `IPCALAB` — IPCALAB contributes 0.0831 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `KALYANKJIL` — KALYANKJIL contributes 0.0872 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `LODHA` — LODHA contributes 0.0831 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `NYKAA` — NYKAA contributes 0.0816 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `RADICO` — RADICO contributes 0.0735 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `RELAXO` — RELAXO contributes 0.0727 exceeding per-position budget 0.05
- [MEDIUM] **POSITION_VAR_BUDGET_BREACH** · `SONACOMS` — SONACOMS contributes 0.0831 exceeding per-position budget 0.05

### Per-sector variance contribution

| Sector | VaR Contribution | Budget Utilisation |
|--------|------------------:|---------------------:|
| Pharma | 0.2786 | 0.9286 |
| Realty | 0.1862 | 0.6208 |
| Auto | 0.1747 | 0.5824 |
| Consumption | 0.1599 | 0.5329 |
| IT | 0.0816 | 0.2719 |
| FMCG | 0.0735 | 0.245 |
| Healthcare | 0.0455 | 0.1518 |

## Position sizing (top-10 by target weight)

For each position, why the size is what it is — and what would
have to change for the size to become 4% or 12% instead.

### `RADICO` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.242 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `APOLLOHOSP` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 0.920 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.158 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `NYKAA` · target **9.75%** · verdict **PASS**

target 9.75% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.265 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.950x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.950x). Change ratio: 1.23x on the current stack.

### `SONACOMS` · target **9.70%** · verdict **PASS**

target 9.70% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.2927 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.2927  —  annualised vol 0.271 vs reference 0.35 -> factor 1.293 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.939x). Change ratio: 0.41x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.939x). Change ratio: 1.24x on the current stack.

### `IPCALAB` · target **9.41%** · verdict **PASS**

target 9.41% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.2551 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.2551  —  annualised vol 0.279 vs reference 0.35 -> factor 1.255 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.883x). Change ratio: 0.42x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.883x). Change ratio: 1.27x on the current stack.

### `LODHA` · target **7.10%** · verdict **PASS**

target 7.10% = base 5% × (confidence=1.5 · regime=1.0 · volatility=0.947 · sector_concentration=1.0) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 0.947  —  annualised vol 0.370 vs reference 0.35 -> factor 0.947 (bounded [0.6, 1.3])
- `sector_concentration` = 1.0  —  sector share 0.00% of cap 30% -> factor 1.000

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.420x). Change ratio: 0.56x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.420x). Change ratio: 1.69x on the current stack.

### `GODREJPROP` · target **5.94%** · verdict **PASS**

target 5.94% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.0376 · sector_concentration=0.7633) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.0376  —  annualised vol 0.337 vs reference 0.35 -> factor 1.038 (bounded [0.6, 1.3])
- `sector_concentration` = 0.7633  —  sector share 7.10% of cap 30% -> factor 0.763

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.188x). Change ratio: 0.67x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.188x). Change ratio: 2.02x on the current stack.

### `PHOENIXLTD` · target **5.51%** · verdict **PASS**

target 5.51% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=0.5653) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.260 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 0.5653  —  sector share 13.04% of cap 30% -> factor 0.565

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.102x). Change ratio: 0.73x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.102x). Change ratio: 2.18x on the current stack.

### `ZYDUSLIFE` · target **5.42%** · verdict **PASS**

target 5.42% = base 5% × (confidence=1.5 · regime=1.0 · volatility=1.3 · sector_concentration=0.5556) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 1.3  —  annualised vol 0.249 vs reference 0.35 -> factor 1.300 (bounded [0.6, 1.3])
- `sector_concentration` = 0.5556  —  sector share 13.33% of cap 30% -> factor 0.556

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.083x). Change ratio: 0.74x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.083x). Change ratio: 2.22x on the current stack.

### `EXIDEIND` · target **5.03%** · verdict **PASS**

target 5.03% = base 5% × (confidence=1.5 · regime=1.0 · volatility=0.9904 · sector_concentration=0.6768) -> PASS

**Factors**

- `confidence` = 1.5  —  calibrated confidence 1.000 vs base 0.58 -> factor 1.500 (bounded [0.5, 1.5])
- `regime` = 1.0  —  regime='Neutral' -> factor 1.00
- `volatility` = 0.9904  —  annualised vol 0.353 vs reference 0.35 -> factor 0.990 (bounded [0.6, 1.3])
- `sector_concentration` = 0.6768  —  sector share 9.70% of cap 30% -> factor 0.677

**Why not 4%?**   to size at 4%, the composite factor would need to become 0.800x base (currently 1.005x). Change ratio: 0.80x on the current stack.

**Why not 12%?**  to size at 12%, the composite factor would need to become 2.400x base (currently 1.005x). Change ratio: 2.39x on the current stack.


## Governance

> Advisory only. This is a target allocation, not an execution instruction.