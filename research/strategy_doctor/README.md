# DEV027 — Strategy Doctor Engine (v0.1)

Institutional post-mortem engine. Runs 15 diagnostic rules against every
closed trade in DEV025's learning corpus and produces an evidence-based
root-cause analysis with an advisory improvement plan.

**Never changes production behaviour.** Advisory only per ARCH001A Article V.

## Directory structure

```
research/strategy_doctor/
├── lib/diagnostics.py       15 diagnostic rules (pure functions)
├── compute/engine.py        Orchestration + pattern aggregation
├── publish/bundle.py        6 output files
├── tests/test_smoke.py      18 tests, all pass
├── run.py                    CLI
└── README.md
```

## 15 Diagnostic categories

| Category | Trigger | Severity |
|:--|:--|:-:|
| `wrong_company` | Score ≥ 70 + conf < 0.6 + loss | MEDIUM |
| `wrong_sector` | Parent sector Weak (< 45) + loss | HIGH |
| `wrong_regime` | Global Risk-Off regime + loss | MEDIUM |
| `late_entry` | MFE > 5% but final loss > 3% | MEDIUM |
| `early_exit` | MFE >> realised return + winning trade | LOW |
| `weak_conviction` | Confidence < 0.6 + loss | MEDIUM |
| `overconfidence` | Confidence ≥ 0.85 + loss > 5% | HIGH |
| `underconfidence` | Confidence < 0.6 + gain > 8% | LOW |
| `high_correlation` | Same-sector cohort losing > 70% | MEDIUM |
| `excess_concentration` | > 30% cohort weight in one sector | MEDIUM |
| `stop_loss_ineffective` | MAE < −5% but recovered to > +3% | LOW |
| `liquidity_shock` | MAE < −15% + return < −8% | HIGH |
| `macro_shock` | > 60% cohort losing | HIGH |
| `volatility_risk` | MFE > 10% AND MAE < −10% | MEDIUM |
| `poor_diversification` | Cohort has ≤ 3 sectors | MEDIUM |

## Execution

```bash
python research/strategy_doctor/run.py
python research/strategy_doctor/tests/test_smoke.py     # 18 tests
```

## Outputs (all under `reports/`)

| File | Contents |
|:--|:--|
| `strategy_doctor.json` | Top-level: trades diagnosed + top failure categories |
| `root_cause_analysis.json` | Every firing diagnosis (~677 on the 1060-trade corpus) |
| `failure_patterns.json` | Category counts + per-sector failure breakdown |
| `success_patterns.json` | Top winning sectors + industries |
| `improvement_plan.json` | Advisory action plan with target modules |
| `strategy_doctor.parquet` | Flat per-trade diagnosis table |

## First live run (2026-07-17)

```
Trades diagnosed:      1060
Winners / Losers:      618 / 442
Total diagnoses fired: 677

TOP FAILURE CATEGORIES:
  overconfidence             218 occurrences
  macro_shock                185 occurrences
  high_correlation            98 occurrences
  wrong_sector                65 occurrences
  liquidity_shock             64 occurrences
  late_entry                  23 occurrences
  excess_concentration        22 occurrences
  volatility_risk              2 occurrences

TOP WINNING SECTORS:
  Infrastructure  111 winners
  Financial Services 84 winners
  Auto             77 winners
  Energy           53 winners
  Pharma           48 winners

IMPROVEMENT PLAN (5 items):
  [overconfidence]      target: DEV020 → DEV029 Confidence Calibration (planned)
  [macro_shock]         target: monitoring / DEV017
  [high_correlation]    target: DEV022
  [wrong_sector]        target: DEV023
  [liquidity_shock]     target: TBD
```

The `overconfidence` finding (218 fires) is consistent with DEV025's ECE 0.29 — same underlying issue seen from two different angles.

## Governance

- Every diagnosis is a pure deterministic function
- No production behaviour changed
- Every improvement plan item is ADVISORY
- Sealed core untouched
- Structurally isolated under `research/strategy_doctor/`
