# DEV022 — Portfolio Construction & Optimization Engine (v0.1)

Turns DEV020 rankings into **institutional portfolios**: 9 portfolio types
× 11 allocation methods = **99 candidate portfolios**, each with constraint
enforcement, risk analytics, and historical stress-test replay.

## Pipeline position

```
DEV020 Company Intelligence → reports/company_context.json
DEV021 Backtesting           → validation reports (used as reference)
        ↓
┌────────────────────────────────────────────────────────┐
│  DEV022  Portfolio Construction & Optimization         │
│                                                          │
│  Candidates (DEV020 top-N filtered by class/confidence) │
│         ↓                                                │
│  Allocator (Equal / Score / HRP / MinVar / MaxSharpe /  │
│              MaxDiv / InvVol / Kelly / Score×Conf / ...) │
│         ↓                                                │
│  Constraint Enforcement (stock/sector/industry caps,    │
│                            cash reserve, min positions)  │
│         ↓                                                │
│  Risk Analytics (vol, beta, div ratio, HHI, effective N) │
│         ↓                                                │
│  Stress Tests (5 historical windows replay)             │
│         ↓                                                │
│  Publish: 6 JSON + portfolio.parquet                    │
└────────────────────────────────────────────────────────┘
```

## Directory structure

```
research/portfolio_construction/
├── lib/
│   ├── allocators.py       11 position-sizing methods (see below)
│   ├── constraints.py       Stock/sector/industry cap enforcement with
│   │                          converge-until-fixed iteration
│   └── stress_tests.py      5 historical replay windows (COVID, 2022 bear,
│                              Vol spike 2025, Rate hike 2022 H1, Adani shock 2023)
├── ingest/                  (empty — reads DEV020 outputs)
├── compute/
│   ├── portfolio_builder.py  9 PortfolioType definitions + build orchestration
│   └── risk_analytics.py     Vol / beta / diversification / HHI / effective N
├── publish/
│   └── bundle.py             6 JSON reports + parquet
├── tests/
│   └── test_smoke.py         32 smoke tests
├── run.py                    CLI
└── README.md
```

## 11 Allocation methods

| Allocator | Description |
|:--|:--|
| `equal` | 1/N per position |
| `score` | Weight ∝ (score − 50); score-weighted |
| `confidence` | Weight ∝ confidence |
| `score_x_confidence` | Weight ∝ score × confidence |
| `inverse_vol` | Weight ∝ 1/annualised vol (low-vol overweight) |
| `volatility` | Weight ∝ annualised vol (aggressive) |
| `hrp` | Hierarchical Risk Parity (López de Prado 2016) |
| `min_variance` | SLSQP min-vol long-only sum-to-1 |
| `max_diversification` | Max Diversification Ratio (Choueifaty-Coignard) |
| `max_sharpe` | Tangency portfolio with 30% per-stock cap (stability) |
| `kelly_quarter` | Fractional Kelly (0.25 × full Kelly, long-only) |

## 9 Portfolio types

| Type | Top-N | Min score | Min conf | Notes |
|:--|:-:|:-:|:-:|:--|
| `top_10` | 10 | 55 | 0.5 | Standard concentrated |
| `top_20` | 20 | 50 | 0.5 | Standard diversified |
| `top_30` | 30 | 45 | 0.5 | Wide diversification |
| `concentrated` | 5 | 65 | 0.5 | High-conviction only |
| `aggressive` | 15 | 60 | 0.5 | Higher-conviction, higher-turnover |
| `balanced` | 20 | 50 | 0.5 | Same as top_20; kept for clarity |
| `conservative` | 25 | 45 | 0.5 | Broadest inclusion |
| `quality` | 15 | 55 | 0.7 | High confidence gate |
| `momentum` | 15 | 60 | 0.5 | Strong-Bullish/Bullish only |

## Default constraints

```python
Constraints(
    max_stock_weight    = 0.30    # No single position > 30%
    min_stock_weight    = 0.005   # Drop positions < 50 bps
    max_sector_exposure = 0.35    # No single sector > 35%
    max_industry_exposure = 0.25  # No single industry > 25%
    cash_allocation     = 0.0     # Fully invested by default
    min_positions       = 3
    max_positions       = 30
)
```

Constraint enforcement iterates until convergence, fixing the largest
violation per pass. If a violation cannot be resolved without breaking
another cap (e.g. degenerate constraint conflict), excess allocation is
left as unassigned cash and documented in `violations` — never silently
absorbed.

## 5 stress-test windows

| Window | Description |
|:--|:--|
| **COVID_crash_2020** | Feb-Apr 2020 pandemic crash |
| **Bear_2022_Q2Q3** | 2022 mid-year global bear market |
| **Vol_spike_2025** | Q1 2025 volatility spike |
| **Rate_hike_2022_H1** | Fed rate hike cycle H1 2022 |
| **Adani_shock_2023** | Hindenburg Adani short-report Jan-Mar 2023 |

For each portfolio × window: cumulative return, max drawdown, worst day,
annualised vol, coverage % (tickers with data in window).

## Execution

```bash
# Prerequisites: DEV020 company_context.json must exist
python research/company_intelligence/run.py

# Then DEV022:
python research/portfolio_construction/run.py                     # full 99 portfolios
python research/portfolio_construction/run.py --no-stress         # skip stress replay (faster)
python research/portfolio_construction/run.py --allocators equal,hrp,min_variance
python research/portfolio_construction/run.py --portfolios top_10,top_20,concentrated

# Smoke tests
python research/portfolio_construction/tests/test_smoke.py        # 32 tests, all pass
```

## Outputs (all under `reports/`)

| File | Contents |
|:--|:--|
| `portfolio.json` | Every (portfolio_type × allocator) with positions, weights, risk, stress |
| `portfolio.parquet` | Flat per-position table across all portfolios |
| `risk_report.json` | Per-portfolio risk summary (vol, beta, HHI, effective N) |
| `allocation_report.json` | Sector + industry breakdowns per portfolio |
| `rebalance_report.json` | Heuristic rebalance signals per portfolio |
| `stress_test.json` | Historical replay under 5 stress windows |
| `portfolio_leaderboard.json` | Sorted by expected Sharpe |

## First live run — 2026-07-17

```
Universe:        208 scored companies (from DEV020)
Portfolios:      99 built (9 types × 11 allocators)
Elapsed:         9.6 seconds

TOP LEADERBOARD (by expected Sharpe):

  portfolio                         N  ExRet%  ExVol%  ExSharpe  Beta  EffN_S  Top3Sec
  top_30 × max_sharpe               9   40.24  16.08    2.192   0.82   7.00    0.664
  conservative × max_sharpe         8   40.40  16.17    2.189   0.81   6.61    0.678
  top_20 × max_sharpe               7   39.07  16.52    2.063   0.81   6.12    0.653
  balanced × max_sharpe             7   39.07  16.52    2.063   0.81   6.12    0.653
  aggressive × max_sharpe           6   37.94  16.98    1.941   0.68   5.29    0.750
  ...
  top_30 × kelly_quarter           22   30.52  15.21    1.678   0.96  17.88    0.455
  ...
```

**Notes on interpretation:**

- The `max_sharpe` optimiser hits its 30% per-stock cap frequently — it concentrates weight in the top few names with the best historical Sharpe, then diversifies mildly. Effective N ~5-9. Beta ~0.7-0.8. High expected Sharpe but arguably overfit.
- `kelly_quarter` with `top_30` gives a much more diversified profile (effective N ~18, top-3 sector share ~46%) with a lower but still strong expected Sharpe.
- Expected metrics use historical mean returns × 252, which OVER-estimates true forward Sharpe (standard bias). Use DEV021 backtests for out-of-sample validation.
- Beta computed on the DEV017 Nifty overlap window (~10 months). Full-window beta requires backfilled Nifty.

## Reuse discipline

- Constituent sector/industry mapping imported from `company_intelligence.lib.company_catalog` — no duplication.
- Nifty benchmark loaded via `research.backtesting.compute.backtest_engine.load_nifty_series` — reused, not re-implemented.
- No new schema; portfolio structures use plain dicts (positions × metadata) that consumers can materialize as ARCH017A `CompositeScore` entities if needed.

## Governance

- Emits **portfolio candidates** — NOT trade signals. The operator must review each candidate before execution.
- Sealed core untouched · MON001 fingerprint invariant · `cumulative_strategy_search = 38` unchanged.
- Rebalance recommendations are advisory heuristics (`>15% single-stock drift`, `>10% sector-cap breach`) — never auto-applied per ARCH001A Article V clause 5.1.
- Structurally isolated under `research/portfolio_construction/`.
- Every constraint violation is recorded in the output — never silently accommodated.

## v0.2 follow-ups

- Rebalance-based backtesting (integrate with DEV021 to test candidate portfolios' actual performance)
- Multi-period optimisation (currently single-period myopic)
- Transaction-cost-aware optimisation
- Black-Litterman prior integration
- Robust optimisation (worst-case covariance)
- CVaR-constrained portfolios
- Dynamic rebalance thresholds (per-portfolio drift bounds)
- Weekly + quarterly rebalance cadences
