# india/equity_engine.py
"""
Multi-factor INDIAN EQUITY engine (config-driven) — the core of the India stock bot.

Combines, all cross-sectionally on a liquid NSE universe, net of realistic Indian costs:
  * FACTORS (price-based, backtestable on free data):
      - momentum   : trailing return (skip recent) — ride relative strength
      - low_vol    : inverse realized volatility   — prefer steadier names
      - trend      : distance above the 200-day MA  — quality of uptrend
    composite = weighted sum of cross-sectional z-scores -> rank -> hold top-N.
  * REGIME FILTER: hold only when the market (Nifty) is above its 200-DMA, else CASH
    (this is the documented defense against momentum CRASHES, e.g. 2026).
  * VOL TARGETING: scale book exposure toward a target annual vol (calmer equity curve).
  * REBALANCE weekly (default), equal-weight the selected names.

Fundamentals (P/E, ROE, F-score) need point-in-time data we don't have for backtest yet,
so they enter LIVE as a screen later (see STRATEGY_RESEARCH_INDIA.md). Everything here is a
plain returns engine so the combination tester can sweep configs cleanly.
"""
import sys, glob, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RAW = ROOT / "data" / "raw" / "india"
COST_BPS = 21.0                      # India round-trip ~brokerage+STT+GST+SEBI+slippage
INDEX = "NSEI"                       # Nifty 50 = market-regime proxy


def load():
    data = {}
    for f in sorted(glob.glob(str(RAW / "*_D1.parquet"))):
        s = os.path.basename(f).replace("_D1.parquet", "")
        data[s] = pd.read_parquet(f).sort_index()
    # exclude indices + macro series (SP500/VIX saved here for the guard) from the STOCK universe
    NON_STOCKS = ("NSEI", "NSEBANK", "SP500", "INDIAVIX", "fundamentals")
    stocks = [s for s in data if s not in NON_STOCKS]
    closes = pd.DataFrame({s: data[s]["close"] for s in stocks}).dropna(how="all")
    index_close = data[INDEX]["close"].reindex(closes.index).ffill()
    return closes.dropna(), index_close


def _zscore_rows(df):
    return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)


def composite_score(closes, weights, mom_lb=120, mom_skip=10, vol_win=60):
    rets = closes.pct_change()
    parts, w = [], []
    if weights.get("momentum", 0):
        mom = closes.shift(mom_skip) / closes.shift(mom_lb) - 1.0
        parts.append(_zscore_rows(mom) * weights["momentum"]); w.append(weights["momentum"])
    if weights.get("low_vol", 0):
        lv = -rets.rolling(vol_win).std()                         # higher score = lower vol
        parts.append(_zscore_rows(lv) * weights["low_vol"]); w.append(weights["low_vol"])
    if weights.get("trend", 0):
        tr = closes / closes.rolling(200).mean() - 1.0
        parts.append(_zscore_rows(tr) * weights["trend"]); w.append(weights["trend"])
    score = sum(parts)
    return score


def backtest(cfg):
    """cfg keys: weights{momentum,low_vol,trend}, topn, rebal, regime(bool), regime_ma,
    vol_target(0=off else annual target), mom_lb, mom_skip, vol_win. Returns daily net rets."""
    closes, index_close = load()
    rets = closes.pct_change().fillna(0.0)
    score = composite_score(closes, cfg["weights"], cfg.get("mom_lb", 120),
                            cfg.get("mom_skip", 10), cfg.get("vol_win", 60))
    topn, rebal = cfg.get("topn", 5), cfg.get("rebal", 5)
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    for dt, row in score.iterrows():
        r = row.dropna()
        if len(r) < topn:
            continue
        win = r.sort_values(ascending=False).index[:topn]
        w.loc[dt, win] = 1.0 / topn
    mask = np.zeros(len(closes), dtype=bool); mask[::rebal] = True
    w[~mask] = np.nan; w = w.ffill().fillna(0.0)

    # regime filter: flat when Nifty below its MA
    if cfg.get("regime", False):
        ma = index_close.rolling(cfg.get("regime_ma", 200)).mean()
        risk_on = (index_close > ma).astype(float)
        w = w.mul(risk_on, axis=0)

    gross = (w.shift(1) * rets).sum(axis=1)
    turnover = (w - w.shift(1)).abs().sum(axis=1)
    net = gross - turnover * (COST_BPS / 1e4)

    # vol targeting: scale exposure toward a target annual vol (causal)
    if cfg.get("vol_target", 0):
        realized = net.rolling(20).std() * np.sqrt(252)
        lev = (cfg["vol_target"] / realized.shift(1)).clip(0.0, 2.0).fillna(1.0)
        net = net * lev
    return net.rename("india")


def stats(net):
    eq = (1 + net).cumprod(); peak = eq.cummax()
    rows = []
    for y, g in net.groupby(net.index.year):
        if len(g) < 30:
            continue
        e = (1 + g).cumprod()
        rows.append((y, 100 * (e.iloc[-1] - 1)))
    pos = sum(1 for _, r in rows if r > 0)
    return dict(total=100 * (eq.iloc[-1] - 1), dd=100 * ((peak - eq) / peak).max(),
                sharpe=net.mean() / (net.std() + 1e-12) * np.sqrt(252),
                pos_years=pos, years=len(rows), yearly=rows,
                worst_year=min((r for _, r in rows), default=0.0))
