# india/compounder.py
"""
ARJUNA — LONG-HOLD COMPOUNDER (the finalized approach).

ONE strategy, ONE frequency. No weekly/monthly confusion:
  * CHECK once a QUARTER (every ~63 trading days).
  * BUY the top-20 stocks by a quality+trend score, equal weight.
  * HOLD them. A held name is only SOLD when it falls out of the top-30 (a buffer) -> low churn,
    low cost, so we ride a winner (like holding SBI from 500 -> 1000) instead of churning it.

Score = z(12m momentum) + z(low-volatility) + z(distance above 200-DMA)  [+ z(quality) optionally].
  - "honest"  : price-only (momentum + low-vol + trend) -> fully causal, no look-ahead.
  - "+quality": adds the snapshot fundamental quality score -> OPTIMISTIC (look-ahead), flagged.

Benchmarked vs NIFTY buy-and-hold and equal-weight buy-and-hold, net of ~21bps round-trip cost.

Run: python india/compounder.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.equity_engine import COST_BPS
from india.feature_engine import load_panels


def load():
    """Full-history loader (keeps the whole date range; per-stock NaN before listing is fine).
    Avoids equity_engine.load()'s dropna(how='any') which truncates to the latest IPO (JIOFIN 2023)."""
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    return closes, idx

RAW = ROOT / "data" / "raw" / "india"
REBAL = 63          # quarterly check
TOPN = 20           # hold 20 names
BUFFER = 30         # keep a held name until it drops out of the top-30 (low churn)


def _z(df):
    return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)


def quality_z(columns):
    """Static cross-sectional quality z-score from the snapshot fundamentals (optimistic)."""
    fp = RAW / "fundamentals.parquet"
    if not fp.exists():
        return None
    f = pd.read_parquet(fp)
    sign = {"returnOnEquity": +1, "profitMargins": +1, "earningsGrowth": +1,
            "debtToEquity": -1, "trailingPE": -1, "priceToBook": -1}
    z = pd.DataFrame(index=f.index)
    for m, s in sign.items():
        if m in f.columns:
            col = pd.to_numeric(f[m], errors="coerce")
            z[m] = s * (col - col.mean()) / (col.std() + 1e-9)
    q = z.mean(axis=1)
    return q.reindex(columns)


def score_panel(closes, use_quality):
    rets = closes.pct_change()
    mom12 = closes.shift(21) / closes.shift(252) - 1.0
    lowvol = -rets.rolling(120).std()
    trend = closes / closes.rolling(200).mean() - 1.0
    score = _z(mom12) + _z(lowvol) + _z(trend)
    if use_quality:
        q = quality_z(closes.columns)
        if q is not None:
            score = score.add(q, axis=1)        # static tilt toward quality names
    return score


def backtest(use_quality=False):
    closes, index_close = load()
    rets = closes.pct_change().fillna(0.0)
    score = score_panel(closes, use_quality)
    rebal_idx = set(closes.index[::REBAL])

    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    held = []
    entry_day = {}                       # for holding-duration stats
    spells = []                          # (symbol, days_held)
    for dt in closes.index:
        if dt in rebal_idx:
            row = score.loc[dt].dropna()
            if len(row) >= TOPN:
                ranked = row.sort_values(ascending=False)
                top_buffer = set(ranked.index[:BUFFER])
                # keep held names still inside the buffer; refill up to TOPN from the top
                kept = [s for s in held if s in top_buffer]
                for s in ranked.index:
                    if len(kept) >= TOPN:
                        break
                    if s not in kept:
                        kept.append(s)
                # record exits
                for s in held:
                    if s not in kept:
                        spells.append((s, (dt - entry_day[s]).days)); entry_day.pop(s, None)
                for s in kept:
                    entry_day.setdefault(s, dt)
                held = kept
        if held:
            w.loc[dt, held] = 1.0 / len(held)
    w = w.fillna(0.0)
    gross = (w.shift(1) * rets).sum(axis=1)
    turnover = (w - w.shift(1)).abs().sum(axis=1)
    net = gross - turnover * (COST_BPS / 1e4)

    # benchmarks (buy-and-hold, net of one entry cost)
    nifty = index_close.pct_change().fillna(0.0)
    eqw = rets.mean(axis=1)
    avg_hold_days = np.mean([d for _, d in spells]) if spells else np.nan
    turns_per_yr = turnover.sum() / (len(closes) / 252)
    return net, nifty, eqw, dict(avg_hold_days=avg_hold_days, turns_per_yr=turns_per_yr,
                                 n_spells=len(spells), final_held=held, score=score)


def yearly_table(net, nifty, label):
    eq = (1 + net).cumprod(); peak = eq.cummax()
    print(f"\n  {label}")
    print(f"  {'year':<6}{'strat%':>9}{'nifty%':>9}{'edge':>8}{'start_Rs':>13}{'end_Rs':>13}{'gain_Rs':>13}")
    comp = 100000.0
    for y, g in net.groupby(net.index.year):
        if len(g) < 20:
            continue
        sr = (1 + g).prod() - 1
        ny = (1 + nifty.reindex(g.index).fillna(0)).prod() - 1
        start = comp; comp *= (1 + sr); gl = comp - start
        print(f"  {y:<6}{100*sr:>9.1f}{100*ny:>9.1f}{100*(sr-ny):>+8.1f}{start:>13,.0f}{comp:>13,.0f}{gl:>+13,.0f}")
    sh = net.mean() / (net.std() + 1e-12) * np.sqrt(252)
    print(f"  {'-'*64}")
    print(f"  TOTAL {100*(eq.iloc[-1]-1):+.0f}%   Sharpe {sh:.2f}   maxDD {100*((peak-eq)/peak).max():.1f}%"
          f"   Rs1,00,000 -> Rs{(1+net).cumprod().iloc[-1]*1e5:,.0f}")
    return eq.iloc[-1] - 1, sh, ((peak - eq) / peak).max()


if __name__ == "__main__":
    print("=" * 78)
    print("  ARJUNA LONG-HOLD COMPOUNDER  (quarterly check, hold top-20, sell only if out of top-30)")
    print("=" * 78)
    results = {}
    for use_q in (False, True):
        net, nifty, eqw, info = backtest(use_quality=use_q)
        label = ("+QUALITY (optimistic, snapshot fundamentals)" if use_q
                 else "HONEST (price-only: momentum + low-vol + trend, no look-ahead)")
        tot, sh, dd = yearly_table(net, nifty, label)
        results[use_q] = (tot, sh, dd, info)
        print(f"  avg holding duration: {info['avg_hold_days']:.0f} days "
              f"(~{info['avg_hold_days']/30:.1f} months)   turnover ~{info['turns_per_yr']:.1f}x/yr")

    # Nifty benchmark line
    eqn = (1 + nifty).cumprod(); shn = nifty.mean()/(nifty.std()+1e-12)*np.sqrt(252)
    peakn = eqn.cummax()
    print("\n  " + "=" * 60)
    print(f"  BENCHMARK  NIFTY buy-and-hold: {100*(eqn.iloc[-1]-1):+.0f}%   Sharpe {shn:.2f}"
          f"   maxDD {100*((peakn-eqn)/peakn).max():.1f}%   Rs1,00,000 -> Rs{eqn.iloc[-1]*1e5:,.0f}")
    print("  (the bar to beat on return AND Sharpe AND drawdown, net of cost)")

    # current picks to actually hold
    info = results[True][3]
    print("\n  CURRENT TOP-20 TO HOLD (by +quality score, as of latest data):")
    last = info["score"].index.max()
    picks = info["score"].loc[last].dropna().sort_values(ascending=False).head(TOPN)
    print("   " + ", ".join(picks.index))
