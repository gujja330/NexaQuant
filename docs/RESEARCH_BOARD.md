# ARJUNA — Research Board (the heartbeat)

> One living tracker. Not architecture, not documents — hypotheses, evidence, decisions.
> **v2 is COMPLETE.** Not because it's perfect — because it answered its research question.

## v2 — question answered

> **Can public, price-derived features produce reliable weekly/monthly stock recommendations?**
> **Answer: NO** (for every approach tested) — while regime-aware portfolio construction DOES
> improve risk-adjusted *portfolio* outcomes. Two different achievements; both now evidenced.

## v3 — the Discovery Program (new question)

> **Can point-in-time earnings, events, institutional flows, and fundamentals measurably improve
> recommendation quality BEYOND the current baseline?**
> Objective is no longer "build ARJUNA." It is: **find ONE reproducible source of alpha.**
> If the answer is also "no", that is a valuable result. If "yes", it's ARJUNA Discover's first edge.

## The board

| ID | Hypothesis | Status | Evidence |
|---|---|---|---|
| H1 | Momentum ranks winners | ❌ Rejected | RQS 0.522, IC 0.030 (weak) |
| H2 | Low-volatility ranks winners | ❌ Rejected | RQS 0.501, hit 20% — it's a RISK factor |
| H3 | Composite price factors rank winners | ❌ Rejected | RQS 0.492, IC 0.004 |
| H4 | Regime improves portfolio risk | ✅ Accepted | Sharpe 1.28→2.02; backpaper OOS 1.61 vs 0.62 |
| H5 | PIT fundamentals improve ranking | ⏳ Unknown | needs data |
| H6 | Earnings surprise improves ranking | ⏳ Unknown | needs data |
| H7 | Event data improves ranking | ⏳ Unknown | needs data |
| H8 | Institutional flow improves ranking | ⏳ Unknown | needs data |

## The development cycle (enforced)

```
Hypothesis → Dataset → Baseline → Evidence → Decision
```
No coding until a hypothesis is clearly defined. A good story is not evidence.

## The only work allowed (next 6 months)

1. **Acquire data** — PIT fundamentals · earnings · events · institutional flow.
2. **Validate data** — does it lift RQS *beyond* the baseline? (Incremental Information, below.)
3. **Forward paper** — did the live recommendations actually work?

**Forbidden:** new ML models · new dashboards · new architecture · new confidence formulas.

## The metric that decides a dataset: Incremental Information

Don't ask "does PIT work?" Ask "does PIT improve recommendations *beyond what ARJUNA already
knows*?"
```
Portfolio only        RQS 0.50
Portfolio + dataset   RQS 0.59     ->  incremental +0.09 = the dataset's value
```
A dataset earns a place in ARJUNA Discover ONLY if its incremental RQS is positive AND survives
rolling OOS + forward paper.

## The three products (a quant research platform, not a "stock picker")

- **ARJUNA Portfolio** — capital allocation (DONE, frozen, forward-paper pending).
- **ARJUNA Discover** — research candidate generation → a WATCHLIST (data-gated; empty until a
  dataset clears the gate).
- **ARJUNA Evidence** — measures whether ideas actually work: the **Recommendation Registry**
  (`india/recommendation_registry.py`, every rec stored + scored) and the **RQS scorecard**
  (`india/evidence/recommendation_quality.py`).

## Live evidence status

- Recommendation Registry seeded: 19 historical recs / 285 picks scored → **RQS 0.509 (≈ random)** —
  confirms the champion's *selection* has no recommendation skill (it's a risk engine).
- First **LIVE** forward rec logged (matures next quarter). Forward observations now accumulating —
  that database will be worth more than another 100 backtests.
