# AEGIS — Evidence-Driven Alpha Research (the next phase)

> NOT "AI-first." NOT "data-first." **Evidence-first.** Data alone is not enough — every dataset
> must earn promotion through the same scientific gate. The bottleneck is no longer algorithms; the
> open question is whether *new, point-in-time information* adds incremental predictive value —
> which is **unproven** until tested.

## The correction (scientific humility)

We do NOT claim "the edge lives in non-price information." What we actually have is:

> **Our evidence shows the price-derived features we tested did not produce a useful ranking signal.
> We do NOT yet have evidence that non-price data WILL succeed. The next phase investigates whether
> additional point-in-time information adds incremental predictive value — and rejects what doesn't.**

That distinction matters. A good story is not evidence.

## Three parallel tracks

```
                         AEGIS Research
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
   Track A                  Track B                  Track C
   Portfolio Engineering    Alpha Data Research      Validation Framework
   🟢 Production (frozen)    🟡 Research               🟢 Built (the gate)
```

### Track A — Portfolio Engineering (DONE, frozen)
HRP/EW · regime · sector cap · position sizing · quarterly rebalance. Backpaper-passed (OOS Sharpe
1.61 vs Nifty 0.62). Forward paper is its only remaining test.

### Track B — Alpha Data Research (the six streams)
| # | Stream | Price-derivable? | Priority |
|---|---|---|---|
| 1 | Earnings (dates, surprise, trend, guidance, margin) | NO | ⭐⭐⭐⭐⭐ |
| 2 | Relative Strength (stock vs sector vs Nifty) | YES (low prior) | ⭐⭐⭐ |
| 3 | Sector Rotation (which sector attracts money) | PARTLY | ⭐⭐⭐⭐ |
| 4 | Institutional Flow (FII/DII/MF/ETF history) | NO | ⭐⭐⭐⭐⭐ |
| 5 | News/EVENT (orders, approvals, promoter buys, upgrades) | NO | ⭐⭐⭐⭐⭐ |
| 6 | Fundamental CHANGE (Δ ROE, Δ valuation, acceleration) | NO (PIT) | ⭐⭐⭐⭐⭐ |

Frontier = the non-price streams (1, 4, 5, 6). Whether ANY of them works is **unknown** — that is
the experiment, not the assumption.

### Track C — Validation Framework (BUILT: `evidence/recommendation_quality.py`)
The gate that prevents emotional attachment to any dataset. Every method/dataset is scored on what
users actually care about — recommendation quality — not Sharpe:

- **RQS** (Recommendation Quality Score): avg forward-return percentile of the picks. 0.50 = random.
- **Hit Rate**: % of picks finishing in the TOP QUARTILE over the horizon.
- **Avg rank**: where the picks land out of the universe (lower = better).
- **IC**: Spearman of score vs forward return (>0.05 = useful).

**Current scorecard (price-factor baselines, top-20, monthly, 3-month horizon, ~56 samples):**

| Method | RQS | Avg rank | Hit% | IC | Verdict |
|---|---|---|---|---|---|
| Random | 0.495 | 113/224 | 26% | — | none |
| Momentum | 0.522 | 107/224 | 31% | +0.030 | weak |
| Quality (risk-adj) | 0.503 | 111/224 | 27% | +0.025 | none |
| Low-Vol | 0.501 | 112/224 | 20% | −0.038 | none |
| Alpha (composite) | 0.492 | 114/224 | 21% | +0.004 | none |

Reading: **no price factor has recommendation skill** (all ~dead-center). Momentum is marginally
best but below the useful IC bar. Low-Vol (what we use) has the *worst* hit rate — it's a RISK
factor, not a recommendation factor. **These rows are the bar every new dataset must clear.**

> Note: true Quality/Value factors need POINT-IN-TIME fundamentals we don't have causally — we
> can't even *score* them here. That gap is itself the argument for PIT fundamentals as dataset #1.

## The DATA CHALLENGE (how every dataset competes)

```
New Dataset → Features → IC → RQS / Hit Rate → rolling OOS → Forward Paper → Production?
```
Each dataset runs the *identical* pipeline; the scorecard decides. Winners survive, stories don't.
Promotion criteria (all required): IC > 0.05 · RQS lift over baselines · beats standard factors ·
survives rolling OOS · survives forward paper.

## AEGIS Discover → outputs a WATCHLIST, not a buy list

Research and portfolio management are separate functions (as in real desks):
```
New-data signals → AEGIS Discover → WATCHLIST (20, with WHY/catalysts/risks/horizon)
                                          → AEGIS Portfolio decides → Final Buy List (5)
```
Discover proposes a watchlist; Portfolio disposes. Institutions don't buy everything research
suggests — and neither should AEGIS.

## The five datasets to acquire (priority)

1. Point-in-time fundamentals · 2. Earnings history & revisions · 3. FII/DII & institutional flow
history · 4. Event database · 5. Sector-rotation indicators (cheapest, lowest prior).

## The phase name

**Evidence-Driven Alpha Research.** Not AI-first, not data-first — evidence-first. The five
questions every dataset must answer: (1) new information? (2) improves ranking quality? (3) beats
existing baselines? (4) survives rolling OOS? (5) survives forward paper? Only then → AEGIS Discover.
