# AEGIS — Indian-equity risk-allocation system

> AEGIS is **not** a stock-picker. It's a **risk-allocation & regime-management** system.
> (Returns are unpredictable; risk is. See [docs/AEGIS_V2_ARCHITECTURE.md](../docs/AEGIS_V2_ARCHITECTURE.md).)

## Clean structure

```
india/
  config.py            ← ONE place to tune everything (dynamic CONFIG)
  ── DATA ──
  broker_angelone.py   Angel One SmartAPI (clean OHLCV pull, incremental)
  data_nse.py          universe (NIFTY100 / NIFTY200) + yfinance pull
  fundamentals_nse.py  fundamentals snapshot (yfinance)
  news_sentiment.py    FinBERT + Google News RSS (live, forward sentiment)
  ── FEATURES / SIGNALS ──
  feature_engine.py    ~30 technical+fundamental+macro features -> panel
  sectors.py           Nifty-200 sector map
  regime_hmm.py        breadth engine + (rejected) HMM regime (Layer 1)
  global_risk.py       Global Risk Engine — S&P/US-VIX/DXY/oil/gold (Layer 1, Tier-1) ⭐
  equity_engine.py     cost model + helpers
  labels.py, dataset.py   ML training data (used by research/)
  ── STRATEGY ──
  arjuna_v2.py         risk construction (inv_vol/min_var/HRP) + regime + global  ← the strategy
  moonshot.py          OPTIONAL satellite (quality-growth basket + barbell; doesn't beat Core)
  arjuna_strategy.py   v1 quality-basket helpers (screen, reject) still used by runner/news
  validation.py        Deflated Sharpe Ratio + purged walk-forward (rigor gate)
  ── EXECUTION ──
  run_arjuna.py        build the live (paper) portfolio from CONFIG
  daily_run.py         daily orchestrator (news -> portfolio -> paper log)
  research/            validation + analysis experiments (the evidence trail; not production)
```

## Run it
```bash
python india/run_arjuna.py --capital 100000            # current risk-weighted portfolio (paper)
python india/arjuna_v2.py                              # backtest the construction methods
python india/validation.py                             # Deflated-Sharpe gate
python india/research/multibagger_analysis.py          # why we don't chase doublers
```

## What's validated
- INV_VOL + simple regime: Sharpe **1.64**, maxDD **14.3%** (vs EW 1.11, Nifty 0.80) — **Deflated Sharpe 0.967 (ROBUST)**.
- AI return-prediction (13 model families): all AUC ≈ 0.50 → dropped. Risk prediction works (vol AUC 0.76).

## Deps
Core: `pip install -r india/requirements.txt`. Research extras (torch/transformers/sb3) are heavy &
optional — only needed to re-run the AI validation in `research/`.
