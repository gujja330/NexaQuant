# Risk & Capital Engine · v2.0

**Position sizing + risk budget · P3 in [PHASE2_MASTER_ROADMAP.md](../../docs/PHASE2_MASTER_ROADMAP.md).**

Every position answers three counter-questions in evidence terms:

- **Why 6% allocation?**
- **Why not 4%?**
- **Why not 12%?**

Advisory-only. Produces target weights + a portfolio-level risk decision.
Does NOT write to DEV022 portfolio.json, does NOT execute any trades.

## Sizing model

```
target_weight = base_weight × f_confidence × f_regime × f_volatility × f_sector_concentration
```

Every factor is bounded (documented ranges) and emits an explanation
string. The final weight is clamped to `[FLOOR_WEIGHT, CEILING_WEIGHT]`
= `[1%, 15%]`.

| Factor | Range | Rationale |
|---|---|---|
| Confidence | [0.5, 1.5] | Higher calibrated confidence -> larger size, bounded so miscalibration cannot dominate |
| Regime | [0.5, 1.2] | Dampen in Risk-Off (0.5x), mild boost in Risk-On (1.2x), neutral otherwise |
| Volatility | [0.6, 1.3] | Smaller size for high-vol names; reference 35% annualised vol |
| Sector Concentration | [0.3, 1.0] or 0 | Damps as sector approaches 30% cap; hits 0 (BLOCK) at cap |

## Portfolio risk model

Parametric variance decomposition with a conservative default correlation
matrix (`rho = 0.30`). Correlations can be passed in for a more accurate
model — the current default keeps the calculation deterministic and
requires no external estimator.

Reports:

- Portfolio annualised volatility
- VaR 95% and 99% (z-based)
- CVaR 95% (Expected Shortfall)
- Per-position variance contribution + budget utilisation
- Per-sector variance contribution + budget utilisation

## Budgets (declared, transparent)

- Total portfolio vol: **20% annualised**
- Per-position variance contribution: **5%**
- Per-sector variance contribution: **30%**
- 95% VaR confidence level

Breaches produce advisory alerts, not blocks (except sector cap).

## Outputs

- `reports/risk_capital_v2_latest.json` — headline
- `reports/risk_capital_v2_<date>.json` — timestamped snapshot
- `reports/risk_capital_v2_explanation_<date>.md` — human-readable per-position report with counter-questions answered
- `reports/risk_capital_v2_sizing.parquet` — flat sizing table

## Governance

- Advisory only.
- Deterministic — same recommendations + same regime + same prices produce identical target weights.
- Tenant-generic — no hardcoded tickers or sectors.
- Reads DEV023 recommendations + DEV017 regime + DEV029 calibration + `data/raw/india/{ticker}_D1.parquet` for vol estimation.
- Bounded factors mean the model cannot produce a runaway concentration under any single-input extreme.

## Run

```
python research/risk_capital_v2/run.py
python research/risk_capital_v2/tests/test_smoke.py
```
