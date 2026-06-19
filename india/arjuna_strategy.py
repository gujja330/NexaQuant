# india/arjuna_strategy.py
"""
ARJUNA — FINAL STRATEGY (evidence-based).

After testing rotation + AI stock-selection (all LOST to owning the basket), the validated core is:
  OWN A DIVERSIFIED EQUAL-WEIGHT BASKET AND HOLD IT, rebalanced quarterly.

This module builds and compares, net of ~21bps, over the full clean window:
  1. EW-100        : equal-weight all 100 (the ideal basket; many orders).
  2. EW-30 liquid  : equal-weight the 30 most-liquid names (practical, tradeable order count).
  3. EW-30 quality : equal-weight 30 by a robust quality+low-vol+trend screen.
  4. + VIX de-risk : overlay that cuts exposure in high-fear regimes (kept only if it helps).
All vs NIFTY-50 and the equal-weight-100 benchmark.

HONEST CAVEAT: the universe is today's Nifty-100 members -> survivorship bias inflates the past;
real forward returns will be lower. The RELATIVE ranking of variants is still informative.

Run: python india/arjuna_strategy.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.feature_engine import load_panels
from india.equity_engine import COST_BPS

REBAL = 63          # quarterly
K = 30              # practical basket size
BUFFER = 40         # keep a held name until it leaves the top-40 (low churn)


def _z(df):
    return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)


def vix_high():
    _, _, _, _, _, vix, _ = load_panels()
    if vix is None:
        return None
    return vix > vix.rolling(120, min_periods=30).quantile(0.80)


def screen(closes, vols, kind):
    """Per-date score used to choose the basket. 'liquid' = turnover; 'quality' = trend+lowvol+mom."""
    if kind == "liquid":
        return np.log((closes * vols).rolling(20).mean() + 1)
    rets = closes.pct_change()
    mom = closes.shift(21) / closes.shift(252) - 1
    lowvol = -rets.rolling(120).std()
    trend = closes / closes.rolling(200).mean() - 1
    return _z(mom) + _z(lowvol) + _z(trend)


def backtest(kind="all", k=K, vix_derisk=False, universe=None):
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    if universe is not None:                          # restrict to a chosen universe (e.g. Nifty-100)
        cols = [c for c in closes.columns if c in set(universe)]
        closes, vols = closes[cols], vols[cols]
    rets = closes.pct_change().fillna(0.0)
    rebal_idx = set(closes.index[::REBAL])
    score = None if kind == "all" else screen(closes, vols, kind)

    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    held = []
    for dt in closes.index:
        if dt in rebal_idx:
            avail = closes.loc[dt].dropna().index
            if kind == "all":
                held = list(avail)
            else:
                row = score.loc[dt].dropna()
                if len(row) >= k:
                    ranked = row.sort_values(ascending=False)
                    buf = set(ranked.index[:max(k, BUFFER)])
                    kept = [s for s in held if s in buf]
                    for s in ranked.index:
                        if len(kept) >= k: break
                        if s not in kept: kept.append(s)
                    held = kept
        if held:
            w.loc[dt, held] = 1.0 / len(held)
    w = w.fillna(0.0)
    gross = (w.shift(1) * rets).sum(axis=1)
    net = gross - (w - w.shift(1)).abs().sum(axis=1) * (COST_BPS / 1e4)
    if vix_derisk and vix is not None:
        hi = (vix > vix.rolling(120, min_periods=30).quantile(0.80)).reindex(net.index).fillna(False)
        net = net * hi.map({True: 0.5, False: 1.0})
    return net, idx, held, score


def stats(net):
    eq = (1 + net).cumprod(); peak = eq.cummax()
    sh = net.mean() / (net.std() + 1e-12) * np.sqrt(252)
    return dict(total=100*(eq.iloc[-1]-1), sharpe=sh, dd=100*((peak-eq)/peak).max(),
                end=eq.iloc[-1]*1e5)


def line(name, net):
    s = stats(net)
    print(f"  {name:<28}{s['total']:>+7.0f}%{s['sharpe']:>8.2f}{s['dd']:>8.1f}%   Rs{s['end']:>11,.0f}")
    return s


if __name__ == "__main__":
    print("=" * 74)
    print("  ARJUNA FINAL — equal-weight basket variants (full window, net of cost)")
    print("=" * 74)
    print(f"  {'variant':<28}{'total':>8}{'Sharpe':>8}{'maxDD':>8}   {'Rs1L ->':>13}")
    ew100, idx, _, _ = backtest("all");           line("EW-100 (own all, hold)", ew100)
    liq, _, _, _ = backtest("liquid", K);         line("EW-30 most liquid", liq)
    qual, _, heldq, scoreq = backtest("quality", K); line("EW-30 quality screen", qual)
    qv, _, _, _ = backtest("quality", K, vix_derisk=True); line("EW-30 quality + VIX de-risk", qv)
    nifty = idx.pct_change().fillna(0.0);         line("NIFTY-50 (benchmark)", nifty)

    print("\n  Verdict: keep the variant with the best Sharpe that is practical to trade.")
    print("\n  CURRENT EW-30 QUALITY BASKET TO HOLD (equal weight ~3.3% each):")
    last = scoreq.index.max()
    picks = scoreq.loc[last].dropna().sort_values(ascending=False).head(K)
    print("   " + ", ".join(picks.index))
