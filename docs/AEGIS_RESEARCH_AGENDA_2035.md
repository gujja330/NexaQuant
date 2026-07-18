# AEGIS Research Agenda 2035

**Institutional research strategy · 5–10 year horizon · no implementation.**

Written in the voice of a simulated Head of Quantitative Research
(BlackRock · Renaissance Technologies · Two Sigma · AQR). This document
is a research backlog. It does not modify architecture, propose new
engines, or schedule engineering work.

Governed by (in order of precedence):

1. [NEXAQUANT_MANIFESTO.md](NEXAQUANT_MANIFESTO.md) — why AEGIS exists
2. [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) — 14 ADRs
3. [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) — the constitution
4. [PHASE2_MASTER_ROADMAP.md](PHASE2_MASTER_ROADMAP.md) — Phase 2 delivery

Any research program below that conflicts with (1)–(3) is not viable.
Any program in tension with (4) is a Phase 3 candidate, not Phase 2.

---

## How to read this document

Every domain is evaluated identically. Fields:

- **Why it matters** — the decision-quality lever it moves
- **Research questions** — 3–5 concrete, disprovable questions
- **Current maturity / Future maturity** — 0–10, honest
- **Expected impact** — Low / Medium / High / Transformative
- **Difficulty** — Low / Medium / High / Foundational
- **Dependencies** — upstream research that must resolve first
- **Engine owner** — where the work lands
- **Engine version target** — mapped to
  [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md)
- **Success metrics** — from the fixed 13-metric panel (ADR-013)
- **Six-priority mapping** — which of {allocation · preservation ·
  calibration · validation · expectancy · explainability} it serves
- **Verdict** — worth researching? Which phase? Tier?

Six-priority mapping uses shorthand: **A**llocation · **P**reservation ·
**C**alibration · **V**alidation · **E**xpectancy · **X**plainability.

---

## Group I — Signal & Alpha

### 1. Alpha Research

- **Why it matters.** The confidence signal today has no predictive
  power (ADR-008). Every downstream engine inherits that noise. Rebuilding
  the raw signal is the highest-impact research program AEGIS has.
- **Research questions.**
  - Which features on the current data actually discriminate winners from losers?
  - What signal decays with liquidity, market cap, or holding period?
  - Can a stacking ensemble of narrow signals beat a monolithic composite?
  - How much of the current confidence variance is noise vs signal?
- **Current / Future maturity.** 2 / 8
- **Impact.** Transformative
- **Difficulty.** Foundational
- **Dependencies.** Validation Engine v2.0 (live paper trading) —
  required to distinguish real signal from backtest overfit.
- **Engine owner.** Adaptive Recommendation Engine
- **Version.** v2.0 (P0 in Phase 2)
- **Success metrics.** Precision@5 discrimination between confidence
  tiers · ECE below 0.05 · Win-rate spread ≥ 15pp between top and bottom
  confidence buckets.
- **Six-priority.** C · E · A · X
- **Verdict.** Tier S · Phase 2 · P0

### 2. Factor Investing

- **Why it matters.** Every institutional research house decomposes
  returns into Value · Growth · Momentum · Quality · Low-Vol · Size.
  Without factor attribution, AEGIS cannot answer "is this alpha or
  hidden beta?"
- **Research questions.**
  - Which factors drive the current recommendation set's returns?
  - Is AEGIS's edge orthogonal to the standard factor zoo?
  - How does factor exposure shift across regimes?
- **Current / Future maturity.** 1 / 7
- **Impact.** High
- **Difficulty.** Medium
- **Dependencies.** Alpha Research (Domain 1) must clarify what
  discriminating signal exists before attribution is meaningful.
- **Engine owner.** Adaptive Recommendation Engine (as explanation tool,
  not new intelligence)
- **Version.** v2.x (post-v2.0 rebuild)
- **Success metrics.** Factor-decomposed attribution report · residual
  alpha statistically distinguishable from zero at 2 quarters.
- **Six-priority.** X · V · E
- **Verdict.** Tier A · Phase 2 late / Phase 3

### 3. Regime Detection

- **Why it matters.** DEV030 revealed regime-conditional champions
  (top_5_ew in Risk-On, top_20_ew in Risk-Off). Every strategy shows
  2nd-half Sharpe degradation vs 1st-half — regime shift the platform
  is not yet handling explicitly.
- **Research questions.**
  - Can regime be classified from price/volume alone, or does it require
    macro variables?
  - Is regime a hidden Markov process or a continuous state?
  - How quickly can a shift be detected without over-fitting to noise?
- **Current / Future maturity.** 3 / 7
- **Impact.** High
- **Difficulty.** High
- **Dependencies.** Historical per-date regime labels (currently
  fallback classifier only) — must be persisted.
- **Engine owner.** Research Foundation
- **Version.** Foundation v1.6 (unblocks Risk & Capital v2.3)
- **Success metrics.** Per-regime Sharpe improvement · reduced
  regime-crossing drawdown · advance-warning median lead time ≥ 10 days
  before realized drawdown breach.
- **Six-priority.** P · A · V
- **Verdict.** Tier S · Phase 2 late

### 4. Macro Intelligence

- **Why it matters.** DEV017 captures 23 macro variables but they feed
  a coarse 3-way regime classifier. Institutional-grade macro decomposes
  yield curves, credit spreads, currency baskets, and commodity chains
  as first-class inputs.
- **Research questions.**
  - Which macro variables actually cause equity returns vs merely
    correlate with them?
  - What is the macro lead time — how far in advance do specific macro
    shifts telegraph equity regime changes?
  - Can macro attribution isolate country/currency/rate factors from
    company-specific alpha?
- **Current / Future maturity.** 3 / 7
- **Impact.** High
- **Difficulty.** High
- **Dependencies.** Multi-market data (blocked on Multi-Asset engine).
- **Engine owner.** Research Foundation
- **Version.** Foundation v2.0 (Phase 3)
- **Success metrics.** Macro-attributed excess return decomposition ·
  reduced surprise on Fed / RBI announcement days.
- **Six-priority.** A · V · X
- **Verdict.** Tier A · Phase 3

---

## Group II — Portfolio & Allocation

### 5. Portfolio Construction

- **Why it matters.** 99 constructions exist in DEV022 but none has an
  individual track record. A better construction cannot be identified
  because none is validated against the others.
- **Research questions.**
  - Does HRP genuinely beat equal-weight net of turnover on the AEGIS
    universe, or is the improvement inside the estimation-error band?
  - When does concentration outperform diversification?
  - What construction is optimal per regime × market cap × sector concentration?
- **Current / Future maturity.** 5 / 8
- **Impact.** High
- **Difficulty.** Medium
- **Dependencies.** Validation Engine v2.2 (per-portfolio backtest).
- **Engine owner.** Risk & Capital Engine
- **Version.** v2.2 (correlation-aware)
- **Success metrics.** Per-construction Sharpe · turnover-adjusted CAGR ·
  drawdown-adjusted Calmar.
- **Six-priority.** A · P · E
- **Verdict.** Tier S · Phase 2 mid

### 6. Position Sizing

- **Why it matters.** Position sizing is the second-most decisive
  choice in portfolio management, after security selection. Equal-weight
  is a placeholder; Kelly-¼ is a partial answer; the discipline is
  under-researched inside AEGIS.
- **Research questions.**
  - What is the correct sizing function of (confidence × edge × correlation)?
  - How much size dampening does regime uncertainty justify?
  - Is size-symmetry (equal in / equal out) suboptimal?
- **Current / Future maturity.** 4 / 8
- **Impact.** High
- **Difficulty.** Medium
- **Dependencies.** Alpha Research (Domain 1) — sizing is meaningless
  with an uncalibrated confidence signal.
- **Engine owner.** Risk & Capital Engine
- **Version.** v2.0 (P3 in Phase 2)
- **Success metrics.** Expectancy improvement per unit variance ·
  drawdown-adjusted CAGR.
- **Six-priority.** A · P · E
- **Verdict.** Tier S · Phase 2

### 7. Cross-Asset Allocation

- **Why it matters.** Equity-only is a coverage hole. Debt · gold ·
  commodity · FX rotate on macro cycles and provide portfolio drawdown
  buffers equity alone cannot.
- **Research questions.**
  - What cross-asset weights minimise drawdown at the current expected
    return level?
  - How does cross-asset dispersion change across regimes?
  - Where does India-specific cross-asset behavior diverge from global?
- **Current / Future maturity.** 0 / 6
- **Impact.** High
- **Difficulty.** High
- **Dependencies.** Multi-Asset Intelligence engine (governance-blocked
  until Phase 3).
- **Engine owner.** Multi-Asset Intelligence Engine
- **Version.** v1.0
- **Success metrics.** Portfolio Calmar (CAGR / MaxDD) improvement ·
  reduced regime-crossing drawdown.
- **Six-priority.** P · A
- **Verdict.** Tier A · Phase 3

### 8. Portfolio Optimization

- **Why it matters.** Beyond Markowitz + HRP, modern optimisation
  (robust optimisation, Bayesian portfolio inference, distributionally
  robust methods) can improve out-of-sample performance materially.
- **Research questions.**
  - Do Bayesian shrinkage priors on covariance improve out-of-sample
    Sharpe on the AEGIS universe?
  - How much of Markowitz's poor OOS performance is estimation error
    vs objective misspecification?
  - Is distributionally-robust optimisation worth its complexity here?
- **Current / Future maturity.** 4 / 7
- **Impact.** Medium
- **Difficulty.** High
- **Dependencies.** Position Sizing (Domain 6).
- **Engine owner.** Risk & Capital Engine
- **Version.** v2.2 / v2.3
- **Success metrics.** OOS Sharpe · turnover-adjusted OOS CAGR ·
  drawdown reduction.
- **Six-priority.** A · P
- **Verdict.** Tier A · Phase 3

### 9. Capital Preservation

- **Why it matters.** Priority #2 in the six-priority order. The single
  metric that separates institutional wealth management from retail
  speculation is *how much of drawdown one avoids*, not *how much of
  upside one captures*.
- **Research questions.**
  - What are the leading indicators of a 15%+ drawdown?
  - Can position-level circuit breakers (auto-tighten stop-loss on
    regime shift) preserve capital without giving back winners?
  - What is the empirical cost of over-defensive sizing during
    prolonged Risk-On regimes?
- **Current / Future maturity.** 3 / 8
- **Impact.** Transformative
- **Difficulty.** High
- **Dependencies.** Regime Detection (Domain 3) · Validation Engine v2.3
  (edge decay).
- **Engine owner.** Risk & Capital Engine
- **Version.** v2.1 (dynamic risk budget) + v2.3 (regime-cond)
- **Success metrics.** Max drawdown constrained inside declared budget ·
  Ulcer Index improvement · Calmar improvement.
- **Six-priority.** P · A
- **Verdict.** Tier S · Phase 2

---

## Group III — Risk & Validation

### 10. Risk Modeling

- **Why it matters.** DEV024 emits 11 alert types but the underlying
  risk model is threshold-based, not distributional. Institutional risk
  is stated as VaR / CVaR / expected shortfall with confidence intervals.
- **Research questions.**
  - Which risk measure (VaR / CVaR / ulcer / max-DD) is best-aligned
    with AEGIS's capital-preservation objective?
  - How does risk-model regime dependency compare across measures?
  - Can risk contribution attribution reveal which positions consume
    disproportionate risk budget?
- **Current / Future maturity.** 4 / 7
- **Impact.** High
- **Difficulty.** Medium
- **Dependencies.** Regime Detection (Domain 3).
- **Engine owner.** Risk & Capital Engine
- **Version.** v2.1
- **Success metrics.** Ex-post risk vs ex-ante forecast · CVaR
  realisation-vs-forecast bias.
- **Six-priority.** P · V
- **Verdict.** Tier A · Phase 2 late / Phase 3

### 11. Model Drift

- **Why it matters.** Every strategy in the current backtest shows
  2nd-half Sharpe degradation. Drift is real, present, and unmonitored
  live.
- **Research questions.**
  - What is the correct drift-detection statistic: KL divergence on
    signal distribution, rolling-Sharpe changepoint, or something else?
  - How much data is needed for a reliable drift signal?
  - Should drift trigger promotion review, sizing dampening, or both?
- **Current / Future maturity.** 2 / 8
- **Impact.** High
- **Difficulty.** Medium
- **Dependencies.** Validation Engine v2.0 (live tracking).
- **Engine owner.** Validation Engine
- **Version.** v2.3 (P8 in Phase 2)
- **Success metrics.** Median advance-warning lead time · false-positive
  rate below documented threshold.
- **Six-priority.** V · P
- **Verdict.** Tier S · Phase 2

### 12. Validation Science

- **Why it matters.** PIT-safe walk-forward backtest is the floor of
  validation science. The ceiling includes cross-market backtests,
  synthetic scenarios, and continuous OOS reconciliation — all absent
  today.
- **Research questions.**
  - How wide is AEGIS's backtest window vs institutional norms
    (rolling 20-year is standard; AEGIS has ~3)?
  - Can synthetic-market bootstrapping supplement thin real-market
    history without overfit to the bootstrap?
  - What is the correct expected-vs-actual reconciliation cadence?
- **Current / Future maturity.** 4 / 8
- **Impact.** Transformative
- **Difficulty.** Medium
- **Dependencies.** None (this is the enabling program for many others).
- **Engine owner.** Validation Engine
- **Version.** v2.0 through v2.4
- **Success metrics.** Live-run continuous operation days · expected-vs-
  actual divergence within tolerance for ≥ 2 quarters.
- **Six-priority.** V
- **Verdict.** Tier S · Phase 2 · P1

### 13. Forecast Calibration

- **Why it matters.** DEV029 rebuilt calibration methodology; the
  finding was that raw confidence has no signal. The next question is
  whether AEGIS's *rebuilt* confidence can be genuinely calibrated to
  probabilities.
- **Research questions.**
  - Once the raw signal is rebuilt, does Platt / Isotonic still
    correctly collapse to base rate, or does discrimination survive?
  - Are conditional calibration guarantees (per sector / regime)
    achievable, or is only marginal calibration realistic?
  - What is the trade-off between sharpness and reliability?
- **Current / Future maturity.** 8 / 9
- **Impact.** Medium (already high maturity; incremental gains)
- **Difficulty.** Medium
- **Dependencies.** Alpha Research (Domain 1) — must produce a real
  signal before calibrating it means anything.
- **Engine owner.** Adaptive Recommendation Engine
- **Version.** v2.0 (as verification step) · v2.4 (conditional calibration)
- **Success metrics.** ECE below 0.05 · sharpness improvement (variance
  of calibrated confidence) above current 0.
- **Six-priority.** C · X
- **Verdict.** Tier S · Phase 2 (as verification of Domain 1)

---

## Group IV — Learning & Intelligence

### 14. Continuous Learning

- **Why it matters.** DEV025 updates on trade-closure only. Institutional
  systems learn continuously — MFE / MAE tracking, entry-timing accuracy,
  stop-loss efficacy — across the open-position window.
- **Research questions.**
  - What features of the open-position window are predictive of eventual
    outcome (winner vs loser)?
  - Can stop-loss thresholds be dynamically adjusted based on realised
    MFE?
  - Does continuous learning improve expectancy or merely add complexity?
- **Current / Future maturity.** 3 / 7
- **Impact.** Medium
- **Difficulty.** Medium
- **Dependencies.** Validation Engine v2.0 (live tracking captures the
  data continuous learning would train on).
- **Engine owner.** Adaptive Recommendation Engine
- **Version.** v3.x
- **Success metrics.** Expectancy improvement · reduced stop-out rate
  on eventual winners.
- **Six-priority.** E · A
- **Verdict.** Tier A · Phase 3

### 15. Causal Inference

- **Why it matters.** Correlations are treated as causal today. This is
  a known institutional failure mode — factor "premia" that vanish
  when the causal chain is properly identified.
- **Research questions.**
  - Which of AEGIS's discriminating features are causal vs merely
    correlated with returns?
  - Can natural experiments (Fed announcements, index inclusions,
    earnings surprises) be exploited for causal identification?
  - What is the causal impact of AEGIS's own recommendation on
    subsequent price (self-influence at scale)?
- **Current / Future maturity.** 0 / 5
- **Impact.** High
- **Difficulty.** Foundational
- **Dependencies.** Continuous Learning · Regime Detection.
- **Engine owner.** Adaptive Recommendation Engine (as research lens)
- **Version.** v3.x
- **Success metrics.** Identified causal features vs merely correlated
  ones · robustness of causal features across regime shifts.
- **Six-priority.** V · X · E
- **Verdict.** Tier A · Phase 3 / Phase 4

### 16. Bayesian Modeling

- **Why it matters.** Point-estimate confidence is fragile. Bayesian
  posterior distributions provide credible intervals — "80% confidence
  with a 95% credible band of 65–90%" is materially more useful than
  "80% confidence."
- **Research questions.**
  - Which priors are informative but not overwhelming for AEGIS-scale
    data?
  - Is Bayesian model averaging across the 6 backtested strategies
    better than the current single-champion approach?
  - How is a Bayesian confidence integrated with DEV028's content-
    addressed audit trail (posteriors are distributions, not scalars)?
- **Current / Future maturity.** 1 / 6
- **Impact.** Medium
- **Difficulty.** High
- **Dependencies.** Compatible with determinism (ADR-006) only if
  posteriors are computed via deterministic MCMC (fixed seed + fixed
  iterations) or closed-form.
- **Engine owner.** Adaptive Recommendation Engine
- **Version.** v3.x
- **Success metrics.** Credible interval coverage · calibration under
  distributional shift.
- **Six-priority.** C · X
- **Verdict.** Tier B · Phase 3 / Phase 4

### 17. Knowledge Graph Intelligence

- **Why it matters.** DEV031-B built the graph substrate. The intelligence
  extractable from it (community-level alpha, propagation-based
  risk signals, path-explainability improvements) is largely untapped.
- **Research questions.**
  - Do graph-community memberships predict correlated draw-downs?
  - Can propagation scores from a "stress source" (regime, macro shock)
    identify vulnerable positions in advance?
  - What supply-chain / customer / supplier data would materially
    improve the graph's predictive power?
- **Current / Future maturity.** 5 / 8
- **Impact.** High
- **Difficulty.** Medium
- **Dependencies.** Supply-chain data (blocked on data-vendor decision).
- **Engine owner.** Research Foundation
- **Version.** Foundation v1.7+
- **Success metrics.** Graph-community backtest edge · propagation
  early-warning lead time.
- **Six-priority.** X · P · A
- **Verdict.** Tier A · Phase 3

### 18. Reinforcement Learning

- **Why it matters.** The most controversial topic. RL in autonomous
  trading contexts is well-explored academically and consistently
  under-performs simpler methods on real markets. It also structurally
  conflicts with advisory-only (ADR-002) if used to drive execution.
- **Research questions.**
  - Can RL be used *offline*, for feature discovery on historical
    trajectories, without any online execution loop?
  - Is the sample-efficiency ceiling of RL compatible with AEGIS's
    thin (1,060 trades) learning corpus?
  - What is the empirical evidence that RL beats simpler stacking on
    institutional-scale equity data? (Answer today: weak.)
- **Current / Future maturity.** 0 / 3
- **Impact.** Low (evidence-adjusted); Medium (aspirational)
- **Difficulty.** Foundational
- **Dependencies.** Would require a decade of trade history AEGIS does
  not have.
- **Engine owner.** N/A
- **Version.** N/A
- **Success metrics.** Only relevant if a specific offline-RL question
  is opened; not scheduled.
- **Six-priority.** none of the six clearly (E possibly)
- **Verdict.** Tier C · watch academic literature · **should probably
  never be implemented for autonomous trading**; may be Tier B for
  offline signal-discovery research once the corpus grows 10×.

---

## Group V — Human Factors

### 19. Explainable AI

- **Why it matters.** ADR-002 (advisory-only) requires human review of
  every recommendation. Explainability quality determines whether that
  review is meaningful or ceremonial.
- **Research questions.**
  - What is the correct explanation depth — should the operator see
    every graph traversal or only the top-3 factors?
  - Do counterfactual explanations ("would not have recommended if X")
    improve decision quality more than positive explanations?
  - How is explanation stability measured — same conditions producing
    same explanation over time?
- **Current / Future maturity.** 6 / 9
- **Impact.** High
- **Difficulty.** Medium
- **Dependencies.** Knowledge Graph Intelligence (Domain 17).
- **Engine owner.** Adaptive Recommendation Engine (surfaces
  explanations) + Delivery Layer (presents them)
- **Version.** Adaptive v2.x + Delivery v2.x
- **Success metrics.** Operator acceptance rate · explanation-stability
  score · counterfactual explanation accuracy.
- **Six-priority.** X · V
- **Verdict.** Tier S · Phase 2 late

### 20. Behavioral Finance

- **Why it matters.** Recommendations flow through a human decision.
  If the human systematically deviates from the recommendation, the
  platform's realised value is bounded by behavioral factors, not
  algorithmic ones.
- **Research questions.**
  - Which recommendations does the operator override, and are the
    overrides systematically better or worse than the algorithm?
  - Do time-of-day / week-of-month effects show up in AEGIS's own
    users?
  - Can UX design mitigate known biases (recency, loss aversion,
    confirmation)?
- **Current / Future maturity.** 0 / 4
- **Impact.** Medium
- **Difficulty.** Medium
- **Dependencies.** Delivery Layer usage telemetry (blocked on
  Delivery Layer v2.x with authenticated write path).
- **Engine owner.** Delivery Layer
- **Version.** v2.x
- **Success metrics.** Override quality · recommendation-follow-through rate.
- **Six-priority.** X
- **Verdict.** Tier B · Phase 3

### 21. Decision Science

- **Why it matters.** A recommendation platform is only as good as the
  quality of decisions it enables. Decision science studies the *joint*
  algorithm-human system, not either component alone.
- **Research questions.**
  - What is the correct division of labor between algorithm and human?
  - Where does the algorithm compensate for human weakness, and vice
    versa?
  - How is "decision quality" measured independent of "return"?
- **Current / Future maturity.** 2 / 6
- **Impact.** High
- **Difficulty.** High
- **Dependencies.** Behavioral Finance (Domain 20).
- **Engine owner.** cross-cutting; leans on Delivery Layer + Adaptive Rec
- **Version.** cross-cutting
- **Success metrics.** Joint expectancy (algorithm × human) vs
  algorithm-alone expectancy.
- **Six-priority.** X · V
- **Verdict.** Tier B · Phase 3 / Phase 4

### 22. Institutional Governance

- **Why it matters.** Multi-tenant, compliance, audit — the operational
  substrate an institutional buyer requires. Not research per se, but
  research is required to understand what compliance regimes AEGIS
  must satisfy.
- **Research questions.**
  - Which regulatory regimes govern advisory platforms in AEGIS's
    target markets?
  - Is AEGIS's audit trail (DEV028 DNA) sufficient for SEBI / SEC /
    equivalent audit?
  - What is the minimum viable compliance layer for the first
    institutional client?
- **Current / Future maturity.** 3 / 7
- **Impact.** High
- **Difficulty.** Medium (but not primarily technical)
- **Dependencies.** External counsel / compliance advisory.
- **Engine owner.** N/A (governance, not engine)
- **Version.** N/A
- **Success metrics.** First institutional-client onboarding without
  compliance blocker.
- **Six-priority.** V · X
- **Verdict.** Tier A · Phase 3

---

## Group VI — Data & Market Structure

### 23. Market Microstructure

- **Why it matters.** AEGIS ignores intraday microstructure today —
  bid-ask spread, order-book depth, adverse-selection cost. For daily
  rebalance this is acceptable; for finer horizons or execution
  integration it is not.
- **Research questions.**
  - What is the true realised cost per trade in AEGIS's target
    universe (currently assumed constant)?
  - How much of DEV021's backtest performance would survive realistic
    slippage assumptions?
  - Which tickers in the universe are structurally illiquid enough to
    warrant exclusion?
- **Current / Future maturity.** 2 / 6
- **Impact.** Medium
- **Difficulty.** Medium
- **Dependencies.** Intraday data feed (not currently available).
- **Engine owner.** Validation Engine
- **Version.** v2.2
- **Success metrics.** Realised-vs-modelled cost per trade · liquidity-
  filtered backtest divergence from full-universe backtest.
- **Six-priority.** V · E
- **Verdict.** Tier A · Phase 3

### 24. Alternative Data

- **Why it matters.** Every institutional shop uses alt-data (satellite,
  credit card, corporate disclosure NLP, employment postings). AEGIS
  uses only price + macro. This is a coverage gap, not a research gap
  per se — but which alt-data actually improves AEGIS's decisions is a
  research question.
- **Research questions.**
  - Which alt-data streams provide durable edge on the AEGIS universe?
  - What is the marginal cost of each stream vs its marginal impact
    on Precision@K?
  - How does alt-data edge decay with vendor commoditisation?
- **Current / Future maturity.** 0 / 5
- **Impact.** Medium
- **Difficulty.** High (vendor evaluation + integration)
- **Dependencies.** Institutional Governance (data-vendor procurement).
- **Engine owner.** Research Foundation
- **Version.** Foundation v3.x
- **Success metrics.** Precision@5 lift per data stream · cost-per-lift
  ratio.
- **Six-priority.** E · X
- **Verdict.** Tier B · Phase 3 / Phase 4

### 25. Simulation & Synthetic Markets

- **Why it matters.** AEGIS's real-market history is thin (2022+). To
  stress-test strategies against scenarios not present in history
  (rate spikes, currency crises, sector-specific dislocations) synthetic
  markets are the only credible option.
- **Research questions.**
  - What is a credible generative model for synthetic Indian equity
    markets that produces regime shifts + drawdowns of realistic scale?
  - How does one avoid strategies overfit to the synthetic generator
    rather than to real market dynamics?
  - What synthetic scenarios (Volcker shock · Asian crisis · COVID
    scale) should AEGIS stress-test against?
- **Current / Future maturity.** 0 / 5
- **Impact.** Medium (bounded by the "trained on the generator" risk)
- **Difficulty.** High
- **Dependencies.** Validation Engine v2.4.
- **Engine owner.** Validation Engine
- **Version.** v2.4 / v3.0
- **Success metrics.** Strategy survival rate under scenario ensembles ·
  identified failure modes not present in the real backtest.
- **Six-priority.** V · P
- **Verdict.** Tier B · Phase 3

---

## Ranked tiers

Ordered by evidence-weighted impact on the six priorities, matched to
current dependencies.

### Tier S — pursue in Phase 2

Programs that materially compound decision quality *and* are within
technical reach *and* have a defensible dependency chain that Phase 2
can execute.

1. **Domain 1 · Alpha Research** — the P0 confidence rebuild.
2. **Domain 12 · Validation Science** — the P1 live validation harness.
3. **Domain 6 · Position Sizing** — P3.
4. **Domain 9 · Capital Preservation** — priority #2 in the six-priority order.
5. **Domain 11 · Model Drift** — P8.
6. **Domain 5 · Portfolio Construction** — indirectly through the
   Validation Engine unlocking per-portfolio track records.
7. **Domain 3 · Regime Detection** — foundational for capital preservation.
8. **Domain 13 · Forecast Calibration** — validates Domain 1.
9. **Domain 19 · Explainable AI** — Phase 2 late.

### Tier A — Phase 3 · high-impact when dependencies clear

10. **Domain 10 · Risk Modeling**
11. **Domain 4 · Macro Intelligence**
12. **Domain 2 · Factor Investing**
13. **Domain 17 · Knowledge Graph Intelligence**
14. **Domain 22 · Institutional Governance**
15. **Domain 14 · Continuous Learning**
16. **Domain 7 · Cross-Asset Allocation** (Multi-Asset engine)
17. **Domain 8 · Portfolio Optimization** (Bayesian, robust)
18. **Domain 23 · Market Microstructure**
19. **Domain 15 · Causal Inference**

### Tier B — Phase 3 / Phase 4 · valuable but conditional

20. **Domain 24 · Alternative Data** — vendor decisions, not code.
21. **Domain 25 · Simulation & Synthetic Markets** — high risk of
    generator overfit.
22. **Domain 20 · Behavioral Finance** — needs Delivery Layer telemetry.
23. **Domain 21 · Decision Science** — depends on 20.
24. **Domain 16 · Bayesian Modeling** — compatibility with determinism
    requires careful implementation.

### Tier C — watch, do not implement

25. **Domain 18 · Reinforcement Learning** — evidence-weak for equity
    trading; conflicts with advisory-only if online-execution loop;
    revisit only when the trade corpus grows 10× and only for offline
    signal-discovery use.

---

## AEGIS Research Agenda 2035

### Immediate (0–6 months) · finish Phase 2 P0/P1

1. **Alpha Research** — feature-importance study on 1,060-trade corpus.
   Deliverable: a signal specification for Adaptive v2.0 confidence rebuild.
2. **Validation Science** — live paper-trading harness. Deliverable:
   Validation v2.0 operating for ≥ 30 days.
3. **Forecast Calibration** — verify Domain 1's rebuilt signal actually
   discriminates.

### Near-term (6–24 months) · rest of Phase 2 · early Phase 3

4. **Position Sizing** — Risk & Capital v2.0 with sizing traceable to
   inputs (why 6% not 4% not 12%).
5. **Capital Preservation** — Risk & Capital v2.1 dynamic budget.
6. **Regime Detection** — persisted per-date historical labels.
7. **Model Drift** — Validation v2.3.
8. **Portfolio Construction** — per-construction backtest history via
   Validation v2.2.
9. **Explainable AI** — Adaptive v2.x explanation surface.

### Medium-term (2–5 years) · Phase 3

10. **Institutional Governance** — first institutional-client compliance
    layer.
11. **Factor Investing** — attribution as explanation tool.
12. **Risk Modeling** — VaR / CVaR with confidence intervals.
13. **Macro Intelligence** — expanded macro decomposition.
14. **Knowledge Graph Intelligence** — community-level alpha + propagation.
15. **Continuous Learning** — MFE / MAE / entry-timing during open
    positions.
16. **Market Microstructure** — realistic slippage modeling.
17. **Cross-Asset Allocation** — precursor to Multi-Asset Engine v1.0.

### Long-term (5–10 years) · Phase 4 vision

18. **Causal Inference** — separate causal from correlational features.
19. **Bayesian Modeling** — posteriors and credible intervals as
    first-class outputs.
20. **Alternative Data** — targeted vendor decisions with measurable
    Precision@K lift.
21. **Simulation & Synthetic Markets** — stress-testing against scenarios
    not present in real history.
22. **Portfolio Optimization** — robust / distributionally-robust
    beyond HRP + Markowitz.

### 10-year vision

By 2035, AEGIS should be:

- A **continuously validated** platform whose confidence signal is
  probabilistically calibrated with credible intervals.
- A **regime-aware** allocator whose position sizing responds to macro
  shifts without operator intervention.
- A **multi-asset** capital preservation engine spanning equity · debt ·
  gold · commodity · FX in AEGIS's home market plus at least one
  international market.
- An **institutionally-audited** platform with a compliance layer
  sufficient for a first institutional client onboarding.
- A **causally-grounded** intelligence layer where alpha is decomposed
  into factor · macro · behavioral · idiosyncratic components with
  documented causal identification.
- **Still deterministic. Still advisory-only. Still evidence-driven.**
  The constitutional invariants do not change over the 10-year horizon.

---

## What AEGIS will NOT research

Stated explicitly to prevent conversation drift:

- **Autonomous execution / RL-driven trading.** Conflicts with ADR-002.
  Revisit only under a superseding ADR + external audit certification.
- **High-frequency trading / sub-second horizons.** Wrong problem for
  an advisory platform.
- **Options / derivatives strategies as primary product.** Adjacent
  domain; equity focus first.
- **Retail speculation features** (leverage recommendations, options
  gambling, day-trading signals). Contrary to mission (responsible
  long-term capital allocation).
- **Prediction markets / crypto meme assets.** Adjacent domain.
- **Sentiment-only signals** as standalone alpha. Well-known to decay
  fast; may enter as a feature inside Domain 1, never as a domain.
- **AGI / general-purpose AI research.** Out of scope.

If a proposal falls in the "will not research" list, it is not deferred —
it is rejected, with a pointer to this document.

---

## How to open a new research domain

If a candidate domain emerges outside this list:

1. Write a one-page proposal answering the same fields as every
   domain above (Why · Questions · Maturity · Impact · Difficulty ·
   Dependencies · Owner · Version · Metrics · Six-priority · Verdict).
2. Run the [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) §9
   research acceptance criteria against it.
3. If it passes, append here with the next domain number. If it
   requires a new engine or violates an ADR, open a new ADR first.
4. If it does not clearly serve the six priorities, reject — do not
   defer indefinitely, do not park in a research parking lot.

---

## Closing

This document is a research backlog with a 10-year horizon. It says
what could be researched, when, by whom, and against which success
metrics. It does not schedule engineering work — that is
[PHASE2_MASTER_ROADMAP.md](PHASE2_MASTER_ROADMAP.md)'s job. It does
not modify architecture — that is
[ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md)'s job. It does
not open new engines — that is a governance decision under
[DESIGN_DECISIONS.md](DESIGN_DECISIONS.md).

When a research program produces a shipping proposal, that proposal
runs through the constitution, opens an ADR if governance is affected,
lands in the roadmap if scheduled, and — only then — becomes code.

Read this once to understand the horizon. Consult it when the platform's
next research direction is unclear. Update it when a domain's maturity
shifts materially.
