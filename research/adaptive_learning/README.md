# DEV025 — Adaptive Portfolio Learning Engine (v0.1)

Continuous learning engine that evaluates every recommendation type from
DEV020/023 against realised historical outcomes and produces **advisory**
improvement suggestions. Never auto-applies changes (ARCH001A Article V clause 5.1).

## Directory structure

```
research/adaptive_learning/
├── lib/
│   ├── trade_history.py     Walk-forward PIT reconstruction of trade log
│   │                          (extends DEV021 with dim-value + MFE/MAE per trade)
│   ├── calibration.py       Confidence calibration: reliability diagram,
│   │                          Brier score, ECE, per-sector calibration
│   └── patterns.py          Score-bucket accuracy, sector/industry perf,
│                              dimension correlations, stop/target effectiveness
├── compute/
│   ├── engine.py            Orchestrator + cached trade history
│   └── suggestions.py       8 suggestion categories, evidence-based, advisory only
├── publish/
│   └── bundle.py            6 outputs
├── tests/
│   └── test_smoke.py        29 tests, all pass
├── run.py                    CLI
└── README.md
```

## Execution

```bash
python research/adaptive_learning/run.py                    # use cached trade history
python research/adaptive_learning/run.py --rebuild-cache    # force rebuild (~90s)
python research/adaptive_learning/tests/test_smoke.py       # 29 tests, all pass
```

## Outputs

| File | Contents |
|:--|:--|
| `learning_summary.json` | Top-level aggregate: trades, win rate, Brier, ECE, n_suggestions |
| `recommendation_accuracy.json` | Score buckets · sector/industry perf · stop/target stats |
| `confidence_calibration.json` | Reliability curve · per-sector calibration flags |
| `pattern_discovery.json` | Dimension correlations · best/worst sectors/industries |
| `improvement_suggestions.json` | 8-category advisory suggestions (never auto-applied) |
| `learning.parquet` | Per-trade rows with dim values + MFE/MAE |

## Suggestion categories

- **confidence_calibration** — ECE > 0.10 → recommend isotonic regression
- **sector_calibration** — per-sector over/under-confidence flags
- **score_calibration** — non-monotone score→win-rate ordering
- **dimension_effectiveness** — drop dimensions with |Spearman| < 0.05; upweight |ρ| > 0.15
- **stop_loss_optimisation** — evidence-based stop tightening/widening
- **target_optimisation** — hit-rate driven target adjustment
- **sector_allocation** — persistently-underperforming sectors
- **holding_period** — evidence for shorter vs longer holds

## First live run (2026-07-17)

```
Trades analysed:       1060 (walk-forward, top-20 monthly)
Win rate:              58.30%
Avg return:            +2.00% · Median +1.58%
Max gain / max loss:   +85.25% / −34.48%
Avg hold:              20.5 bars · MFE 7.01% · MAE −5.22%
Brier score:           0.3295
Expected Calibration Error: 0.2868
Suggestions generated: 22

TOP SUGGESTIONS:
  [HIGH]   SUG-CALIB-001: ECE 0.287 → fit isotonic regression on confidence
  [MEDIUM] SUG-CALIB-SEC-IT: predicted 0.869, actual 0.410, gap −0.459
  [MEDIUM] SUG-CALIB-SEC-BANKING: predicted 0.861, actual 0.492, gap −0.369
  [MEDIUM] SUG-CALIB-SEC-PHARMA: predicted 0.885, actual 0.527, gap −0.357
  [MEDIUM] SUG-CALIB-SEC-HEALTHCARE: predicted 0.868, actual 0.520, gap −0.348
```

## Governance

- **No auto-tuning.** Every suggestion is advisory. Operator must review.
- Sealed core untouched.
- Structurally isolated under `research/adaptive_learning/`.
- Trade history cached at `data/market_intelligence/derived/trade_history_cache.parquet` — regenerable.

## v0.2 follow-ups

- Regime-conditional accuracy (bull vs bear regime patterns)
- Sequential-dependence analysis (does recent-loss cluster predict next-loss?)
- Multi-strategy learning (compare Top-5 vs Top-20 vs Kelly)
- Sharpe-improvement suggestions with statistical significance
