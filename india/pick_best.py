# india/pick_best.py
"""
CONCENTRATED best-stock picker (what you actually asked for): combine ALL signals into one score
and hold the BEST few names, rotating weekly or monthly. No equal-weight-everything.

Composite score (per stock, per day, causal except fundamentals which are a snapshot tilt):
  technical : 3m + 6m + 12m momentum, low-vol, distance above 200-DMA
  fundamental: quality z-score (ROE, margins, debt, PE/PB)  [snapshot -> optimistic, flagged]
  sector    : the stock's sector momentum (ride strong sectors)

Picks top-N (1 / 3 / 5), equal among the few, rebalanced weekly (5d) or monthly (21d), net of
~21bps cost. Compared to Nifty buy-and-hold over the full window. Shows Rs, CAGR, per-year, and
the current best picks. News is NOT included (no feed) — stated honestly.

Run: python india/pick_best.py
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
from india.sectors import SECTORS

RAW = ROOT / "data" / "raw" / "india"
YEARS = 5.47


def _z(df):
    return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)


def quality_z(columns):
    fp = RAW / "fundamentals.parquet"
    if not fp.exists():
        return pd.Series(0.0, index=columns)
    f = pd.read_parquet(fp)
    sign = {"returnOnEquity": +1, "profitMargins": +1, "earningsGrowth": +1,
            "debtToEquity": -1, "trailingPE": -1, "priceToBook": -1}
    z = pd.DataFrame(index=f.index)
    for m, s in sign.items():
        if m in f.columns:
            col = pd.to_numeric(f[m], errors="coerce")
            z[m] = s * (col - col.mean()) / (col.std() + 1e-9)
    return z.mean(axis=1).reindex(columns).fillna(0.0)


def composite(closes, use_fundamentals=True):
    rets = closes.pct_change()
    mom3 = closes.shift(5) / closes.shift(63) - 1
    mom6 = closes.shift(10) / closes.shift(126) - 1
    mom12 = closes.shift(21) / closes.shift(252) - 1
    lowvol = -rets.rolling(120).std()
    trend = closes / closes.rolling(200).mean() - 1
    sect = pd.Series({s: SECTORS.get(s, "Other") for s in closes.columns})
    sector_mom = mom6.T.groupby(sect).transform("mean").T
    score = _z(mom3) + _z(mom6) + _z(mom12) + _z(lowvol) + _z(trend) + _z(sector_mom)
    if use_fundamentals:
        score = score.add(quality_z(closes.columns), axis=1)   # static quality tilt
    return score


def backtest(topn, rebal, use_fundamentals=True):
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    rets = closes.pct_change().fillna(0.0)
    score = composite(closes, use_fundamentals)
    rebal_idx = set(closes.index[::rebal])
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    held = []
    for dt in closes.index:
        if dt in rebal_idx:
            row = score.loc[dt].dropna()
            if len(row) >= topn:
                held = list(row.sort_values(ascending=False).index[:topn])
        if held:
            w.loc[dt, held] = 1.0 / len(held)
    w = w.fillna(0.0)
    gross = (w.shift(1) * rets).sum(axis=1)
    net = gross - (w - w.shift(1)).abs().sum(axis=1) * (COST_BPS / 1e4)
    return net, idx, score


def report(net, idx, label):
    eq = (1 + net).cumprod(); peak = eq.cummax()
    sh = net.mean() / (net.std() + 1e-12) * np.sqrt(252)
    tot = eq.iloc[-1] - 1
    cagr = (1 + tot) ** (1 / YEARS) - 1
    ny = (1 + idx.pct_change().fillna(0)).cumprod()
    print(f"  {label:<26}{100*tot:>+7.0f}%{100*cagr:>7.1f}%{sh:>7.2f}{100*((peak-eq)/peak).max():>7.1f}%   Rs{eq.iloc[-1]*1e5:>10,.0f}")
    return tot, cagr, sh


if __name__ == "__main__":
    print("=" * 78)
    print("  PICK-BEST — concentrated top-N (all signals), weekly vs monthly, net of cost, ~5.5y")
    print("=" * 78)
    print(f"  {'strategy':<26}{'total':>8}{'CAGR':>7}{'Sharpe':>7}{'maxDD':>7}   {'Rs1L ->':>13}")
    for rebal, rname in ((5, "weekly"), (21, "monthly")):
        print(f"  -- hold {rname} --")
        for n in (1, 3, 5):
            net, idx, score = backtest(n, rebal)
            report(net, idx, f"top-{n} ({rname})")
    # Nifty benchmark
    _, idx, score = backtest(5, 21)
    nifty = idx.pct_change().fillna(0.0); neq = (1 + nifty).cumprod()
    nsh = nifty.mean()/(nifty.std()+1e-12)*np.sqrt(252)
    print(f"  {'NIFTY buy & hold':<26}{100*(neq.iloc[-1]-1):>+7.0f}%{100*((neq.iloc[-1])**(1/YEARS)-1):>7.1f}%{nsh:>7.2f}{'':>7}   Rs{neq.iloc[-1]*1e5:>10,.0f}")
    print("\n  CURRENT BEST PICKS (today's top-5 by composite score):")
    last = score.index.max()
    print("   " + ", ".join(score.loc[last].dropna().sort_values(ascending=False).head(5).index))
    print("\n  NOTE: news/global-news NOT in the score (no live feed wired). Fundamentals are a snapshot.")
