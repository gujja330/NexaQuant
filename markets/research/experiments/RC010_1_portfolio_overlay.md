# RC010.1 — Regime overlay on the USA portfolio (risk-management view)

**Status:** PROMOTED (cross-market defensive risk overlay) · **Date:** 2026-06-29 · **Script:** `experiments/rc010_1_portfolio_overlay.py`

Equal-weight USA portfolio (breadth>=30), regime overlay from SPX+VIX, lagged (no look-ahead). Judged as
RISK MANAGEMENT. Period 1980-03-18..2026-06-29, 11664 days.

| Metric | Portfolio | +Overlay |
|---|--:|--:|
| CAGR | +22.9% | +20.4% |
| Sharpe | 1.13 | 1.38 |
| Sortino | 1.52 | 1.97 |
| MaxDD | -55.4% | -38.0% |
| Ulcer index | 9.26 | 7.39 |
| Max underwater (days) | 557 | 569 |

**By regime state** (RC010.2/.3/.4 — annualized mean portfolio return while in each):
- Strong: +46.9%/yr over 7659 days (overlay holds 1.00x)
- Neutral: +1.0%/yr over 3166 days (overlay holds 0.60x)
- Weak: -117.9%/yr over 839 days (overlay holds 0.36x)

**Verdict:** reduces portfolio risk (drawdown/Ulcer) but at some CAGR cost - characterize the trade-off. The overlay de-risks in Neutral/Weak states; it helps iff those states carry low/
negative returns (defensive correctness) and hurts if they're false alarms in a bull.

**Next best experiment:** characterize CAGR-vs-drawdown trade-off; tune regime thresholds per market.
