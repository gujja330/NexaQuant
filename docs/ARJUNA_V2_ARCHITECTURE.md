# AEGIS v2 — Adaptive Risk & Regime Allocation System

> **NOT an AI stock-selection system.** A risk-allocation & regime-management system —
> **AQR / Bridgewater / BlackRock-style risk investing, for retail.**

Identity settled by evidence: 13 model families found no return-selection edge; the gains all came
from **regime management + risk-based construction**. AEGIS stopped trying to be a mini-RenTech.

## Fundamental Principle
```
Cross-sectional returns are UNPREDICTABLE.  Risk, volatility, drawdowns, regimes are PREDICTABLE.
AEGIS forecasts Risk · Regime · Exposure · Weights — never returns.
Objective: long-term RISK-ADJUSTED compounding. Survival first; raw CAGR last.
```
Proof: return prediction AUC ≈ 0.50 (13 models); **volatility AUC 0.76, drawdown 0.62**.

## VALIDATED CHAMPION (Nifty-200, net of cost, ~5.5y, Deflated-Sharpe gated)
| Strategy | CAGR | Sharpe | maxDD | DSR |
|---|---|---|---|---|
| **HRP + regime + Global Risk** ⭐ | 17.7% | **2.04** | **12.8%** | **0.996** |
| HRP + simple regime | 16.9% | 1.71 | 14.1% | 0.975 |
| EW baseline | 17.0% | 1.11 | 20.7% | 0.74 (overfit) |
| Nifty-50 | 10.8% | 0.80 | 17.2% | — |
Default config (`india/config.py`): `method=hrp, regime=global`.

---

## Layered Architecture

**Layer 0 — Data Integrity** (most important): split/dividend-adjusted prices, survivorship
awareness, point-in-time fundamentals *(gap)*, **purged walk-forward + Deflated Sharpe** (built);
PBO/SPA *(planned)*.

**Layer 1 — Market State** (strongest alpha source): **simple regime** (VIX + Nifty-200-DMA, built)
+ **Global Risk Engine** (S&P trend, US-VIX, USD/DXY — built, lifted Sharpe 1.71→2.04) + breadth
(built) + FII/DII *(planned, free NSE)*. **Simple > fancy: HMM was tested and LOST (1.06 vs 1.64) → rejected.**

**Layer 2 — Risk Forecasting** (validated signal): historical/EWMA vol; XGBoost vol model (AUC 0.76);
GARCH/EGARCH, quantile/Bayesian/conformal uncertainty *(planned)*.

**Layer 3 — Correlation Engine** (the diversification truth): 20 stocks ≠ 20 bets (HDFC/ICICI/SBI
= one trade). Ledoit-Wolf covariance + **HRP cluster weights** (built; beat inv-vol) + sector caps.

**Layer 4 — Portfolio Construction**: inverse-vol · min-variance · **HRP** (champion) · per-name cap;
vol-targeting available (tested — *levers up, doesn't raise Sharpe* → off by default).

**Layer 5 — News Defense** (blow-up avoidance, NOT alpha): FinBERT + Google News RSS (built, live) —
drops fraud/default/downgrade names before ordering.

---

## AEGIS-Core vs AEGIS-Lab  (physically implemented)
- **Core = `india/`** — only what SURVIVED: simple+global regime, risk model, correlation/HRP,
  min-var/inv-vol, news filter, validation, breadth.
- **Lab = `india/research/`** — sandbox: XGBoost/LightGBM, LSTM/Transformer, RL, GNN, HMM, target
  tests, multibagger analysis. **Nothing graduates to Core without: DSR > 0.95 + purged-CV +
  cross-period + cross-universe robustness** (PBO/SPA planned).

## REMOVED from the architecture (failed their tests — keep out to prevent complexity creep)
❌ LSTM/Transformer forecasting ❌ RL/PPO/SAC stock-picking ❌ GNN ❌ HMM regime (lost to simple)
❌ Chronos/PatchTST/TimeGPT/TimesFM ❌ world models ❌ agentic/multi-agent ❌ knowledge graph
❌ causal AI ❌ multibagger *prediction*. Evidence: **data is the bottleneck, not the model.**

---

## AEGIS-Moonshot (OPTIONAL satellite — power-law, not prediction)
VC philosophy: don't predict which doubles; own 40 quality+growth+momentum names (equal-weight,
sector-capped, annual hold) and let winners drive it. **Honest result:** Moonshot CAGR 12.1%,
Sharpe 0.87 — it does NOT beat Core (2.04); a 70/30 barbell *dilutes* Sharpe to 1.62.
→ **Moonshot is a personal risk-appetite choice (lottery upside at the cost of Sharpe), NOT an
edge.** Multibaggers (BSE 58x) aren't identifiable in advance (2/10 ≈ random) — broad holding owns
them, but the risk-managed Core remains the rational anchor.

## Capacity & Reality  (mandatory honesty — retail systems overstate alpha)
Track & report: turnover · slippage · taxes · concentration · sector & correlation exposure ·
**cross-period stability · cross-universe stability (Nifty-100 vs 200)**. Survivorship inflates CAGR
→ trust the Sharpe/DD *improvement over EW*, not absolute returns.

## Free Data Stack
Price: Angel SmartAPI ✅ · Regime: India-VIX/breadth ✅, **Global (S&P/VIX/DXY/oil/gold/US10Y/USDINR) ✅**,
FII/DII (NSE, planned) · News: Google RSS + FinBERT ✅ · Factors: Fama-French (planned) ·
Macro: FRED (planned) · Fundamentals: yfinance snapshot / SimFin (US). **Real gap: point-in-time INDIA fundamentals.**

## v2.5 status (built + tested)
- ✅ **FII/DII flow engine** (`fii_dii.py`) — NSE live; no free history → forward-collected (like news).
- ✅ **PBO** (`validation.py`) — Probability of Backtest Overfitting across 10 configs = **0.00** (robust).
- ❌ **GARCH/EWMA vol** (`risk_forecast.py`) — corr with next-month vol 0.442/0.439 vs trailing **0.444**
  → no improvement, REJECTED (trailing vol is good enough; keep it simple).
- ⏸ Conformal uncertainty · triple-barrier+meta-label · Fama-French — Lab/deferred (low fit for the
  rules-based Core; revisit only with a prediction model or new data).
Validation gate now = **Deflated Sharpe + PBO + purged walk-forward**.

## Crypto (parked — stocks first)
Risk principle (vol-targeting, regime de-risk) transfers to gold/BTC; cross-sectional selection does
not (~10-20 liquid assets).
