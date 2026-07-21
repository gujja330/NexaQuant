# AEGIS Executive Dashboard

**Last updated:** 2026-07-21 · Sprint 7.5 · Persistence & Factor Library · **SHIPPED**
**Overwritten every sprint** — always the current state of AEGIS.

---

## Pipeline Status

```
✅ Feature Store              Sprint 2.5   · 81 features · fingerprint b65ceb49a83a
✅ Feature Intelligence       Sprint 2.6   · governance + drift + selection
✅ Model Factory              Sprint 2.7   · 11 models + ensemble
✅ Recommendation Engine v3   Sprint 3     · conflict + calibration + regime + explainer
✅ Risk Engine                Sprint 4     · Kelly + caps + VaR/CVaR
✅ Portfolio Engine           Sprint 5     · N-name + rebalance diff + cash policy
✅ Learning Engine            Sprint 6     · outcome ledger + attributions + calibration
✅ Macro & Intermarket Intel  Sprint 6.5   · commodities+FX+bonds+CB+VIX+rotation+regime+impact matrix+KG
✅ Execution Simulator        Sprint 7     · fills + slippage + equity curve + statistics
✅ Persistence + Factor Lib   Sprint 7.5   · append-only history for every engine + 22-factor library ← WE ARE HERE
⚪ Walk-Forward Validation    Sprint 8     · pending  (unblocked; ledgers now populate daily)
⚪ AI Validation Auditor      Sprint 9     · pending
⚪ Research Factory           Sprint 10    · pending
```

---

## Today's Runtime Results (2026-07-21)

| Metric                                | India         | USA           |
|:-------------------------------------:|--------------:|--------------:|
| Recommendations                       | 15            | 15            |
| STRONG_BUY + BUY                      | 0             | 0             |
| HOLD                                  | 15            | 15            |
| SELL + STRONG_SELL                    | 0             | 0             |
| Disagreement → HOLD                   | 10            | 6             |
| **Active Positions**                  | **0**         | **0**         |
| Cash %                                | 100.0%        | 100.0%        |
| Gross Exposure                        | 0.00%         | 0.00%         |
| Portfolio Volatility (ann)            | 0.00%         | 0.00%         |
| VaR 95% 1d                            | 0.00%         | 0.00%         |
| CVaR 95% 1d                           | 0.00%         | 0.00%         |
| HHI                                   | 0.000         | 0.000         |
| Effective N                           | 0.0           | 0.0           |
| Turnover                              | 0.00%         | 0.00%         |
| **Executed Trades (Sprint 7 NEW)**    | **0**         | **0**         |
| Simulated P&L                         | ₹0            | $0            |
| Portfolio Value (starting AUM)        | ₹10,000,000   | $1,000,000    |
| Ending Equity                         | ₹10,000,000   | $1,000,000    |
| Total Commission                      | ₹0            | $0            |
| Total Slippage                        | ₹0            | $0            |
| Sharpe / Sortino / Calmar             | n/a (1-day)   | n/a (1-day)   |
| Portfolio Verdict                     | PASS          | PASS          |
| Execution honest_empty flag           | TRUE          | TRUE          |

---

## Learning Corpus State

| Field                | India     | USA       |
|:--------------------:|----------:|----------:|
| Rec history rows     | 0         | 0         |
| New closed today     | 0         | 0         |
| Corpus total         | 0         | 0         |
| Win rate             | n/a       | n/a       |
| Calibration method   | identity  | identity  |

---

## Cumulative Test Health

```
Sprint 1  (backend validation)                12/12  ✅
Sprint 2  (canonical + market intel + AI)     12/12  ✅
Sprint 2.5 (feature store + AI)               12/12  ✅
Sprint 2.6 (feature intel + registry + gate)  18/18  ✅
Sprint 2.7 (model factory + 11 models)        14/14  ✅
Sprint 3  (recommendation intelligence v3)    22/22  ✅
Sprint 4  (risk engine)                       23/23  ✅
Sprint 5  (portfolio engine)                  20/20  ✅
Sprint 6  (learning engine)                   19/19  ✅
Sprint 7  (execution simulator + statistics)  26/26  ✅
Sprint 6.5 (macro & intermarket intelligence) 22/22  ✅
Sprint 7.5 (persistence + factor library)     18/18  ✅
─────────────────────────────────────────────────────────
TOTAL                                        218/218 ✅
```

## Backend Validation

- **India:** WARNING (3 pre-existing legacy artifacts stale — not Sprint 7)
- **USA:** PASS · 67/67 datasets · confidence 0.913

## Model Registry (all EXPERIMENTAL)

- `aegis.recommendation.v3` · `aegis.risk.v1` · `aegis.portfolio.v1` · `aegis.learning.v1` · `aegis.execution.v1` · `aegis.macro_intel.v1` · **`aegis.factor_library.v1` (NEW)**

---

## 🚨 CURRENT BOTTLENECK — Why Everything Downstream Is Empty

The pipeline is architecturally complete but **the Recommendation Engine emitted zero BUY/SELL calls today**. This cascades:

```
Recommendation:  0 BUY, 0 SELL, 15 HOLD           ← ROOT CAUSE
     ↓ (nothing to size)
Risk:            0 sized positions
     ↓ (nothing to construct)
Portfolio:       0 positions, 100% cash, 0 trades
     ↓ (nothing to execute)
Execution:       0 fills (honest_empty=True)
     ↓ (no fills → no P&L → no metrics)
Learning:        0 corpus rows, identity calibration
```

**Why the Recommendation Engine emitted all HOLDs:**

1. **Regime = neutral** → dampener 0.95 on both BUY and SELL confidence
2. **Equal-weight ensemble across 11 models** → per-ticker model agreement rarely > 60%
3. **Disagreement safety valve** collapsed 6-10 tickers to HOLD
4. **Calibrated confidence** on remaining tickers sits just below the 0.50 BUY threshold
5. **Learning corpus is empty** → no `historical_precision` to loosen calibration

**What's needed for meaningful output:**
- Either **≥ 60 days of live-forward recommendations closing their horizons** (fills learning corpus → loosens calibration for well-performing models)
- Or **Sprint 8 Walk-Forward** runs → generates historical outcomes at scale → populates the learning corpus retroactively → calibration engages → BUY/SELL calls flow

Neither the Risk Engine, Portfolio Engine, nor Execution Simulator is defective. The synthetic-input tests prove they all size, construct, and fill correctly given real BUY/SELL input:
- Risk Engine synthetic: 4 sized · gross 24% · HHI 0.333 · port vol 4.7%
- Portfolio Engine synthetic: 4 positions · gross 95% · effN 3.9 · turnover 47.5%
- Execution Simulator synthetic: 1 fill · notional $50,025 · commission $15.01

---

## Sprint 7.5 · Persistence + Factor Library State (2026-07-21)

| History file | India | USA |
|---|---|---|
| `recommendation_history.parquet` | wired · begins accumulating on next Rec Engine run | wired · begins accumulating on next Rec Engine run |
| `risk_history.parquet` | wired | wired |
| `portfolio_history.parquet` | wired (alongside existing portfolio_state_history) | wired |
| `macro_history.parquet` | wired (alongside per-symbol history parquets from Sprint 6.5) | wired |
| `execution_history.parquet` | wired | wired |
| `learning_history.parquet` | wired | wired |
| `factor_library.json / .parquet / _history.parquet` | 22 factors · **3 confident** (VIX + derived) | 22 factors · **11 confident** (WTI, Brent, Gold, USD, VIX, Fed cycle, curve, rotation) |

**How to apply going forward:** every daily `aegis_daily_v2.py` and `usa_daily.py` run automatically appends a fresh row per engine per market. No operator action required. Fail-open: if an append fails, the daily JSON snapshot still writes and the failure is logged to `reports/persistence_errors.jsonl` for auditability.

---

## Sprint 6.5 · Live Macro State (2026-07-21)

| Signal              | India                  | USA                            |
|:-------------------:|:----------------------:|:------------------------------:|
| Primary Regime      | risk_on                | unknown (VIX-only signal)      |
| Macro Score         | 0.40                   | -0.10                          |
| Confidence          | 0.5                    | 0.9                            |
| Vol Regime          | calm                   | normal (VIX 18.65)             |
| Central Bank Cycle  | RBI (thin data)        | Fed · neutral                  |
| Yield Curve         | (thin data)            | Normal · no inversion          |
| Active Commodity Impacts | 0                 | 2 (WTI + Brent up)             |
| Currency            | INR                    | USD                            |

---

## NEXT BOTTLENECK

**Historical depth for meaningful walk-forward.** Sprint 7.5 architecturally unblocks Sprint 8 — every engine now writes to its `_history.parquet` on every run — but the ledgers are **empty on day 1**. Sprint 8 will produce sparse walk-forward windows until 60+ trading days accumulate.

**Two acceleration paths:**
1. **Backfill** — run the daily orchestrator with an `--asof <date>` cursor across historical price data to seed the ledgers. Requires runners to accept a historical cutoff parameter.
2. **Snapshot-first Sprint 8** — build the engine, let it operate on the accumulating ledger, and refine metrics as history grows. Dashboard will visibly show `n_walk_forward_windows` incrementing daily.

**Recommended:** Snapshot-first Sprint 8. Build now, refine as history deepens.

Below that (previous bottleneck, still open):

**Sprint 8 · Walk-Forward Validation cannot produce meaningful metrics until it has historical BUY/SELL recommendations to replay.**

Evidence from today's run:
- `reports/recommendation_history.parquet` — **does not exist yet**
  - No historical ledger of recommendations means walk-forward has nothing to iterate over.
  - Would need to be written by Sprint 3 Recommendation Engine on each run (append `recommendations_v3.json` snapshot as a row).
  - **This is the single change that unblocks Sprint 8**: add a ledger-append step to the Rec Engine's runner.
- `reports/learning_corpus.parquet` — empty (0 rows)
- `reports/execution_ledger.parquet` — empty (0 fills)

**Required for Sprint 8 to produce real metrics:**
1. Rec Engine must write to `recommendation_history.parquet` on each run (~ 5-line change to Sprint 3 runner)
2. Data horizon must reach back ≥ 12 months (Feature Store snapshots + raw prices)
3. At least **one non-neutral regime day** in that history so the classifier emits some BUY/SELL

Without item 1, Sprint 8's engine will run but produce empty walk-forward windows.

---

## Latest Commit

Sprint 7.5 · Persistence & Factor Library · docs/AEGIS_SPRINT75_REPORT.md
Prior: Sprint 6.5 · Macro & Intermarket Intelligence · docs/AEGIS_SPRINT65_REPORT.md
