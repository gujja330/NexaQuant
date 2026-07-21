# AEGIS Executive Dashboard

**Last updated:** 2026-07-21 · Sprint 7.6 shipped · **Phase 3 Roadmap LOCKED**
**Overwritten every sprint** — always the current state of AEGIS.
**Roadmap authority:** [`docs/AEGIS_PHASE3_ROADMAP.md`](../docs/AEGIS_PHASE3_ROADMAP.md)

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
✅ Persistence + Factor Lib   Sprint 7.5   · append-only history for every engine + 22-factor library
✅ Historical Backfill+Replay Sprint 7.6   · replay framework + 35 USA + 26 India feature snapshots  ← WE ARE HERE
⚪ Full-Pipeline Replay       Sprint 7.7   · pending  (headless engine drivers for rec/risk/portfolio/execution)
⚪ Walk-Forward Validation    Sprint 8     · pending  (unblocked; feature snapshots + ledgers accumulating)
⚪ Institutional AI Auditor   Sprint 9     · pending  (EXPANDED — per-trade multi-dim root-cause report)
⚪ Research Factory           Sprint 10    · pending  (Phase 2 terminal engine)
──────────────────────────────────────────────────────────────────────
Phase 3 · Institutional Intelligence Layer (LOCKED 2026-07-21)
   1. Market Memory Engine        · deterministic recall ("have we seen this?")
   2. Event Intelligence          · Fed/RBI/war/election/tariff/earnings/M&A → linked
   3. Relationship Graph          · Oil→Transport→Airlines→IndiGo→Margins→EPS→Rec
   4. Institutional Explainability · "BUY because Macro 82% · Sector 76% · Commodity 91%"
   5. Scenario Engine             · deterministic simulation ("Oil +15% → what happens")
   6. Strategy Lab                · auto-generate Momentum/MR/Quality/Value/Macro/Rotation
   7. Portfolio Optimizer         · efficient frontier layer after Sprint 5
   8. Institutional Dashboard     · Plotly/Streamlit — consolidated live view

⛔ NO new core engines after Phase 3. NO new AI agents (6 is the full set).
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
Sprint 7.6 (historical backfill + replay)     19/19  ✅
Telegram HTTP 400 fallback                    10/10  ✅
─────────────────────────────────────────────────────────
TOTAL                                        237/237 ✅
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

## Sprint 7.6 · Backfill State (2026-07-21)

| Artifact | India | USA |
|---|---|---|
| Feature snapshots on disk | **26 days** (2026-06-15 → 07-21) | **35 days** (2026-06-01 → 07-21) |
| Walk-forward verdict | PARTIAL | PARTIAL |
| Rec / Risk / Portfolio / Execution history rows | 0 (Sprint 7.7) | 0 (Sprint 7.7) |
| Macro history rows | 0 (Sprint 7.7 fetcher) | 1 |
| Factor library rows | 22 | 22 |

Backfill CLI: `python -m backend.replay backfill --from 2026-06-01 --to 2026-07-21 --market usa --steps features --resume` (0.64 s/day USA · 2.6 s/day India).

---

## NEXT BOTTLENECK

**Sprint 7.7 · Full-Pipeline Historical Replay.** Sprint 7.6 landed feature-snapshot backfill (35 USA + 26 India days deterministically produced). What remains before Sprint 8 becomes institutional:

1. **yfinance macro-symbol fetcher** — 5y daily bars for CL=F, BZ=F, GC=F, SI=F, HG=F, NG=F, UUP, ^TNX, ^TYX, ^FVX, ^IRX, ^VIX → `data/raw/macro/`.
2. **Headless engine drivers** — programmatic Rec/Risk/Portfolio/Execution execution per historical asof using the feature snapshots already on disk. NO runner changes (per operator "never affect current pipeline" rule).

Sprint 7.6's framework already wraps these (resume, integrity, quality, reports). Sprint 7.7 plugs in the two producers and the deferred-status steps auto-flip to backfilled.

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

Sprint 7.6 · Historical Backfill & Replay · docs/AEGIS_SPRINT76_REPORT.md
Prior: Phase 3 Roadmap LOCK (9753201) · Telegram fallback (d4df8d5) · Sprint 7.5 (9861a98)
