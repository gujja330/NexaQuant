# RC010 — Cross-market regime overlay (India's edge → USA)

**Status:** investigate (cross-market DEFENSIVE overlay) · **Date:** 2026-06-29 · **Script:** `experiments/rc010_regime_crossmarket.py`

Tested the LOCKED `regime_exposure` (de-risk below 200-DMA and/or VIX top-quintile) on deep USA index
history vs buy-and-hold; India run as the reference baseline. Lagged signal, no look-ahead.

| Market | Sharpe (B&H → regime) | CAGR (B&H → regime) | MaxDD (B&H → regime) | per-year DD-improved |
|---|---|---|---|---|
| **USA (1927–2026, 99y)** | +0.42 → **+0.51** | +6.3% → +6.5% (preserved) | −86% → **−72%** | **91/99** |
| India (2021–26 ref, ~6y) | +0.79 → +0.59 | +10.7% → +6.1% | −17% → −18% | 4/6 |

## Verdict: INVESTIGATE — cross-market as a DEFENSIVE overlay, not unconditional alpha
- **What generalizes (robust):** drawdown reduction. On 99 years of USA — through 1929, 1937, 2000, 2008,
  2020 — the overlay cut MaxDD by 14 points and reduced drawdown in **91/99 years**, while *preserving*
  CAGR and lifting full-period Sharpe. The defensive *property* is real and cross-market.
- **What does NOT generalize (the honest caveat):** unconditional return benefit. Sharpe improved in only
  **36/99 individual USA years** — the gains concentrate in crisis regimes. In a sustained bull with no
  crisis (India 2021–26), the overlay simply costs upside (Sharpe +0.79→+0.59). Net value is
  **regime-conditional**: it pays when the period contains stress, drags when it doesn't.

## Why the India reference "failed" (consistent, not contradictory)
India's validated Sharpe-~2.0 edge was the overlay applied to the *selected portfolio* over 2021–26; here we
applied the generic overlay to the *raw Nifty index* over that same short bull window — a different, harder
test with no crisis to protect against. The USA 99-year test is the fair one for a crisis-protection tool,
and there it clearly works.

## Implication
Catalogue the regime overlay as a **cross-market defensive / risk-management overlay** (high confidence on
drawdown reduction), not a return enhancer. That is genuinely valuable — the closest thing AEGIS has to a
Global factor — but promote it *as risk management*, and validate on a selected USA paper portfolio across
both crisis and bull sub-periods before any "Global alpha" claim.

**Next best experiment:** apply the overlay to the USA *paper portfolio* (not just the index), split crisis
vs bull sub-periods to quantify the conditional trade-off, then forward-track.
