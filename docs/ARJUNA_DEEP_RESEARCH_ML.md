# AEGIS — Deep Research: ML in Stock Picking (external report, saved 2026-06-22)

> Independent deep-research report commissioned to pressure-test AEGIS's conclusions against
> recent academic + industry evidence. Verdict: it **confirms** our findings and adds a formal
> trigger/guardrail protocol for reopening ML. Distilled action summary first; full report below.

## What this means for us (distilled)

1. **Our core conclusion is externally validated.** Across the literature, ML beats simple factors
   only with *rich/alternative data* (macro, PIT fundamentals, sentiment) and heavy validation —
   and even then results are fragile (design choices add 59% noise; ~50% OOS accuracy; only
   13–23% of settings beat buy-and-hold). On free public price data, return prediction ~= coin
   flip. Exactly what we found (AUC ~0.50), now corroborated.
2. **Risk-management rules matching/beating ML is a known result, not a fluke.** The report ranks
   HRP + regime (our champion) as the robust performer; model-driven selection failed. This is the
   same Model-Driven vs Portfolio-Engineering split we proved.
3. **The edge is data, not models.** Priority order it recommends: **(1) point-in-time fundamentals,
   (2) historical news/sentiment, (3) analyst revisions, (4) insider/flows, (5) options flow.**
   PIT fundamentals are top priority — they remove look-ahead bias that silently inflates backtests.
4. **Reopen ML only on a trigger, never for exploration** (see protocol below).
5. **The candidate ML tasks it green-lights are exactly our Future-2 Lab ideas:** cross-sectional
   *ranking* (not absolute return), **recovery-speed prediction**, **persistence scoring**, and
   **volatility/risk prediction** — i.e. rank by RISK/resilience, the predictable side.

## The reopen-ML protocol (adopt as governance)

**Triggers (need ≥1):**
- New data arrives (PIT fundamentals, news archive, analyst revisions) → justifies a fresh hypothesis.
- Forward performance shortfall (e.g. live CAGR < 8% over a year, or risk metrics breached).
- A prototype shows deflated Sharpe > 0.9 / PBO < 0.05 under rigorous CV.

**Candidate tasks (relative/risk, not absolute return):**
1. Cross-sectional ranking (probability of relative outperformance) on up-to-date inputs.
2. Recovery-speed prediction (which drawdown stocks bounce fastest).
3. Persistence scoring (who stays top-quartile / stays low-risk 6–12m).
4. Volatility/crash-risk refinement (already AUC ~0.76).

**Evaluation (every experiment):** walk-forward / purged CV · nested CV for tuning · deflated
Sharpe + PBO given trial count · realistic costs (0.1–0.5% + tax).

**Guardrails:** Core v2.1 stays frozen and live. ML lives in a separate Lab sandbox with its own
logs. A model reaches production ONLY via a decision gate: passes DSR, beats Core's rolling Sharpe,
acceptable turnover + drawdown — net of cost, on forward data.

```
Data upgrades (PIT/news) -> Lab ML (rank/recovery/persistence) -> Validation (WF-CV, DSR, PBO, costs)
   -> pass gates? --yes--> Production gate (into Core)
                  --no---> refine/discard / wait for new data
```

## Lab experiment log

**2026-06-22 — Resilience ranking (Ideas 2-4 / report tasks 2-3): TESTED, REJECTED.**
`india/evidence/resilience_ranking.py`. Predicting forward low-drawdown out-of-sample:
trailing volatility ALONE scores AUC 0.679; the full resilience set (recovery, anti-fragility,
consistency, downside-beta) scores 0.664 — i.e. resilience features add **-0.014 AUC** (negligible/
slightly worse). Volatility is 57% of all predictive power. The resilience composite DOES pick
different stocks (21% overlap with low-vol) but without any predictive edge, so those picks would
be worse, not better. **Conclusion: resilience ranking just re-derives (slightly worse than) the
low-vol factor AEGIS already selects on — not worth a portfolio A/B.** Caveat: target was forward
drawdown; a dedicated "fastest-recovery" target is an open follow-up, but vol's dominance makes a
different result unlikely. Consistent with: risk is predictable, but VOLATILITY is its efficient summary.

This leaves the **data unlock (PIT fundamentals / news / analyst revisions)** as the only genuinely
open frontier — exactly the report's conclusion.

---

## Full report (as provided)

### Executive Summary
Recent academic and industry work shows mixed success for ML in stock picking. Deep-learning and
ensemble ML methods can sometimes edge out traditional factors, especially when rich data
(macroeconomics, alternative inputs) are used. Chen et al. (2020) used deep nets with macro data and
no-arbitrage criteria to achieve higher out-of-sample Sharpe than benchmarks. Wolff and Echterling
(2020) report ML models on S&P500 factors/fundamentals (weekly) yielded "substantial and significant"
outperformance over an equal-weighted portfolio. Robeco (Hanauer & Kalsbach, 2023) found ML ensembles
on 36 standard factors (15,000 EM stocks, 1990-2021) produced ~1.0-1.2% monthly vs ~0.8% for linear
models. State Street's (2024) ML model using media sentiment showed "strong efficacy" in predicting
sector-relative returns.

Despite this promise, ML in practice often fails to produce reliable alphas. AEGIS's own tests found
every ML strategy (XGBoost, LSTM, GNN, RL, etc.) essentially hit chance (AUC ~50%) in return
prediction, while only risk-related targets (volatility, drawdowns) were predictable. Chen et al.
(2024) show ML performance varies enormously with design choices, top-minus-bottom returns ranging
0.13%-1.98% monthly. Peng & de Moraes (2024) found SVMs on DJIA30 technical signals yield ~50% OOS
accuracy and "only 13-23% of hyperparameter settings beat buy-and-hold," highlighting rampant
overfitting. Models often fit noise or look-ahead leakage rather than genuine signals.

Meanwhile, AEGIS's portfolio-engineering rules (risk-parity weighting, sector caps) achieved very
high Sharpe (~2.0) and low drawdown without any prediction models. HRP with regime-based global
exposure (quarterly) is robust (Sharpe ~2.0, DD ~11%), whereas all ML-driven stock-picking attempts
failed. Risk-management rules and constraints matched or outperformed complex ML in real backtests.

Looking forward, AEGIS's edge likely lies in data, not new models. Point-in-time fundamentals,
historical news/sentiment, analyst revisions, insider signals, and options flow are potential
upgrades. Using proper point-in-time financials dramatically changes backtest results. Recommended:
a strict sandbox process — trigger ML research only on new data or after forward-test failures, use
walk-forward and multiple-testing controls (purged CV, deflated Sharpe, PBO, realistic costs), and
promote to production only via a decision gate.

### 1. ML Success Stories (2018-2023)
- Deep asset-pricing (Chen 2020): DNNs + macro + no-arbitrage; best OOS Sharpe/pricing.
- Ensemble ML on standard factors (Robeco 2023): ~1.2%/mo vs 0.8% linear, net of costs; no new
  factors, just non-linear interactions + rolling retraining.
- Factor ranking (Wolff & Echterling 2020): weekly cross-sectional classifiers, long top quintile;
  significant outperformance — but penalized logistic nearly matched complex ML.
- Technical + tuning (Chin 2022): ML improves many variables, but sensitive to period/tuning.
- Industry (State Street 2024): alt-data (media sentiment) + ML; strong OOS sector-relative efficacy.
Takeaway: ML works with large/rich data, careful feature selection, ensembling, proper CV, and
economic-significance focus.

### 2. Common Failure Modes
- Overfitting & multiple testing (winner's curse; design noise > standard error by 59%).
- Look-ahead / data leakage (no true PIT data => overstated).
- Non-stationarity / regime shifts (train 2010-17 fails 2020-26 without regime conditioning).
- Transaction costs & slippage (high-turnover alphas vanish net of frictions).
- Low signal-to-noise (public info priced in; return prediction worse than coin flip; EMH).
- Label noise / target ambiguity (raw returns noisy; ranking IC ~ zero).
Guard with purged walk-forward CV, deflated Sharpe, PBO.

### 3. Model-Driven vs Portfolio-Engineering (AEGIS evidence)
All model-driven selection (ML, RL, GNN) failed to produce robust strategies; portfolio-engineering
(risk parity, sector caps, regime sizing) achieved high Sharpe with acceptable drawdown.

| Method | Data | Assumptions | Strengths | Weaknesses | AEGIS result |
|---|---|---|---|---|---|
| ML tree classifiers | prices, std factors | stable cross-sectional patterns | non-linear interactions | overfits, lookahead | fails (AUC~0.50) |
| Deep learning (LSTM/Transformer) | prices, technicals | temporal patterns | sequence modeling | data-hungry, opaque, unstable | no better than random |
| RL (PPO) | price history | learnable environment | dynamic strategies | overfits, unrealistic sim | lost to buy-and-hold |
| Risk-parity (HRP) | covariance | diversify by risk | no predictions, robust | ignores valuation | best: Sharpe ~2.0, DD ~11% |
| Sector caps | sectors + HRP inputs | limit concentration | diversification | may cap alpha | Sharpe ~2.0, better spread |
| Inverse-vol / min-var | covariance | low-vol overweight | simple, low turnover | ignores corr / erratic small caps | lower Sharpe (~1.5-1.8) |

### 4. Data Upgrades (priority)
1. PIT fundamentals (high) — removes look-ahead; moderate-high cost.
2. Historical news/sentiment (medium) — license + NLP; lookahead-sensitive.
3. Analyst forecasts/revisions (medium) — leads fundamentals.
4. Insider trades / institutional flows (low-medium) — free from filings.
5. Options/derivatives flow (low-medium) — expensive, short-term.

### 5. Roadmap & Guardrails
Triggers, candidate tasks, evaluation protocols, and production gating — captured in the protocol
section at the top of this file.

### Conclusion
AEGIS Core v2.1 should remain rule-based, not predictive, until new evidence justifies change.
Finalize data (PIT fundamentals), continue forward testing, set quantitative triggers, document
rather than code new models. The brain stays focused on capital allocation and risk management;
unlock ML only on new timely data or forward-performance failure, with rigorous validation.

*Sources: peer-reviewed studies + industry reports as cited, plus AEGIS's own backtests.*
