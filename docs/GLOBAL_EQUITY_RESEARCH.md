# NexaQuant — Deep Equity Research: USA + India

A comprehensive, honest research base for equities across **US and Indian** markets — factors,
technicals, fundamentals (screener-style), F&O/options, AI, costs, and the **regulatory reality
for an Indian resident** (which is the decisive practical filter). Same discipline as the
gold/BTC system: nothing is adopted until it passes our rigor gate on that market's data, net
of that market's real costs. Compiled 2026-06-18. Parallel to (does not change) the FX/crypto
system. India specifics live in `india/STRATEGY_RESEARCH_INDIA.md`.

---

## 0. THE REGULATORY REALITY (read this first — it decides what's even possible)
You are an **Indian resident**. Under RBI's **LRS** (Liberalised Remittance Scheme):

| | US markets | Indian markets |
|---|---|---|
| Buy/hold stocks & ETFs | ✅ (LRS, up to $250k/yr) | ✅ |
| **Intraday / day-trading** | ❌ **banned** (same-day buy/sell not allowed) | ✅ allowed |
| **Options / Futures (F&O)** | ❌ **banned** (no foreign derivatives/margin) | ✅ allowed |
| Automation API | IBKR API (positional only) | **free**: Angel One / Upstox / Fyers / Dhan |

**Implication:** **US = positional stock/ETF investing only.** All the intraday + F&O ambition
must happen in **India**. (Sources: [Zerodha — Can Indians trade US F&O](https://zerodha.com/z-connect/varsity/can-indians-trade-in-the-us-fo), [INDmoney LRS](https://www.indmoney.com/learn/us-stocks/what-is-lrs-liberalised-remittance-scheme), [Vested day-trading](https://vestedfinance.com/blog/us-stocks/day-trading-in-us-markets-for-indian-investors/))

---

## 1. THE FACTOR FOUNDATION (works in BOTH markets)
Decades of academic + practitioner evidence (Fama-French, AQR) — the most robust, *global* edge:

| Factor | What it is | Evidence |
|---|---|---|
| **Momentum** | 6–12m past return (skip last 1m) | strongest standalone; "Value & Momentum Everywhere" (AQR) — holds in India too |
| **Value** | cheap P/B, P/E, EV/EBIT | Fama-French (1992); weaker recently |
| **Quality** | high ROE/ROCE, profitability, F-Score | Fama-French 5-factor (2015) added profitability + investment |
| **Low Volatility** | low beta/variance | higher risk-adjusted return (low-vol anomaly) |
| **Size** | small-cap premium | real but noisy, liquidity-constrained |

⚠️ **Honest caveat — factor decay:** post-publication, factor returns have **shrunk**
(crowding) — "The Incredible Shrinking Factor Return" (Research Affiliates). Still positive,
but smaller and lumpier than backtests imply. *Momentum + Quality* combined is the most durable.
([Value and Momentum Everywhere – AQR/NYU](https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf),
[Shrinking factor returns](https://www.researchaffiliates.com/publications/articles/604-the-incredible-shrinking-factor-return-unabridged))

---

## 2. USA EQUITIES — positional only (for you)
- **Strategy that's legal + works:** cross-sectional **momentum + quality** basket of US
  large-caps / ETFs, **monthly rebalance**, delivery (no intraday, no options).
- **Automation:** **Interactive Brokers API** (works from India for US stocks, positional).
  INDmoney/Vested are app-based (little/no retail trading API).
- **Costs/tax:** LRS TCS (>₹10L remittance), forex conversion spread, US dividend withholding
  ~25% (file **W-8BEN**), Indian capital-gains tax on sale, repatriation rules.
- **Role:** diversification + USD exposure (hedges INR), captures US mega-cap/tech trend.
  Best *once funded* (LRS + costs make tiny amounts inefficient).

## 3. INDIA EQUITIES — full access (where the action is)
- **Cash equity:** intraday allowed; cross-sectional momentum + multi-factor screens.
- **Fundamentals (screener.in toolkit):** PE, PB, ROE, **ROCE**, D/E, EPS & sales growth,
  promoter holding, FCF + composite **Piotroski F-Score (8–9 ≈ +13%/yr)** and **Magic Formula**.
- **Free APIs:** Angel One SmartAPI / Upstox / Fyers / Dhan → native Python, runs on your PC
  during market hours (you log in daily anyway — no 24/7 hosting needed).
- Full detail + sources in **`india/STRATEGY_RESEARCH_INDIA.md`**.

## 4. F&O / OPTIONS — India only (US F&O is banned for you)
- **India:** Iron Condor (defined risk, ~52% win / PF 1.4 on BankNifty), short straddle
  (regime-dependent, gap-day blow-up). **SEBI: ~90% of retail F&O traders LOSE.** Needs margin
  (₹1–1.5 lakh). → **last priority**, defined-risk only, after a proven cash edge + capital.
- **US options:** **not accessible** to Indian residents — skip entirely.

## 5. AI / ML — both markets
- **Helps:** predicting **factor returns / factor momentum**, **regime detection**, dynamic
  factor-weight rotation (used by quant funds). Fundamentals+technicals as features → meta-label
  P(win), gated by CPCV.
- **Weak:** raw price/intraday prediction. *AI = selector/rotator/validator, not an oracle*
  (the same conclusion as our gold/BTC work — AUC≈0.5 for naive price models).
  ([Can ML predict factor returns? – Alpha Architect](https://alphaarchitect.com/predict-factor-returns/))

## 6. CROSS-MARKET DIVERSIFICATION
US and Indian equities are **imperfectly correlated** → a US-positional + India-active portfolio
is smoother than either alone (the diversification principle that lifted our gold/BTC engine).
US gives USD/tech exposure; India gives EM growth + (legally) intraday & F&O.

## 7. PITFALLS THAT WRECK NAIVE BACKTESTS (both markets)
1. **Survivorship bias** — use full historical universe incl. delisted (India small-caps
   overstate **20–25%**); or stick to stable large-caps.
2. **Costs** — India: brokerage ₹20, **STT**, GST, SEBI, stamp, slippage; US: forex + TCS +
   withholding. Small trades are eaten alive — model costs HONESTLY.
3. **F&O 90% retail loss rate** (SEBI). Treat as the most dangerous step.
4. **Factor crowding/decay** — discount backtest factor returns.
5. **Intraday is the hardest game** (competition + cost drag) — swing/positional has the better
   documented retail edge.
6. **Liquidity / gap risk** — liquid names only; overnight gaps jump stops.

---

## 8. THE HONEST, CAPITAL- & REGULATION-AWARE PLAN
Validate each on real data, net of real costs, before any capital (same gate as gold/BTC):

1. **India cash equity — cross-sectional momentum + multi-factor** (free API, intraday legal,
   breadth makes selection work). **← start here; data already pulled in `india/`.**
2. **India trend/breakout entry timing** on the selected stocks (reuse our engine).
3. **US positional factor basket** (momentum+quality, monthly, IBKR API) — diversification once funded.
4. **AI factor-rotation / meta-label** layer — once enough data, gated by CPCV.
5. **India F&O** — last, defined-risk only, with adequate capital.
6. **US F&O / US intraday** — ❌ not possible for an Indian resident; do not pursue.

**Capital reality:** at ₹1,000 / $12, costs dominate everywhere — this is a *grow-into-it* plan.
The infra, though, is finally free and easy: **India via free broker APIs on your own PC during
market hours.** That's the realistic first live battleground.

---

### Sources
- [Fama–French model (Wikipedia)](https://en.wikipedia.org/wiki/Fama%E2%80%93French_three-factor_model)
- [Value and Momentum Everywhere — AQR / Asness, Moskowitz, Pedersen](https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf)
- [The Incredible Shrinking Factor Return — Research Affiliates](https://www.researchaffiliates.com/publications/articles/604-the-incredible-shrinking-factor-return-unabridged)
- [Quality, Factor Momentum & the Cross-Section — Alpha Architect](https://alphaarchitect.com/cross-section-of-returns/)
- [Can Machine Learning Predict Factor Returns? — Alpha Architect](https://alphaarchitect.com/predict-factor-returns/)
- [Can Indians Trade in US F&O? — Zerodha](https://zerodha.com/z-connect/varsity/can-indians-trade-in-the-us-fo)
- [Day Trading in US Markets for Indian Investors — Vested](https://vestedfinance.com/blog/us-stocks/day-trading-in-us-markets-for-indian-investors/)
- [LRS explained — INDmoney](https://www.indmoney.com/learn/us-stocks/what-is-lrs-liberalised-remittance-scheme)
- India equities detail + sources → `india/STRATEGY_RESEARCH_INDIA.md`
