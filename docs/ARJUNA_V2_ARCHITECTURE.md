# ARJUNA v2 — Architecture (evidence-based redesign)

Replaces the v1 "pick winners" framing, which the data killed. v2 is built on what the data
actually supports.

## The one finding that defines v2
Tested 13 model families (XGBoost…Transformer…RL…GNN) on *return* prediction → **all AUC ≈ 0.50**
(coin flip). Then reframed the **target** (the real insight): same XGBoost, predict **risk** →
**volatility AUC 0.76, drawdown AUC 0.62.** 

> **Returns are unpredictable. Risk is predictable. So v2 stops picking winners and constructs the
> portfolio around forecastable risk + market regime.**

This is how AQR/BlackRock actually earn risk-adjusted alpha (low-volatility anomaly), not how
retail systems chase tips.

## What v2 IS (built + validated, `india/arjuna_v2.py`)
Broad Nifty-200 basket, monthly rebalance, net of ~21bps:
1. **Risk-based weights** — inverse-volatility (risk-parity lite) or minimum-variance (Ledoit-Wolf
   shrinkage covariance), per-name cap for diversification.
2. **Regime de-risk overlay** — cut exposure when India VIX is high AND/OR Nifty < 200-DMA.
   *(This is the dominant lever.)*
3. Goal = **higher Sharpe + smaller drawdown**, NOT higher raw return.

**Validated result (full window):** INV_VOL+regime → Sharpe **1.64**, maxDD **14.3%** (vs EW 1.11/20.7%,
Nifty 0.80/17.2%). MIN_VAR+regime → CAGR 21.3%, Sharpe 1.61. The Sharpe/DD *improvement* over
equal-weight is the honest, survivorship-free signal.

## Why NOT "pick the next multibagger"
`india/multibagger_analysis.py`: the doublers (BSE 58x, MAZDOCK 23x) were **not identifiable in
advance** (our screen caught 2/10 ≈ random 1.3/10). Since you can't predict *which* stock 58x's,
owning a broad basket is the rational way to *hold* the winners you can't pick. Concentration =
betting on prediction we've proven doesn't work.

## Curated roadmap — what actually adds value at OUR scale (retail, free data, 220 stocks, ~5y)
The institutional 37-module list is correct *for a fund*. Filtered to what moves the needle here:

### ADD next (high ROI, tractable with free/near-free data)
- **HMM/GMM regime model** — upgrade the VIX+trend rule (already the biggest lever) to a learned
  bull/bear/crash state. ⭐
- **Breadth engine** — % above 200-DMA, advance/decline, new highs/lows. Free, powerful regime input. ⭐
- **FII/DII flow engine** — NSE publishes daily; India-specific regime signal. ⭐
- **Triple-barrier labels + meta-labeling** (López de Prado) — better than fixed-horizon return;
  primary finds candidates, secondary filters. ⭐
- **Purged + embargoed walk-forward CV + Deflated Sharpe** — rigor gate; prevents the overfit that
  faked Sharpe 1.23 before. ⭐ (non-negotiable)
- **GARCH/EGARCH volatility** — refine the risk forecast that already works (AUC 0.76).
- **SHAP explainability** — show *why* each name is weighted (easy, builds trust).
- **Corporate-action correctness** — verify Angel data is split/dividend adjusted.

### Data-blocked (the real bottleneck — needs sourcing/paid)
- **Point-in-time fundamentals** — the #1 institutional item; no free source → snapshot bias today.
- **Earnings-call NLP, insider trades, options/OI flow, analyst revisions** — need data feeds.
- **Alt-data (satellite, credit-card, shipping)** — institutional only; not feasible retail.

### Low ROI for us right now (model complexity without new signal)
- **Foundation time-series (Chronos/PatchTST/TimesFM), GNN, causal AI, knowledge graph, world
  model, agentic/self-improving** — elegant, but 13 models already showed model choice isn't the
  bottleneck; these re-process signal-less features. Revisit only after new DATA is added.

**The honest meta-point:** our bottleneck is **data, not model sophistication.** Regime + risk
construction + rigorous validation + (where free) breadth/FII/news is the 80/20. Frontier models
add little until point-in-time fundamentals / alt-data / news history exist.

## News (live, forward-only)
`india/news_sentiment.py` (FinBERT + Google News RSS) runs daily via the `ArjunaDailyPaper`
scheduled task, used as a **blow-up filter** (drop strongly-negative names). Can't be backtested
(no free historical news) → validated forward.

## Does this apply to CRYPTO (gold/BTC system)?
**Yes — the risk principle transfers; the selection part doesn't.** Crypto vol clustering is even
stronger → **vol-forecast position sizing + regime de-risk** would lift the gold/BTC system's
Sharpe. But crypto has few liquid assets (~10-20), so the *cross-sectional* low-vol/min-var effect
is weak — there it's about **risk-targeting a few instruments**, not ranking a universe.

## Status
v1 (equal-weight basket + news filter) + v2 (risk + regime) built and validated. Forward paper
running. Next build = HMM regime + breadth + FII + triple-barrier/meta-label under purged-CV/DSR.
