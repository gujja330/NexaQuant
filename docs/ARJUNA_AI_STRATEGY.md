# ARJUNA — Finalized AI Strategy (v1 spec)

Status: **FINALIZED for build** (2026-06-19). This is the single source of truth that
synthesizes the three research docs with the clean-data reality check. Build to THIS;
do not deviate without updating this file.

Synthesizes:
- [STRATEGY_RESEARCH_INDIA.md](STRATEGY_RESEARCH_INDIA.md) — India's edge = multi-factor screening (positional/swing).
- [STOCK_SELECTION_CHECKLIST.md](STOCK_SELECTION_CHECKLIST.md) — combine fundamentals + technicals + news + macro; AI = ranker, not oracle.
- [AI_ML_REFINEMENT_PLAN.md](AI_ML_REFINEMENT_PLAN.md) — rich features + cross-sectional return-rank framing + GBT + purged-CV/Deflated-Sharpe gate.

---

## 0. The reality this must beat (the honest bar)
On clean Angel data (2021-06 → 2026-06, the only forward-tradeable window):

| | ₹1L → | Total | CAGR | Sharpe | maxDD |
|---|---|---|---|---|---|
| **Nifty buy-and-hold** | **₹1,72,401** | **+72%** | **10.5%** | **0.79** | **17.2%** |
| Old Arjuna (pure momentum top-5) | ₹1,22,636 | +23% | 3.8% | 0.28 | 33.9% |

**The old strategy LOSES to a passive index fund on every metric.** v1 is only worth trading
real money if it beats Nifty buy-and-hold on **return AND Sharpe AND drawdown**, net of cost.
If it can't clear that bar out-of-sample, the honest answer is "buy a Nifty index fund."

## 1. Locked decisions (user sign-off 2026-06-19)
- **Universe:** Nifty 100 (broad enough to fix the concentration that doubled drawdown; liquid, low manipulation risk).
- **Horizon:** build BOTH **monthly** and **weekly** rebalance; compare head-to-head; keep whichever beats the index net of cost.
- **Fundamentals:** include ALL of them (full screener toolkit, below). Honest caveat handled in §4.

## 2. Features (rich, per stock, per rebalance date) — the whole point
**Technical (clean from Angel daily data — zero look-ahead):**
- Multi-horizon momentum: 1m / 3m / 6m / 12m return (skip last ~1–2 wks).
- Low-volatility / beta (60d, 120d annualized vol).
- Trend: distance from 20/50/200-day MA, ADX, RSI(14).
- Liquidity/turnover: avg traded value, volume trend.
- Drawdown / downside vol (momentum-crash guard).

**Fundamental (ALL — the full screener toolkit):**
- Quality: **Piotroski F-Score (0–9)**, ROCE, ROE, gross/operating/net margins, interest coverage.
- Value: PE, PB, EV/EBITDA, **earnings yield (Magic Formula)**, dividend yield, valuation vs own 5y history.
- Growth: EPS growth, sales growth (YoY + multi-yr CAGR).
- Balance sheet: debt/equity, FCF, promoter holding %, dilution check.
- Composite: **Magic-Formula rank** (ROCE + earnings yield), DVM-style score.

**Macro / sector (regime context):**
- India VIX level + regime (high-fear de-risk).
- USD/INR, crude, US S&P (global risk-on/off; broad-USD is a key EM driver).
- Sector momentum + the stock's sector membership.
- (v2) FinBERT news sentiment on headlines/earnings calls.

## 3. Model & portfolio
- **Target:** cross-sectional **rank of forward return** over the rebalance horizon (Gu-Kelly-Xiu framing), NOT binary win/loss (that's what starved the AUC-0.47 test).
- **Model:** gradient-boosted trees (HistGBM) first; add a small NN + ensemble only if GBT clears the gate.
- **Portfolio:** long the top basket — **top 15–20 names** (NOT top-5; concentration was the killer), equal-weight, rebalance monthly AND weekly (compare).
- **Overlay:** VIX de-risk (cut exposure in high-fear regimes) — the one risk control that helped.
- **AI role:** a RANKING overlay on the factor core — tilt toward high score, down-weight low. Not an oracle, not a replacement for risk management.

## 4. The fundamentals honesty protocol (point-in-time problem)
Free fundamentals (yfinance/screener) give only TODAY's snapshot. Using them on past dates
leaks look-ahead bias and inflates results. Per user ("try all fundamentals"), v1 DOES use the
full fundamental set, but under strict honesty rules:
1. **Label every backtest** that uses snapshot fundamentals as **"OPTIMISTIC (look-ahead) — not tradeable as-is."**
2. **Run the technicals+macro-only model in parallel** (zero look-ahead) as the *honest floor*.
3. The gap between the two = the look-ahead inflation. Report it openly.
4. v2 = source point-in-time fundamentals (scrape/paid) to close the gap and re-validate.
   Only the point-in-time (or technical-only) result is allowed to justify real money.

## 5. Validation gate (NON-NEGOTIABLE — this is what nearly fooled us before)
A variant is KEPT only if, out-of-sample:
- **Purged + embargoed walk-forward CV** (no leakage across the rebalance boundary).
- **Deflated Sharpe Ratio** > 0 after correcting for the number of trials.
- **Beats Nifty buy-and-hold** over the SAME window on return AND Sharpe AND drawdown.
- Survives **realistic Indian costs** (~21bps round-trip) + slippage.
- Stable across the monthly vs weekly comparison (not a single lucky config).

Remember: a narrow 23-stock universe once faked Sharpe 1.23. Breadth + this gate is the defense.

## 6. Build order (when we start — NOT yet; finalize first)
1. Expand universe to Nifty 100; pull clean history via Angel (incremental append already built).
2. Feature pipeline: technical+macro (clean) → add full fundamentals (flagged optimistic).
3. Label = forward-return rank; build HistGBM ranker.
4. Backtest BOTH horizons, BOTH feature sets (honest floor vs optimistic), vs Nifty.
5. Apply the §5 gate. Keep only what passes.
6. If it passes → paper-trade on Angel during market hours → then fund.
7. If it fails the Nifty bar → say so plainly; recommend indexing or a genuinely different signal.

## 7. Explicitly OUT of v1
- F&O / options (SEBI: ~90% retail lose; needs margin + a proven cash edge first).
- Intraday (hardest game; our M5/M15 tests lost; low prior).
- Any leverage. Any naked-short-premium.

---
**Bottom line:** v1 = a broad-universe, multi-factor, AI-ranked basket (monthly & weekly), with a
hard "beat the Nifty net of cost, out-of-sample" gate and an explicit honesty protocol for the
fundamentals look-ahead problem. Modest, real, and validated — or we don't trade it.
