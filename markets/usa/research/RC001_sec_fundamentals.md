# Research Cycle 001 — SEC fundamentals vs price-only baseline

**Status:** CLOSED · **Verdict:** NOT PROMOTED · **Date:** 2026-06-29 · **Harness:** `core/usa_research.py`

## Question
Does adding point-in-time SEC EDGAR fundamentals (ROE, net margin, revenue growth, leverage) measurably
improve USA stock selection over the price-only baseline? Promote only on statistically meaningful lift.

## Method
- **Point-in-time:** fundamentals reconstructed as KNOWN at each past rebalance via SEC `filed` dates
  (`normalize_one(ticker, today=rebalance_date)`) — no look-ahead.
- **Walk-forward:** monthly rebalance (21d), ~quarter forward window (63d), over available USA history.
- **Universe:** 80 names with BOTH price history and SEC filings.
- **Composite:** z-scored blend of f_roe + f_net_margin + f_rev_growth_yoy − f_debt_to_equity.
- **Tests:** (1) Information Coefficient = Spearman corr(composite, fwd return), mean + IC-IR;
  (2) incremental lift = fwd-return percentile of price+fundamental selection vs price-only.

## Result
| Metric | Result | Promote bar | Pass |
|---|---|---|---|
| Walk-forward dates | 21 | — | — |
| mean IC | **+0.019** | > 0.03 | ✗ |
| IC-IR (consistency) | **+0.84** | > 2.0 | ✗ |
| Lift (fund vs price-only) | **−0.008** | > +0.02 | ✗ (negative) |

## Verdict
**NOT PROMOTED.** Faint, inconsistent signal; tilting selection toward "strong fundamentals" slightly
*reduced* forward returns. The data-layer gate rejected the factor rather than curve-fit it in.

## Caveats (honest scope)
- Limited USA price history (~2y) and SEC coverage (80 names) → low statistical power. A null here is
  "no evidence it helps," NOT "proven useless."
- Static composite + equal weights (no learned blend yet). A learned/non-linear combination, or single
  factors in isolation (e.g. quality-only, growth-only), were not separately tested.

## Next options (do NOT auto-pursue — pick deliberately)
1. **Widen coverage** (full SEC fetch for the screened universe + longer price history) and re-run — the
   cheapest way to turn "insufficient power" into a real yes/no.
2. **Decompose** the composite — test each fundamental factor's IC alone before blending.
3. **Move on** to the next dataset (earnings/insider/ETF/macro/news), accepting fundamentals as
   "parked — not promoted on current evidence."
