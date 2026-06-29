# AEGIS Research Leaderboard

The single knowledge base of **every experiment across USA and India**. Source of truth: `LEADERBOARD.csv`
(this file is the human-readable view). Append a row for every cycle — promotions AND rejections. Over time
this is the institutional memory that stops us re-testing dead ideas and shows what actually has edge.

**Status legend:** ✅ KEPT (validated, in/near production) · 🟡 INVESTIGATE (real lead, not yet significant)
· 🔴 REJECT-as-positive / WEAK · ⚪ NEUTRAL / no effect · ❌ NOT PROMOTED

**Read IC-IR, not single ICs.** Promote bar: IC > 0.03 AND \|IC-IR\| > 2.0 (non-overlap) AND positive lift,
then paper-forward — never straight to a live baseline.

## USA — Research (paper only)
| Cycle | Factor / experiment | IC | IC-IR | n | Status | Note |
|---|---|---:|---:|---:|---|---|
| RC001.1 | revenue growth (YoY) | +0.108 | +1.53 | 7 | 🟡 investigate | best lead; Healthcare/Materials; faded 2026 |
| RC001.1 | ROE | −0.134 | −3.79 | 7 | 🔴 reject-as-positive | INVERSE across sectors (Tech −0.22) & regimes; fade candidate |
| RC001.1 | net margin | −0.083 | −1.11 | 7 | 🔴 weak | weak negative |
| RC001.1 | debt/equity (low=good) | +0.032 | +0.41 | 7 | ⚪ neutral | not significant |
| RC001.0 | composite (equal-weight) | +0.028 | +0.69 | 7 | ❌ not promoted | failed by **cancellation**, not uselessness |
| RC001.2 | LGBM learned blend (purged) | +0.083 | +1.89 | 15 | 🟡 investigate | naive +0.287 was leakage; honest edge = down-ROE/up-growth |
| RC001.8 | growth × low-debt | — | — | — | ⚪ no effect | low-debt adds −0.006; no interaction |

## INDIA — Production (frozen) + decomposition evidence
| Cycle | Factor / experiment | Lift | Status | Note |
|---|---|---|---|---|
| decomp | regime overlay | + | ✅ KEPT | the **entire** Sharpe~2.0 edge = defensive regime timing |
| decomp | HRP weighting | flat | ⚪ neutral | ~0 over equal-weight |
| decomp | stock selection | flat | ⚪ neutral | ~0 over equal-weight; selection is not the alpha |
| decomp | pure momentum top-5 | − | ❌ not promoted | loses to Nifty buy-and-hold on every metric |
| gate | dynamic Top-N | − | ❌ not promoted | lost OOS; price optimisation exhausted (frozen-not-rejected) |

## Standing leads to validate (next, with more power)
1. **Growth-tilt / ROE-inverse** blend (NOT equal-weight) — sector-conditional (favor Healthcare growth,
   fade Tech ROE). Needs longer history to rule out a 2024–26 regime artifact.
2. **Purged learned blend** — re-test once coverage gives enough non-overlapping dates for IC-IR > 2.
