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
from india.sectors import SECTORS

RAW = ROOT / "data" / "raw" / "india"
REBAL = 63          # quarterly
K = 30              # practical basket size
BUFFER = 40         # keep a held name until it leaves the top-40 (low churn)


def _z(df):
    return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)


def weak_fundamental_names():
    """Names to REJECT on weak fundamentals (snapshot): high debt + negative margin, or
    bottom-decile composite quality. Checklist sec.4 — eliminate bad before ranking.
    NOTE: snapshot (current) fundamentals -> a live screen, flagged optimistic for backtest."""
    fp = RAW / "fundamentals.parquet"
    if not fp.exists():
        return set()
    f = pd.read_parquet(fp)
    bad = set()
    de = pd.to_numeric(f.get("debtToEquity"), errors="coerce")
    pm = pd.to_numeric(f.get("profitMargins"), errors="coerce")
    bad |= set(f.index[(de > 200) & (pm < 0)])                 # over-levered AND loss-making
    if "quality_score" in f.columns:
        q = pd.to_numeric(f["quality_score"], errors="coerce")
        bad |= set(f.index[q < q.quantile(0.10)])              # bottom-decile quality
    return bad


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


def select_with_sector_cap(ranked, held, k, sector_cap):
    """Pick k names by score with a buffer, capping names per sector (genuine diversification)."""
    buf = set(ranked.index[:max(k, BUFFER)])
    kept = [s for s in held if s in buf]
    sec_count = {}
    for s in kept:
        sec_count[SECTORS.get(s, "Other")] = sec_count.get(SECTORS.get(s, "Other"), 0) + 1
    for s in ranked.index:
        if len(kept) >= k:
            break
        if s in kept:
            continue
        sec = SECTORS.get(s, "Other")
        if sector_cap and sec_count.get(sec, 0) >= sector_cap:
            continue
        kept.append(s); sec_count[sec] = sec_count.get(sec, 0) + 1
    return kept


def regime_overlay(net, idx, vix, use_vix, use_trend):
    """Portfolio-level de-risk (NOT per-stock stops, which whipsaw): scale exposure down when
    India VIX is in its high-fear regime and/or the Nifty is below its 200-DMA."""
    scale = pd.Series(1.0, index=net.index)
    if use_vix and vix is not None:
        hi = (vix > vix.rolling(120, min_periods=30).quantile(0.80)).reindex(net.index).fillna(False)
        scale *= hi.map({True: 0.6, False: 1.0})
    if use_trend:
        below = (idx < idx.rolling(200).mean()).reindex(net.index).fillna(False)
        scale *= below.map({True: 0.6, False: 1.0})
    return net * scale


def backtest(kind="all", k=K, vix_derisk=False, trend_derisk=False, sector_cap=None,
             reject_weak=False, weight="equal", universe=None, rebal=REBAL):
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    if universe is not None:                          # restrict to a chosen universe (e.g. Nifty-100)
        cols = [c for c in closes.columns if c in set(universe)]
        closes, vols = closes[cols], vols[cols]
    rets = closes.pct_change().fillna(0.0)
    rebal_idx = set(closes.index[::rebal])
    score = None if kind == "all" else screen(closes, vols, kind)
    bad = weak_fundamental_names() if reject_weak else set()

    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    held = []
    for dt in closes.index:
        if dt in rebal_idx:
            if kind == "all":
                held = list(closes.loc[dt].dropna().index)
            else:
                row = score.loc[dt].dropna()
                if bad:
                    row = row.drop(labels=[s for s in bad if s in row.index], errors="ignore")
                if len(row) >= k:
                    held = select_with_sector_cap(row.sort_values(ascending=False), held, k, sector_cap)
        if held:
            if weight == "score" and score is not None:
                sc = score.loc[dt, held].dropna().sort_values(ascending=False)
                raw = np.arange(len(sc), 0, -1, dtype=float)   # linear tilt: best name gets most
                for s, wt in zip(sc.index, raw / raw.sum()):
                    w.loc[dt, s] = wt
            else:
                w.loc[dt, held] = 1.0 / len(held)
    w = w.fillna(0.0)
    gross = (w.shift(1) * rets).sum(axis=1)
    net = gross - (w - w.shift(1)).abs().sum(axis=1) * (COST_BPS / 1e4)
    if vix_derisk or trend_derisk:
        net = regime_overlay(net, idx, vix, vix_derisk, trend_derisk)
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
