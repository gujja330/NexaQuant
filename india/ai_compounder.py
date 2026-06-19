# india/ai_compounder.py
"""
ARJUNA — AI-DRIVEN LONG-HOLD COMPOUNDER.

The research (Gu-Kelly-Xiu) says ML helps with rich features. So here the ML model DRIVES the
long-hold: a gradient-boosted model is trained (walk-forward, out-of-sample) on the 31 rich
features to predict next-month forward return; we HOLD the top-20 by ML score with a top-30
BUFFER (low churn -> long holds, like riding SBI up). Net of ~21bps. Benchmarked vs Nifty.

Honest about scale: 100 stocks x 5y x 31 features is ~1000x less data than the studies' 30k x
60y x 900. So expect a SMALL edge at best; the gate is still "beat Nifty net of cost".

Run: python india/ai_compounder.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.dataset import build_dataset, feature_list
from india.feature_engine import load_panels
from india.equity_engine import COST_BPS
from sklearn.ensemble import HistGradientBoostingRegressor

TOPN, BUFFER = 20, 30


def make_model():
    return HistGradientBoostingRegressor(
        max_depth=3, max_iter=300, learning_rate=0.04, l2_regularization=1.0,
        min_samples_leaf=60, early_stopping=True, validation_fraction=0.15, random_state=0)


def nifty_monthly(dates):
    _, _, _, _, idx, _, _ = load_panels()
    idx_m = idx.reindex(pd.DatetimeIndex(dates)).ffill()
    return (idx_m.shift(-1) / idx_m - 1.0)             # 1-month-forward index return, aligned


def ai_backtest(feature_set="full", min_train_frac=0.45, retrain_every=3, embargo=1):
    df = build_dataset("M").dropna(subset=["fwd_ret"])
    feats = feature_list(feature_set)
    dates = np.array(sorted(df.index.get_level_values("date").unique()))
    n0 = int(len(dates) * min_train_frac)
    model, last_fit = None, -10_000
    held, rets, rdates, ic_list = [], [], [], []
    entry, spells = {}, []
    for i in range(n0, len(dates)):
        td = dates[i]
        if model is None or (i - last_fit) >= retrain_every:
            tr = df[df.index.get_level_values("date").isin(dates[: i - embargo])]
            model = make_model().fit(tr[feats].values, tr["fwd_ret"].values)
            last_fit = i
        te = df[df.index.get_level_values("date") == td].copy()
        te["pred"] = model.predict(te[feats].values)
        ic_list.append(te["pred"].corr(te["fwd_ret"], method="spearman"))
        ranked = te.sort_values("pred", ascending=False)
        syms = ranked.index.get_level_values("symbol")
        top_buffer = set(syms[:BUFFER])
        kept = [s for s in held if s in top_buffer]
        for s in syms:
            if len(kept) >= TOPN:
                break
            if s not in kept:
                kept.append(s)
        for s in held:                                  # record exits for holding-duration stat
            if s not in kept:
                spells.append((td - entry.get(s, td)).days); entry.pop(s, None)
        for s in kept:
            entry.setdefault(s, td)
        # realized next-month return of the held basket, net of turnover cost
        fwd = te.reset_index().set_index("symbol")["fwd_ret"]
        realized = fwd.reindex(kept).mean()
        turnover = 2 * len(set(kept) ^ set(held)) / max(len(kept) + len(held), 1) if held else 1.0
        rets.append(realized - turnover * (COST_BPS / 1e4))
        rdates.append(td); held = kept
    s = pd.Series(rets, index=pd.DatetimeIndex(rdates))
    avg_hold = np.mean(spells) if spells else np.nan
    return s, np.nanmean(ic_list), avg_hold, held


def show(strat, nifty_fwd, eqw_fwd, ic, avg_hold, label):
    eq = (1 + strat).cumprod(); peak = eq.cummax()
    nf = nifty_fwd.reindex(strat.index).fillna(0.0)
    ew = eqw_fwd.reindex(strat.index).fillna(0.0)
    print(f"\n  {label}   (IC {ic:+.3f}, avg hold ~{avg_hold/30:.1f} months)")
    print(f"  {'year':<6}{'AI%':>9}{'EW100%':>9}{'edge*':>8}{'nifty%':>9}{'start_Rs':>13}{'end_Rs':>13}{'gain_Rs':>13}")
    comp = 100000.0
    for y, g in strat.groupby(strat.index.year):
        sr = (1 + g).prod() - 1
        ey = (1 + ew.reindex(g.index).fillna(0)).prod() - 1
        ny = (1 + nf.reindex(g.index).fillna(0)).prod() - 1
        start = comp; comp *= (1 + sr)
        print(f"  {y:<6}{100*sr:>9.1f}{100*ey:>9.1f}{100*(sr-ey):>+8.1f}{100*ny:>9.1f}{start:>13,.0f}{comp:>13,.0f}{comp-start:>+13,.0f}")
    sh = strat.mean() / (strat.std() + 1e-12) * np.sqrt(12)
    esh = ew.mean() / (ew.std() + 1e-12) * np.sqrt(12)
    nsh = nf.mean() / (nf.std() + 1e-12) * np.sqrt(12)
    ewfull = (1 + ew).cumprod(); nffull = (1 + nf).cumprod()
    print(f"  {'-'*74}")
    print(f"  AI       {100*(eq.iloc[-1]-1):>+5.0f}%  Sharpe {sh:.2f}  maxDD {100*((peak-eq)/peak).max():.1f}%  -> Rs{eq.iloc[-1]*1e5:,.0f}")
    print(f"  EW-100*  {100*(ewfull.iloc[-1]-1):>+5.0f}%  Sharpe {esh:.2f}   <- FAIR benchmark (equal-weight all 100)  -> Rs{ewfull.iloc[-1]*1e5:,.0f}")
    print(f"  Nifty50  {100*(nffull.iloc[-1]-1):>+5.0f}%  Sharpe {nsh:.2f}   (large-cap only; mid-cap beta flatters AI vs this)")
    print(f"  *edge = AI minus EQUAL-WEIGHT-100 (the honest alpha, strips out mid-cap beta)")


if __name__ == "__main__":
    print("=" * 80)
    print("  ARJUNA AI LONG-HOLD COMPOUNDER  (ML scores -> hold top-20, top-30 buffer, OOS)")
    print("=" * 80)
    dfM = build_dataset("M")
    mdates = sorted(dfM.index.get_level_values("date").unique())
    nf = nifty_monthly(mdates)
    eqw = dfM.groupby(level="date")["fwd_ret"].mean()       # equal-weight Nifty-100 (fair benchmark)
    for fs in ("floor", "full"):
        strat, ic, avg_hold, held = ai_backtest(feature_set=fs)
        label = "TECHNICALS ONLY (honest)" if fs == "floor" else "FUNDAMENTALS + TECHNICALS"
        show(strat, nf, eqw, ic, avg_hold, label)
    print("\n  CURRENT TOP-20 TO HOLD (latest ML scores, fund+tech):")
    print("   " + ", ".join(held))
