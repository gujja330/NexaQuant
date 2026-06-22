# NexaQuant — Gold + BTC Short-Term Trading System

A pragmatic, **evidence-first** trading engine. The goal is short-term, profitable
trades on gold and BTC (later FX / commodities). Before building a large multi-agent
stack, we **prove an edge actually exists** on the data we have, net of realistic costs.

> Honesty rule of this repo: **no claim is made unless a script in `research/`
> produces it out-of-sample, net of costs.** The "75-80% win rate" PDF in `docs/`
> is an academic best-case survey — our own architecture doc targets a realistic
> **50-60% win rate, Sharpe 1.0-1.5, 1-4% monthly**. We trust the realistic numbers.

---

## What we found so far (run the probes yourself)

Data: ~2 years of clean gold OHLCV — `H1` (11,822 bars), `H4` (3,198), `D1` (622),
`W1` (105, resampled). Out-of-sample = last 30% (~2025).

| Finding | Evidence |
|---|---|
| **A real edge exists, but it's risk-adjusted, not magic.** Long-only EMA-20/50 trend on H1 made ~the same money as buy-and-hold gold but with **~half the drawdown** (OOS Sharpe **3.2 vs 2.3**). | `research/edge_probe.py` |
| **Win rate is a trap.** RSI mean-reversion won 65% of trades but **lost money** (small wins, big losses). Trend-following won only ~38-55% but was **profitable** (big winners). Expectancy & payoff ratio matter, not win %. | `research/edge_probe.py` |
| **Most of the absolute return is gold beta**, not timing skill — 2023-2025 was a historic gold bull. In a sideways/bear regime this long-only edge will shrink or invert. | buy-and-hold benchmark in `edge_probe.py` |
| **The edge is cost-robust.** Sharpe barely moves from $0.30 → $1.00 round-trip cost. Trend trades are large vs. spread. | cost-sensitivity block |
| **Top-down MTF couldn't be validated here.** Adding D1/W1 bias filters made no OOS difference and slightly hurt in-sample — because this sample is essentially **one regime**. The method is sound (and how you intend to trade), but proving it needs a **multi-regime sample** and the **M5/M15 execution data we don't have yet**. | `research/mtf_edge_probe.py` |
| **SMC works only for its continuation pillars.** Market Structure (BOS) + FVG had **positive** edge (FVG+Structure on H4: Sharpe **1.9 in AND out of sample**). Liquidity-sweep-fading and deep-discount buying had **negative** edge on trending gold. Stacking all 5 pillars ("A+") **lost money**. | `research/smc_probe.py` |
| **The regime gate helps (where we have data).** Gating continuation to TREND regime only lifted H1 OOS Sharpe **3.19 → 3.55** and cut drawdown **~33%** ($254→$172). Adding range mean-reversion kept return up with less drawdown. (H4 = mixed, smaller sample.) | `research/regime_gated_probe.py` |
| **Naive per-bar vol-sizing churns cost.** Rebalancing size every bar created huge turnover and *hurt* Sharpe — sizing must be set once at entry, not continuously. | `research/regime_gated_probe.py` |
| **AI meta-labeling is PREMATURE (not wrong).** HistGradientBoosting on rules entries scored **AUC ≈ 0.51 (coin-flip)** — only 154 entries / 43 OOS and technical-only features. The framework is built & correct; it needs more data (M5/M15, BTC) and **fundamental features** to gain skill. Empirically confirms: AI gets strong as the feature set widens. | `research/meta_label_probe.py` |
| **RIGOR GATE verdict (the honest bottom line).** Regime-gated continuation on H1: **100% of 6 walk-forward folds positive**, **Deflated Sharpe 0.94** (just under the 0.95 bar — *nearly* robust to multiple-testing). H4 is weak (DSR 0.31, 2 losing folds). CPCV of the AI meta-labeler: **AUC 0.47 → no skill yet**. So: H1 edge is real & almost-robust but still partly bull-beta; H4 and the AI need more data before any capital. | `research/validation_runner.py` |
| **EXIT MANAGEMENT decides profit, not entries.** Same entries, total return swings −$60 → +$519 by exit logic alone. **Stop-loss is mandatory**; **tight trailing turns the edge NEGATIVE** (chokes winners); **momentum-ride** (hold while close>EMA20, hard ATR stop) gives the best risk-adjusted result — Sharpe 3.3–4.1, ~40% less drawdown, big winners (up to 8.7R). Scale-out lifts win-rate to 64%. | `research/exit_probe.py` |
| **Canonical playbook end-to-end.** Entry + ATR stop + momentum-ride + scale-out: **H4 robust** (IS Sharpe 1.4 / OOS 2.7, positive both); H1 strong OOS (5.5) but negative IS (bull-dependent — needs AI/fundamentals/more regimes). | `research/playbook_backtest.py` |
| **First AI win: learned (HMM) regime gate beats the ADX rule on H1.** Causal Gaussian-HMM (full-cov, multi-restart) on ADX/vol/move-size → more selective gate that excludes volatile chop: H1 OOS drawdown **156→49 (~3× lower)**, Sharpe **3.4→8.2**. On H4 too restrictive (1 trade) — needs more data. Confirms: AI helps where data is sufficient. | `research/hmm_regime_probe.py` |
| **HMM gate makes the H1 playbook ROBUST.** End-to-end, swapping ADX→HMM in the canonical playbook flipped H1 in-sample Sharpe **−1.34 → +0.87** (now positive IS *and* OOS 9.86, drawdown halved) — closing the "bull-dependent" gap. H4 keeps ADX (HMM too restrictive on small sample). Rule: **HMM where data is plentiful, ADX otherwise.** | `research/playbook_backtest.py` |

**Bottom line:** there is a modest, honest, cost-robust edge — trend-continuation,
including SMC's Structure + FVG. It is *not yet* a proven all-weather strategy. The
mean-reversion SMC pillars (sweeps, discount) only help in ranging regimes, so a
**regime gate** must turn pillars on/off. Confirming any of this needs (1) M5/M15 +
BTC data and (2) a sample with non-bull regimes.

---

## Intended workflow (your design)

```
ANALYSIS (bias / direction)        EXECUTION (precise entry)
  Weekly  -> primary trend           15-min  -> entry timing
  Daily   -> trend + S/R             5-min   -> trigger / stop placement
  4-hour  -> setup
  1-hour  -> refinement
        + technical indicators (EMA, RSI, ATR, structure)
```
Higher timeframes decide *whether* and *which way* to trade; lower timeframes decide
*exactly when*. This cuts drawdown and tightens entries — exactly where our edge lives.

---

## Project structure

```
nexaquant/
├── README.md              <- this file (source of truth)
├── config_loader.py       <- DYNAMIC settings: data-derived cost/pip for ANY instrument
├── run_nexaquant.py       <- END-TO-END pipeline: data->regime->entry->AI size->exit->gate->GO/NO-GO
├── config/base_config.yaml<- pipeline/instruments/account/regime/sizing (no plaintext secrets)
├── data/
│   ├── prepare_data.py    <- resamples W1; reports missing M5/M15
│   ├── pull_mt5.py        <- pull M5/M15/H1/H4/D1 for XAUUSD+BTCUSD (Windows+MT5)
│   ├── pull_open_data.py  <- NO-KEY deep crypto history (Binance data dumps)
│   ├── pull_stooq.py      <- NO-KEY daily OHLCV + macro (Stooq: gold/FX/indices)
│   ├── fundamentals.py    <- FREE macro feed (yfinance/FRED/COT) -> macro-bias features
│   ├── sentiment.py       <- FinBERT news sentiment -> f_news_sentiment feature
│   ├── econ_calendar.py   <- economic calendar (NFP/CPI) -> EVENTS.parquet for the guard
│   └── raw/               <- *_{W1,D1,H4,H1}.parquet (+ FUNDAMENTALS/SENTIMENT/EVENTS)
├── research/              <- honest backtests / edge discovery
│   ├── edge_probe.py · mtf_edge_probe.py · smc_probe.py · regime_gated_probe.py
│   ├── meta_label_probe.py · exit_probe.py · playbook_backtest.py · hmm_regime_probe.py
│   ├── long_short_probe.py   <- long vs short vs both (shorts bleed on bull gold)
│   ├── trade_report.py       <- WHICH chart + plan + blotter + PIPS + $ account view
│   └── validation_runner.py  <- rigor gate: walk-forward + DSR + CPCV verdict
├── strategy/
│   ├── smc.py · regime.py (ADX + causal HMM) · risk.py (sizing + proba_to_size)
│   ├── meta_label.py      <- AI: triple-barrier + HistGBM/ensemble + calibration + MTF/fundamental feats
│   ├── event_guard.py     <- stay away from volatility: vol-spike + news blackout
│   ├── risk_manager.py    <- portfolio kill switch: daily-loss, drawdown, correlation
│   └── playbook.py        <- CANONICAL strategy: symmetric entry + ATR stop + momentum-ride + scale-out
├── backtest/
│   ├── engine.py · trade_sim.py (SL/trail/momentum/scale-out, $/pips, AI sizing)
│   └── validator.py       <- walk-forward + Purged CV + Deflated Sharpe + PBO (overfitting)
├── execution/
│   └── live_trader.py     <- MT5 bot: dry-run / paper / live; autonomous SL/trail/scale-out + kill switch
└── docs/                  <- source PDFs + NexaQuant_Architecture.pdf (11pp) + STRATEGY.md
    └── build_architecture.py  <- regenerates the colourful architecture + research-evidence deck
```

---

## What the research says (deep-research, adversarially verified — 18 claims confirmed, 7 killed)

The literature **validates the architecture** and adds cautions. Full cited table on
page 10 of `docs/NexaQuant_Architecture.pdf`. Headlines:
- **Stop-losses are regime-conditional** — add value under momentum, hurt under
  mean-reversion (Kaminski & Lo 2014). → *Exactly why we only stop inside the TREND regime.*
- **Fixed take-profit didn't beat letting it run** on FX/metals/crypto (Vezeris 2018). →
  *Validates momentum-ride > 2R target.*
- **Naive single-factor volatility-targeting fails OOS net of costs** (Cederburg 2020;
  Barroso & Detzel 2021). → *Matches our cost-churn finding; size cost-aware / multifactor.*
- **Spurious backtests need trial-adjusted metrics** — Deflated/Probabilistic Sharpe +
  purged CV (Bailey & López de Prado; Harvey & Liu). → *Exactly our `backtest/validator.py`.*
- **Deep RL is overfit-prone**, needs explicit overfitting tests (Gort 2022). → *Defer RL behind the gate.*
- **SMC (FVG/OB/ICT): zero verified academic edge** → *treat as folklore; our edge is the trend/momentum overlap.*
- **Scope caveat:** most strong evidence is *monthly US equities*, not intraday gold/BTC —
  mechanisms transfer but we must **re-validate on our instruments** (the rigor gate does this).
- **Avoid (refuted):** specific ATR(12,6,2) params · Kelly-VIX hybrid sizing · "vol-scaling doubles t-stat" · CVaR-variant superiority.

## Multi-pair / multi-timeframe / multi-year results (real data, 2021-2026)

Pulled 5 instruments free from Binance (BTC/ETH/BNB/SOL) + gold, ran the full pipeline
across timeframes and an anchored yearly walk-forward (train→predict each year):

- **Best timeframe = H4 (then H1), NOT lower.** Lower TFs took more trades but *lost* to
  noise + cost (ETH H1: 55 trades, −1%; ETH H4: 15 trades, +21%). `research/timeframe_compare.py`
- **No long-only pair is all-weather** — it's a trend-follower; almost everything lost in
  the **2022 crypto bear**. `research/walk_forward_yearly.py`
- **Regime-aware LONG+SHORT fixes it:** BTC **H4** long+short is profitable in **all 5 years
  incl. the 2022 bear** (+20.5% where long-only was +0.8%). `research/long_short_walkforward.py`
- **Confidence-scaled sizing helps:** sizing up in strong trends (ADX) took BTC H4 from
  +50% → **+117%** and *raised* Sharpe 2.0 → 2.4 (drawdown 19%→30%). Real edge, not just
  leverage — but only when Sharpe rises. `research/confidence_sizing_test.py`

**Recommended configuration (evidence-based):** trade **BTC or XAU on H4**, **regime-aware
long+short**, momentum-ride exit + scale-out, **confidence-scaled size** (by trend strength),
hard ATR stop. Still requires the validation gate + 30-day paper before live.

**DEEP multi-decade walk-forward (`research/deep_walkforward.py`, free yfinance daily):**
The honest reality check across ~2 decades of regimes (2008/2013/2015/2020/2022...):

| Instrument | Span | Years profitable | avg/yr | verdict |
|---|---|---|---|---|
| **BTC** | 2014–26 | **7/11 (64%)** | +78%* | best fit (trending crypto) |
| Gold | 2000–26 | 13/25 (52%) | +0.7% | marginal on *daily* |
| S&P 500 | 1927–26 | 48/98 (49%) | +1.0% | ~coin-flip |
| EURUSD | 2003–26 | 6/22 (27%) | −0.6% | **unsuitable** |
| WTI oil | 2000–26 | 8/25 (32%) | −4.4% | **unsuitable** |

*BTC avg skewed by 2017 (+704%); median +10%, worst −42%.

**The honest truth this exposes:** on DAILY across all history the trend edge is weak / break-even
for most assets — the strong recent numbers were **H4 in the 2023–26 trending regime**, not a
universal edge. The strategy is a **trend-follower whose niche is trending assets (BTC, gold) in
trending regimes on H4.** FX, oil, equities daily → no edge. This *confirms* focusing on BTC+gold,
and tempers expectations: it is a regime-dependent edge, not a money machine. (Also: a single HMM
fit does not generalise across decades → use the stateless ADX gate, or rolling-refit HMM, for
long-horizon work.)

**Final rigor gate (both pairs, `research/final_validation.py`):**
- **BTC H4 is the lead config** — walk-forward **5/5 years profitable**, **PBO 0.22 (low overfit)**,
  all-weather incl. 2022 bear. Earned a paper-trading trial.
- **BTC H1 is overfit (PBO 0.87) — dropped.** H4 is the timeframe.
- **XAU** needs deeper history (only ~1 walk-forward year) before its gate is trustworthy.
- Deflated Sharpe is below 0.9 on the *raw always-in signal* — but the edge lives in the
  EXIT MANAGEMENT (stops/momentum-ride/scale-out), which that measure doesn't capture; the
  per-year trade results are the relevant evidence. Next real test = **30-day paper trading**.

## The model layer (ML / RL / DL) — staged, because data is the bottleneck

The feature matrix in `strategy/meta_label.py` is the substrate every model plugs into.
The honest sequence (each step only once the prior one has fuel):
1. **ML meta-labeling (built)** — HistGBM P(win). Today AUC≈0.51 (too few samples,
   technical-only). Strengthens automatically as features/data grow.
2. **ML ensemble** — average/stack HistGBM + RandomForest + Logistic for variance
   reduction. One-line swap of the classifier; do once data supports it.
3. **RL sizing/exits** — SAC/PPO to size & time the meta-labeled signal (not to invent
   signals). Needs ~10k+ decisions across regimes -> unlocked by M5/M15 + BTC.
4. **DL features** — CNN/transformer representations fed AS FEATURES into the ensemble.
5. **Multi-agent ensemble** — specialised trend / mean-reversion / risk agents combined
   by a regime-weighted meta-learner (the original MARL vision).
> Rule: model complexity may only increase together with data breadth AND validation
> rigor (purged CV + paper trading). More models on thin data = more ways to overfit.

## Roadmap (the only safe path to live money)

1. **[blocked on data] Pull M5/M15 + BTCUSD from MT5** (`data/pull_mt5.py`) so we can
   test the real execution TF, get a second instrument, and 10-100x the training set.
2. **Pull fundamentals** (`data/fundamentals.py`, free) — macro-bias features that make
   the model layer predictive (top of the top-down funnel + AI feature).
3. **Get a multi-regime sample** — history incl. bear/range gold so edges + regime gate
   prove out beyond the 2023-25 bull.
4. **Regime gate + ATR sizing (built)** — already lifts H1 OOS Sharpe & cuts drawdown.
5. **Walk-forward + purged CV in `backtest/`** — hundreds of trades, regime-stratified.
6. **30-day paper trading** — confirm backtest ≈ live before any capital.
7. **Tiny live capital, ramp 25% → 50% → 100%.** Then, and only then, generalise to
   FX / other commodities.

## Quick start
```bash
pip install -r requirements.txt
python data/prepare_data.py        # build W1, report what's missing
python research/edge_probe.py      # single-timeframe edge + benchmark
python research/mtf_edge_probe.py  # top-down multi-timeframe probe
```

## Security note
The old config committed a **live broker password in plaintext**. It has been
replaced with `${MT5_PASSWORD}` (read from environment). **Rotate that Exness
password now** — assume it is compromised.
```
