# ARJUNA v2 — Architecture

> **ARJUNA is NOT a stock-picking system.**
> **ARJUNA is a risk-allocation and regime-management system.**

That one line changes everything below.

---

## Fundamental Principle
```
Cross-sectional stock returns are largely UNPREDICTABLE.
Risk, volatility, drawdowns and market regimes contain PERSISTENT STRUCTURE.

ARJUNA therefore forecasts:  Risk · Regime · Exposure · Portfolio weights
                       NOT:  next-period returns.

Objective: maximise long-term RISK-ADJUSTED COMPOUNDING (survival first), not raw CAGR.
```
**Evidence:** 13 model families (XGBoost…Transformer…RL…GNN) on return prediction → all AUC ≈ 0.50.
Same XGBoost on **risk**: volatility AUC **0.76**, drawdown **0.62**. The target was the problem.

---

## The ARJUNA Doctrine
```
Markets are mostly efficient.            Regime matters more than stock selection.
Returns are noisy.                       Portfolio construction matters more than models.
Risk contains structure.                 Data quality matters more than model complexity.
Survival dominates prediction.           Robustness matters more than backtests.
Diversification beats concentration.     Long-term compounding beats short-term accuracy.
```

## Anti-Fragility Objective (in priority order)
1. **Survival** (avoid catastrophic loss)  2. **Drawdown reduction**  3. **Risk-adjusted compounding**
4. **Upside participation**  5. Raw CAGR is *secondary*.

---

## Four-Layer Architecture

### Layer 0/1 — Market State  (breadth sits at the TOP — it often turns before price)
- **Breadth engine** — % above 20/50/200-DMA, advance/decline, new-high/new-low *(built: `regime_hmm.breadth_series`)*
- **Regime** — VIX + Nifty-200-DMA rule *(built, validated; the simple rule BEAT a 3-state HMM — kept the simple one)*
- **FII/DII flows** *(planned — NSE daily; India-specific)*
- Output → **risk-regime score → exposure multiplier**

### Layer 2 — Risk Forecasting  (our strongest validated signal)
- Historical vol, EWMA, **GARCH/EGARCH** *(planned)*, **XGBoost vol model (AUC 0.76, validated)**, drawdown-probability
- Output → expected volatility · expected drawdown · **confidence/range** (uncertainty, see below)

### Layer 3 — Portfolio Construction  (most of the alpha)  *(built: `arjuna_v2.py`)*
- **Inverse-volatility** (risk-parity lite) · **Minimum-variance** (Ledoit-Wolf shrinkage)
- **HRP** *(planned)* · risk budgeting · **per-name cap · sector cap · correlation cap**
- Output → target weights

### Layer 4 — Execution  *(built: `run_arjuna.py`, `daily_run.py`)*
- Monthly rebalance · **news blow-up filter** (FinBERT, drop strongly-negative names) · costs (~21bps) · cash mgmt
- Output → final portfolio

---

## Validated state (what's real today)
| | result | gate |
|---|---|---|
| **INV_VOL + simple regime** | Sharpe **1.64**, maxDD **14.3%** (vs EW 1.11/20.7%, Nifty 0.80/17.2%) | **Deflated Sharpe 0.967 → ROBUST** |
| HMM regime | Sharpe 1.06 | DSR 0.705 → rejected (simpler won) |

Validation: **Deflated Sharpe Ratio** (discounts for ~20 trials) + purged walk-forward (`validation.py`).
Survivorship inflates CAGR; the **Sharpe/DD improvement over EW is the honest, transferable signal.**

---

## Correlation Engine  (highest-ROI addition after regime)
A "20 risk-weighted stocks" basket can secretly be ONE bet (HDFC/ICICI/Axis/Kotak/SBI all move together).
Need: correlation caps → **HRP** → dynamic covariance (Ledoit-Wolf) → cluster-aware weights. *(min-var shrinkage built; HRP/clustering planned)*

## Uncertainty  (don't report a point estimate)
Not "vol = 23%" but "vol 23% (range 18–29%, confidence 82%)". Future: **quantile regression · conformal prediction · Bayesian**.

## Dynamic Exposure / Vol-Targeting  (Bridgewater/AQR/Man style)
Target ~constant portfolio volatility (e.g. 12%/yr). Market vol up → exposure down. Kelly-capped.

## Crisis-Alpha Overlay
For COVID/war/inflation/election shocks: crash overlay → cash / low-beta tilt / (gold ETF). Survival first.

## Capacity & Robustness  (retail systems overestimate alpha — track honestly)
Turnover · capacity · slippage · concentration · sector & correlation exposure · tax drag ·
stability across periods AND across universes (Nifty-100 vs 200). Reported, not hidden.

---

## Things ARJUNA INTENTIONALLY AVOIDS  (protects against complexity creep)
❌ LSTM/Transformer return forecasting  ❌ RL stock-picking  ❌ LLM "stock tips"
❌ Indicator/GA curve-fitting  ❌ social-media hype  ❌ predicting multibaggers
❌ single-stock concentration. *(All tested or reasoned out — they don't survive the gate.)*

Why not multibaggers: `multibagger_analysis.py` — the doublers (BSE 58x) were **not identifiable in
advance** (2/10 ≈ random). Broad risk-weighted holding is how you *own* the winners you can't pick.

---

## v2.1 build priorities
1. HMM/learned regime *(tested — simple won; revisit with better features)* 2. **Breadth engine** ⭐
3. **FII/DII flows** ⭐ 4. **HRP portfolio** ⭐ 5. **GARCH vol** ⭐ 6. **Dynamic vol-targeting** ⭐
7. Conformal uncertainty 8. Correlation clusters 9. Triple-barrier + meta-label
10. **Deflated Sharpe + PBO + SPA tests** ⭐ *(DSR built)*

## Free Data Stack (per layer — most of v2.1 is buildable for FREE)
| Need | Free source | Status |
|---|---|---|
| Price / OHLCV | **Angel SmartAPI** (built) + yfinance | ✅ have (220 stocks) |
| India VIX, sector indices | NSE / yfinance | ✅ have VIX; sectors mapped |
| **Breadth** (%>20/50/200-DMA, A/D, hi-lo) | **build from our Nifty-200** | ⭐ free, highest-ROI, partly built |
| **FII/DII flows** | **NSE daily** | ⭐ free, planned |
| Macro (rates, CPI, USD, yields) | **FRED (`fredapi`)** + yfinance (DX-Y, ^TNX) | ⭐ free, planned |
| Commodities (gold/crude) | yfinance (GC=F, CL=F) | free |
| Factor returns (value/mom/quality) | **Kenneth French / Fama-French library** | ⭐ free, planned |
| News + sentiment | **Google News RSS + FinBERT** (built) | ✅ live |
| Alt-data | **Google Trends (`pytrends`)**, Wikipedia views | free, planned |
| Options (OI, PCR) | NSE option chain | free |
| Historical fundamentals | **SimFin** (strong US, limited India) / yfinance snapshot | partial |
| Validation | purged-CV + **Deflated Sharpe** (built) | ✅ |

## The real ceiling (corrected — narrower than I first said)
Much of what I earlier called "blocked" is actually FREE (breadth, FII/DII, FRED macro, factors,
Trends, option chain) — and should be in v2.1. The genuinely hard gaps remain: **point-in-time
INDIAN fundamentals** (SimFin is US-centric; #1 gap) and **scaled earnings-call transcripts**.
**Lesson stands: spend effort on free regime/risk/breadth data + rigor, not on model complexity.**

## Crypto note (parked per user)
Risk principle (vol-targeting, regime de-risk) transfers to gold/BTC; cross-sectional selection does
not (~10-20 liquid assets). Out of scope for now — stocks first.
