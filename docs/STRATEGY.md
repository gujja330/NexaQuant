# NexaQuant — High-Level Strategy

**Thesis:** profit comes from *edge × payoff × risk control*. Entries give a small edge;
**exits and risk management create the bigger profits.** SL, trailing, momentum-riding,
and position sizing matter more than how many trades we take.

---

## The strategy in one picture

```
        ┌───────────── BIAS (top-down) ─────────────┐
WEEKLY/DAILY trend  +  MACRO fundamentals (yields↓, USD↓ = gold bullish)
        └──────────────────────┬─────────────────────┘
                               ▼   permission to go long?
                       ┌─── REGIME GATE ───┐
              TREND → continuation ON   |  VOLATILE → stand aside
              RANGE → mean-revert ON    |
                               ▼
                  ENTRY (execution TF: M15/M5; tested on H1/H4)
        regime-gated continuation: EMA20>EMA50 + bullish structure/FVG
                               ▼
   ┌──────────────────── TRADE MANAGEMENT (where profit is made) ───────────────────┐
   │  STOP-LOSS    : hard 2×ATR stop — every loser capped (non-negotiable)            │
   │  BIGGER PROFIT: MOMENTUM-RIDE — hold while close > EMA20; exit when momentum dies │
   │  SCALE-OUT    : bank ~40% at +1.5R, move stop to breakeven, ride the rest         │
   │  SIZING       : volatility-targeted, fractional-Kelly capped                      │
   └──────────────────────────────────────────────────────────────────────────────────┘
                               ▼
              AI META-LABEL (when data-rich): P(win) gates / sizes entries
                               ▼
         VALIDATION GATE: walk-forward + Purged CV + paper trading → capital
```

---

## Why these exit rules (measured, OOS, net of cost — `research/exit_probe.py`)

| Exit style | Win% | Payoff | Max winner | Total | MaxDD | Sharpe |
|---|---|---|---|---|---|---|
| Let it run forever (stop only) | 22% | 12.5 | 33R | highest $ | high | 1.3 |
| Tight trailing | 36% | 1.3 | 2.7R | **negative** | — | −1.3 |
| **Momentum-ride** | 57% | 3.3 | 6.2R | high $ | **lowest** | **3.3** |
| **Momentum + scale-out** | 64% | 2.3 | 4.3R | high $ | **lowest** | **3.8** |

- **Stop-loss is mandatory** — it caps every loser; without it one bad trade erases many.
- **Don't choke winners** — a tight trailing stop turns a profitable edge *negative*.
- **Ride momentum for bigger profits** — hold while price stays above the fast EMA; this
  captures large R-multiples yet cuts drawdown ~40% vs letting it run blindly.
- **Scale-out** trades a little total profit for higher win-rate and a smoother curve.

## Canonical end-to-end result (`research/playbook_backtest.py`)
- **H4: robust** — positive in-sample AND out-of-sample (Sharpe 1.4 → 2.7, payoff 1.7–2.5).
- **H1: bull-dependent** — strong OOS (Sharpe 5.5) but negative in the choppy early sample;
  needs the AI/fundamental filters and multi-regime data before it's trustworthy.

## What makes it stronger (the roadmap)
1. **More data** (`data/pull_open_data.py` Binance, `data/pull_stooq.py` gold/FX — no keys)
   → multi-regime samples fix the H1 in-sample weakness.
2. **Fundamentals** (`data/fundamentals.py`) → macro bias as top-of-funnel + AI feature.
3. **AI meta-label / ensemble** → gate the weaker entries once features & samples are rich.
4. **Rigor gate** (`research/validation_runner.py`) → only configs that survive walk-forward
   + Purged CV + paper trading get capital.

## Hard rules
- Stop-loss on every trade. No exceptions.
- Never deploy a config that hasn't cleared the validation gate + 30-day paper trading.
- Model complexity rises only with data breadth and validation rigor.
