# AEGIS Phase 2 · Institutional Intelligence Architecture (Sprints 4-9)
**Locked design · 2026-07-21 · Author: aegis-core with operator sign-off pending**

> **Purpose:** This is the *single* architectural specification for every remaining sprint (4 through 9) plus cross-cutting layers (Reporting, Explainability, Benchmarks, Regime Analytics, Statistical Validation, Research Factory). Once this is signed off, downstream sprints are pure implementation work — no more re-architecting mid-flight.

---

## Table of Contents

1. [Cross-cutting principles (recap of locked contracts)](#cross-cutting-principles-recap-of-locked-contracts)
2. [Phase 2 pipeline diagram](#phase-2-pipeline-diagram)
3. **[Sprint 4 · Risk Engine](#sprint-4--risk-engine)**
4. **[Sprint 5 · Portfolio Engine](#sprint-5--portfolio-engine)**
5. **[Sprint 6 · Learning Engine](#sprint-6--learning-engine)**
6. **[Sprint 7 · Execution Simulator](#sprint-7--execution-simulator)**
7. **[Sprint 8 · Institutional Walk-Forward Validation](#sprint-8--institutional-walk-forward-validation)**
8. **[Sprint 9 · AI Validation Auditor](#sprint-9--ai-validation-auditor)**
9. **[Sprint 10 · Research Factory](#sprint-10--research-factory)**
10. [Cross-cutting concerns](#cross-cutting-concerns)
    - Institutional Reporting · Explainability · Benchmark Engine · Regime Analytics · Statistical Validation · Research Factory
10. [Data model — every JSON schema + dataclass](#data-model--every-json-schema--dataclass)
11. [AI agents catalog](#ai-agents-catalog)
12. [Testing / acceptance criteria per sprint](#testing--acceptance-criteria-per-sprint)
13. [Sprint prompts — ready to invoke](#sprint-prompts--ready-to-invoke)

---

## 🔒 Governing constraint (operator-locked 2026-07-21)

> **Do NOT redesign previous architecture.** Every new sprint MUST consume the outputs of previous completed sprints (Feature Store → Feature Intelligence → Model Factory → Recommendation Engine). All engines must remain deterministic, replayable, append-only, walk-forward safe, AI-assisted (never AI-controlled), and backward compatible.

Sprint 4 onward is pure implementation against this specification. If a sprint requires a schema change to an earlier engine, the change MUST be:
1. Non-breaking (additive fields only, or a schema-version bump)
2. Documented in a `docs/AEGIS_SCHEMA_CHANGELOG.md` entry
3. Approved via `backend.promotion.promotion_gate.approve_model` for any promoted engine

No exceptions.

---

## Cross-cutting principles (recap of locked contracts)

Every Phase 2 sprint MUST honor these — they are locked in memory and enforced by contract tests:

| # | Principle | Reference memory |
|---|---|---|
| 1 | **Deterministic** — same inputs + same cutoff → identical output. No random state, no `time.time()`, no `datetime.now()` inside model logic. Pass timestamps in from the caller. | [[aegis_institutional_walkforward]] |
| 2 | **Walk-forward safe** — every engine accepts a `cutoff: date` argument; no row with `date > cutoff` may enter the computation. | [[aegis_institutional_walkforward]] |
| 3 | **Append-only storage** — every persistent artifact (features, learning corpus, execution ledger, promotion ledger, model registry) is append-only. Never overwrite history. | [[aegis_data_persistence]] |
| 4 | **Human-in-the-loop for promotion** — no feature, model, weight change, or strategy config reaches production automatically. Promotion goes through `backend.promotion.promotion_gate.approve_model / approve_feature` with WF evidence + operator identity. | [[aegis_self_learning]] |
| 5 | **AI never recommends or promotes** — AI agents explain, validate, summarize, propose. AI outputs never contain `buy`/`sell`/`target_price`/`recommendation`/`action`/`promoted`/`approved` keys (contract-tested). | [[aegis_ai_embedded_architecture]] |
| 6 | **Model registry stamp on every decision** — every engine that emits a per-ticker decision must call `backend.model_registry.stamp(model_id)` and embed the returned dict in its output. Walk-forward replay reconstructs which model+features+approval were in effect. | [[aegis_model_factory]] |
| 7 | **Feature Store is the sole input** — no engine reads raw canonical data. All inputs come from `features/{market}/YYYY-MM-DD.parquet` filtered through `selected_features.json`. | [[aegis_feature_store]], [[aegis_feature_intelligence]] |
| 8 | **Tenant-generic** — no hardcoded ticker lists, sector names, or country-specific constants inside engines. Everything comes from `MarketProfile` + `universe.json` + `datasets.yaml`. | [[feedback_tenant_generic]] |
| 9 | **Currency invariant** — India rows carry INR + `₹`; USA rows carry USD + `$`. Never mix. Every monetary field is labelled with its currency. | [[aegis_usa_v1_locked]] |
| 10 | **Legacy separation** — `research/adaptive_rec_v2/` is UNTOUCHED. New engines live under `backend/{engine}/` with per-market runners at `india/{engine}/run.py` and `usa/research/{engine}/run.py`. | [[aegis_recommendation_v3]] |

---

## Phase 2 pipeline diagram

```
                     ┌────────────────────────────────────────┐
                     │             MARKET DATA                │
                     └────────────────┬───────────────────────┘
                                      │  daily ingest (append-only)
                                      ▼
                     ┌────────────────────────────────────────┐
                     │      CANONICAL DATA MODEL              │
                     │      (9 row kinds · Sprint 2)          │
                     └────────────────┬───────────────────────┘
                                      ▼
                     ┌────────────────────────────────────────┐
                     │      FEATURE STORE                     │
                     │      (81 features · Sprint 2.5)        │
                     └────────────────┬───────────────────────┘
                                      ▼
                     ┌────────────────────────────────────────┐
                     │      FEATURE INTELLIGENCE              │
                     │      (governance · drift · selection)  │
                     │      (Sprint 2.6)                      │
                     └────────────────┬───────────────────────┘
                                      │ selected_features.json
                                      ▼
                     ┌────────────────────────────────────────┐
                     │      MODEL FACTORY                     │
                     │      (11 models · ensemble · Sprint 2.7)│
                     └────────────────┬───────────────────────┘
                                      │ ensemble.json
                                      ▼
                     ┌────────────────────────────────────────┐
                     │      RECOMMENDATION INTELLIGENCE v3    │
                     │      (Sprint 3 · BUY/SELL/HOLD)        │
                     └────────────────┬───────────────────────┘
                                      │ recommendations_v3.json
                                      ▼
                     ┌────────────────────────────────────────┐
                     │       RISK ENGINE          [Sprint 4]  │
                     │  position sizing · exposure caps ·     │
                     │  vol adj · sector limits · Kelly       │
                     └────────────────┬───────────────────────┘
                                      │ sized_positions.json
                                      ▼
                     ┌────────────────────────────────────────┐
                     │       PORTFOLIO ENGINE     [Sprint 5]  │
                     │  N-name portfolio · weights ·          │
                     │  rebalance · diversification           │
                     └────────────────┬───────────────────────┘
                                      │ portfolio_v3.json
                                      ▼
                     ┌────────────────────────────────────────┐
                     │       LEARNING ENGINE      [Sprint 6]  │
                     │  prediction ↔ outcome ledger ·         │
                     │  feature/model attribution ·           │
                     │  confidence calibration ·              │
                     │  failure clustering                    │
                     └────────────────┬───────────────────────┘
                                      │ learning_corpus.parquet
                                      ▼
                     ┌────────────────────────────────────────┐
                     │       EXECUTION SIMULATOR  [Sprint 7]  │
                     │  realistic fills · slippage ·          │
                     │  commissions · gaps · corp actions     │
                     └────────────────┬───────────────────────┘
                                      │ simulated_fills.parquet + equity_curve.parquet
                                      ▼
                     ┌────────────────────────────────────────┐
                     │  INSTITUTIONAL WALK-FORWARD  [Sprint 8]│
                     │  freeze → full-stack replay →          │
                     │  performance metrics × N windows       │
                     └────────────────┬───────────────────────┘
                                      │ walkforward/{market}/{cutoff}.json
                                      ▼
                     ┌────────────────────────────────────────┐
                     │   AI VALIDATION AUDITOR    [Sprint 9]  │
                     │  why? which regimes? which models?     │
                     │  which features? next hypotheses       │
                     └────────────────────────────────────────┘
```

Cross-cutting (touch every layer):
- **Reporting** (PDF · daily/weekly/monthly/quarterly/annual)
- **Explainability** (every decision traceable)
- **Benchmark Engine** (NIFTY / S&P / equal-weight / buy-hold / random)
- **Regime Analytics** (bull/bear/sideways/high-vol/etc)
- **Statistical Validation** (Sharpe/Sortino/Calmar/IR/Alpha/Beta/…)
- **Research Factory** (candidate features + models + strategies)

---

## Sprint 4 · Risk Engine

### Purpose

Convert Recommendation Intelligence v3 (BUY/SELL/HOLD calls) into **sized positions** with explicit risk budgets. Enforces exposure caps, sector concentration limits, volatility-adjusted sizing, and Kelly-fractional bet sizing.

### Inputs

- `reports/recommendations_v3.json` (Sprint 3 output — per-ticker action, calibrated_confidence, ensemble_score, etc.)
- `reports/market_intelligence_summary.json` (regime, VIX)
- `reports/feature_intelligence.json` (selected features)
- Feature snapshot for volatility/liquidity per ticker
- Portfolio priors: `configs/risk_budget.yaml` (operator-owned)

### Output

- `reports/sized_positions.json` — per-ticker target weight, target notional, risk budget consumed
- `reports/risk_report.json` — portfolio-level metrics (concentration, sector exposure, expected VaR)
- `reports/ai_risk_narrative.json` — AI Risk Analyst

### File layout

```
backend/risk/
  __init__.py
  types.py                   # SizedPosition, RiskBudget, RiskReport dataclasses
  sizing.py                  # Kelly-fractional + confidence-weighted sizing
  exposure_caps.py           # per-ticker, per-sector, per-country caps
  vol_adjustment.py          # inverse-vol scaling; VIX regime dampener
  concentration.py           # HHI, top-K concentration checks
  var_cvar.py                # parametric VaR + CVaR from feature-based vol
  engine.py                  # RiskEngine.run() composes everything
backend/ai/risk_analyst.py   # per-portfolio narrative + budget audit
india/risk_engine/run.py     # emits reports/sized_positions.json + risk_report.json
usa/research/risk_engine/run.py
configs/risk_budget.yaml     # operator-owned config
```

### Core types

```python
@dataclass
class SizedPosition:
    market:              str
    ticker:              str
    action:              str                    # BUY / STRONG_BUY / SELL / STRONG_SELL / HOLD
    ensemble_score:      float
    confidence:          float                  # regime_adjusted from Sprint 3
    target_weight:       float                  # 0..cap (long) or 0..-cap (short)
    target_notional:     float                  # in market currency
    risk_budget_bps:     float                  # bps of portfolio risk consumed
    stop_loss_pct:       float                  # e.g. -0.08 for -8%
    take_profit_pct:     float | None
    vol_20d_annualised:  float
    kelly_fraction:      float                  # theoretical Kelly (before capping)
    cap_reason:          str                    # "kelly" | "per_ticker_cap" | "sector_cap" | "confidence_gate"
    model_stamp:         dict

@dataclass
class RiskReport:
    market:                    str
    asof:                      date
    n_positions:               int
    total_long_exposure_pct:   float
    total_short_exposure_pct:  float
    cash_pct:                  float
    hhi_concentration:         float           # 0..1
    top_5_concentration_pct:   float
    per_sector_exposure_pct:   dict[str, float]
    portfolio_var_95_1d_pct:   float
    portfolio_cvar_95_1d_pct:  float
    verdict:                   str             # PASS | WARNING | FAIL
    breaches:                  list[dict]
```

### Sizing formula (Sprint 4 baseline)

For every BUY / STRONG_BUY:

```
raw_kelly    = confidence × ensemble_score / vol_20d_annualised²
kelly_frac   = min(raw_kelly, MAX_KELLY_FRACTION)    # e.g. 0.25 = 25% Kelly
size_by_conf = kelly_frac × CONFIDENCE_TIER_MULT[action]     # STRONG_BUY: 1.0, BUY: 0.6
size_by_vol  = size_by_conf × (TARGET_VOL / vol_20d_annualised)
target_wgt   = min(size_by_vol, PER_TICKER_CAP, sector_headroom)
```

For SELL / STRONG_SELL: same magnitude but short-side. (For Sprint 4 baseline we may treat SELL as "trim/exit existing long only" and gate outright shorting behind `configs/risk_budget.yaml`'s `enable_shorts` flag.)

### Configurable risk parameters (`configs/risk_budget.yaml`)

```yaml
market_defaults:
  india:
    max_kelly_fraction:       0.25
    per_ticker_cap:           0.06     # 6% per name
    per_sector_cap:           0.25     # 25% per sector
    target_portfolio_vol:     0.15     # 15% annualised
    enable_shorts:            false
    default_stop_loss_pct:    -0.08
    confidence_tier_mult:
      STRONG_BUY:  1.00
      BUY:         0.60
      SELL:       -0.60
      STRONG_SELL: -1.00
  usa:
    max_kelly_fraction:       0.30
    per_ticker_cap:           0.08
    per_sector_cap:           0.30
    target_portfolio_vol:     0.14
    enable_shorts:            true
    default_stop_loss_pct:    -0.10
```

### Post-run acceptance (contract-tested)

- No `target_weight` > `per_ticker_cap`
- No sector's total weight > `per_sector_cap`
- Every position has a non-null `stop_loss_pct`
- Every SizedPosition carries a `model_stamp` from `backend.model_registry`
- Portfolio VaR & CVaR computed and stored (parametric — enough to enforce a portfolio-vol cap)
- Deterministic (contract test: same inputs → same weights to 4dp)
- Walk-forward safe (accepts cutoff; no future data)

### AI Risk Analyst

Emits `ai_risk_narrative.json` with:
- Portfolio composition summary (long/short/cash split, sector concentration, top-5 concentration)
- Budget audit: fraction of Kelly-optimal that was capped
- Regime consistency: does the exposure match the regime? (bull regime with mostly cash → flag)
- Downgrade candidates: positions with confidence borderline enough that a small drop would exit them

Contract tests same as Sprint 3 analyst.

---

## Sprint 5 · Portfolio Engine

### Purpose

Take `sized_positions.json` and construct the **investable portfolio**: which N names, at what weights, when to rebalance, and how it fits diversification / cash / risk-budget constraints.

### Inputs

- `reports/sized_positions.json` (Sprint 4 output)
- `reports/risk_report.json`
- `configs/portfolio_config.yaml` (target N names, rebalance cadence, min position size)
- Prior state: `reports/portfolio_state.json` (yesterday's holdings — for rebalance diff)

### Output

- `reports/portfolio_v3.json` — final holdings with weights + intended actions vs prior state
- `reports/portfolio_diff.json` — trades needed (buy X, sell Y, add Z%)
- `reports/portfolio_state.json` — updated state (append-only history at `reports/portfolio_state_history.jsonl`)
- `reports/ai_portfolio_narrative.json`

### File layout

```
backend/portfolio/
  __init__.py
  types.py                   # Position, PortfolioSnapshot, Diff
  construction.py            # top-N selection + reweighting
  diversification.py         # HHI/sector/style constraints
  rebalance.py               # diff yesterday vs today; produce trade list
  cash_manager.py            # cash policy (min 5% cash, boost cash in stress regime)
  state.py                   # load/save portfolio state + append history
  engine.py
backend/ai/portfolio_analyst.py
india/portfolio_engine/run.py
usa/research/portfolio_engine/run.py
configs/portfolio_config.yaml
```

### Core algorithm (Sprint 5 baseline)

1. From `sized_positions.json`, keep only positions with |target_weight| ≥ `min_position_size` (e.g. 0.5%)
2. Sort by |confidence × target_weight| descending
3. Take top-N (configurable per market; e.g. India=20, USA=15)
4. Renormalize weights so sum ≤ (1 − cash_reserve)
5. Diff against `portfolio_state.json`:
   - **Add**: in new set, not in prior
   - **Remove**: in prior, not in new set
   - **Adjust**: in both but weight changed by > `rebalance_threshold_bps` (e.g. 25 bps)
   - **Hold**: in both, weight change ≤ threshold
6. Emit portfolio + diff + AI narrative

### Types

```python
@dataclass
class Position:
    ticker:            str
    weight:            float
    notional:          float
    entry_date:        date
    entry_price:       float | None
    days_held:         int
    action_source:     str            # e.g. "aegis.recommendation.v3"
    model_stamp:       dict

@dataclass
class PortfolioSnapshot:
    market:            str
    asof:              date
    n_positions:       int
    total_weight:      float          # 0..1 (long side)
    cash_pct:          float
    positions:         list[Position]
    hhi:               float
    top_5_pct:         float
    per_sector_pct:    dict[str, float]

@dataclass
class TradeInstruction:
    ticker:            str
    action:            str            # "OPEN" | "CLOSE" | "INCREASE" | "DECREASE" | "HOLD"
    delta_weight:      float
    prior_weight:      float
    new_weight:        float
    reason:            str
```

### Config (`configs/portfolio_config.yaml`)

```yaml
market_defaults:
  india:
    target_n_positions:        20
    min_position_size:         0.005
    cash_reserve_min:          0.05
    cash_reserve_stress:       0.25    # in stress regime, hold 25% cash minimum
    rebalance_threshold_bps:   25
    rebalance_frequency:       "weekly"
  usa:
    target_n_positions:        15
    min_position_size:         0.01
    cash_reserve_min:          0.05
    cash_reserve_stress:       0.20
    rebalance_threshold_bps:   30
    rebalance_frequency:       "weekly"
```

### AI Portfolio Analyst

- Diversification quality (HHI, effective N, sector count)
- Turnover assessment (are we churning?)
- Concentration risks (any single position > 10%? sector > 30%?)
- Cash policy compliance
- Rebalance efficiency (few trades or many?)

### Post-run acceptance

- N positions ≤ `target_n_positions`
- Sum of weights + cash_pct = 1.0 (within 0.1%)
- No sector > per-sector cap (inherited from `risk_budget.yaml`)
- HHI computed and stored
- Deterministic
- Walk-forward safe

---

## Sprint 6 · Learning Engine

### Purpose

**Close the feedback loop.** For every recommendation ever emitted, once its horizon closes, record the outcome, compute error, run feature and model attribution, cluster failures, and update the learning corpus + confidence calibration.

This is what unlocks Sprint 8 walk-forward validation with real metrics (win-rate, Sharpe, profit-factor) instead of `insufficient_history` placeholders.

### Inputs

- Historical recommendations: `reports/recommendation_history.parquet` (append-only ledger of every rec emitted)
- Historical prices: `features/{market}/{date}.parquet` for outcome computation
- `reports/portfolio_v3.json` sequence (for actual position outcomes)
- `reports/execution_ledger.parquet` (from Sprint 7 when available)

### Outputs

- `reports/learning_corpus.parquet` — append-only per-recommendation outcome ledger
- `reports/feature_attribution.json` — per-recommendation feature attribution
- `reports/model_attribution.json` — per-recommendation model attribution
- `reports/failure_clusters.json` — recurring failure patterns
- `reports/confidence_calibration.json` — recalibration curves
- `reports/ai_learning_narrative.json`

### File layout

```
backend/learning/
  __init__.py
  types.py                       # LearningRow, Attribution, FailureCluster
  outcome_computer.py            # match rec → future price → return_pct → is_winner
  feature_attribution.py         # SHAP-style + permutation on selected features
  model_attribution.py           # which ensemble models contributed to good/bad calls
  failure_clustering.py          # k-means / DBSCAN on failed-rec features
  calibration.py                 # Platt / isotonic scaling
  corpus.py                      # read/append learning corpus (parquet)
  engine.py
backend/ai/learning_analyst.py
india/learning_engine/run.py
usa/research/learning_engine/run.py
configs/learning_config.yaml
```

### Core types

```python
@dataclass
class LearningRow:
    """One row per closed-horizon recommendation. This is the atomic unit."""
    market:                str
    ticker:                str
    rec_asof:              date           # when the recommendation was emitted
    horizon_close_date:    date           # when the horizon ended
    action:                str
    ensemble_score:        float
    calibrated_confidence: float
    regime_at_rec:         str
    top_models:            list[str]
    top_features:          list[str]
    # Outcome
    entry_price:           float
    exit_price:            float
    return_pct:            float          # signed; positive = winner for BUY, negative winner for SELL
    is_winner:             bool
    horizon_days:          int
    hit_stop_loss:         bool
    hit_take_profit:       bool
    # Attribution
    feature_attribution:   dict           # {feature: contribution_score}
    model_attribution:     dict           # {model_id: contribution_score}
    # Root cause
    error_bucket:          str            # "underestimated_vol" | "regime_change" | "surprise_earnings" | "worked_as_expected" | ...
    # Provenance
    model_stamp_at_rec:    dict
    feature_set_version:   str
    schema_fingerprint:    str

@dataclass
class FailureCluster:
    cluster_id:            int
    n_members:             int
    dominant_features:     dict           # feature → mean value in cluster
    dominant_error_bucket: str
    representative_tickers: list[str]
    recommended_step:      str            # e.g. "reduce weight on Value model in high-vol regime"
```

### Attribution methodology

**Feature attribution** (per closed rec):
1. Take the feature vector at rec_asof
2. For each selected feature: measure the marginal impact on the ensemble score by holding that feature at its cross-sectional median and re-scoring (permutation-style)
3. Rank features by absolute impact; store top-10 with sign

**Model attribution** (per closed rec):
1. From the model registry stamp at rec_asof, retrieve per-model scores from `ensemble.json` (historical version)
2. For each model: contribution = model_score × ensemble_weight × sign_of_return
3. If positive → model was right; negative → model was wrong

### Failure clustering

- Filter learning corpus to `is_winner == False` (losers only)
- Feature vector = features at rec_asof (from historical Feature Store)
- Cluster with K-means (k=5) OR DBSCAN with eps auto-tuned via elbow
- For each cluster: dominant features + dominant regime + representative tickers
- Emit `failure_clusters.json` with cluster interpretations

### Confidence calibration

- For each confidence bin (0.0-0.1, 0.1-0.2, ..., 0.9-1.0):
  - Empirical win-rate over historical closed recs in that bin
- Fit Platt (logistic regression) or isotonic to map raw confidence → empirical win-probability
- Store calibration curve at `confidence_calibration.json`
- Sprint 3's `calibration.py` reads this on next run (populates the `historical_precision` field)

### Config (`configs/learning_config.yaml`)

```yaml
horizon_days_default:    60
error_buckets:
  - underestimated_vol
  - regime_change
  - surprise_earnings
  - liquidity_shock
  - sector_rotation_missed
  - worked_as_expected
clustering:
  algorithm:  "kmeans"       # or "dbscan"
  k:          5
calibration:
  method:     "isotonic"     # or "platt"
promotion:
  min_horizons_before_promotion: 30
```

### AI Learning Analyst

- Overall win-rate + Sharpe over the last N horizons
- Which models are the biggest alpha generators? Which are alpha destroyers?
- Which features are stable across regimes? Which drift?
- Which failure clusters recur most? What's the recommended step?
- Deprecation candidates: models with sustained negative attribution

Contract: never emits promoted/approved.

### Post-run acceptance

- Every closed rec has a `LearningRow` entry
- `learning_corpus.parquet` is strictly append-only (natural key: market + ticker + rec_asof)
- Deterministic
- Walk-forward: `engine.run(cutoff)` only reads recs where `horizon_close_date <= cutoff`

---

## Sprint 7 · Execution Simulator

### Purpose

Turn `portfolio_diff.json` into **realistic fills** — with slippage, commissions, partial fills, overnight gaps, and corporate-action adjustments. This is what turns "paper" backtests into believable equity curves.

### Inputs

- `reports/portfolio_diff.json` (Sprint 5 output)
- Historical prices (canonical bars)
- Corporate actions (from Feature Store's `canonical_corporate_action`)
- `configs/execution_config.yaml`
- Prior fills ledger

### Outputs

- `reports/execution_ledger.parquet` — every simulated fill, append-only
- `reports/equity_curve.parquet` — daily equity value + cash + positions
- `reports/performance_metrics.json` — Sharpe, DD, CAGR, hit rate, etc.
- `reports/ai_execution_narrative.json`

### File layout

```
backend/execution/
  __init__.py
  types.py                   # Fill, Slippage, ExecutionState
  slippage_model.py          # linear-impact + vol-adjusted slippage
  commissions.py             # per-market commission schedules
  fill_engine.py             # simulate day's fills; partial fills; VWAP option
  gap_handler.py             # overnight gap logic
  corp_action_adjuster.py    # split/dividend adjustments to holdings
  equity_curve.py            # daily mark-to-market
  metrics.py                 # Sharpe/Sortino/Calmar/DD/hit-rate/turnover
  engine.py
backend/ai/execution_analyst.py
india/execution_simulator/run.py
usa/research/execution_simulator/run.py
configs/execution_config.yaml
```

### Fill algorithm (Sprint 7 baseline)

For each row in `portfolio_diff.json`:

```
slippage_bps = MIN_SLIPPAGE_BPS + LIQUIDITY_IMPACT × (order_size / adv_20d) + VOL_IMPACT × vol_20d
fill_price   = mid_price × (1 + sign(action) × slippage_bps / 10_000)
commission   = fixed_bps × notional        # e.g. 3 bps
n_days_to_fill = ceil(order_size / (max_participation × adv_20d))
```

Partial fills: if `order_size > max_daily_participation × ADV`, spread across N days.

### Gap handling

Overnight gap > ±3% between yesterday's close and today's open → mark stop-loss or take-profit hit at *open*, not intraday.

### Corporate actions

Dividend day: cash += position × dividend_amount
Split day: shares_held × split_ratio; entry_price ÷= split_ratio

### Performance metrics computed daily

```python
sharpe_ann     = (daily_returns.mean() / daily_returns.std()) × sqrt(252)
sortino_ann    = (daily_returns.mean() / downside_dev) × sqrt(252)
calmar         = cagr / abs(max_drawdown)
max_drawdown   = ((equity / equity.cummax()) - 1).min()
information_ratio = (portfolio_return - benchmark_return).mean() / active_std × sqrt(252)
profit_factor  = winners.sum() / abs(losers.sum())
hit_rate       = winners.count() / trades.count()
```

### Config (`configs/execution_config.yaml`)

```yaml
market_defaults:
  india:
    commission_bps:              3.0
    min_slippage_bps:            2.0
    liquidity_impact_bps:        50.0   # bps per (order_size / adv_20d)
    vol_impact_bps:              15.0
    max_daily_participation:     0.10   # 10% of ADV per day
    gap_stop_out_threshold_pct:  3.0
  usa:
    commission_bps:              1.0
    min_slippage_bps:            1.0
    liquidity_impact_bps:        30.0
    vol_impact_bps:              10.0
    max_daily_participation:     0.15
    gap_stop_out_threshold_pct:  3.0
```

### Post-run acceptance

- Every trade in `portfolio_diff.json` maps to at least one Fill in the ledger
- `execution_ledger.parquet` append-only
- Equity curve is monotone in time (no gaps)
- Sharpe/Sortino/Calmar/DD/PF/HR all computed
- Deterministic
- Walk-forward: engine.run(cutoff) never reads prices > cutoff

---

## Sprint 8 · Institutional Walk-Forward Validation

### Purpose

The framework the operator has been driving toward since Stage 0. **The full-stack replay on frozen data.**

Freeze Feature Store + configs + code at a historical date → replay every layer (Feature Intelligence → Model Factory → Recommendation → Risk → Portfolio → Execution → Learning) → compare to actual market outcomes → produce institutional-grade metrics.

### Method: expanding-window walk-forward (from [[aegis_institutional_walkforward]])

```
Loop:
  1. Freeze training data at current cutoff (starts at Dec 31 2024).
  2. Replay full stack over horizon window (45-60 days).
  3. Once the horizon closes, compare predictions to actuals.
  4. Expand training set to include the window.
  5. Advance cutoff by horizon length; repeat.
Non-overlapping windows → N independent verdicts.
```

### Inputs

- Historical Feature Store snapshots (require ≥ 12 months of daily snapshots — will accumulate as Sprint 2.5+ continues to run)
- Historical prices back to Dec 2024
- Sprint 3-7 engines (all walk-forward safe)
- `configs/walkforward_config.yaml`

### Outputs

- `walkforward/{market}/{cutoff_YYYY-MM-DD}/` per-window artifacts:
  - `recommendations.json` — what the engine would have said on cutoff+1
  - `portfolio.json`
  - `execution_ledger.parquet`
  - `equity_curve.parquet`
  - `metrics.json`
- `walkforward/{market}/summary.json` — aggregate across all windows
- `walkforward/{market}/india_vs_usa_comparison.json` (in Sprint 9 auditor)
- `reports/ai_walkforward_narrative.json`

### File layout

```
backend/walkforward/
  __init__.py
  types.py                   # WalkForwardWindow, WalkForwardSummary
  freeze.py                  # snapshot repo state at a cutoff
  replay.py                  # replay every engine at a cutoff
  window_iterator.py         # generate cutoff dates over the study period
  metrics_aggregator.py      # aggregate per-window metrics into a summary
  engine.py                  # WalkForwardEngine.run(start_date, end_date)
backend/ai/walkforward_analyst.py
india/walkforward/run.py
usa/research/walkforward/run.py
configs/walkforward_config.yaml
```

### The critical 24 metrics (from operator's spec)

Return · risk-adjusted · execution · behavioral · model-quality:

| Return | Risk-adjusted | Execution | Behavior | Model quality |
|---|---|---|---|---|
| Win Rate | Sharpe | Turnover | Avg Winner | Recommendation Accuracy |
| Profit Factor | Sortino | Holding Period | Avg Loser | Confidence Calibration |
| Expected Value | Calmar | Sector Allocation | Hit Rate | AI Accuracy |
| Alpha | Max Drawdown | Risk Exposure | | Fusion Accuracy |
| Beta | Recovery | Portfolio Volatility | | Strategy Accuracy |
| | Information Ratio | Tracking Error | | |

Every window's `metrics.json` contains ALL 24. Summary aggregates as median + P25 + P75 across windows.

### Counterfactual: "if today's engine ran back then"

For every historical cutoff:
1. Save the *actual* engine version that would have run then (via model_registry stamp)
2. ALSO run the *current* engine on the same frozen data
3. Diff the two — this is the counterfactual analysis the operator wants

Stored at `walkforward/{market}/{cutoff}/counterfactual.json`.

### Config (`configs/walkforward_config.yaml`)

```yaml
start_date:                    "2024-12-31"
horizon_days:                  60
end_date:                      null       # null = up to today
windows_before_first_report:   1          # min windows before emitting metrics
counterfactual_enabled:        true
markets:
  - india
  - usa
```

### Post-run acceptance

- N windows generated per market, deterministic on same inputs
- All 24 metrics populated per window
- Summary computed with median + P25 + P75
- Counterfactual populated when `counterfactual_enabled: true`
- Every window's artifacts stamped with the engine versions in effect
- Never uses data past the cutoff (contract-tested by running at a distant-past cutoff and verifying no future-dated rows appear in outputs)

---

## Sprint 9 · AI Validation Auditor

### Purpose

**Explain the walk-forward.** Not "win rate = 63%", but *why* — which regimes, models, features, sectors, market caps, macro conditions, confidence buckets drove the results. Propose hypotheses. Recommend model deprecations. Never promote.

### Inputs

- `walkforward/{market}/summary.json` + per-window artifacts
- Feature attribution + model attribution history (Sprint 6)
- Failure clusters (Sprint 6)
- Model registry
- Feature registry with governance metadata

### Outputs

- `reports/ai_validation_audit.json` — comprehensive audit
- `reports/ai_audit_summary.md` — human-readable
- `reports/counterfactual_analysis.json`
- `reports/hypothesis_backlog.json` — new candidate features/models proposed

### File layout

```
backend/ai/validation_auditor.py            # THE Sprint 9 agent
backend/ai/regime_slicer.py                 # slice metrics by regime
backend/ai/sector_slicer.py                 # slice metrics by sector
backend/ai/confidence_bucket_analyzer.py    # slice metrics by confidence bin
india/ai_auditor/run.py
usa/research/ai_auditor/run.py
```

### Auditor questions

The Sprint 9 auditor MUST answer:

1. **Overall verdict** — pass/fail vs benchmark; is the alpha real?
2. **Regime breakdown** — bull/bear/neutral/stress performance
3. **Model contribution** — which of the 11 models generated alpha? Which destroyed it?
4. **Feature drivers** — which features consistently correlated with winners?
5. **Sector breakdown** — which sectors were reliable? Which were coin flips?
6. **Market cap breakdown** — mega/large/mid/small (USA); large-cap/mid-cap (India)
7. **Volatility regime** — did the engine perform in high-vol vs low-vol?
8. **Macro conditions** — high-rates / low-rates / dollar-strength / oil-shock
9. **Confidence calibration** — do 80% conf calls actually win 80% of the time?
10. **Failure taxonomy** — top recurring failure clusters
11. **Which models should be retired?** — proposal for operator review
12. **Which hypotheses should be tested?** — new candidate features/models

### Cross-market compare

`india_vs_usa_comparison.json`:
- Win rate India vs USA
- Sharpe India vs USA
- Max DD India vs USA
- Which market performed better in each regime?
- Cross-market feature stability

### Contract

- Never emits `buy`/`sell`/`target_price`/`recommendation`/`action`/`promoted`/`approved` keys
- Every proposal is routed to the Research Factory backlog for operator promotion
- Deterministic on same inputs (template-driven; LLM upgrade later behind determinism="llm-cached")

---

## Sprint 10 · Research Factory

### Purpose

**Systematically evolve the feature and model catalog.** Where AI agents propose (Sprint 2.6 `feature_research`, Sprint 2.7 `model_analyst`, Sprint 9 `validation_auditor`), the Research Factory *takes those proposals and drives them through experiments*.

**Contract (already locked in Sprint 2.6):** AI proposes. Research Factory experiments. Promotion Gate approves. Operator promotes. Nothing ever auto-promotes.

### Inputs

- `reports/hypothesis_backlog.json` (Sprint 9 output — new candidate features/models proposed by AI Auditor)
- `research/candidates/{feature,model}/*.yaml` — operator-added or AI-proposed candidates
- Historical Feature Store (for backtesting candidates)
- Learning corpus (Sprint 6 output) — for outcome-based scoring
- Walk-Forward runner (Sprint 8) — for out-of-sample validation

### Outputs

- `reports/experiment_ledger.jsonl` — append-only record of every experiment
- `reports/candidate_status.json` — current state of every proposal (PROPOSED / BACKTESTING / WALK_FORWARD / READY_FOR_APPROVAL / REJECTED / PROMOTED)
- `reports/ai_research_narrative.json`

### File layout

```
backend/research_factory/
  __init__.py
  candidate_registry.py         # load candidates from YAML files
  candidate_feature_pipeline.py # feature: compute → backtest → WF → gate
  candidate_model_pipeline.py   # model: instantiate → backtest → WF → gate
  hypothesis_generator.py       # template-based (Sprint 10 v0); LLM later
  experiment_tracker.py         # append-only ledger + status transitions
  engine.py                     # ResearchFactory.run()
backend/ai/research_narrator.py # summarizes what's in the pipeline
india/research_factory/run.py
usa/research/research_factory/run.py
configs/research_config.yaml
research/candidates/
  feature/                       # candidate feature YAMLs (proposed by AI or operator)
  model/                         # candidate model YAMLs
```

### Candidate feature YAML (schema)

```yaml
# research/candidates/feature/global_stress_index.yaml
name:               global_stress_index
category:           macro
status:             PROPOSED            # PROPOSED / BACKTESTING / WALK_FORWARD / READY_FOR_APPROVAL / REJECTED / PROMOTED
proposed_by:        "ai:feature_research"    # or "human:surya"
proposed_on:        "2026-07-20"
formula:            "z(macro_vix) + z(macro_move) - z(macro_dxy_change) - z(macro_wti_change)"
dependencies:
  - macro_vix
  - macro_move
  - macro_dxy
  - macro_wti_oil
business_rationale: "Composite cross-asset stress score; historically a leading indicator for equity drawdowns."
economic_intuition: "Cross-asset stress detaches capital from risk assets; equities discount future cashflows more heavily."
experiments:
  backtest:
    status:   pending
    result:   null
  walk_forward:
    status:   pending
    n_windows: 0
    p_value:  null
    stability_score: null
  latest_evaluation_utc: null
```

### Candidate model YAML (schema)

```yaml
# research/candidates/model/vol_arb_v1.yaml
name:               vol_arb_v1
model_type:         "custom_signal"           # from ModelType or "custom_signal"
proposed_by:        "human:surya"
proposed_on:        "2026-07-21"
algorithm:          "weighted_rule_v1"
feature_dependencies:
  - volatility_20d
  - volatility_60d
  - macro_vix
business_rationale: "Short vol when realised is far below implied; the mean-revert edge is the vol premium."
economic_intuition: "Volatility risk premium: implied > realised on average; systematic short vol with strict risk controls earns the premium."
implementation:     "backend/research_factory/candidate_models/vol_arb_v1.py"
experiments:
  backtest:      { status: pending, result: null }
  walk_forward:  { status: pending, n_windows: 0, verdict: null }
```

### Pipeline (per candidate)

```
PROPOSED
  ↓  ResearchFactory.run() triggers backtest
BACKTESTING
  ↓  historical Feature Store + Sprint 6 outcome computer → in-sample metrics
  ↓  if backtest passes threshold → advance
WALK_FORWARD
  ↓  Sprint 8 walk-forward engine runs the candidate over N historical windows
  ↓  metrics: win_rate, Sharpe, PF, stability
  ↓  if walk-forward passes → advance
READY_FOR_APPROVAL
  ↓  backend/promotion/promotion_gate.check_promotion() returns READY_FOR_APPROVAL
  ↓  operator invokes approve_feature() / approve_model()
PROMOTED
  ↓  Feature Registry / Model Factory registry adds the entry as ACTIVE
```

### Config (`configs/research_config.yaml`)

```yaml
backtest:
  min_horizons:          10
  min_sharpe:            0.5
  min_win_rate:          0.50
walk_forward:
  min_windows:           3
  min_p_value:           0.05
  min_stability_score:   0.60
scheduler:
  cadence:               "weekly"       # weekly scan of new candidates
  parallel_experiments:  4              # max concurrent
```

### Experiment tracker (`reports/experiment_ledger.jsonl`)

Append-only. One row per state transition:

```json
{
  "candidate_id":   "feature.global_stress_index",
  "state_from":    "PROPOSED",
  "state_to":      "BACKTESTING",
  "timestamp_utc": "2026-07-21T14:30:00Z",
  "triggered_by":  "research_factory.scheduler",
  "notes":         "auto-scheduled from hypothesis_backlog"
}
```

### AI Research Narrator (`backend/ai/research_narrator.py`)

Summarises the state of the pipeline for the operator:
- How many candidates are in each state?
- Which candidates are furthest along?
- Which candidates got rejected and why?
- What did the most recent walk-forward runs show?
- Are we generating enough new hypotheses (health signal)?

Contract: never emits promoted/approved keys; the AI Narrator NEVER moves a candidate to PROMOTED itself.

### Post-run acceptance

- `experiment_ledger.jsonl` append-only, natural key = (candidate_id, timestamp_utc)
- Every state transition logged with `triggered_by`
- No candidate advances past `READY_FOR_APPROVAL` without operator `approve_*` call
- Backtest results deterministic on same Feature Store + same seed (if any randomness); walk-forward deterministic per Sprint 8 contract
- Rejected candidates preserve their history — no deletion, just a REJECTED state
- Contract-tested: `approve_*` from AI-only source raises `ValueError`

### AI-proposed candidates

Sprint 2.6's `feature_research` agent already emits a template bank of 5 hypotheses. Sprint 10:
1. Automatically writes each hypothesis into `research/candidates/feature/*.yaml` with `proposed_by: "ai:feature_research"`
2. Sprint 9 auditor's `hypothesis_backlog.json` proposals become candidates too
3. Sprint 10's own `hypothesis_generator.py` scans for gaps in the feature space (missing categories, low-dispersion existing features) and proposes fills

Every AI proposal is a candidate — never a promotion. Operator remains in the loop.

---

## Cross-cutting concerns

### Institutional Reporting

**Purpose:** Auto-generated PDFs for the operator + stakeholders.

**File layout:**
```
backend/reporting/
  __init__.py
  pdf_builder.py              # ReportLab-based PDF generation
  html_to_pdf.py              # wkhtmltopdf fallback (already have HTML reports)
  templates/                  # HTML templates per report type
  cadence_scheduler.py        # daily / weekly / monthly / quarterly / annual
india/reporting/run.py
usa/research/reporting/run.py
configs/reporting_config.yaml
```

**Reports:**
| Cadence | Content |
|---|---|
| Daily | Morning brief · new recommendations · risk report · portfolio · AI narratives (short) |
| Weekly | Weekly performance + turnover · top winners/losers · regime commentary |
| Monthly | Full 24-metric dashboard · attribution · calibration state · model registry status |
| Quarterly | Walk-forward re-run · benchmark comparison · sector rotation review · India vs USA compare |
| Annual | Institutional audit · full learning corpus review · roadmap for next year |

**Contract:** every PDF is a deterministic render of a locked JSON snapshot. Same JSON → same PDF bytes (modulo timestamp footer). PDFs stored at `reports/pdf/{cadence}/{YYYY-MM-DD}.pdf`.

### Explainability Layer

**Purpose:** Every decision the platform makes is traceable back to its inputs and reasoning.

**Every artifact in the pipeline already stamps:**
- `model_stamp` (from model_registry)
- `feature_set_version`
- `schema_fingerprint`
- `run_utc`
- `asof`

**Sprint 9 auditor adds:** `explainability_index.json` — a lookup from `(market, ticker, asof)` to the full lineage:
```
recommendation → ensemble → per-model scores → features → canonical → raw
```

### Benchmark Engine

**Purpose:** compare AEGIS against reference strategies.

**Benchmarks:**
| Market | Reference strategies |
|---|---|
| India | NIFTY 50 · NIFTY 500 · SENSEX · Equal-weight portfolio · 60/40 (equity/gold) · Random 20-name |
| USA | S&P 500 · Nasdaq 100 · Dow 30 · Russell 2000 · Equal-weight portfolio · 60/40 · Random 15-name |

**File layout:**
```
backend/benchmark/
  __init__.py
  reference_returns.py        # load index prices, compute period returns
  equal_weight.py             # equal-weight universe portfolio
  random_strategy.py          # random selection with seed
  buy_and_hold.py             # naive top-N by market cap, hold forever
india/benchmark_v3/run.py
usa/research/benchmark_v3/run.py
```

Output: `reports/benchmark_v3.json` with alpha/beta/IR vs each reference over 1M/3M/6M/1Y/YTD windows.

### Strategy Comparison

Head-to-head evaluation of each Model Factory model as a *standalone strategy*: what if we ran ONLY Momentum? Only Value? Only Quality?

`backend/strategy_comparison/` runs each model as a solo portfolio through Sprint 7 execution and reports the 24 metrics per strategy. Output: `reports/strategy_comparison.json` — a ranked table.

### Regime Analytics

**Regimes tracked** (locked taxonomy):
| Category | Regimes |
|---|---|
| Trend | bull · bear · sideways |
| Volatility | low_vol (VIX<15) · normal (15-25) · elevated (25-35) · stress (>35) |
| Macro | rate_hikes · rate_cuts · steady · dollar_strong · dollar_weak · oil_shock |
| Event | earnings_season · fed_meeting · election · other |

Regime tagging happens in `backend/regime_analytics/tagger.py`; every daily artifact carries a `regime_tags` list. Sprint 8 walk-forward slices metrics by regime automatically.

### Statistical Validation methodology

Locked metric definitions (avoid confusion across sprints):
```
sharpe_ann = (r.mean() / r.std()) × sqrt(252)                      # r = daily returns, excess of risk-free
sortino_ann = (r.mean() / r[r<0].std()) × sqrt(252)
calmar = cagr / abs(max_drawdown)
info_ratio = (rp - rb).mean() / (rp - rb).std() × sqrt(252)         # rp, rb = portfolio, benchmark daily
alpha, beta = OLS regression of daily excess returns on benchmark
profit_factor = winners.sum() / abs(losers.sum())
recovery_factor = total_return / abs(max_drawdown)
hit_rate = n_winners / n_trades
expected_value = winners.mean() × hit_rate - abs(losers.mean()) × (1 - hit_rate)
avg_holding_period_days = trades.holding_days.mean()
turnover = sum(abs(weight_change)) / 2   per rebalance
tracking_error = (rp - rb).std() × sqrt(252)
```

All in `backend/statistics/metrics.py` — SINGLE source of truth. Every engine that reports these metrics MUST import from here.

### Experiment Registry (cross-cutting · emerges through Sprints 4-8)

**Purpose:** unify every version stamp into a single per-run experiment record. Not a new sprint — an emergent artifact that Sprints 4-8 write to naturally.

**File:** `reports/experiment_registry.jsonl` (append-only). One row per full pipeline run per market:

```json
{
  "run_id":              "aegis.india.2026-07-21T03:15:00Z",
  "market":              "india",
  "asof":                "2026-07-21",
  "written_utc":         "2026-07-21T03:15:00Z",
  "feature_set_version": "b65ceb49a83a",
  "schema_fingerprint":  "b65ceb49a83a",
  "model_stamps":        [ … model_registry entries active this run … ],
  "config_hashes": {
    "risk_budget.yaml":       "<sha256>",
    "portfolio_config.yaml":  "<sha256>",
    "execution_config.yaml":  "<sha256>",
    "learning_config.yaml":   "<sha256>",
    "walkforward_config.yaml":"<sha256>"
  },
  "engine_versions": {
    "recommendation":  "aegis.recommendation.v3 · 1.0.0",
    "risk":            "aegis.risk.v1 · 1.0.0",
    "portfolio":       "aegis.portfolio.v1 · 1.0.0",
    "learning":        "aegis.learning.v1 · 1.0.0",
    "execution":       "aegis.execution.v1 · 1.0.0"
  },
  "walkforward_run_id":  null,
  "ai_validation_report_id": null
}
```

**How it accumulates:**
- Sprint 4 introduces `backend/experiment_registry/writer.py` (a 30-line helper) — every engine that runs calls `experiment_registry.append_stamp(run_id, engine_id, ...)` at the end of its runner.
- Sprint 5-7 add their engine stamps to the same run_id record.
- Sprint 8 walk-forward creates a new run_id per window; the registry is where WF reports get anchored.
- Sprint 9 AI auditor's report_id is written back to close the loop.

**Contract:** append-only. `run_id` is deterministic — `f"aegis.{market}.{asof.isoformat()}T{time_component}Z"` where time_component comes from the run's UTC timestamp passed in by the orchestrator (never `datetime.now()` inside engine code).

**AI never writes to the Experiment Registry.** Only deterministic engine runners write. AI outputs reference `run_id` for audit but never mutate the registry.

---

### Research Factory

**Purpose:** systematically evolve the feature and model catalog. AI proposes, human promotes.

**File layout:**
```
backend/research_factory/
  __init__.py
  candidate_feature_pipeline.py   # candidate → backtest → WF → promotion gate
  candidate_model_pipeline.py     # same for candidate models
  hypothesis_generator.py         # deterministic templates first; LLM later
  experiment_tracker.py           # ledger of every proposed candidate + status
```

**Contract:** the Research Factory ONLY writes to `research/candidates/{feature,model}/*.yaml`. No code in the Feature Registry or Model Factory changes automatically. Promotion routes through Sprint 2.6's `promotion_gate`.

---

## Data model — every JSON schema + dataclass

### File layout of shared schemas

```
backend/schemas/                        # NEW — introduced with Sprint 4
  __init__.py
  json_schemas.py                       # Python dicts of JSON schemas per artifact
  validators.py                         # jsonschema-based validators
  __schemas__/                          # actual .json schema files
    sized_positions.schema.json
    risk_report.schema.json
    portfolio_v3.schema.json
    portfolio_diff.schema.json
    learning_row.schema.json
    execution_fill.schema.json
    equity_curve.schema.json
    performance_metrics.schema.json
    walkforward_window.schema.json
    walkforward_summary.schema.json
    validation_audit.schema.json
```

Every engine writes its output, then runs `validators.validate_output(engine, path)` before returning success. This is enforced in CI (backend/tests/test_schemas.py — new).

### Canonical dataclass diagram (union of every Phase 2 type)

```
SizedPosition  (Sprint 4)
  ↓ list                             (many-to-one)
RiskReport
  ↓
Position       (Sprint 5)
  ↓ list
PortfolioSnapshot
  ↓ diff
TradeInstruction
  ↓ execute
Fill            (Sprint 7)
  ↓ mark-to-market
EquityPoint
  ↓ aggregate
PerformanceMetrics
  ↓ per-window
WalkForwardWindow  (Sprint 8)
  ↓ aggregate
WalkForwardSummary
  ↓ audit
ValidationAudit    (Sprint 9)

Every closed rec creates:
Recommendation → LearningRow  (Sprint 6)
  ↓ analyze
FeatureAttribution
ModelAttribution
FailureCluster
```

---

## AI agents catalog

Every AI agent in Phase 2, with its role and contract:

| Agent | File | Sprint | Reads | Emits | Never |
|---|---|---|---|---|---|
| Data Quality | `backend/ai/data_quality.py` | 2 | backend_validation_summary | data health narrative | recommends |
| Market Analyst | `backend/ai/market_analyst.py` | 2 | MarketIntelligenceResult | regime narrative | recommends |
| Evidence Summarizer | `backend/ai/evidence_summarizer.py` | 2 | CanonicalDataset bundle | cross-source snapshot | recommends |
| Feature Anomaly | `backend/ai/feature_anomaly.py` | 2.5 | feature snapshot | outlier list | recommends |
| Feature Quality | `backend/ai/feature_quality.py` | 2.5 | ValidationResult | narrative | recommends |
| Feature Importance | `backend/ai/feature_importance.py` | 2.5 | feature snapshot | dispersion ranking | recommends |
| Feature Conflict | `backend/ai/feature_conflict.py` | 2.5 | feature snapshot | conflict flags | recommends |
| Feature Research | `backend/ai/feature_research.py` | 2.6 | governance + importance | hypotheses | promotes |
| Model Analyst | `backend/ai/model_analyst.py` | 2.7 | model descriptions + metrics | ensemble participation proposal | promotes |
| Recommendation Analyst | `backend/ai/recommendation_analyst.py` | 3 | RecommendationBatch | conviction highlights | promotes |
| **Risk Analyst** | `backend/ai/risk_analyst.py` | **4** | RiskReport | budget audit | promotes |
| **Portfolio Analyst** | `backend/ai/portfolio_analyst.py` | **5** | PortfolioSnapshot + diff | diversification narrative | promotes |
| **Learning Analyst** | `backend/ai/learning_analyst.py` | **6** | learning corpus + attribution | model contribution narrative | promotes |
| **Execution Analyst** | `backend/ai/execution_analyst.py` | **7** | execution ledger + equity | slippage / fill narrative | promotes |
| **Walk-Forward Analyst** | `backend/ai/walkforward_analyst.py` | **8** | walkforward summary | window-level narrative | promotes |
| **Validation Auditor** | `backend/ai/validation_auditor.py` | **9** | everything | full audit + hypothesis backlog | promotes |

All 16 agents contract-tested against the forbidden-keys set `{buy, sell, target_price, recommendation, action, promoted, approved}`.

---

## Testing / acceptance criteria per sprint

Every sprint MUST include a `backend/tests/test_sprint{N}.py` file with:
- Contract test: no-recommendation from every AI agent introduced
- Determinism test: same inputs → identical outputs
- Walk-forward test: engine accepts cutoff; distant-past cutoff produces valid but empty/tiny output
- Model registry test: every engine that emits a decision stamps
- Schema validation test: output matches JSON schema
- Integration test: per-market runner executes cleanly, emits all declared outputs

Enforced in CI (`.github/workflows/aegis-ci.yml`).

Additionally, cross-sprint tests in `backend/tests/test_cross_sprint.py`:
- End-to-end deterministic replay (Sprint 4 → 5 → 7 with a fixed seed dataset)
- No engine reads data past cutoff (fuzz test: pass random cutoffs, verify)
- Every artifact carries `run_utc`, `asof`, `market`, `model_stamp` (where applicable)

---

## Sprint prompts — ready to invoke

Copy-paste these to me one at a time.

### Sprint 4 prompt

> **Sprint 4 — Risk Engine**
>
> Implement the Risk Engine per docs/AEGIS_PHASE2_ARCHITECTURE.md § "Sprint 4 · Risk Engine".
>
> - Build `backend/risk/` (types.py, sizing.py, exposure_caps.py, vol_adjustment.py, concentration.py, var_cvar.py, engine.py) exactly as specified.
> - Build `backend/ai/risk_analyst.py` — contract-tested no-promotion.
> - Build `configs/risk_budget.yaml` with the market defaults shown.
> - Build `india/risk_engine/run.py` and `usa/research/risk_engine/run.py`.
> - Wire into both orchestrators, both datasets.yaml (+4 entries each), and both SPAs (Risk tile).
> - Regression suite `backend/tests/test_sprint4.py` covering: sizing math, per-ticker cap, per-sector cap, VaR/CVaR computation, AI analyst no-promotion, both runners emit valid JSON matching the schema, walk-forward determinism.
> - CI: add Sprint 4 regression step.
> - Report: `docs/AEGIS_SPRINT4_REPORT.md`.
> - Do NOT touch legacy engines. Do NOT skip ahead to Portfolio/Learning.

### Sprint 5 prompt

> **Sprint 5 — Portfolio Engine**
>
> Implement per docs/AEGIS_PHASE2_ARCHITECTURE.md § "Sprint 5 · Portfolio Engine".
>
> - `backend/portfolio/` full framework with prior-state diff.
> - `backend/ai/portfolio_analyst.py`.
> - `configs/portfolio_config.yaml` with target N per market.
> - Per-market runners + wiring + regression + CI + report.
> - Prior state stored at `reports/portfolio_state.json` and append-only at `reports/portfolio_state_history.jsonl`.
> - Contract tests: N-cap enforced · sector cap enforced · cash + weights sum to 1.0 · deterministic · walk-forward safe.

### Sprint 6 prompt

> **Sprint 6 — Learning Engine**
>
> Implement per docs/AEGIS_PHASE2_ARCHITECTURE.md § "Sprint 6 · Learning Engine".
>
> - `backend/learning/` full framework including outcome computer, feature/model attribution, failure clustering, confidence calibration.
> - `learning_corpus.parquet` schema locked to the `LearningRow` dataclass. Append-only, natural key = (market, ticker, rec_asof).
> - `backend/ai/learning_analyst.py`.
> - Sprint 3's `calibration.py` now reads `confidence_calibration.json` on each run and populates `historical_precision` — this closes the loop.
> - Model registry `walk_forward_metrics` field gets populated per model.
> - Regression suite: attribution correctness on synthetic data, clustering produces stable clusters on identical inputs, calibration curve monotonically maps, walk-forward safe.

### Sprint 7 prompt

> **Sprint 7 — Execution Simulator**
>
> Implement per docs/AEGIS_PHASE2_ARCHITECTURE.md § "Sprint 7 · Execution Simulator".
>
> - `backend/execution/` with slippage · commissions · fills · gap handler · corp actions · equity curve · metrics.
> - `configs/execution_config.yaml` with per-market defaults.
> - `backend/ai/execution_analyst.py`.
> - `backend/statistics/metrics.py` — SINGLE source of truth for Sharpe/Sortino/Calmar/etc. Every downstream sprint that reports metrics imports from here.
> - Regression: slippage math on synthetic prices, partial fills over multiple days, dividend/split adjustments, deterministic equity curves, walk-forward safe.

### Sprint 8 prompt

> **Sprint 8 — Institutional Walk-Forward Validation**
>
> Implement per docs/AEGIS_PHASE2_ARCHITECTURE.md § "Sprint 8 · Institutional Walk-Forward Validation".
>
> - `backend/walkforward/` including freeze, replay, window_iterator, metrics_aggregator, engine.
> - Walks the whole pipeline: FS → FI → MF → Rec → Risk → Portfolio → Execution → Learning → Metrics.
> - Expanding-window methodology per the locked memory [[aegis_institutional_walkforward]].
> - Counterfactual: also replay CURRENT engines on historical cutoffs; diff vs what-was-then.
> - All 24 metrics per window; summary aggregates as median + P25 + P75.
> - `configs/walkforward_config.yaml`.
> - Regression: engine.run(cutoff) is deterministic, no future data leaks (fuzz test with random distant-past cutoffs).
> - This sprint requires ≥ 12 months of historical Feature Store snapshots to produce meaningful results — Sprint 2.5 must have been accumulating history.

### Sprint 9 prompt

> **Sprint 9 — AI Validation Auditor**
>
> Implement per docs/AEGIS_PHASE2_ARCHITECTURE.md § "Sprint 9 · AI Validation Auditor".
>
> - `backend/ai/validation_auditor.py` — the main auditor.
> - Slicers: regime · sector · market-cap · confidence-bucket · vol-regime · macro-condition.
> - Cross-market compare: India vs USA on every metric + regime.
> - Hypothesis backlog: proposes new candidate features/models routed to Research Factory.
> - Contract: never emits promoted/approved keys; every proposal goes through Sprint 2.6 promotion_gate.
> - `docs/AEGIS_SPRINT9_REPORT.md` — the first *real* institutional audit if walk-forward has run.

### Sprint 10 prompt

> **Sprint 10 — Research Factory**
>
> Implement per docs/AEGIS_PHASE2_ARCHITECTURE.md § "Sprint 10 · Research Factory".
>
> - `backend/research_factory/` — candidate registry, feature/model pipelines, hypothesis generator, experiment tracker, engine.
> - `research/candidates/{feature,model}/` YAML schema locked exactly as documented.
> - `backend/ai/research_narrator.py` — contract-tested no-promotion.
> - `configs/research_config.yaml` with backtest + WF thresholds.
> - Sprint 2.6's AI feature_research hypotheses auto-flow into `research/candidates/feature/` YAML.
> - Sprint 9's `hypothesis_backlog.json` proposals auto-flow into candidate YAMLs.
> - State machine: PROPOSED → BACKTESTING → WALK_FORWARD → READY_FOR_APPROVAL → PROMOTED. Every transition ledger-logged. Operator required for the final PROMOTED transition.
> - Regression: candidate advances through states deterministically; no candidate promotes without operator; rejected candidates preserve history.
> - This is the LAST Phase 2 sprint. After Sprint 10, AEGIS is a self-evolving system with a locked human-in-the-loop safety valve.

---

## Sign-off checklist

Before Sprint 4 kicks off, the operator confirms:

- [ ] I have read the cross-cutting principles and none surprise me.
- [ ] The Sprint 4 → 9 flow (Rec → Risk → Portfolio → Learning → Execution → WF → Audit) is the correct order.
- [ ] The 24-metric list is complete.
- [ ] The Feature Store schema is frozen (81 features · fingerprint b65ceb49a83a) — any additions go through the promotion gate.
- [ ] Legacy `research/adaptive_rec_v2/` remains untouched.
- [ ] Every AI agent obeys the no-promotion contract.
- [ ] `configs/` files (risk_budget, portfolio_config, execution_config, learning_config, walkforward_config, reporting_config) are operator-owned and version-controlled.
- [ ] Human-in-the-loop is enforced at every promotion gate.
- [ ] Determinism + walk-forward safety are non-negotiable.
- [ ] India + USA parity: every Phase 2 sprint ships both markets simultaneously.

Once signed off, invoke sprints one at a time via the ready-made prompts above. Each sprint is self-contained; nothing later re-architects anything earlier.
