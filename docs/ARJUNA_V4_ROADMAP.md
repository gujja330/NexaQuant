# ARJUNA v4 Roadmap — "AI: Temporarily Closed, Reopens on Data"

> We are NOT abandoning AI / ML / DL / RL. We are striking off **"AI with our *current data* and
> *current problem formulation*"** — a very different statement. The models are a Ferrari engine;
> our data is kerosene. Institutions run the same engine on jet fuel. **They don't worship models.
> They worship data.** That is the biggest lesson ARJUNA has learned.

## The doctrine: data comes first, models last

```
Data  ->  Features  ->  Targets  ->  Validation  ->  Models
```

Model sophistication is the LAST lever, not the first. The literature (Gu-Kelly, Hanauer/Robeco,
Chen, State Street) agrees: **model choice matters far less than data quality and target design.**
More models != more alpha. This is why "AI doesn't work in finance" is false — Renaissance, Two
Sigma, AQR, BlackRock Aladdin, State Street, Robeco all use ML. The honest statement is narrower:

> AI mostly does NOT work on **5 years · ~220 stocks · daily prices · public fundamentals · India ·
> monthly returns.** That specific combination is the constraint — not AI itself.

## What we have already tested (and why it's closed, not dead)

XGBoost · LightGBM · Random Forest · LSTM · Transformers · RL · GNN · Ranking · Recovery ·
Persistence · Multibagger · Resilience — **all converged to "no edge" or "re-discovering low
volatility."** Not because the models are bad, but because the fuel is wrong.

```python
# the policy, in code (india/config.py):
MODELS_FROZEN_UNTIL_DATA_ARRIVES = True     # NOT *_FOREVER. A signboard, not a tombstone.
```

## The signboard

```
            ┌─────────────────────────────────────────┐
            │   AI / ML / DL / RL — TEMPORARILY CLOSED  │
            │                                           │
            │   Reopens when:                           │
            │     ✓ Point-in-time fundamentals          │
            │     ✓ Historical news archive             │
            │     ✓ Analyst revisions                   │
            │     ✓ Alternative / options-flow data     │
            └─────────────────────────────────────────┘
```

Run `python india/ai_reopen.py` to see which triggers are CLOSED vs ARMED right now.

## v4 triggers — data unlocks, mapped to the models they reopen

| # | Trigger (data arrives) | Reopen these | Task framing |
|---|---|---|---|
| 1 | **Point-in-time fundamentals** | XGBoost · CatBoost · TabNet · FT-Transformer · TabPFN · DeepFM · SAINT | cross-sectional ranking on PIT factors |
| 2 | **Historical news archive** | FinBERT · DeBERTa · FinGPT · Llama · Longformer | event/sentiment drift, timestamped |
| 3 | **Analyst revisions** | LightGBM · CatBoost · LambdaMART (ranking) | revisions lead fundamentals |
| 4 | **Options / derivatives flow** | Temporal Fusion Transformer · Chronos · PatchTST · TimesFM | short-horizon, informed-flow signals |
| — | **RL** (multi-decade, ~20k stocks, multi-asset, macro, costs) | PPO/SAC at institutional scale | dynamic allocation, not 220-stock/5y toy |

Why these are different from what we tested: PIT data removes the look-ahead bias that silently
inflates (and then breaks) backtests; news/analyst/options data is *information not yet in the price*
the way trailing technicals are. New fuel, not a new engine.

## Reopen discipline (so v4 doesn't repeat v1's mistakes)

A trigger fires → work happens in the **Lab** (`india/research/`), never in frozen Core. Every
experiment: walk-forward / purged CV · nested tuning · deflated Sharpe + PBO for the trial count ·
realistic costs. A model reaches production ONLY via the decision gate: beats Core's rolling Sharpe,
acceptable turnover + drawdown, **net of cost, on forward data.** See the protocol in
`docs/ARJUNA_DEEP_RESEARCH_ML.md`.

## The arc

```
v1  Maybe LSTM finds multibaggers.        (wrong question)
v2  Returns are hard. Risk is predictable. (the reframe)
v3  Portfolio engineering > prediction.    (manage wealth — ARJUNA OS)
v4  New data unlocks new AI.               (signboard reopens)
```

No tombstone on ML/DL/RL/Transformers/GNN/FinGPT/TimesFM — a signboard. Reopens when the fuel
arrives. That is exactly how the firms that *do* win with ML actually operate.
