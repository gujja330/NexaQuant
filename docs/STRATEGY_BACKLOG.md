# NexaQuant — Strategy & Signal Backlog (master list)

Research-sourced candidate strategies/signals to evaluate for NexaQuant, across **fundamentals,
technicals, AI/ML, microstructure, and risk/portfolio**. Compiled 2026-06-18 from verified
sources (peer-reviewed journals, AQR, López de Prado's framework, World Gold Council / CB data,
Glassnode-style on-chain research, recent arXiv).

**Governing rule (earned the hard way):** a *context/filter/size* signal can add edge; a raw
*trigger* signal usually doesn't. We have already REJECTED pyramiding, candle-streak triggers,
pure-expansion entries, and fast timeframes (M5/M15) because they failed back-testing. Nothing
on this list is adopted until it passes the same rigor gate (per-year walk-forward + CPCV +
Deflated Sharpe, drawdown-aware). This is a *test queue*, not a promise.

Priority key: **P1** = strong evidence + good fit, test soon · **P2** = conditional / needs the
ML layer · **P3** = frontier / research-only, do not risk capital yet.

---

## A. FUNDAMENTALS  (macro for gold, on-chain/flows for BTC)
Slow signals — they set **bias/regime over weeks–months**, not H4 entries. Best used as a
**context filter** or a **meta-label feature**, never as a standalone trigger. This is the
"fundamentals make the AI strong" layer the project has repeatedly asked for.

### Gold (XAUUSD)
| Signal | Evidence | Use in NexaQuant | Prio |
|--------|----------|------------------|------|
| **Real yields** (10y TIPS) — inverse to gold | Long-established; weakened 2020-25 (gold rose with yields under fiscal stress) | Bias filter / feature; free from FRED | P1 |
| **DXY (US dollar index)** — inverse to gold | "DXY up = gold down"; DXY -9/10% in 2025 ↔ gold +65% | Bias filter / feature; free (yfinance) | P1 |
| **Central-bank demand** — structural bid | CBs bought >1,000 t/yr since 2022 (≈2× decade avg) | Slow regime context (quarterly) | P2 |
| **VIX / risk-off** — safe-haven flows | Used in practitioner gold L/S frameworks | Volatility/risk-on-off feature | P2 |
| **Inflation + fiscal deficits** | 2020-25 regime where gold rose despite yields | Macro regime feature | P2 |

### Bitcoin (BTCUSD)
| Signal | Evidence | Use in NexaQuant | Prio |
|--------|----------|------------------|------|
| **MVRV Z-score** — over/undervaluation | Standard cycle gauge; BUT failed to give clean top this cycle | Cycle-bias feature; do NOT over-trust | P2 |
| **SOPR** — profit/loss of moved coins | Marks profit-taking phases (>1 profit, <1 loss) | Distribution/accumulation feature | P2 |
| **NUPL** — net unrealized profit/loss | Sentiment regime proxy | Feature | P2 |
| **Spot-ETF net flows** | $21.4B net inflows in 2025 drove price | Demand feature (data access harder) | P2 |
| **Perp funding rate** — leverage/positioning | Extreme funding ↔ squeeze risk | Risk/contrarian filter | P1 |
| **Long-term-holder distribution** | LTH selling + miner selling = cycle-top tell | Regime risk feature | P2 |

> Honest caveat: on-chain "top indicators" **failed this cycle** (Bitcoin Magazine, CryptoQuant).
> On-chain is for weeks-to-months positioning, *not* short-term timing. Use as context, size-down
> risk, never as a hard trigger.

---

## B. TECHNICALS  (beyond what we already run)
| Signal | Evidence | Use in NexaQuant | Prio |
|--------|----------|------------------|------|
| **Volatility targeting / scaling** | AQR / Alpha Architect: Sharpe 0.40→0.48-0.51; "adds momentum free" | Size overlay (equal risk per trade) | **P1** |
| **Multi-lookback TSM** (1/3/6/12) | Moskowitz/AQR: ~11%/yr, half equity vol, robust through every recession | Entry confirmation (sign agreement) | **P1** |
| **RSI *divergence*** (not level) | 2025 gold: levels unreliable, divergences more reliable | Exhaustion/confirmation feature | P2 |
| **MACD histogram expansion** | Acceleration/fade cue | Momentum feature | P3 |
| **VWAP / volume profile** | Institutional benchmark; academic edge MIXED, real for execution | Execution price (not alpha) | P3 |
| **Lengthy-candle size boost** | ✅ ALREADY ADOPTED: H4 +42%→+54%, same DD | Confidence booster (shipped) | done |

---

## C. AI / ML
| Technique | Evidence | Use in NexaQuant | Prio |
|-----------|----------|------------------|------|
| **Meta-labeling** (López de Prado) | Widely adopted by multi-manager funds; "not a silver bullet" — filters false positives + sizes | Wire as `confidence_source:"ai"` once it clears CPCV | **P1** |
| **Trend-scanning labels** | Newer alt to triple-barrier; may lift AUC/precision | Test inside existing meta_label validation | P2 |
| **LLM news sentiment** (GPT/OPT > FinBERT) | OPT long-short Sharpe 3.05 vs FinBERT 2.07 in studies; generative LLMs beat lexicon/FinBERT | Daily sentiment feature; beware look-ahead bias | P2 |
| **Deep RL position sizing** | Academic results modest & fragile (e.g. 11.87%/5yr); overfit-prone | Sim-only sizing experiment | P3 |
| **Transformer / TFT forecasting** | FinTSB/reviews: non-stationarity + shocks make direct price forecasting unreliable | Feature only, gated | P3 |

> The honest AI thesis: AI helps **most as a selector/sizer/validator** (meta-labeling, CPCV,
> Deflated Sharpe) — not as a price oracle. Our biggest realized AI win so far is AI **validation**
> catching overfit configs (it flagged BTC H1 as a mirage).

---

## D. RISK / PORTFOLIO  (often the biggest Sharpe lever)
| Idea | Evidence | Use in NexaQuant | Prio |
|------|----------|------------------|------|
| **Volatility targeting** | (see B) — best-verified Sharpe improver | Position-size overlay | **P1** |
| **Risk-managed momentum** (crash protection) | 2025 crypto study: scale down after vol spikes ↑ risk-adjusted return | Cut/skip size after extreme counter-move/vol | **P1** |
| **Risk parity across BTC + gold** | AQR: ~60% higher Sharpe vs 60/40 over 39y | Allocate by inverse-vol across the two | P2 |
| **Multi-edge portfolio** (add range-regime mean-reverter) | Diversification = the verified free lunch | Mean-reversion sleeve active in range regimes | P2 |

---

## E. FRONTIER / UPCOMING  (watch; do not bet capital)
| Idea | Evidence | Stance | Prio |
|------|----------|--------|------|
| **LLM multi-agent trading frameworks** | 84-study review (2022-25): prompting/fine-tune/multi-agent/RL | Explore for research/feature gen | P3 |
| **Alpha-GPT signal generation** | LLM-assisted creative signal discovery | Idea generator, then OUR gate | P3 |
| **Order-flow imbalance (Hawkes)** | Strong HFT evidence; off-exchange volume > on-exchange since Nov-2024 | Wrong timeframe for us (HFT) | P3 |
| **Quantum-enhanced DRL** | Experimental FX agent results | Watch only | P3 |

---

## First research round — recommended test order (preserved verbatim)
The original short-list before this round's fundamentals/microstructure additions:

| Priority | Idea | Why first |
|----------|------|-----------|
| 1 | **Volatility-targeting overlay** | Best-verified Sharpe improver; small change to existing code |
| 2 | **Risk-managed momentum filter** | Directly attacks our drawdowns; uses existing `event_guard` |
| 3 | **Meta-label as AI confidence source** | The "AI strengthens it" payoff you've asked for — but gated |

Start with **#1 and #2** — both small, evidence-backed, testable on BTC H4 the same way we tested
everything else. If either fails the rigor gate, we drop it (like pyramiding).

## Consolidated build queue (merging both research rounds)
1. **Volatility-targeting overlay** — small change to `strategy/risk.py`; best-verified. *(build first)*
2. **Risk-managed momentum filter** — uses existing `event_guard.py`; attacks our drawdowns.
3. **Fundamental bias layer** — DXY + real-yield (gold), funding rate (BTC) as **context filters**
   first, then as meta-label features. Free data; directly the "fundamentals + technicals + AI" thesis.
4. **Multi-lookback TSM confirmation** — diversify the single EMA signal.
5. **Meta-label → AI confidence source** — only after it clears CPCV/Deflated-Sharpe with real skill.
6. **Multi-edge mean-reversion sleeve** — structural Sharpe via diversification (bigger build).

Each ships only if it beats the current champion on the per-year walk-forward without worse
drawdown — same discipline that rejected pyramiding, streaks, and fast timeframes.

---

### Sources

**Risk / portfolio / momentum**
- [AQR – Risk Parity Is Even Better Than We Thought](https://www.aqr.com/Insights/Perspectives/Risk-Parity-Is-Even-Better-Than-We-Thought)
- [AQR – Alternative Thinking 2025 (Capital Market Assumptions)](https://www.aqr.com/-/media/AQR/Documents/Insights/Alternative-Thinking/Alternative-Thinking-2025-Capital-Market-Assumptions.pdf)
- [Alpha Architect – Volatility Targeting Improves Risk-Adjusted Returns](https://alphaarchitect.com/volatility-targeting-improves-risk-adjusted-returns/)
- [Alpha Architect – Time Series Momentum: The Historical Evidence](https://alphaarchitect.com/time-series-momentum-aka-trend-following-the-historical-evidence/)
- [Cryptocurrency market risk-managed momentum strategies (ScienceDirect, 2025)](https://www.sciencedirect.com/science/article/abs/pii/S1544612325011377)
- [Systematic Trend-Following with Adaptive Portfolio Construction in Crypto (arXiv 2026)](https://arxiv.org/pdf/2602.11708)
- [Forecast-to-Fill: Benchmark-Neutral Alpha in Gold Futures 2015–2025 (arXiv)](https://arxiv.org/pdf/2511.08571)

**Fundamentals — gold macro & BTC on-chain**
- [J.P. Morgan Global Research – Gold Price Predictions 2026/2027](https://www.jpmorgan.com/insights/global-research/commodities/gold-prices)
- [VanEck – Gold in 2025: Structural Strength](https://www.vaneck.com/us/en/blogs/gold-investing/gold-in-2025-a-new-era-of-structural-strength-and-enduring-appeal/)
- [OANDA – Gold's 2025 Breakout: Drivers, Inflation, Geopolitics & Technicals](https://www.oanda.com/us-en/trade-tap-blog/analysis/technical/gold-2025-breakout/)
- [ACY – Gold Strategy Using VIX, US Yields, and the Dollar](https://acy.com/en/market-news/education/gold-strategy-using-vix-yields-dxy-2025-l-s-162409/)
- [checkonchain – BTC On-Chain Metrics & Indicators](https://charts.checkonchain.com/)
- [Bitcoin Magazine – Why Bitcoin Price Top Indicators Failed This Cycle](https://bitcoinmagazine.com/markets/why-bitcoin-price-top-indicators-failed)
- [Using on-chain data to predict Bitcoin cycles (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0275531926002138)

**AI / ML / meta-labeling / sentiment**
- [Meta-Labeling overview (Wikipedia)](https://en.wikipedia.org/wiki/Meta-Labeling)
- [Why Meta-Labeling Is Not a Silver Bullet (QuantConnect)](https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/)
- [Does Meta Labeling Add to Signal Efficacy? (Hudson & Thames)](https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/)
- [Trend-Scanning Labeling Method (MQL5 ML Blueprint Part 3)](https://www.mql5.com/en/articles/19253)
- [Sentiment trading with large language models (arXiv 2412.19245)](https://arxiv.org/abs/2412.19245)
- [Large Language Models in equity markets: review of 84 studies (Frontiers/PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12421730/)
- [Reinforcement Learning in Financial Decision Making: A Systematic Review (arXiv 2025)](https://arxiv.org/pdf/2512.10913)
- [FinTSB: A Practical Benchmark for Financial Time Series Forecasting (arXiv 2025)](https://arxiv.org/pdf/2502.18834)

**Microstructure / order flow**
- [Federal Reserve – Order Flow Imbalances and Amplification of Price Movements (2025)](https://www.federalreserve.gov/econres/notes/feds-notes/order-flow-imbalances-and-amplification-of-price-movements-evidence-from-u-s-treasury-markets-20251103.html)
- [VWAP: The Holy Grail for Day Trading Systems — Zarattini & Aziz (SSRN)](https://papers.ssrn.com/sol3/Delivery.cfm/4631351.pdf?abstractid=4631351&mirid=1)
