# ARJUNA — Strategy Decision (2026-06-22)

> The honest answer to "we can't pick stocks, the weights don't work, where's the potential?"
> This document records the decomposition test that settled it and the two-style decision it forced.

## 1. The test

We turned the regime overlay OFF to isolate what stock **selection** and **weighting** contribute
on their own (Nifty-200, quarterly, net of cost, ~5.5y):

| Construction | CAGR | Sharpe | maxDD | last-4Q |
|---|---|---|---|---|
| Buy Nifty-50 index | 10.8% | 0.80 | 17.2% | −0.6% |
| EW all-200 (no brains) | **17.0%** | 1.11 | 20.7% | +6.2% |
| HRP all-200 (weighting only) | 14.6% | 1.12 | 20.2% | +2.2% |
| EW selected-15 (selection only) | 15.9% | **1.30** | 18.2% | +5.1% |
| INV_VOL selected-15 | 15.9% | 1.30 | 18.2% | +5.1% |
| MIN_VAR selected-15 | 13.7% | 1.15 | 18.0% | +2.2% |
| HRP selected-15 (v2.1 champion) | 15.6% | 1.28 | 17.8% | +4.7% |

## 2. What it proved (both user intuitions were correct)

- **HRP weighting adds nothing.** HRP-15 (Sharpe 1.28) is tied with / behind dumb equal-weight
  (1.30). INV_VOL = EW exactly. HRP-all-200 < EW-all-200 on return. The López-de-Prado machinery
  is decorative.
- **Stock selection adds little.** Picking 15 low-vol names *lowered* return (17.0% → 15.9%) and
  only nudged Sharpe via less drawdown. The dumbest option — hold all 200 equally — made the most.
- **The whole risk-adjusted edge is the REGIME overlay.** Every construction above tops out at
  Sharpe ~1.3. The live champion scores 2.02. The difference is 100% the regime/risk-manager
  (defensive exposure timing) — not selection, not weighting.

Root cause: returns here are unpredictable (AUC ~0.50 across 13 model families; momentum loses to
Nifty). Weighting can't beat a coin flip either. The only structural, repeatable effect is
**de-risking in bad regimes.**

## 3. The breakthrough — pair the best return engine with the one real edge

Equal-weight is the highest-return basket; regime is the only edge. Nobody had combined them:

| Config | CAGR | Sharpe | maxDD | Calmar | last-4Q |
|---|---|---|---|---|---|
| EW-200, regime OFF | 17.0% | 1.11 | 20.7% | 0.82 | +6.2% |
| **EW-200 + REGIME (BROAD)** | **20.6%** | 1.98 | 12.8% | **1.61** | **+10.5%** |
| HRP-15 + regime (v2.1 champion) | 16.4% | 2.02 | 11.2% | 1.46 | +7.5% |

**BROAD = EW basket + regime delivers +4.2pp CAGR over the champion at the same Sharpe.** The
selection + HRP were *costing* ~4 points of return a year for a negligible risk benefit.

Promotion gate (the bar for changing Core): **PASSED.**
- Deflated Sharpe **0.992** (>0.95 = robust; discounted for ~30 configs explored).
- Cross-period: higher CAGR in every sub-window (2021-22 18.5%, 2023-24 33.5%, 2025-26 7.9%) vs
  champion (15.3 / 25.3 / 7.0) at comparable Sharpe/DD.
- Cross-universe: holds on Nifty-100 (CAGR 19.3%, Sharpe 1.95, DD 13.2%) — not a 200-name artifact.

## 4. The decision — two validated styles, one engine (the regime overlay)

- **BROAD (higher potential, index-fund route).** Equal-weight the whole basket + regime cash rule.
  ~20% CAGR, Sharpe ~2.0, DD ~13%. Implement as an equal-weight / broad index fund + de-risk to
  cash/liquid fund when the regime flags stress. *This is where the return potential is.*
- **CONCENTRATED (individual-stock route).** 15 names + regime (the v2.1 champion). ~16.4% CAGR,
  Sharpe 2.02, DD 11.2%. For investors who want to hold specific shares with small capital; the
  ~4pp lower CAGR is the price of holding 15 names instead of the whole basket.

Set via `CONFIG.style = "broad" | "concentrated"` (see `india/config.py`, `style_kwargs()`).

## 5. The honest caveat

All CAGR figures are **survivorship-inflated** (today's index constituents). BROAD is the *most*
flattered because it holds every small/midcap that survived and re-rated, so the forward return
gap over CONCENTRATED is probably smaller than the +4pp shown. **Sharpe parity (~2.0 both) is the
trustworthy read.** The defensible, repeatable claim is: *a broad basket timed by the regime
overlay beats buy-and-hold on risk-adjusted terms and cuts drawdowns roughly in half* — not that
we can pick winners. We proved we can't, and stopped pretending.
