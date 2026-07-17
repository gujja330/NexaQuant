# DEV021 — Historical Validation & Backtesting Engine (v0.1)

Walk-forward backtest engine that validates the DEV017-020 intelligence stack
against 4+ years of historical AEGIS-universe data. Point-in-time company
scoring, deterministic replay, no look-ahead bias.

## Pipeline position

```
DEV017 Global      →  reports/global_context.json  (context awareness)
DEV018 Sector      →  reports/sector_context.json
DEV019 Industry    →  reports/industry_context.json
DEV020 Company     →  reports/company_context.json
        ↓
┌──────────────────────────────────────────────────────────┐
│  DEV021  Historical Validation & Backtesting Engine       │
│                                                            │
│  For each rebalance date T:                                │
│    1. Score every ticker using ONLY bars ≤ T (PIT)          │
│    2. Build portfolios per strategy                         │
│    3. Hold until T+1 (next rebalance)                       │
│    4. Compute realised return + slippage                    │
│                                                            │
│  Aggregate:                                                │
│    Equity curve · daily returns · 20+ metrics per strat    │
│    Sector & industry attribution                            │
│    Failure analysis (worst trades, worst months, DD)        │
│    Self-improvement recommendations (advisory only)         │
│                                                            │
│  Publish:  6 JSON files + parquet + equity CSV             │
└──────────────────────────────────────────────────────────┘
```

## Directory structure

```
research/backtesting/
├── lib/
│   ├── pit_scorer.py        Point-in-time company scorer (subset of DEV020's
│   │                          11 dimensions computable from OHLCV alone)
│   ├── strategies.py        Top-N EW, Top-N score-weighted, EW universe,
│   │                          extensible via STRATEGIES dict
│   └── metrics.py           20 institutional metrics: CAGR, Sharpe, Sortino,
│                              Calmar, Treynor, Alpha, Beta, IR, Tracking
│                              Error, Max DD, Recovery, Profit Factor, Win
│                              Rate, Expectancy, Turnover, etc.
├── ingest/                  (empty — consumes existing parquet stores)
├── compute/
│   ├── backtest_engine.py   Walk-forward main loop with monthly rebalance
│   │                          Slippage-adjusted (10 bps × turnover)
│   ├── attribution.py       Sector + industry P&L attribution
│   └── failure_analysis.py  Worst 10 trades, worst 5 months, top DD episodes
├── publish/
│   └── bundle.py            Emits 6 JSON + parquet + equity CSV
├── tests/
│   └── test_smoke.py        26 tests including PIT no-look-ahead guarantee
├── run.py                    CLI with --start / --end / --strategies flags
└── README.md
```

## Point-in-time discipline

**The anti-look-ahead guarantee is the most important property of this engine.**

Given a ticker's OHLCV DataFrame `df` and a backtest date `T`,
`pit_scorer.score_ticker_at(df, T)` slices `df.loc[df.index <= T]` *before*
computing anything. Percentile normalisations, moving averages, momentum RoCs
— everything uses only bars available up to `T`.

The smoke test `test_pit_scorer_no_lookahead` verifies this: it computes a
score at date T, then appends fabricated future bars to the dataframe and
recomputes at the same T. The two scores must be byte-identical.

**Verified: they are.**

## Composite (10 dimensions)

Subset of DEV020's 11-dimension model — the ones computable from raw OHLCV
alone. Industry / sector RS dimensions from DEV020 are deferred to v0.2 (would
require rebuilding DEV018/019 aggregates at each PIT date, which is expensive).

| Dimension | Weight |
|:--|:-:|
| Momentum (blended 20/60/120d percentile) | 0.20 |
| RS vs Nifty 50 | 0.15 |
| Trend (MAs above count) | 0.13 |
| Volatility (inverted percentile) | 0.10 |
| Max drawdown (inverted, mapped) | 0.10 |
| 52-week position | 0.10 |
| Liquidity (ADV in INR crore percentile) | 0.08 |
| Volume trend (20d/90d ratio) | 0.07 |
| Breakout status | 0.05 |
| Technical strength (blend of momentum+trend+RS) | 0.02 |
| **Sum** | **1.00** |

Missing dimensions cause renormalisation + confidence reduction.

## Strategies

| ID | Description |
|:--|:--|
| `top_5_ew` | Top 5 by score, equal weight |
| `top_10_ew` | Top 10 by score, equal weight |
| `top_20_ew` | Top 20 by score, equal weight |
| `top_10_sw` | Top 10 by score, weight ∝ (score − 50) |
| `top_20_sw` | Top 20 by score, weight ∝ (score − 50) |
| `ew_universe` | Equal-weight all scored tickers (baseline) |

Rebalance frequency: **monthly (business month-end)**. Weekly and quarterly
are v0.2 follow-ups.

## Benchmarks

- **BENCHMARK_NIFTY50** — Nifty 50 from DEV017's raw store

DEV017 stores ~300 days of Nifty history by default. Backtest windows before
that are handled by restricting benchmark-relative metrics (alpha, beta, IR,
tracking error) to the **overlap window** only. This is documented in the
output:

```
"benchmark_overlap_start": "2025-09-15",
"benchmark_overlap_end":   "2026-06-30",
"benchmark_overlap_days":  204
```

For a full 2022-2026 benchmark comparison, fetch Nifty with a longer window
first: modify `research/global_intelligence/ingest/yfinance_ingest.py::fetch_variable`
to `period_days=1500` and re-run DEV017. (v0.2)

## Performance metrics (20+)

Computed per strategy:

**Return-based.** CAGR · Annual Volatility · Sharpe · Sortino · Calmar
**Benchmark-relative.** Alpha (CAPM) · Beta · Treynor · Information Ratio · Tracking Error
**Drawdown.** Max DD % · Peak date · Trough date · Recovery date · Recovery days
**Trade-level.** N trades · Win rate % · Loss rate % · Profit factor · Avg winner · Avg loser · Expectancy · Best trade · Worst trade
**Portfolio ops.** Turnover (annualised) · N rebalances · Avg positions

## Attribution (v0.1)

Trade-level sector and industry aggregation. For each sector (and industry):

- Number of trades
- Average per-trade return
- Cumulative contribution to portfolio P&L (weighted)
- Win rate

Signal-level attribution (which of the 10 dimensions drove alpha) is
**deferred to v0.2** — requires ablation runs with each dimension zeroed in
turn.

## Failure analysis

- **Worst 10 trades** — largest per-trade losses with entry/exit prices, sector
- **Best 10 trades** — for comparison
- **Worst 5 months** — largest monthly drawdowns
- **Best 5 months** — for comparison
- **Top 5 drawdown episodes** — ranked by depth, with start/trough/end/recovery duration

## Execution

```bash
# Prerequisites: DEV017-020 must have run at least once (need constituent parquets
# + Nifty 50 in shared raw store)

# Full default (2022-01-01 to 2026-06-30, all 6 strategies)
python research/backtesting/run.py

# Custom window
python research/backtesting/run.py --start 2023-01-01 --end 2025-12-31

# Subset of strategies
python research/backtesting/run.py --strategies top_10_ew,top_20_ew

# Smoke tests (no network)
python research/backtesting/tests/test_smoke.py    # 26 tests, all pass
```

## Outputs (all under `reports/`)

| File | Contents |
|:--|:--|
| `backtest_summary.json` | Universe size · rebal dates · full per-strategy metrics |
| `backtest_summary.parquet` | Flat metric table, one row per strategy |
| `strategy_comparison.json` | Compact leaderboard shape (CAGR/Sharpe/Alpha/DD/Turn per strategy) |
| `performance_metrics.json` | All metrics per strategy, verbose |
| `signal_attribution.json` | Sector + industry attribution per strategy |
| `failure_analysis.json` | Worst trades / months / drawdown episodes per strategy |
| `self_improvement.json` | Advisory recommendations (never auto-applied — ARCH001A Article V clause 5.1) |
| `backtest_equity_curves.csv` | Long-format equity curves per strategy + benchmark |

## First live run — 2026-07-17

```
Universe:       208 tickers
Window:         2022-01-01 → 2026-06-30 (54 monthly rebalances)
Strategies:     top_5/10/20_ew, top_10/20_sw, ew_universe
Elapsed:        79.6 seconds

STRATEGY LEADERBOARD (sorted by Sharpe):

  strategy               CAGR   Sharpe  Sortino  Calmar   Alpha   Beta    MaxDD    Turn   #Tr    Win%
  top_20_sw              0.241   1.06    1.24    1.22    0.300   0.83   -19.68   8.01  1060   58.30
  top_20_ew              0.240   1.06    1.24    1.19    0.302   0.85   -20.19   7.73  1060   58.30
  top_5_ew               0.248   0.97    1.20    0.98    0.297   0.75   -25.24   9.96   265   60.75
  ew_universe            0.178   0.80    0.99    0.88    0.266   1.04   -20.38   0.01 10957   54.74
  top_10_sw              0.201   0.78    0.94    0.85    0.256   0.80   -23.76   9.10   530   57.74
  top_10_ew              0.195   0.75    0.91    0.81    0.251   0.80   -24.08   8.97   530   57.74
  BENCHMARK_NIFTY50     -0.049  -0.71   -0.99   -0.32    n/a     n/a    -15.18   n/a    n/a    n/a
```

**Every AEGIS-scored strategy delivers positive alpha vs Nifty 50 on this dataset**
(over the 10-month benchmark overlap window). Top-20 strategies show the
highest Sharpe/Sortino, top-5 shows the highest CAGR but worst MaxDD (thin
diversification).

**Read carefully:** these results are on the *same dataset* that trained the
DEV017-020 weight tables. Full walk-forward would require future out-of-sample
periods to accumulate before the numbers can be treated as unbiased. See
ARCH001A Article IV clause 4.3.

## Reuse discipline

Every canonical entity — none in DEV021 uses ARCH017A dataclasses directly
because the backtest works with raw return series, but the design principles
(deterministic, PIT-safe, code-SHA stamped, reproducible) are honoured. Metric
functions are pure and seeded where randomness is involved (bootstrap methods
in v0.2 will use fixed seeds).

Company sector/industry lookup is imported from
`research/company_intelligence/lib/company_catalog.py` — no duplicated ticker
map.

## Governance

- **NO** BUY/SELL/EXIT signals emitted. Advisory only.
- Self-improvement recommendations are **never auto-applied** (ARCH001A
  Article V clause 5.1).
- Sealed core (MON001) untouched.
- Structurally isolated under `research/backtesting/`; not importable by
  production per ARCH001A Article VII clause 7.1.

## v0.2 follow-ups

- Backfill Nifty 50 with 1500+ days for full-window benchmark comparison
- Weekly + quarterly rebalance
- Signal-level attribution via ablation
- Regime-conditional metrics (bull / bear / high-vol / election year windows)
- Multi-benchmark comparison (Nifty 500, sector indices)
- Bootstrap confidence intervals on Sharpe/Alpha (deflated Sharpe from Bailey
  & López de Prado)
- Full DEV018/019 layer historical re-computation for true stack backtest
- Risk-parity + volatility-targeting strategies
- Paper-trade mode (real-time signals on live prices)
