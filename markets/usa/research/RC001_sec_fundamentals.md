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

---

# RC001.x — deep decomposition (2026-06-29)

Instead of fleeing to the next dataset after the composite failed, we extracted everything the SEC data
can tell us: per-factor IC, learned blend, sector/regime conditioning, holding-period sweep. Panel cached
to `markets/usa/research/rc001_panel.parquet` (74 names, 21 dates).

## ⚠️ Methodology fix that changed the conclusions
The first deep run produced TWO spectacular results — LGBM IC **+0.287** and a 252d-horizon IC-IR **+2.56**.
Both were **artifacts of overlapping forward-return windows**: at 21d cadence a 63d window overlaps the next
~2 dates (252d: ~11), and quasi-static quarterly fundamentals let the model partly memorise stocks whose
train/test return windows leaked across the split. We hardened the harness — **embargo** overlapping-label
train dates (LGBM) and measure IC-IR on **non-overlapping dates only** — and both effects collapsed.

| Cycle | Naive (leaky) | Corrected (honest) | Read |
|---|---|---|---|
| RC001.2 LGBM | IC +0.287, IR 6.80 | **IC +0.083, IR 1.89** | ~70% was leakage; not significant |
| RC001.5 @252d | IC +0.081, IR 2.56 | **insufficient** | entirely overlap inflation |

## What survives (honest, non-overlap, fwd 63d, 7 independent dates)
| Factor | mean IC | IC-IR | Verdict |
|---|---|---|---|
| f_roe | **−0.134** | −3.79 | reliably *inversely* predictive |
| f_net_margin | −0.083 | −1.11 | weak negative |
| **f_rev_growth_yoy** | **+0.108** | +1.53 | best positive lead, **underpowered** |
| f_debt_to_equity | +0.032 | +0.41 | none |

- **The composite failed by CANCELLATION**, not because fundamentals are useless: revenue growth (+) and
  ROE (−) net to ~0 when equal-weighted. Decomposition answered the open question.
- Learned blend's honest edge (+0.083 > equal-weight +0.028) is interpretable as exactly this — down-weight
  ROE, up-weight growth — but does NOT clear significance on current data.
- Sector (Financials −0.077, Tech −0.053) and regime conditioning: nothing significant (n=5–7).

## Verdict (RC001 overall): NOT PROMOTED — but with a real lead and a clear blocker
The blocker is **statistical power** (74 names × 7 independent dates), not the model. The hardened harness
caught two false positives the naive version would have promoted — the gate working as intended.

## Next options (do NOT auto-pursue — pick deliberately)
1. **Widen coverage** (full SEC fetch for the screened universe + longer price history), then re-run the
   growth-vs-ROE lead and the purged learned blend — the only way to turn the lead into a real yes/no.
2. **Test the growth−ROE tilt directly** as a single hypothesis (RC001 says equal-weight is wrong; a
   long-growth/short-quality tilt is the specific thing to validate).
3. **Move on** to the next dataset (earnings/insider/ETF/macro/news), parking fundamentals as
   "growth is a weak positive lead; ROE inverse; not promoted on current power."

---

# RC001.6 / .7 / .8 — explainability (2026-06-29, `core/usa_explain.py`)

Before widening coverage we asked WHY (analysis, not a framework change). Pooled within-date rank-IC over
the cached panel (74 names, 21 dates, fwd 63d).

## RC001.6 — WHY is ROE negative? (it is BROAD, not a one-sector fluke)
ROE-IC by sector: Tech **−0.221**, Healthcare −0.168, Utilities −0.145, Industrials −0.123,
Consumer Disc −0.113, Financials −0.033, Real Estate −0.016, **Materials +0.145** (only positive).
Inverse in **both regimes** (−0.149/−0.148) and **every year** (−0.125 → −0.227 worsening into 2026).
→ In this universe/period high-ROE names systematically underperformed, hardest in Tech — a
"quality-already-priced-in / mega-cap mean-reversion" signature. **Caveat:** so regime-stable *within* a
2024–26 rate-driven rotation that it may itself be a regime artifact; longer history must test this.

Revenue-growth-IC by sector: Healthcare **+0.244**, Materials +0.141, Consumer Disc +0.102,
Industrials +0.074, Financials +0.022, Utilities ~0, Tech −0.009, Real Estate −0.161. Growth pays in
healthcare/cyclicals, is **absent in Tech**, and **faded in 2026** (+0.13 in 2025 → −0.01).

## RC001.7 — is it a size effect? NO
ROE inverse in every cap bucket (Mid −0.171, Small −0.159, Mega −0.130, Large −0.076). Growth positive in
every bucket (Mid +0.136, Mega +0.119, Large +0.078, Small +0.031). Neither finding is driven by one size
segment → both are robust to size, which strengthens the hypothesis.

## RC001.8 — factor interaction growth × low-debt: NONE
high-growth+low-debt 0.510 vs high-growth+high-debt 0.519 vs high-growth-any 0.515. Low-debt adds −0.006.
Debt is not a useful conditioner — parked.

## Net of explainability
The "growth-tilt / ROE-inverse" lead is **robust across sectors, sizes, and regimes** (growth concentrated
in healthcare/cyclicals; ROE-inverse broad, strongest in Tech). The one open risk is that ROE-inverse is a
2024–26 regime artifact — which is precisely what coverage+history expansion must now test. Every result is
logged in `markets/research/LEADERBOARD.csv`.
