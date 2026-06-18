# NexaQuant India — Strategy Research (NSE equities + F&O)

Deep, source-backed research for the **parallel Indian-markets module**. Covers fundamentals
(screener-style), technicals/quant, F&O/options, and AI — plus the **Indian-specific pitfalls**
that wreck naive backtests. Same evidence-first rule as the gold/BTC system: nothing is
adopted until it passes our rigor gate on Indian data, net of *Indian* costs.

Compiled 2026-06-18. This does NOT change the gold/BTC system — it's the research base for
`india/`.

---

## A. FUNDAMENTALS (screener-style factors) — strongest documented edge in India
These are **positional/swing** signals (rebalance weekly–monthly), the natural fit for a
small account and a "pick the right stocks" model.

| Factor / screen | What it captures | Evidence |
|---|---|---|
| **Piotroski F-Score (8–9)** | accounting quality (9 ratios) | ~+13.4%/yr vs market over 20y backtests |
| **Magic Formula** (Greenblatt) | high ROCE + high earnings yield | classic value+quality; works on NSE mid/large |
| **Multi-factor** (Quality+Value+Momentum+Low-Vol) | combined factor score | 2025 NSE-500 study: top-50 score → corr-filter → 25 equal-weight |
| **Momentum** (6–12m return, skip 1m) | trend persistence | the single most robust factor on NSE/BSE |
| **Low-Volatility** | low beta/variance | downside-protected, higher risk-adj return |
| **DVM / Coffee-Can** | durability+valuation+momentum / buy-hold quality | Trendlyne screens, long-horizon outperformance |

**Screener metrics to compute** (the "screener.in" toolkit): PE, PB, ROE, **ROCE**, debt/equity,
EPS growth, sales growth, dividend yield, promoter holding %, interest coverage, free cash flow,
+ the composite **Piotroski F** and **Magic-Formula rank**.

## B. TECHNICALS / QUANT (entry timing on the selected stocks)
| Approach | Notes |
|---|---|
| **Cross-sectional momentum** (rank universe, long top-N) | breadth finally exists (50–200 stocks) — this is where it *works* (it failed on 4 cryptos) |
| **Trend continuation** (EMA20/50 + ADX regime) | our existing engine — reusable on stocks |
| **Breakout** (Donchian / 52-week high, volume-confirmed) | momentum ignition; our breakout edge ports over |
| **Golden crossover, RSI>50, MACD** | common Streak-style signals; weak alone, ok as filters |
| **Low-vol + trend combo** | screen low-beta, ride trends — smoother |

Backtest infra reference: [BacktestIndia](https://backtestindia.com/) (NSE factor backtests 2006–2025),
[AlgoTest](https://algotest.in/blog/best-backtesting-software-for-options-trading-in-india/) (F&O).

## C. F&O / OPTIONS (Nifty / BankNifty / FinNifty) — high risk, defer
| Strategy | Behaviour | Honest verdict |
|---|---|---|
| **Short straddle/strangle** | sell premium; prints in low-vol range | **DISASTER on gap days** (Nifty gaps 1.5% → blow-up). Regime-dependent. |
| **Iron Condor** | defined-risk short strangle + hedges | ~52% win, **PF 1.4** on BankNifty (5y) — modest, defined risk |
| **Directional (futures/long options)** | leveraged trend | leverage cuts both ways |

⚠️ **The brutal truth:** SEBI's own studies show **~90% of retail F&O traders lose money.**
F&O also needs **real margin** (futures ≈ ₹1–1.5 lakh; option lot sizes are large). For a
₹1,000 account, **F&O is off the table** until capital + a *proven* cash-equity edge exist.
"Trade F&O if confident" only after the bot has a validated edge AND the account can fund it.

## D. AI / ML — where it genuinely helps (and where it doesn't)
- **Works:** ML predicting **factor returns / factor momentum** → dynamic factor-weight rotation
  (used by quant MFs/PMS); regime detection. *AI as a selector/rotator/validator.*
- **Weak:** ML for raw **price prediction** (esp. intraday) — Indian data is high-vol, noisy;
  most credible research is on US markets. Same lesson as gold/BTC: **AI is a filter, not an oracle.**
- Fundamentals + technicals as FEATURES into a meta-label (P[win]) — the "screener + AI" idea —
  is legitimate *once there's enough data*, gated by CPCV.

## E. INDIAN-SPECIFIC PITFALLS (these kill naive backtests — must handle)
1. **Survivorship bias** — using only *current* index members overstates returns **20–25%**
   for small-caps. Must include delisted/changed constituents, or stick to stable large-caps.
2. **Costs are brutal on small trades** — brokerage (₹20/order), **STT**, GST, SEBI, stamp duty,
   + slippage (~0.05%) + impact. A ₹1,000 trade can lose 1–2% round-trip to costs alone.
3. **F&O retail loss rate ~90%** (SEBI). Treat F&O as the *last*, most-dangerous step.
4. **Liquidity** — stick to liquid large-caps; small-caps have impact cost + manipulation risk.
5. **Gap risk** — Indian stocks gap on overnight news; intraday stops can be jumped.
6. **Intraday is the hardest game** — heavy competition, cost drag (our M5/M15 crypto tests LOST).
   Swing/positional has a far better documented edge for retail.

## F. PRIORITIZED, CAPITAL-AWARE TEST PLAN (for a small account)
Validate in this order — keep only what passes the gate, net of Indian costs:

1. **Cross-sectional momentum** on the liquid NSE universe (rank, long top-N, weekly rebalance)
   — breadth makes this viable; cheapest, most documented. *(build first)*
2. **Multi-factor screen** (momentum + quality[F-score/ROCE] + low-vol) — long top basket.
3. **Trend/breakout entry** on the selected stocks (our existing engine) — timing layer.
4. **Fundamentals as features → meta-label** (the "screener + AI" payoff) — gated by CPCV.
5. **Intraday** — only if 1–3 show edge; honest low prior (costs + competition).
6. **F&O** — LAST. Only with proven edge + adequate capital; start with defined-risk (Iron Condor),
   never naked short straddle on a small account.

**Capital reality:** ₹1,000 ≈ a few shares of one stock; costs dominate. This direction shines
once the account is funded to where positional baskets + (later) F&O are viable. The *infra* is
free and easy (Angel One / Upstox API, native Python, runs during market hours on your PC).

---

### Sources
- [Effect of Piotroski F-Score on Indian equity returns (ResearchGate)](https://www.researchgate.net/publication/312397957_Effect_of_F_Score_on_Stock_Performance_Evidence_from_Indian_Equity_Market)
- [Multi-factor stock selection on NSE-500 (IJCRT 2025)](https://www.ijcrt.org/papers/IJCRT2505426.pdf)
- [Survivorship bias in India's Nifty Smallcap 250 (arXiv 2026)](https://arxiv.org/pdf/2603.19380)
- [BacktestIndia — NSE factor backtesting 2006–2025](https://backtestindia.com/)
- [AlgoTest — F&O options backtesting India](https://algotest.in/blog/best-backtesting-software-for-options-trading-in-india/)
- [Zerodha Varsity — Iron Condor](https://zerodha.com/varsity/chapter/iron-condor/)
- [Can Machine Learning Predict Factor Returns? (Alpha Architect)](https://alphaarchitect.com/predict-factor-returns/)
- [Evaluating ML models for stock forecasting (SAGE 2025)](https://journals.sagepub.com/doi/10.1177/09711023251349445)
- [Fundamental screeners 2026 guide for India (Winvesta)](https://www.winvesta.in/blog/investors/fundamental-analysis-tools-and-screeners-2026-guide)
