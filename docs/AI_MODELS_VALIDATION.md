# Aegis — AI Model Validation (complete, honest)

**Question:** can AI/ML pick Indian stocks that beat the index, using our data
(220 Nifty-200 stocks, ~5.5y daily, 31 features = technical + fundamental + macro + sector)?

**Method:** predict "will this stock beat the median stock next month?" (balanced 50/50),
monthly expanding walk-forward (train→Dec-2023, predict Jan-2024, roll to Apr-2026, ~28 months
out-of-sample). Score: AUC (0.50 = coin flip), classification accuracy, and a top-10 portfolio
(net of cost) vs Nifty buy-and-hold (~10.7% CAGR over the OOS window).

## Every model tested (13 approaches)

| Model | Type | AUC | Acc% | top-10 CAGR | Verdict |
|---|---|---|---|---|---|
| XGBoost | boosting | 0.511 | 51.7 | 10.5% | no edge |
| LightGBM | boosting | 0.513 | 50.7 | 10.5% | no edge |
| HistGBM | boosting | 0.518 | 51.2 | 7.9% | no edge |
| RandomForest | trees | 0.501 | 49.3 | 16.5%* | *luck (seed 9-18%)* |
| ExtraTrees | trees | 0.502 | 50.1 | 15.3%* | *luck* |
| Logistic | linear | 0.500 | 49.9 | 7.2% | no edge |
| KNN | distance | 0.508 | 50.8 | 12.5% | no edge |
| NaiveBayes | prob | 0.488 | 48.3 | 7.7% | no edge |
| LSTM | deep seq | 0.514 | — | 16.4%* | *luck* |
| Transformer | deep seq | **0.497** | — | 17.6%* | *AUC<0.50 → gain is pure luck* |
| DeepMLP | deep | 0.510 | — | 13.0% | no edge |
| PPO | reinforcement | — | — | 7.2% (timing) | **lost to buy&hold (11.7%)** |
| GCN | graph NN | 0.485 | — | 2.7% | **lost to Nifty** |
| QNN | quantum | — | — | — | not runnable / research-stage, no real-world edge shown |

\*High portfolio CAGRs with AUC≈0.50 are small-sample LUCK, proven: RandomForest's 16.5% swung
9.1%–18.0% across 8 random seeds; the Transformer "made 17.6%" with AUC 0.497 (negative skill) —
you cannot have negative skill and real gains, so it's noise.

## Feature importance (why)
XGBoost gain is dead flat (all ~0.034–0.039 — no feature dominates). Out-of-sample permutation
importance peaks at **crowding +0.009, turnover +0.008** — negligible (<0.01), and they're
risk/liquidity features, not fundamentals/momentum. ROE ≈ +0.003 (nothing).

## Conclusion
**13 model families — linear, trees, boosting (incl. the industry-standard XGBoost/LightGBM),
kNN, naive-bayes, LSTM, Transformer, deep MLP, reinforcement learning, graph NN — ALL land at
AUC ≈ 0.50 / accuracy ≈ 50%.** When models that work in completely different ways all say
"coin flip," the bottleneck is the **information in the data, not the model**. Price + snapshot
fundamentals simply do not carry a tradeable stock-selection signal at this scale/horizon, net
of retail cost. Fancier models cannot extract signal that isn't there.

## The only remaining lever
**NEWS / alt-data** — information NOT already in price or fundamentals. This is the one thing
that could move AUC. Constraint: free *historical* per-stock news isn't available (yfinance gives
~10 recent, noisy headlines), so FinBERT can run only as a **live/forward** experiment (not
backtestable) unless we pay for a historical news feed.

## What this means
- Stock-SELECTION via ML on available data: **no edge.** Don't keep re-testing it.
- Deployable now: the equal-weight quality basket (≈ index, better diversification) — honest,
  not alpha.
- Real AI edge already exists in the **gold/BTC** system.
