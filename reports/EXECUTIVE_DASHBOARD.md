# AEGIS Executive Dashboard

**Last updated:** 2026-07-21 · Sprint 7.8 (Benchmark Report) shipped · **Phase 3 Roadmap LOCKED**
**Overwritten every sprint** — always the current state of AEGIS.
**Roadmap authority (four-pillar):**
· [`docs/AEGIS_PHASE3_MASTER_ROADMAP.md`](../docs/AEGIS_PHASE3_MASTER_ROADMAP.md) — Phase 3 · WHAT (18 engine sprints · FROZEN 2026-07-24)
· [`docs/AEGIS_PHASE4_PRODUCT_COMPLETION.md`](../docs/AEGIS_PHASE4_PRODUCT_COMPLETION.md) — Phase 4 · WHICH (20 product modules · LOCKED 2026-07-24)
· [`docs/AEGIS_PHASE5_DEVELOPMENT_STANDARDS.md`](../docs/AEGIS_PHASE5_DEVELOPMENT_STANDARDS.md) — Phase 5 · HOW (coding constitution · LOCKED 2026-07-24)
· [`docs/AEGIS_PHASE6_EXECUTION_BLUEPRINT.md`](../docs/AEGIS_PHASE6_EXECUTION_BLUEPRINT.md) — Phase 6 · WHO + WHEN (parallel execution · LOCKED 2026-07-24)

**Wave 1 (Repository Intelligence) · SHIPPED 2026-07-24:**
· [`docs/AEGIS_REPO_AUDIT.md`](../docs/AEGIS_REPO_AUDIT.md) — Sprint A1 · 10 recommendation entry points · 59 engines mapped · 6 cross-cutting risks
· [`reports/research_engine_inventory.json`](../reports/research_engine_inventory.json) — Sprint A2 · 59 engines · 25 categories · status matrix (39 Connected · 13 Partially · 3 Active · 4 Missing)

**Wave 2 (Historical Intelligence) · Sprint B0 CLOSED 2026-07-24:**
· [`reports/history_quality_report.json`](history_quality_report.json) — Sprint B0 India · PARTIAL · score 70/100 · 2 CA flags (MM_D1 stalled — accepted debt)
· [`usa/reports/history_quality_report.json`](../usa/reports/history_quality_report.json) — Sprint B0 USA · PARTIAL · score 58/100
· [`reports/global/history_quality_comparison.json`](global/history_quality_comparison.json) — cross-market delta (USA -12 vs India · worse market = USA)

**Wave 1 + Wave 2 · CLOSED 2026-07-24:**
· [`docs/AEGIS_WAVE_1_2_CLOSURE_REPORT.md`](../docs/AEGIS_WAVE_1_2_CLOSURE_REPORT.md) — every A1/A2/B0 finding classified · 1 Must-Fix (factor_library validator) shipped · 4 Accepted debt items ledger'd · Definition of Done ✓ for all three sprints

**v2.2 · End-to-End Stabilization Audit · LOCKED 2026-07-27 · NO-GO (49/100):**
· [`docs/AEGIS_V2_2_AUDIT.md`](../docs/AEGIS_V2_2_AUDIT.md) — 20-phase framework · 7 parallel investigation subagents · 42 findings classified (14 Must-Fix · 14 Accepted Debt · 2 Environment · 12 Expected Future)
· **Weighted Production Readiness Score: 49/100 → NO-GO** (target ≥75 for GO)
· Path to GO: **Sprint C0 → 55** (data + silent breakages) · **Sprint C1 → 75** (keystone + telegram + scheduler + champion) · **Sprint C2 → 82** (replay determinism + explainability)
· Top 5 blockers (weight-adjusted): keystone `reports/recommendations.json` unowned · Runner 2 100% HOLD · Rec accuracy corpus n=10 · 6 Telegram senders no dedup · sector taxonomy divergence
· Silent breakages found: ATR dead code in Feature Store (356k bars affected) · ADX uses `close.diff()` not `high.diff()` · Sector `isinstance(dict)` vs on-disk list mismatch · VEDL -64.9% unrecorded corp action · 13 India OHLC anomalies · MON001 fingerprint sentinel dormant · STRONG_BUY unreachable in stress · Classifier `_MATRIX` dead code · NIFTY200 missing LTIM/PEL/TATAMOTORS
· No code modified in audit phase per "Investigation First" directive · 280/280 tests still green · fingerprint `e4c070673568c52d…` preserved

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
✅ Historical Backfill+Replay Sprint 7.6   · replay framework + 35 USA + 26 India feature snapshots
🟡 Full-Pipeline Replay       Sprint 7.7   · SHIPPED PARTIAL · headless drivers + walk-forward + lookahead guard
       └ USA: 137 feat, 135 rec/risk/portfolio rows · India: 94 feat, 68 rec/risk/portfolio rows · 0 leaks
       └ Runner 1 audit-trail ingest: 48 legacy recs · 10 closed positions from raw prices
✅ Recommendation Benchmark  Sprint 7.8   · comprehensive metric panel + statistical significance gates  ← WE ARE HERE
       └ Wilson 95% CI on win rate · normal-approx CI on mean return · sample-size verdicts
       └ Runner 1 verdict on 10 trades: DIRECTIONAL_ONLY (win-rate CI [23.66%, 76.34%])
       └ Runner 1 vs Runner 2: CANNOT_COMPARE_INSUFFICIENT_DATA (need ≥30 closed each)
⚪ Recommendation Orchestrator Sprint 7.9   · deferred until benchmark shows statistically-meaningful edge
⚪ Full Institutional WF      Sprint 8     · deferred until orchestrator (or corpus grows organically)
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
Sprint 7.7 (full replay + walk-forward)       14/14  ✅
Sprint 7.7 Runner 1 (legacy audit-trail)      11/11  ✅
Sprint 7.8 (recommendation benchmark report)  17/17  ✅
Telegram HTTP 400 fallback                    10/10  ✅
─────────────────────────────────────────────────────────
TOTAL                                        279/279 ✅
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

## Sprint 7.8 · Benchmark on Runner 1 (2026-07-21, India, 10 trades)

| Metric | Value | 95% CI | Verdict |
|---|---:|---:|---|
| Sample | 10 | | **DIRECTIONAL_ONLY** — cannot claim edge |
| Mean return | +0.08% | [-3.70%, +3.87%] | CI straddles zero |
| Win rate | 50.0% | [23.66%, 76.34%] | CI straddles both extremes |
| Expectancy/trade | +0.08% | | Barely positive |
| Profit factor | 1.04 | | Barely positive |
| Reward/risk | 1.04 | | Winners barely outweigh losers |
| Max drawdown | -17.4% | | |
| Max consec losses | 3 | | |

**STRONG_BUY vs BUY** (directional only — 4 BUY samples):
- STRONG_BUY (n=6): +0.85% mean, 66.7% win rate
- BUY (n=4): -1.07% mean, 25.0% win rate
- Edge: **+1.92 pp mean · +41.67 pp win-rate** (unconfirmed — n_min < 30)

**Comparison Runner 1 vs Runner 2**: `CANNOT_COMPARE_INSUFFICIENT_DATA`  (Runner 1: 10 closed · Runner 2: 0 closed · need ≥30 each)

---

## Sprint 7.7 · Replay + Walk-Forward State (2026-07-21)

| Artifact | India | USA |
|---|---|---|
| Feature snapshots on disk | **94 days** (2026-03-01 → 07-21) | **137 days** (2026-01-01 → 07-21) |
| Rec history rows | **68** | **135** |
| Risk history rows | **68** | **135** |
| Portfolio history rows | **68** | **135** |
| Execution history rows | 0 (Sprint 7.9 — price provider) | 0 (Sprint 7.9) |
| Learning corpus rows | 0 (see below) | 0 (see below) |
| Macro history rows | 0 (yfinance fetcher deferred) | 1 |
| Factor library rows | 22 | 22 |
| Lookahead leaks | **0** | **0** |
| Walk-forward reports emitted | 7 (metrics/statistics/per_model/per_sector/per_macro_regime/drawdowns/summary) | 7 |
| Walk-forward verdict | PARTIAL | PARTIAL |

**One-line diagnosis:** replay works perfectly; rec engine emits **100% HOLD** across all 203 replayed dates → no BUY/SELL to close a horizon on → walk-forward metrics blank. This is exactly the two-runner blend problem Sprint 7.8 addresses.

---

## NEXT BOTTLENECK

**Corpus depth** for both runners. Sprint 7.8's benchmark framework is complete — every metric carries sample size + CI + significance verdict. What's missing is **data**, and data grows one trading day at a time.

Two mechanical paths:
1. **Grow Runner 1's audit trail organically** — daily pipeline appends to `data/aegis_recommendation_db.csv`; re-run ingest weekly. Reaches STATISTICALLY_MEANINGFUL (n≥30) in roughly 6-8 more weeks.
2. **Fix Runner 2's cold-start calibration** so Rec Engine v3 emits actionable BUY/SELL calls. That's a Sprint 3 change, not a benchmark change.

**Only when both runners cross n=30 closed positions each** should the Recommendation Orchestrator (Sprint 7.9) start weighting them.

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

Sprint 7.8 · Recommendation Benchmark Report · docs/AEGIS_SPRINT78_REPORT.md
Prior: Sprint 7.7 Runner 1 audit-trail ingest (3a2c1b2) · Sprint 7.7 replay (343eecf) · Sprint 7.6 (e934e40)
