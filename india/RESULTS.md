# NexaQuant India — Test Results (saved for review)

All numbers below are reproducible — re-run the script in brackets. Daily data, net of
realistic Indian costs (~21 bps round-trip). Universe: 23 liquid NSE large-caps + Nifty/BankNifty.
Honest caveats apply throughout: survivorship-light (current large-caps only ≈ overstates ~20%),
2025–26 soft, ₹-small-account costs dominate.

---

## Combination sweep — find the most DEPENDABLE config  [`python india/combo_test.py`]
Ranked by robustness (Sharpe + %profitable-years − drawdown penalty):

| Config | Total% | CAGR | maxDD% | Sharpe | Pos yrs | Worst yr |
|--------|------:|-----:|------:|------:|:------:|------:|
| **momentum + low-vol** (regime off, vt off) ⭐ | **+143** | **13.5%** | **18.9** | **1.04** | **6/7** | −15.0 |
| momentum + low-vol (vol-target 15%) | +128 | 12.5% | 22.4 | 0.94 | 6/7 | −17.2 |
| low-vol + trend | +90 | 9.6% | 23.1 | 0.84 | 5/7 | −15.7 |
| momentum only | +94 | 9.9% | 23.5 | 0.70 | 6/7 | −12.8 |
| mom + low-vol + trend | +82 | 9.0% | 19.4 | 0.70 | 5/7 | −11.5 |
| (all regime=ON variants) | 5–63 | low | high | <0.6 | 3–4/7 | — |

**Winner: Momentum + Low-Volatility, top-5, weekly rebalance, equal weight.**
- Adding low-vol to momentum lifted Sharpe **0.70 → 1.04** and turned 2025 from +0.5% → **+12%**.
- **Regime filter + vol-targeting HURT** on this 2020–26 window (Indian secular bull — staying invested beat timing it). Kept OFF.

### Winner's per-year
| Year | Return |
|------|------:|
| 2020 | +8.4% |
| 2021 | +49.4% |
| 2022 | +7.3% |
| 2023 | +24.4% |
| 2024 | +17.9% |
| 2025 | +12.1% |
| 2026 (YTD) | −15.0% |

---

## Per-instrument trend/breakout (the gold/BTC bot run on each stock)  [`python india/validate_india.py`]
Name-specific, like gold-vs-BTC:
- **Strong:** ADANIENT trend (Sharpe 5.2), ASIANPAINT (4.7), ITC (4.2), BAJFINANCE / INFY breakout (~3).
- **Loses:** HDFC / ICICI / AXIS banks, POWERGRID, KOTAKBANK (range-bound names).
- **Indices:** Nifty trend mild +ve (0.9); Bank Nifty ~flat.

---

## Fundamentals + earnings (free, yfinance)  [`python india/fundamentals_nse.py`]
- Quality z-score (ROE↑, debt↓, margin↑, PE/PB↓). Current top-quality: **TCS, INFY, AXISBANK, ICICIBANK, HDFCBANK**.
- Earnings calendar (next results date per stock) → enables PEAD-drift + risk-aware sizing.
- **LIVE screen only** (current snapshot, not point-in-time) — used as a tilt on top of mom+low-vol, NOT a historical backtest.

---

## How to regenerate / check any of this
```bash
python india/data_nse.py            # refresh prices
python india/fundamentals_nse.py    # refresh fundamentals + earnings dates
python india/combo_test.py          # the combination sweep (table above)
python india/validate_india.py      # cross-sectional + per-instrument validation
```
Data lives in `data/raw/india/`. Research in `india/STRATEGY_RESEARCH_INDIA.md` and
`docs/GLOBAL_EQUITY_RESEARCH.md`.
