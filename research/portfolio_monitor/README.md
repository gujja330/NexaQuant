# DEV024 — Portfolio Monitoring & Rebalancing Engine (v0.1)

Watches a live portfolio, refreshes market values from latest parquet closes,
computes drift, generates alerts + rebalance quantities, and produces an
institutional-grade monitoring bundle. **Advisory only. No orders placed.**

## Pipeline position

```
DEV023 Recommendations → reports/recommendations.json
DEV022 Portfolios       → reports/portfolio.json
        ↓
        holdings.json (operator-maintained) or --demo (synthesised)
        ↓
┌───────────────────────────────────────────────────────┐
│  DEV024  Portfolio Monitoring & Rebalancing            │
│                                                         │
│  1. Load holdings, refresh market values                 │
│  2. Compute exposures + attribution                      │
│  3. Scan alerts (target/stop/drift/DD/time-exit/rec)     │
│  4. Generate rebalance plan (exact share deltas)         │
│  5. Compute portfolio health score                       │
│                                                         │
│  Publish: 5 JSON + 1 parquet                            │
└───────────────────────────────────────────────────────┘
```

## Directory structure

```
research/portfolio_monitor/
├── lib/
│   ├── holdings.py         Portfolio + Position dataclasses; JSON loader;
│   │                          market-value refresh; --demo synthesiser
│   └── alerts.py           Alert engine — 11 alert types
├── ingest/                  (empty)
├── compute/
│   └── engine.py            Main orchestrator: exposures + attribution +
│                              rebalance planning + health scoring
├── publish/
│   └── bundle.py            5 JSON + parquet outputs
├── tests/
│   └── test_smoke.py        20 tests, all pass
├── run.py                    CLI
└── README.md
```

## Holdings JSON schema

```json
{
    "portfolio_id":            "my_portfolio_2026-07-15",
    "created_date":            "2026-07-15",
    "cash":                    500000,
    "total_invested_capital":  10000000,
    "holdings": [
        {
            "ticker":                "IPCALAB",
            "shares":                500,
            "avg_cost":              1850.00,
            "target_weight":         0.10,
            "entry_date":            "2026-07-15",
            "recommendation_type":   "Strong-Buy",
            "recommendation_source": "DEV023",
            "target_price":          2070,
            "stop_loss":             1698,
            "trailing_stop":         1720
        }
    ]
}
```

## 11 Alert types

| Alert | Trigger |
|:--|:--|
| **STOP_LOSS_HIT** | latest_close ≤ stop_loss (severity: CRITICAL) |
| **TRAILING_STOP_TRIGGERED** | latest_close ≤ trailing_stop (WARNING) |
| **TARGET_REACHED** | latest_close ≥ target_price (INFO) |
| **WEIGHT_DRIFT** | \|current − target\| / target > 25% (WARNING) |
| **PORTFOLIO_DRAWDOWN_WARNING** | Portfolio PnL < −10% (WARNING) |
| **PORTFOLIO_DRAWDOWN_CRITICAL** | Portfolio PnL < −15% (CRITICAL) |
| **TIME_EXIT_DUE** | days_held ≥ max_holding_days (CRITICAL) |
| **TIME_EXIT_APPROACHING** | days_held ≥ max − 15d (INFO) |
| **CONFIDENCE_DROP** | Current DEV023 rec = Sell/Avoid (CRITICAL) |
| **CONFIDENCE_DROP_MODERATE** | Current DEV023 rec = Reduce (WARNING) |
| **NO_PRICE_DATA** | No parquet data for ticker (WARNING) |

## Rebalance actions

For each position:

| Action | Trigger |
|:--|:--|
| **CLOSE_POSITION** | DEV023 recommendation = Sell (priority 1) |
| **REDUCE_POSITION** | DEV023 recommendation = Reduce → halve position (priority 2) |
| **DECREASE_POSITION** | Current weight > target × 1.25 (priority 3) |
| **INCREASE_POSITION** | Current weight < target × 0.75 (priority 4) |

Only actions above min-threshold (1 share, INR 1000 value) are emitted.

## Execution

```bash
# Operator-maintained portfolio:
python research/portfolio_monitor/run.py --holdings my_portfolio.json

# Demo portfolio from top DEV023 recommendations:
python research/portfolio_monitor/run.py --demo
python research/portfolio_monitor/run.py --demo --portfolio-type top_5_ew
python research/portfolio_monitor/run.py --demo --capital 5000000

# Smoke tests
python research/portfolio_monitor/tests/test_smoke.py    # 20 tests, all pass
```

## Outputs

| File | Contents |
|:--|:--|
| `reports/portfolio_monitor.json` | Full portfolio snapshot: positions, exposures, health |
| `reports/portfolio_monitor.parquet` | Flat per-position table |
| `reports/rebalance_plan.json` | Prioritised action plan with exact share deltas |
| `reports/performance_report.json` | PnL + attribution (winners/losers by sector/industry) |
| `reports/alerts.json` | All alerts with severity + type breakdown |
| `reports/portfolio_health.json` | Health score + concentration + exposures |
| `reports/holdings_demo.json` | (only with `--demo`) Synthesised portfolio for reference |

## First live demo run — 2026-07-17

```
Demo portfolio: 10 positions from top DEV023 Strong-Buy/Buy recs
Capital:        INR 10,000,000 (5% cash reserve)

Portfolio ID:     demo_top_10_ew_2026-07-17
Total value:      INR 9,990,813
Invested:         INR 10,000,000
P&L:              INR −9,187 (−0.09%)  [day-0, minimal drift]
Cash:             INR 500,000 (5.00%)
Positions:        10 total, 10 priced
Effective N:      11.08   HHI=0.0902
Top sector:       Pharma (47.5%)
Health score:     100.0/100

Alerts:           0 (fresh portfolio, no drift/stops/deterioration yet)

Rebalance plan:   10 INCREASE_POSITION actions
                  (5% cash reserve creates initial 0.5%-per-position drift)

Winners/Losers:   all near-zero (fresh entry)
```

## Portfolio health score (0-100)

```
health_score = 100 − 10 × n_critical_alerts − 2 × n_warning_alerts
```

Range map:

- **90-100**: All clear
- **70-89**: Minor drift or warnings
- **50-69**: Multiple warnings or a critical alert
- **< 50**: Multiple critical alerts — operator intervention needed

## Reuse discipline

- Sector/industry lookup: from DEV020 `company_catalog` — no re-computation.
- DEV023 recommendations JSON directly consumed for confidence-drop alerts + rebalance guidance.
- Position dataclass matches DEV023 output shape.
- Latest close prices read from `data/raw/india/*.parquet` (same source everything else uses).

## Governance

- **Advisory only.** No orders placed. No broker integration.
- Every rebalance action carries a `reason` field traceable to source signal.
- Sealed core untouched · MON001 fingerprint invariant.
- Structurally isolated under `research/portfolio_monitor/`.
- Health score is a proxy — not a substitute for operator review.

## v0.2 follow-ups

- Multi-portfolio monitoring (currently one at a time)
- Historical portfolio equity curve tracking (currently point-in-time only)
- Actual daily portfolio value snapshotting (needs a persistent store)
- Corporate-action handling (splits, bonuses, dividends)
- Realised-PnL tracking (currently only unrealised)
- Comparison to DEV022 target-portfolio drift over time
- Liquidity-risk alert (ADV-based) — blocked on richer volume history
- Regime-aware alert thresholds (tighter alerts in Risk-Off regimes)
- Sector-drift alerts vs DEV022 targets
