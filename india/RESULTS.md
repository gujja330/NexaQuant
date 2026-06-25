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

---

## Trade blotter (every trade, all stocks)  [`python india/trade_blotter.py`]
- **2,073 trades across 25 stocks** → full CSV at `output/india_trades.csv` (entry/exit dates,
  prices, % move, ₹ P&L on ₹10k/trade, R-multiple, exit reason, win/loss). Filter it freely.
- Example: RELIANCE breakout long 2021-08-17→2021-10-22, ₹904→₹1178, **+19.96% / +3.87R**.

## AI meta-label (P[win] filter)  [`python india/ai_meta.py`]
- 1,824 pooled trades, TIME split (train 1,276 / test 548). **Test AUC = 0.551** (borderline
  skill — better than gold/BTC's ~0.50 thanks to more data).
- Filtering test trades by **P(win) ≥ 0.50** turned the losing 2024–26 test set (take-all −74R)
  into **+3.1R across 31 high-confidence trades (48% win)** — it cuts the junk.
- Top predictive feature: **ADX (trend strength)**. 
- **Verdict:** use as a CONSERVATIVE filter only; AUC 0.55 is weak + small surviving sample.
  Real lift needs fundamentals/earnings features + more stocks/history. AI = modest filter, NOT oracle.

---

## CLEAN re-test + volatility control (champion update)
Fixed a bug (S&P/VIX series had leaked into the stock universe). Clean results:
- **Champion = momentum + low-vol + VIX de-risk** (top-5, weekly): **+145%, Sharpe 1.23,
  maxDD 13.8%, 6/7 profitable years, worst year −9.8%.**
- VIX de-risk (cut exposure when India VIX is in its high regime) improved EVERYTHING vs the
  +143%/Sharpe 1.04 base: higher return, Sharpe 1.04→1.23, drawdown 18.9%→13.8%, and shrank
  the 2026 crash −15% → −9.8%. The "control volatility" instinct was right.
- Sector cap HURT on the 23-stock universe (121%, too restrictive); correlation cap neutral.
- Long-term variant (12m momentum, monthly) was weaker (+68%) → the WEEKLY 6m picker wins.
- Current buy list (2026-06-18): TATASTEEL, NTPC, POWERGRID, ONGC, SUNPHARMA  [`python india/long_term_picker.py`]

## Intraday — REJECTED  [`python india/intraday_engine.py`]
ORB+VWAP on hourly, hard stop + EOD square-off: 11,695 trades, 38% win, **−0.091%/trade**,
losing EVERY year. Same lesson as M5/M15 crypto — intraday is noise+cost. Dropped.

## Influences embedded / to embed → see india/INFLUENCES.md
Global (S&P/China/DXY/crude/USD-INR/VIX), sector rotation (metals/IT/auto/EV), FII flows,
earnings/PEAD. We react to news via its footprint (VIX + price), never predict headlines.

---

## Loss-control test — ALL mechanisms REJECTED  [`python india/loss_control.py`]
Tested trend-confirm entry, momentum-break exit, trailing stops (8/12%), breadth de-risk, and
all combined on the champion. **Every one reduced total return and/or Sharpe:**
- champion (VIX only): 145% / Sharpe 1.23 / maxDD 13.8% / 2026 −9.8%  ← BEST
- momentum-break exit: "fixes" 2026 (−0.3%) but CRUSHES total to 49% (Sharpe 0.83) — whipsaw
- trailing stop 12%: 137% (slightly worse); 8%: 134%; trend-confirm: 103%; breadth: 111%; ALL: 24%
**Conclusion:** stops whipsaw momentum — the losers are the necessary cost of the winners. The
only loss-control that helps is the VIX de-risk already in the champion. Do NOT add stops.

---

## Winners vs Losers analysis — losers are UNPREDICTABLE at entry  [`python india/winners_vs_losers.py`]
Tested the right idea (avoid losers at SELECTION, not via stops). Result on 262 holdings:
- Winners vs losers look ~IDENTICAL at entry on technicals (mom/vol/ADX/RSI/dist-200 differ by
  noise; losers even had slightly HIGHER momentum/ADX — most-extended names reverse).
- AI winner/loser classifier: TEST AUC = 0.469 (WORSE than coin flip). Filtering HURT (43% vs 46% win).
**Conclusion:** you cannot separate future winners from losers at entry from PRICE data — the
losses are statistically unpredictable per-holding. This is WHY the edge is a systematic basket
(hold top-5) and why stops/filters fail. OPEN frontier: point-in-time FUNDAMENTALS (we only have
a current snapshot) might separate them — re-run this test if that data is obtained.

---

## HARDENING (broad universe) — the honest correction  [`python india/picker_pro.py`]
Expanded universe 23 -> ~49 liquid NSE stocks (reduce concentration/survivorship bias). Result:
- The old "champion" (mom+low-vol, Sharpe 1.23) was OVERFIT to the narrow set -> collapsed to
  **Sharpe 0.42 / +46%** on the broad universe.
- **PURE MOMENTUM is the robust champion:** +164% / CAGR ~15% / **Sharpe 0.79** / 6-of-7 years /
  worst -7.4% / maxDD ~25% -> **Rs1L -> Rs2.64L** (net profit Rs1,64,238).
- VIX de-risk now OPTIONAL (lowers DD 24.7%->21.8%, trims return slightly).
**Lesson:** always validate on a BROAD universe — the narrow-set Sharpe 1.23 was an artifact.
Honest scorecard downgraded ~7.5 -> ~6/10: a decent, trustworthy ~15% CAGR momentum engine,
not spectacular. Deck (Aegis_Architecture.pdf) + picks_report updated to these honest numbers.
