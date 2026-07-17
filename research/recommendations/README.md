# DEV023 — Recommendation & Trade Decision Engine (v0.1)

Converts DEV020 scores + DEV022 target portfolios into actionable
recommendations (Strong-Buy / Buy / Accumulate / Hold / Reduce / Sell / Avoid
/ Watchlist) with entry/exit levels and full rationale per ticker.

**Advisory only. No broker integration. No order placement.**

## Pipeline position

```
DEV020 Company Intelligence → company_context.json
DEV022 Portfolios            → portfolio.json, risk_report.json
        ↓
┌────────────────────────────────────────────────────────┐
│  DEV023  Recommendation & Trade Decision Engine        │
│                                                          │
│  For each AEGIS ticker:                                 │
│    1. Extract flat signals from hierarchy                │
│    2. Check if in high-Sharpe target portfolios          │
│    3. Compare vs current holdings (optional)             │
│    4. Apply deterministic decision rules                 │
│    5. Compute entry/exit levels (vol-scaled)             │
│    6. Build rationale (reasons_for + reasons_against)    │
│                                                          │
│  Publish: 5 JSON outputs                                │
└────────────────────────────────────────────────────────┘
```

## Directory structure

```
research/recommendations/
├── lib/
│   ├── decisions.py         Deterministic rules → 8 recommendation types
│   │                          + composite_decision_score + conviction
│   └── entry_exit.py        Vol-scaled entry zones + targets + stops
│                              + expected/max holding periods
├── ingest/                   (empty)
├── compute/
│   └── engine.py             Main orchestration + hierarchy lookup +
│                              current-position enrichment
├── publish/
│   └── bundle.py             5 JSON outputs
├── tests/
│   └── test_smoke.py         26 tests, all pass
├── run.py                    CLI
└── README.md
```

## 8 Recommendation types (deterministic rules)

**For new positions (not currently held):**

| Type | Trigger |
|:--|:--|
| **Strong-Buy** | score ≥ 75 AND classification = Strong-Bullish AND confidence ≥ 0.7 AND in target portfolio |
| **Buy** | classification ∈ {Strong-Bullish, Bullish} AND score ≥ 60 AND confidence ≥ 0.6 |
| **Watchlist** | score 55–60, OR classification ∈ {Bullish, Neutral} with score ≥ 50 |
| **Avoid** | classification = Bearish OR score < 35 |

**For currently-held positions:**

| Type | Trigger |
|:--|:--|
| **Sell** | classification = Bearish OR score < 30 OR unrealised loss > 8% |
| **Reduce** | classification = Weak OR score < 45 OR sector deteriorating |
| **Accumulate** | Still in target portfolio + Strong-Bullish + score ≥ 70 |
| **Hold** | Default for existing positions in reasonable shape |

## Composite Decision Score (0-100)

Blend of company/industry/sector/global into a single score, confidence-attenuated:

```
CDS = confidence × weighted_avg + (1 - confidence) × weighted_avg × 0.6

  where weights: company 0.50 · industry 0.20 · sector 0.15 · global 0.10
```

## Conviction

Direction-adjusted expression of composite score. For BUY-side recs, conviction
tracks CDS. For SELL-side, conviction is 100 - CDS.

## Entry/Exit levels (vol-scaled)

Every buy-side rec includes:

| Level | Calculation |
|:--|:--|
| Ideal entry zone | 20-DMA ± 1.5% |
| Breakout entry | 20-day high × 1.005 |
| Pullback entry | 50-DMA × 0.99 (if MA-50 exists) |
| Support entry | 20-day low × 1.02 |
| Momentum entry | max(latest × 1.005, breakout) if strong |
| Target 1 (conservative) | latest × (1 + 1.5 × σ_20d), clamped to [6%, 12%] |
| Target 2 (aggressive) | latest × (1 + 3.0 × σ_20d), clamped to [12%, 25%] |
| Stop loss | latest × (1 − vol_scaled_pct), floored at −6%, max −10% |
| Trailing stop | latest × (1 − vol_scaled_pct) |
| Expected holding | 60 days (or 90 for Accumulate) |
| Maximum holding | 90 days (or 135 for Accumulate) |

All levels scale to each ticker's 20-day realised volatility — high-vol names
get wider stops and larger targets automatically.

## Current holdings (optional)

Pass `--holdings holdings.json` where the file structure is:

```json
{
    "holdings": [
        {"ticker": "INFY", "shares": 100, "avg_cost": 1500, "current_weight": 0.10},
        {"ticker": "TCS", "shares": 50, "avg_cost": 3200, "current_weight": 0.08}
    ]
}
```

Without holdings, every recommendation is treated as a potential new position.
With holdings, existing positions get Hold/Sell/Reduce/Accumulate logic.

## Execution

```bash
# Prereqs: DEV020 + DEV022 must have run
python research/company_intelligence/run.py
python research/portfolio_construction/run.py

# Then DEV023
python research/recommendations/run.py
python research/recommendations/run.py --holdings holdings.json
python research/recommendations/run.py --min-target-sharpe 1.0     # widen target filter

# Smoke tests
python research/recommendations/tests/test_smoke.py                # 26 tests, all pass
```

## Outputs

| File | Contents |
|:--|:--|
| `reports/recommendations.json` | Every ticker with full decision + entry/exit + rationale |
| `reports/recommendations.parquet` | Flat one-row-per-ticker table |
| `reports/watchlist.json` | Watchlist-only subset |
| `reports/trade_summary.json` | Grouped by recommendation type with condensed rows |
| `reports/execution_plan.json` | Ordered execution plan (by conviction desc within action type) |

## First live run — 2026-07-17

```
Universe:      208 companies from DEV020
Elapsed:       5.9 seconds

RECOMMENDATION SUMMARY:
  Strong-Buy    7
  Buy          44
  Watchlist    30
  Avoid       127

TOP 10 EXECUTION ORDER:
  IPCALAB      Strong-Buy   conv=79.7%   @1863   T1=2070   SL=1698   Pharma
  KALYANKJIL   Strong-Buy   conv=74.8%   @560    T1=627    SL=504    Consumption
  SONACOMS     Strong-Buy   conv=74.2%   @699    T1=769    SL=643    Auto
  EXIDEIND     Strong-Buy   conv=72.9%   @430    T1=482    SL=387    Auto
  ZYDUSLIFE    Strong-Buy   conv=72.2%   @1143   T1=1239   SL=1066   Pharma
  RADICO       Strong-Buy   conv=68.0%   @4113   T1=4496   SL=3807   FMCG
  OFSS         Strong-Buy   conv=61.2%   @11619  T1=13013  SL=10457  IT
  LODHA        Buy          conv=74.6%   @1181   T1=1323   SL=1063   Realty
  GLAND        Buy          conv=74.2%   @2451   T1=2745   SL=2206   Pharma
  GODREJPROP   Buy          conv=72.2%   @2136   T1=2363   SL=1954   Realty
```

Every Strong-Buy carries positive alpha signal from DEV020 + target-portfolio
confirmation + defensible entry/target/stop levels scaled to its own vol.

## Rationale generation

Every recommendation carries `reasons_for` and `reasons_against` lists:

```
IPCALAB Strong-Buy:
  reasons_for:
    - company_score_top_decile:83.5
    - high_confidence:0.98
    - industry_strong:Pharma-Mid-Cap:84.3
    - sector_strong:Pharma:80.5
    - in_target_portfolios:9
```

## Governance

- **Advisory only.** No orders placed. No broker integration (deferred to ARCH011).
- Sealed core untouched · MON001 fingerprint invariant.
- Every recommendation traces to the underlying DEV020/DEV021/DEV022 signals
  via `reasons_for` / `reasons_against`.
- Deterministic: same input produces same output (test_determinism verifies).
- Structurally isolated under `research/recommendations/`.

## Reuse discipline

- Company/sector/industry lookup: from DEV020 `company_context.json` (no
  re-computation).
- Target portfolios: from DEV022 `portfolio.json`.
- Historical prices: from `data/raw/india/*.parquet`.
- No new schema — plain dicts + typed dataclasses (`DecisionInput`, `Decision`,
  `EntryExitLevels`).

## v0.2 follow-ups

- Regime-conditional decision rules (bear regime → tighter Buy criteria)
- Position sizing suggestions (ties to DEV022 allocation)
- Multi-portfolio target awareness (e.g. only recommend if in ≥ 3 target portfolios)
- Historical hit-rate calibration of Strong-Buy vs Buy tiers (needs DEV021 attribution)
- News-driven overrides (blocked on ARCH026)
- Rebalance vs new-recommendation logic (ties to DEV024 planned Portfolio Monitoring)
