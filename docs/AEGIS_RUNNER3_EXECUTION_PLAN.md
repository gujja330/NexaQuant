# AEGIS · Runner 3 · Execution Plan

**Ticket ID:** `RL-Runner3`
**Signed into force:** 2026-08-05
**Owner:** CEO (delegated to Research Lab)
**Status:** OPENED · Tier 1 execution
**Governance:** Article IX (Research Lifecycle) · Article X (Evidence-First Promotion)
**Hard constraint:** Runner 1 (SEALED) and Runner 2 (canonical) code + outputs **must remain untouched** throughout.

---

## 0 · TL;DR

Runner 3 is a **shadow-only** experimental swing-strategy engine built as a
new isolated module. It never writes to `reports/recommendations.json`, never
appears in Telegram until the Day-90 gate clears, and never modifies any file
Runner 1 or Runner 2 reads or writes. After 60–90 shadow days, all three
runners are compared on identical metrics and a CEO decision picks the
canonical.

---

## 1 · Named Evidence Trigger (why now, not just "sounds nice")

Per the constitutional rule *"Research Lab may generate unlimited ideas.
Production accepts only evidence-backed changes"* — Runner 3 opens against
these two documented findings, not against a general "let's try more
signals" impulse:

| Trigger | Threshold | Observed | Source |
|---|---|---|---|
| Rotation Quality below institutional floor | ≥ 1.75 | **1.73** on 2026-07-30 scorecard | `reports/ai_scorecard.json` |
| Runner 1 / Runner 2 consensus drift | ≥ 60% daily | Dipped to **6.7%** on individual days | `reports/research/disagreements/verdict.json` |

Either alone justifies the research spend. Both together = high-priority.

The **first monthly Feature Attribution rollup** (shipped in `c13b05c`
2026-08-05) further motivates a redesigned ensemble: `Trend −6.30pp` edge
and `Growth −2.32pp` edge suggest the current 11-model blend is
weight-inefficient for the current regime.

---

## 2 · Hard Isolation Principles

**Runner 3 must not disturb Runner 1 or Runner 2 in any way.** Every design
decision below serves this constraint.

1. **New package** at `backend/recommendation/runner3/` · self-contained ·
   never imports from `adaptive_rec_v2` (R1) or
   `backend.recommendation.ssot` (R2) except through public feature-store
   contracts.
2. **Separate output tree** at `reports/research/runner3/` · never writes
   to `reports/recommendations.json` (R2's canonical) or
   `data/aegis_today.csv` (R1's canonical).
3. **Separate ledger** at `reports/research/runner3/shadow_ledger.jsonl` ·
   append-only · never merged with `portfolio_ledger.jsonl` (R006 · R2).
4. **Separate config** at `configs/runner3.json` · never mutates
   `configs/adaptive_ensemble_weights.json` or `configs/runner_horizons.json`.
5. **Separate CI verdict** · Runner 3 orchestrator step is `optional: True`
   so a Runner 3 failure never breaks R1/R2 Telegram delivery.
6. **Telegram gated** · Runner 3 output does **not** appear in the daily
   Telegram XLSX until the Day-90 gate clears via explicit CEO decision.
7. **Shared read-only inputs** · Runner 3 may READ from the Feature Store,
   Macro Intel, and Sector Rotation outputs · never WRITE to them.

Any pull request that violates rules 1–7 is auto-blocked in review.

---

## 3 · Tiered Scope (Claude PDF · Part II · Section 2)

The ChatGPT deep-research brief proposed **all 20+ new feeds + 7 model
families at once**. The Claude evaluation flagged this as scope creep and
recommended a tiered approach. This plan adopts the tiered approach exactly:

### Tier 1 · Build now · zero vendor spend

| Component | Data source | Rationale |
|---|---|---|
| Reuse existing ~25 technical features | Existing OHLCV | Already in feature store · no new ingest |
| FII/DII flows adapter | NSE published free feed | Institutional flow signal |
| Earnings calendar adapter | Free exchange bulletins | Event-risk filter · already partially in USA pipeline |
| Options PCR adapter | NSE F&O free feed | Sentiment / positioning proxy |
| XGBoost model (LightGBM fallback) | scikit-learn stack | Tabular baseline · SHAP-explainable |
| Platt / Isotonic calibration layer | scikit-learn | Fixes calibration drift the monthly rollup will surface |

**Tier 1 deliverable · shipped in this sprint.**

### Tier 2 · Only if Tier 1 shows Day-30 lift

| Component | Rationale |
|---|---|
| Insider / institutional holdings | SEC/SEBI filings (free) · adds ownership signal |
| Macro calendar | RBI / Fed calendar (free) · event-risk sizing |
| Walk-forward + regime-specific backtests | Correct methodology · reuse Sprint 8 replay engine |
| Sector ablation studies | Deferred until Tier 1 baseline established |

### Tier 3 · Deferred · evidence-gated only

| Component | Blocker |
|---|---|
| RavenPack news / paid sentiment | Only if Tier 1/2 identifies a specific gap |
| ESG ratings (MSCI Sustainalytics) | ChatGPT PDF itself calls this "exploratory" |
| Tick / orderbook data | Cross-cutting with R004 · joint decision |
| LSTM / Transformer models | Small-sample overfit risk · defer |
| Deep-learning ensembles | Same |

---

## 4 · Architecture (isolation-respecting)

```
                    ┌──────────────────────────┐
                    │   Feature Store (R/O)     │
                    │  (Sprint 4.5 · shared)    │
                    └────────────┬──────────────┘
                                 │
             ┌───────────────────┼───────────────────┐
             │                   │                   │
   ┌─────────▼──────┐  ┌─────────▼──────┐  ┌────────▼─────────┐
   │  Runner 1      │  │  Runner 2      │  │  Runner 3 (NEW)   │
   │  adaptive_v2   │  │  v3 canonical   │  │  runner3/         │
   │  (SEALED)      │  │  (canonical)    │  │  (SHADOW ONLY)    │
   └────────┬───────┘  └────────┬───────┘  └────────┬──────────┘
            │                   │                    │
            ▼                   ▼                    ▼
      aegis_today.csv     recommendations.json  runner3/picks.json
            │                   │                    │
            └─────┐         ┌───┘                    │
                  ▼         ▼                        ▼
              Telegram XLSX (R1/R2 only)       Shadow ledger
                                                 (Telegram: NO)
```

**Read-only shared inputs:**
- `reports/feature_store/*.parquet`
- `reports/macro_regime.json`
- `reports/sector_rotation.json`
- `reports/factor_library.parquet`

**Write-exclusive Runner 3 outputs** (never touched by R1/R2):
- `reports/research/runner3/picks_{market}_{asof}.json`
- `reports/research/runner3/shadow_ledger.jsonl`
- `reports/research/runner3/calibration_state.json`
- `reports/research/runner3/model_binary.pkl` (versioned)
- `reports/research/runner3/day30_gate.json` (verdict output)

---

## 5 · Timeline · With Day-30 Kill Gate

```
Day 0    Ticket opened · Tier 1 scaffold shipped                  [THIS SPRINT]
Day 1-30 Shadow paper-runs daily · picks logged to shadow_ledger  [AUTOMATED]
         Monthly rollups compare R3 vs R1/R2 on identical metrics
Day 30   ┌─────────────────────────────────────────────────────┐
         │ GATE 1 · GO / NO-GO checkpoint                       │
         │                                                       │
         │ PASS criteria (any two of three):                    │
         │  · R3 Sharpe within 0.2 of R2                        │
         │  · R3 Calibration Brier score better than R2         │
         │  · R3 Feature Attribution edge > +3pp on top model   │
         │                                                       │
         │ FAIL: no feature group adds statistically meaningful  │
         │ lift → STAND DOWN · Runner 3 archived · no Day-60    │
         └─────────────────────────────────────────────────────┘
Day 31-60 If GATE 1 passed · continue shadow · widen n
Day 60   Interim scorecard published · 3-runner comparison
Day 61-90 Final shadow window
Day 90   ┌─────────────────────────────────────────────────────┐
         │ GATE 2 · CEO Decision                                │
         │                                                       │
         │ Options:                                              │
         │  A. Promote R3 to canonical (retire R2 to shadow)    │
         │  B. Keep all 3 runners live in perpetuity             │
         │  C. Retire R3 · R2 stays canonical                   │
         │  D. Merge best-of-R2-and-R3 into a new v4            │
         │                                                       │
         │ Decision must cite: 90-day Sharpe · calibration Brier │
         │ · rotation accuracy · feature edge · consensus with   │
         │ R1 as truth-check                                     │
         └─────────────────────────────────────────────────────┘
Day 91+  Post-decision: whichever path chosen becomes canonical.
         R1 remains SEALED as sanity check regardless of decision.
```

**Standing kill switch (Article X):** if 12 months pass without Gate 2
clearing, Runner 3 automatically reverts to `DEFERRED` regardless of
sunk cost.

---

## 6 · Success Metrics (declared BEFORE Day 0 · Article X)

Pre-registered so we cannot goalpost-shift later:

| Metric | R3 must beat | Source |
|---|---|---|
| Sharpe (net of slippage) | R2 within ±0.2 minimum | Rolling 30/60/90 day |
| Calibration Brier score | Better than R2 or absolute < 0.20 | Monthly rollup |
| Rotation directional accuracy | ≥ 60% at Day 90 | R006 rotation_accuracy rollup |
| Feature Attribution edge (top model) | ≥ +3pp | Monthly rollup |
| Drawdown | ≤ R2 max DD | Position store history |
| R1 consensus rate | ≥ 40% daily | Existing disagreement ledger |
| Sample size at Day 30 gate | ≥ 20 closed positions (per Claude PDF n≥20 rule) | Shadow ledger count |
| Sample size at Day 90 gate | ≥ 60 closed positions | Shadow ledger count |

**Below n=20 · no gate decision may be made.** Push the gate rather than
declare on noise (per Claude PDF Section 3 discipline).

---

## 7 · Evaluation Framework · 3-Runner Comparison

New report generated daily at end of pipeline:
`reports/research/runner3/three_runner_comparison_{market}.json`

Columns per runner (R1 · R2 · R3):
- Day count (days in the current window)
- Positions opened / closed / active
- Cumulative return · vs benchmark
- Sharpe · Sortino · Max DD · Calmar
- Win rate · Profit factor
- Calibration Brier score
- Median rotation edge (expected) · median actual
- Feature Attribution top 3 winning models · top 3 losing models
- Sample size flag (`insufficient_data: true` if n<20)

Companion Markdown: `three_runner_comparison_{market}.md` (human-readable
for Telegram attachment on operator request).

At Day 30, 60, 90 the report also emits a `gate_verdict` object with
PASS/FAIL for each declared success metric.

---

## 8 · Deliverables Checklist

### This sprint (shipping now)

- [x] `docs/AEGIS_RUNNER3_EXECUTION_PLAN.md` (this file)
- [ ] `backend/recommendation/runner3/__init__.py` · package
- [ ] `backend/recommendation/runner3/engine.py` · XGBoost + Platt/Isotonic
- [ ] `backend/recommendation/runner3/features_free.py` · FII/DII + earnings + PCR adapters
- [ ] `backend/recommendation/runner3/run.py` · daily runner script
- [ ] `backend/recommendation/runner3/shadow_ledger.py` · append-only picks log
- [ ] `backend/recommendation/runner3/day30_gate.py` · gate evaluation
- [ ] `backend/recommendation/runner3/three_runner_comparison.py` · daily 3-way scorecard
- [ ] `configs/runner3.json` · thresholds + feature toggles
- [ ] `scripts/aegis_daily_v2.py` step added · optional · post-R2
- [ ] `research/tickets/RL_Runner3.json` · formal research ticket
- [ ] Regression test: verify Runner 3 run produces no writes outside allowed paths

### Tier 2 (after Day 30 gate PASS)

- [ ] Insider holdings adapter
- [ ] Macro calendar adapter
- [ ] Walk-forward backtest against 2y history
- [ ] Regime-conditional performance report

### Tier 3 (deferred)

- [ ] RavenPack / paid sentiment · gated on Tier 2 evidence
- [ ] Deep learning models · gated on Tier 2 evidence

---

## 9 · What Doesn't Change

- Runner 1 (adaptive_rec_v2 · SEALED) · no touches
- Runner 2 (v3 canonical) · no touches
- Every existing Telegram sender · every existing XLSX column · every existing rollup
- `configs/adaptive_ensemble_weights.json` · owned by R2 only
- `reports/recommendations.json` · owned by R2 only
- All Guards 1–6 (Pipeline Safety) apply to R1/R2 as before

---

## 10 · Acceptance Criteria (Article X · signed before Day 0)

- All Tier 1 modules ship with tests + docs
- Zero writes from Runner 3 to any R1/R2 output path (verified by test)
- Shadow ledger populates for 30 consecutive days without missed runs
- Day-30 gate emits explicit PASS/FAIL verdict with citations
- 3-runner comparison report available daily starting Day 1
- CEO can inspect any Runner 3 pick with full attribution + feature list
- If Day-30 gate FAILS · Runner 3 marked DEFERRED · no Tier 2 spend

**Signed 2026-08-05 · Runner 3 opens now · Tier 1 execution begins.**
