# AEGIS — Whitepaper

*A risk-managed Indian-equity recommendation system with an evidence-gated research process.*
*Version: Production 1.x (frozen). This document states what AEGIS does and, just as importantly, what it
does not claim.*

---

## 1. Philosophy

AEGIS is built on one empirically-tested premise: **on public price data, future returns are close to
unpredictable, but risk is predictable.** Accordingly, the system does not try to forecast which stock
will rise most. It constructs a diversified, risk-controlled portfolio and times overall market exposure.
A second principle is **honesty over polish**: where evidence is weak or absent, the output says so
("insufficient evidence", "not evaluated") rather than manufacturing a number.

## 2. Architecture

```
Market data → Dynamic tradable universe → [ Market regime · Sector caps · Company selection ·
  Data layers · HRP portfolio · Risk profile ] → Recommendation + Explanation
        → Recommendation database · Evidence scorecard · Delivery (Excel · Sheets · Telegram)
        → Daily CI automation
```
Production and research are separated: a **frozen production engine** and an **isolated research lab**
where any model change must earn promotion.

## 3. Methodology

- **Universe:** built from liquidity/tradability filters (turnover, price floor, history), not a fixed index.
- **Selection:** lowest trailing-volatility names (the only signal with out-of-sample skill), sector-capped.
- **Weighting:** Hierarchical Risk Parity (HRP) — correlation-cluster aware, avoids mean-variance instability.
- **Regime overlay:** scales exposure by market state (volatility gauge, trend, global risk) — the single
  largest validated edge.
- **Dynamic policy:** holding period (regime-conditional) and basket size (breadth/regime) are chosen from
  evidence, risk-first; review cadence adapts to regime.
- **Risk profiles:** one engine, three preferences — Shield (default), Balanced, Growth (experimental).

## 4. Validation

Every idea must survive: walk-forward / rolling out-of-sample testing; the **Deflated Sharpe Ratio** and
**Probability of Backtest Overfitting** (discounting for the number of trials); and a
**recommendation-quality score** (average forward-return percentile; 0.5 = random) that measures whether
*selection* adds skill. It largely does not on price alone — an honest, repeatedly-reproduced finding.

## 5. Evidence

The system measures itself continuously: win rate, rolling-12-month form, sector/regime/holding
breakdowns, **calibration** (do implied probabilities hold up? — they do not at the single-stock level),
and **decision quality** (max favourable / adverse excursion, quality labels). Live recommendations are
snapshotted into a growing database with a full lifecycle and daily change explanations.

## 6. Production

Frozen at tags `v1.0`–`v1.3`. Includes: dynamic universe, dynamic holding/sizing/review, portfolio
construction, risk profiles, explainability (suitability decomposition + attribution), the evidence loop,
daily automation, and recommendation history. Production changes **only** through a formal promotion.

## 7. Research Lab & Promotion Rules

New datasets/models live in `india/ai_lab/` (LAB-001…), tracked by an experiment registry, a leaderboard,
and a research journal. The promotion pipeline:
```
Raw → Validation → Feature engineering → Information Coefficient → Incremental lift
   → Walk-forward → Forward paper → Production gate
```
Promote only if it beats the frozen baseline out-of-sample, holds across folds, survives a trial penalty,
then forward paper. Otherwise: documented "tested, not adopted." **Nothing auto-promotes; a human approves.**

## 8. Results (relative, risk-adjusted — the trustworthy lens)

Backtests show the portfolio beating the index on a risk-adjusted basis with materially lower drawdown.
A risk-tier study found a medium-volatility tier competitive on Sharpe, with high-volatility clearly worse
(≈2× drawdown). Absolute return levels are survivorship-inflated and are **not** the headline; the
relative, risk-adjusted edge is. Live forward paper is the real ongoing test.

## 9. Limitations (stated plainly)

- **Stock selection is not validated as alpha** — picks are risk-managed constituents, not proven winners.
- **Absolute backtest returns are survivorship-inflated**; trust the relative/risk-adjusted signal.
- **Per-stock probabilities are miscalibrated** — do not over-trust the confidence column.
- **No fundamentals / earnings / news / flows yet** — "not evaluated", with a gate ready to test them.
- Backtests are gross of some real-world frictions; capacity and live slippage are untested at scale.

## 10. Future Research

One non-price dataset at a time, each through the gate: earnings surprises → PIT fundamentals →
corporate events → institutional flows → and only then a learning-to-rank model over the *kept* features.
Success is measured by **evidence generated** — datasets tested, hypotheses rejected, and the rare one
that survives to promotion — not by features shipped.

---

*AEGIS is a portfolio-allocation engine with strong explainability and disciplined validation. It is not,
and does not claim to be, an alpha-discovery engine — yet. Whether it becomes one depends entirely on
whether richer information can clear the same evidence bar that price-only signals could not.*
