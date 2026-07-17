# DEV030 — Champion vs Challenger Strategy Framework

**Sprint 15 · Core Quantitative Engine.** Ranks the strategy universe,
picks a champion by evidence, tracks drift, and recommends promotions when
statistical gates are cleared.

> Advisory-only per ARCH001A Article V clause 5.1. No mutation to the
> recommendation engine, HRP, rebal, or any sealed core.

---

## What it does

Given the backtested strategy metrics from DEV021 (`backtest_summary.parquet`),
compute a composite score, rank all strategies, and evaluate whether a
challenger should replace the incumbent champion.

Ranking is done via **min-max normalisation of 9 metrics** (Sharpe, Sortino,
Calmar, Info Ratio, CAGR, Max DD, Win Rate, Profit Factor, Expectancy) and a
transparent weight vector (see `lib/scoring.py::WEIGHTS`).

**Promotion gates** — a challenger is only recommended over the incumbent
champion when ALL of these clear:
- **Margin:** composite score improvement >= 3.0 points
- **Stability:** challenger's 2nd-half Sharpe is not degrading
- **Sample:** both strategies have >= 30 completed trades on record
- **Drawdown:** challenger's max DD is not >5pp worse than champion's

---

## Inputs

- `reports/backtest_summary.parquet` (DEV021) — one row per strategy with
  Sharpe/Sortino/Calmar/CAGR/max_dd/info_ratio/win_rate/profit_factor/expectancy.
- `reports/backtest_equity_curves.csv` (DEV021, optional) — for drift + regime
  analysis.
- `reports/global_context.json` (DEV017) — current regime posture.
- `reports/portfolio.parquet` (DEV022) — 99 challenger portfolio constructions
  (recorded as candidate universe; not yet ranked head-to-head because they
  lack backtest history).
- `reports/confidence_calibration.json` (DEV029) — calibration note appended
  to champion output.

## Outputs (7)

Written to `reports/`:

- **`champion_strategy.json`** — current champion, its metrics, current
  regime, calibration note, governance stamp.
- **`challenger_scoreboard.json`** — full leaderboard + challenger portfolio
  candidate count.
- **`head_to_head_matrix.json`** — pairwise deltas across every pair.
- **`regime_comparison.json`** — per-strategy performance conditional on
  Risk-On / Risk-Off / Neutral regimes.
- **`drift_report.json`** — 1st-half vs 2nd-half stability per strategy +
  rank drift vs prior run.
- **`promotion_recommendation.json`** — decision + gates + reasoning.
- **`strategy_leaderboard.parquet`** — full ranked table with normalised
  metric columns.

Also appended to:
- `data/market_intelligence/derived/champion_history.parquet`
- `data/market_intelligence/derived/champion_challenger_history.parquet`

## Composite scoring weights

| Metric | Weight | Direction |
|---|---:|:---:|
| Sharpe | 25% | higher better |
| Sortino | 15% | higher better |
| Calmar | 15% | higher better |
| Info Ratio | 10% | higher better |
| CAGR | 10% | higher better |
| Max DD | 10% | lower better (inverted) |
| Win Rate | 5% | higher better |
| Profit Factor | 5% | higher better |
| Expectancy | 5% | higher better |

Each metric is min-max normalised to [0, 100] within the strategy universe
before weighting. Composite score is comparable across runs only if universe
membership is stable.

## Governance

- Advisory-only; the champion output is a recommendation, not an action.
- Promotion history is append-only; no rewrite of past decisions.
- Retrain / re-rank only when new backtest data is available. Drift-based.

## Run

```
python research/champion_challenger/run.py
python research/champion_challenger/tests/test_smoke.py
```

## Layout

```
research/champion_challenger/
  lib/
    strategies_io.py   — load DEV021/022/017/029 outputs from disk
    scoring.py         — composite score + leaderboard
    head_to_head.py    — pairwise delta matrix
    regime.py          — regime-conditional performance
    drift.py           — 1st-half vs 2nd-half stability + rank drift
    promotion.py       — 4-gate promotion decision
  compute/
    engine.py          — orchestration
  publish/
    bundle.py          — 7 outputs
  tests/
    test_smoke.py
  run.py               — CLI
```
