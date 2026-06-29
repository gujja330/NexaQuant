# AEGIS Annual Research Review — 2026

Auto-generated from the Leaderboard + registries (`python tools/annual_review.py`). The year in one page.

| Metric | Value |
|---|---|
| Programs active | 5 |
| Experiments logged | 19 |
| Promoted | 2 |
| Investigating | 1 |
| Rejected / closed | 13 |
| Research success rate | 12% |
| Datasets ready | 3/8 |
| Features catalogued | 18 |
| Highest-confidence result | regime_overlay (85 (High)) |

## Promoted this year
- **regime_overlay** (INDIA, decomp) — the ENTIRE Sharpe~2.0 edge is defensive regime timing; validated and in production
- **regime_overlay_portfolio** (USA, RC010.1) — PROMOTED as DEFENSIVE risk overlay (NOT alpha): USA EW portfolio 46y MaxDD -55%->-38%, Ulcer 9.3->7.4, Sortino 1.52->1.9

## Most surprising finding
- **Static fundamentals had no cross-sectional edge** on 14y USA (Program 0): apparent 2y leads (ROE-inverse, revenue growth) were small-sample artifacts that vanished under power. The gate refused to promote them — a model rejection done right.
- **The one validated edge is defensive, not offensive:** the regime overlay is cross-market (India + USA) but as RISK MANAGEMENT (drawdown reduction), not alpha.

## Best / worst domains
- **Best dataset:** SEC EDGAR (PIT, free) — enabled the fundamentals + earnings + insider work.
- **Worst (for alpha):** static fundamental ratios — thoroughly rejected.
- **Best concept:** regime overlay (defensive, cross-market). **Highest single confidence:** low-volatility selection (production both markets).

## What automation bought
- Every experiment auto-publishes (leaderboard + report + dashboard); leakage/PIT discipline caught TWO false positives (LGBM 0.287→0.083; the RC002 PIT-alignment bug) before they could mislead.

## Going into next year
- Adopt the regime overlay as the standard USA risk layer (forward-track).
- Resume alternative-data domains (insider verdict pending, then analyst / ETF / 13F / macro).
- AI only after multiple independent validated domains exist (today: ~1, defensive-only).
