# Program 0 — Research Infrastructure Expansion: old vs new

**Goal:** more *evidence* (history + coverage), not more factors. Re-run RC001 & RC002 on the expanded
dataset and see whether the "Investigate" verdicts strengthen or collapse. **Date:** 2026-06-29.

## What expanded
| | Before | After |
|---|---|---|
| Price history | ~2y (501 days, uniform) | up to max (AAPL 1980+); panel window capped to 14y SEC era |
| SEC coverage | 74 normalized | **208 normalized** (full screened universe fetched) |
| RC001 panel | 74 names · 21 dates · **7 non-overlap** | 204 names · **165 dates · 55 non-overlap** |
| RC002 events | 359 · 8 non-overlap months | **7,799 · 97 non-overlap months** |

## Result — every USA lead collapsed under power
| Factor / experiment | 2y (small N) | 14y expanded (powered) | Read |
|---|---|---|---|
| f_roe | IC −0.134, IR −3.79 | **+0.007, IR 0.41** | "inverse" was a 2024–26 regime artifact — CONFIRMED |
| f_rev_growth_yoy | +0.108, IR 1.53 | **+0.001, IR 0.04** | "best lead" was small-sample noise |
| f_net_margin | −0.083 | +0.011 | flat |
| f_debt_to_equity | +0.032 | −0.024, IR −1.38 | flat |
| learned blend (purged) | +0.083, IR 1.89 | **+0.006, IR 0.49** | no learned edge (naive 0.118 was leakage, again) |
| holding 252d | (overlap IR 2.56) | −0.040, IR −1.45 | the long-horizon "signal" was overlap inflation — dead |
| RC002 earnings surprise | +0.108, IR 0.99 (n8) | **+0.021, IR 0.84 (n97)** | no drift |

Sector/regime slices (RC001.3/.4): nothing robust (a stray Materials −0.113/IR −2.0 and bull −0.026/IR −1.95
are within multiple-testing noise over ~6 sectors).

## Verdict
**All USA fundamental factors and the naive-YoY earnings surprise are NOT PROMOTED — now as confident
rejections, not "insufficient power."** Simple static fundamental ratios carry no cross-sectional IC in this
204-name liquid US universe over 14 years; naive-YoY PEAD shows no drift over 97 non-overlapping months.

## Why this is the project's most important result
1. **Vindication of the discipline.** Had we promoted f_roe or revenue growth on the 2y data, we'd have
   shipped noise. The gate held; Program 0 supplied the power to prove it.
2. **Confirmed the flagged risk.** RC001 explicitly warned ROE-inverse "may be a 2024–26 artifact." It was.
3. **Power, not cleverness, is the bottleneck** — exactly why Program 0 came before RC003.

## Caveats (honest)
- **Survivorship bias:** the 14y panel uses only currently-listed names. This would *inflate* apparent
  factor performance, so a flat result is a *strong* null (the real effect is no better). A survivorship-free
  source (CRSP/Norgate) is on the roadmap, not today.
- **Naive proxy:** RC002 used YoY EPS as the surprise expectation (no free analyst estimates). The null
  rejects *this proxy*, not post-earnings drift in general.

## Implication for the roadmap
Continuing B/C/D/E with simple static features on this universe is unlikely to clear the gate. The higher-value
directions: (a) a survivorship-free dataset, (b) genuinely different signals (insider, flows, revisions —
not static ratios), (c) accept that the USA cross-sectional fundamental edge is ~0 and let India's regime
overlay remain the only validated alpha. Decide deliberately — do not reflexively run RC003.
