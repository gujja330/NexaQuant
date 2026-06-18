# Arjuna — AI/ML Refinement Plan (honest)

## The correction I owe you
I earlier said "AI doesn't help." That was **too narrow and partly wrong**. What I actually showed
was that **AI on 7 price-only features over 300 holdings of one momentum strategy** had no skill
(AUC 0.47). That is NOT evidence against AI for stock selection — it's evidence I **starved** the model.

The literature is clear that ML/DL **does** add real value — *when fed rich features on broad data:*

| Study | What it shows |
|---|---|
| **Gu, Kelly & Xiu (2020)** — Empirical Asset Pricing via ML | Trees + neural nets on **30,000 stocks, 60 yrs, 900+ signals** (94 fundamentals + macro + industry) **DOUBLED** regression-strategy returns. Nonlinear interactions are the source of the gain. |
| LSTM / Transformer + **FinBERT news sentiment** (2024–25) | News-sentiment features processed by an LLM beat price-only baselines. |
| Ke, Kelly & Xiu — text | Supervised news-text models carry return-predictive signal (crude sentiment doesn't). |

**Why mine failed vs why theirs works:**
| | My test (no skill) | Literature (works) |
|---|---|---|
| Features | 7, price-only | **900+**: fundamentals + technicals + news + macro |
| Data | 300 holdings, 1 strategy | 30,000 stocks × 60 yrs |
| Framing | binary win/loss | **cross-sectional return ranking** |

So: **AI is worth doing — but properly.** Refinement, not dismissal.

## The refinement roadmap (what "doing it properly" means here)
1. **RICH feature set** (the whole point):
   - *Technical*: multi-horizon momentum, volatility, ADX/RSI, distance-from-MAs, liquidity/turnover.
   - *Fundamental* (needs point-in-time history): ROE/ROCE, margins, debt, growth, FCF, valuation, Piotroski-F.
   - *News/text*: FinBERT sentiment on headlines + earnings calls (per stock, per day).
   - *Macro/sector*: India VIX, USD/INR, crude, US S&P, sector-momentum, FII/DII flows.
2. **BROAD data**: full Nifty 200/500 universe + as many years as we can get (broker API for clean history).
3. **Right framing**: predict the **cross-sectional rank of forward returns** (Gu-Kelly-Xiu style), not a binary win/loss of one strategy.
4. **Right models**: gradient-boosted trees + a small neural net (the two that won in the literature), ensembled.
5. **Rigorous validation**: purged + embargoed walk-forward CV, Deflated Sharpe, PBO — to avoid the overfit that nearly fooled us on the 23-stock universe.
6. **Use it as a RANKING/overlay** on the momentum core (tilt toward high-score names, down-weight low) — not as an oracle, not replacing risk management.

## What it requires (and the honest caveats)
- **Data we still need:** point-in-time fundamentals (paid/scraped), news feed for sentiment, and the broker's clean historical universe. *The broker connection + a news source are the unlock.*
- **Compute:** more than the current scripts, but fine on the laptop.
- **Honest expectations:** the literature's "doubling" is **gross, pre-cost, on a 30k-stock US universe**. A retail, ~200-stock, cost-laden Indian version will deliver **far less** — but plausibly a *real* lift over pure momentum if features + validation are done right.
- **#1 risk:** overfitting. With 900 features it's easy to fool yourself — the rigor gate (purged CV / Deflated Sharpe) is non-negotiable. We already saw how a narrow universe faked Sharpe 1.23.

## Sequence (ties to the broker connection)
1. **Connect broker** → pull clean Nifty 200/500 history (universe + intraday).  ← next
2. **Add news sentiment** (FinBERT) + macro/sector features.
3. **Source point-in-time fundamentals** (the hardest data gap).
4. **Build the ML ranking model** (GBT + NN, rich features) with purged-CV/Deflated-Sharpe gate.
5. **Overlay on the momentum core**; keep only if it beats pure momentum *out-of-sample, net of cost*.

**Bottom line:** you were right. AI/ML/DL are proven for stock selection with rich features — my
dismissal reflected a starved test, not the method. The refinement is real and worth doing; it just
needs richer data (broker + news + fundamentals) and hard validation, in that order.
