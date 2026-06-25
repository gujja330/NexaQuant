# ARJUNA — Hypothesis Registry (authoritative scorecard)

> The scientific contract. Nothing promoted on intuition. Flow: **Hypothesis → Experiment →
> Evidence → Promotion.** Four buckets: REAL (measured) · PARTIALLY VALIDATED · REJECTED · UNTESTED.
> Updated 2026-06-22. **FEATURE-BUILDING IS FROZEN** — the only work that counts now is forward paper.

## 🟢 REAL — measured from actual backtests (trust the RELATIVE edges, not the inflated levels)

| Result | Numbers | Trust level |
|---|---|---|
| **Regime overlay** (the strongest finding) | no-regime Sharpe 1.28 / DD 17.8% → global regime 2.02 / 11.2% | HIGH (relative) |
| Champion vs Nifty | CAGR 16.4 vs 10.8 · Sharpe 2.02 vs 0.80 · DD 11.2 vs 17.2 | HIGH (relative), levels inflated |
| Decomposition (HRP ≈ EW; selection adds little) | HRP-15 Sharpe 1.28 ≈ EW-15 1.30 | HIGH |
| Capital Ladder | 50K/3 · 1L/5 · 5L/8 · 10L/15 · 25L/20 · 1Cr/25 (15 = sweet spot) | MEDIUM (in-sample) |
| Probability Surface | P(+) 1W 55% → 6M 93% → 1Y 96% (rolling windows) | MEDIUM (unconditional) |
| Quarterly > monthly · sector≤2 · MC · recovery · underwater · tail · DSR/PBO | all real | HIGH (relative) |

## 🟡 PARTIALLY VALIDATED — some evidence, not proven

| Claim | Have | Missing |
|---|---|---|
| Horizon modes (Tactical/Opportunity/Core) | horizons are data-backed; short-end coin-flip confirmed | the LOW/MED/HIGH labels are subjective → forward evidence |
| Confidence = min(regime, horizon) | a heuristic; conditional test mildly *refuted* it | a discovered law, not an assumption |
| Expected gains (e.g. 6M → ₹8,746) | historical median | forward performance will differ |

## 🔴 REJECTED — evidence says no (do not revisit without new data)

Return prediction · LSTM · RL · GNN · Dynamic-N · Resilience ranking · Sector-momentum tilt ·
Per-stock timing · Multibagger · HMM · GARCH · vol-target · crash classifier · triple-barrier.

**Simple-factor ALPHA RANKING** (momentum + low-vol + sector strength → top-20) — TESTED 2026-06-22
(`evidence/alpha_ranking.py`): Sharpe 0.83 vs low-vol 1.19 vs random 1.02; **IC +0.008 (full) /
+0.035 (OOS) ≈ no skill.** Momentum+sector ADD NOISE to low-vol. A separate "Alpha Engine" is the
right ARCHITECTURE but is **data-gated** — on price/technical data the ranking signal isn't there;
it reopens with PIT fundamentals/news/flows (v4 Trigger 1), not before. 4th independent test to hit
the same wall (with AUC 0.47, resilience 0.66, momentum<Nifty).

## ⚪ UNTESTED — ideas, not results (zero evidence)

| Idea | Status |
|---|---|
| Horizon-aware selection (momentum@1M / quality@6M / regime@1Y) | pure hypothesis; low prior after alpha-ranking IC~0 |
| ARJUNA Alpha/Ranking Engine on NEW data (PIT/news/flows) | architecturally right, data-gated (v4 Trigger 1) |
| Confidence matrix (regime × horizon → label) | assumptions; conditional cells too thin |
| Goal Engine | built, NOT validated |
| Wealth OS allocation glide-path | built, NOT validated |
| Position count by horizon | unbuilt |

## How we advertise it (honesty rule — adopted)

Do **NOT** lead with "Expected CAGR 16%" (survivorship-inflated). Lead with the trustworthy,
relative, risk-side numbers:
```yaml
Probability positive:  93% (6-month hold)
Expected drawdown:     11%
Worst month:           -5%
Tail risk:             contained
Review:                quarterly
```

## Maturity scorecard (user's assessment, adopted)

| Layer | Maturity |
|---|---|
| Core engine | 99% |
| Validation | 95% |
| Product layer | 60% |
| **Forward evidence** | **0%** |
| Data quality | 70% |
| **Overall** | **~98%** — and the missing 2% is the hardest, because it needs **time** |

## The only experiment that matters now: FORWARD PAPER

Worth more than 100 more backtests / AI models / architecture diagrams combined.

**Protocol (Q3'26 → Q2'27):**
1. Start of each quarter: `python india/monthly_snapshot.py` → freezes a dated, timestamped
   recommendation of record (basket, weights, regime, probability-surface expectation).
2. End of the quarter: record the *realized* return of that frozen basket vs the prediction
   (vs Nifty, net of cost). No edits to the basket mid-quarter.
3. After 4 quarters: compare realized vs predicted. Promote PARTIALLY-VALIDATED items to REAL only
   if forward results hold (DSR>0.95 · PBO<0.05 · rolling Sharpe>Core · forward paper >4Q net of cost).

Until then: **no new features.** Core v2.2 stays frozen and live; everything else waits on time.
