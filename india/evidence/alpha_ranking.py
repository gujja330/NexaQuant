# india/evidence/alpha_ranking.py
"""
EXPERIMENT (scientific roadmap, step 1-3): is a simple-factor ALPHA RANKING worth building?

AEGIS today = portfolio CONSTRUCTION (how to allocate). Missing = a RANKING engine (which stocks
deserve consideration). Before any ML, test a SIMPLE-FACTOR baseline ranking the user's way:

  Step 1 — Target: cross-sectional forward 3-month return (rank), and "finish in top quintile".
  Step 2 — Baseline alpha score = blend of momentum + low-vol + sector-strength (all causal, ranks).
  Step 3 — Compare a top-20 ALPHA portfolio against: RANDOM-20 (the null), LOW-VOL-20 (what we
           already do), and Nifty. ALL regime-OFF + equal-weight, to isolate SELECTION skill.

Verdict logic: alpha-ranking is only worth pursuing (and only THEN with ML) if it beats RANDOM
AND beats plain LOW-VOL out-of-sample. Otherwise it adds nothing over what AEGIS already has.

Run: python india/evidence/alpha_ranking.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from scipy.stats import spearmanr
from india.feature_engine import load_panels
from india.data_nse import NIFTY200
from india.sectors import sector_of

REBAL, LOOK, TOPN = 63, 120, 20
closes = rets = idx = None


def _load():
    global closes, rets, idx
    c, _, _, _, idx, _, _ = load_panels()
    closes = c[[x for x in c.columns if x in set(NIFTY200)]]
    rets = closes.pct_change()


def alpha_score(dt, cols):
    px = closes.loc[:dt]
    if len(px) < LOOK + 1:
        return None
    mom = (px.iloc[-1] / px.iloc[-127] - 1).reindex(cols)              # ~6m momentum
    inv_vol = (1.0 / rets.loc[:dt].tail(LOOK).std()).reindex(cols)     # low-vol
    sec = pd.Series({x: sector_of(x) for x in cols})
    sec_mom = sec.map(mom.groupby(sec).mean())                         # sector strength
    score = mom.rank() + inv_vol.rank() + sec_mom.rank()
    return score.dropna()


def run(select_fn, seed=0, cost=21):
    rng = np.random.default_rng(seed)
    wrows = {}
    for dt in closes.index[::REBAL]:
        hist = rets.loc[:dt].tail(LOOK).dropna(axis=1, how="any")
        cols = list(hist.columns)
        if len(cols) < 25:
            continue
        sel = select_fn(dt, cols, rng)
        if len(sel) >= 3:
            w = pd.Series(1.0 / len(sel), index=sel)
            wrows[dt] = w
    W = pd.DataFrame(wrows).T.reindex(columns=closes.columns).fillna(0.0)
    W = W.reindex(closes.index).ffill().fillna(0.0)
    gross = (W.shift(1) * rets.reindex(columns=W.columns)).sum(axis=1)
    net = gross - (W - W.shift(1)).abs().sum(axis=1) * (cost / 1e4)
    return net.dropna()


def st(net):
    e = (1 + net).cumprod(); yrs = len(net) / 252
    return (100 * (e.iloc[-1] ** (1 / yrs) - 1),
            net.mean() / (net.std() + 1e-12) * np.sqrt(252),
            100 * ((e.cummax() - e) / e.cummax()).max())


def main():
    _load()
    def alpha_sel(dt, cols, rng):
        sc = alpha_score(dt, cols)
        return [] if sc is None or sc.empty else list(sc.sort_values(ascending=False).head(TOPN).index)
    lowvol_sel = lambda dt, cols, rng: list((1.0 / rets.loc[:dt].tail(LOOK).std().reindex(cols)).dropna().sort_values(ascending=False).head(TOPN).index)
    rand_sel = lambda dt, cols, rng: list(rng.choice(cols, size=min(TOPN, len(cols)), replace=False))

    print("=" * 72)
    print("  EXPERIMENT — does a SIMPLE-FACTOR alpha ranking beat random / low-vol?")
    print("  (top-20, equal-weight, regime OFF, net 21bps — SELECTION skill only)")
    print("=" * 72)

    alpha = run(alpha_sel); lowvol = run(lowvol_sel)
    rands = [run(rand_sel, seed=s) for s in range(6)]
    rand = pd.concat(rands, axis=1).mean(axis=1)                       # avg random portfolio
    nif = idx.pct_change().reindex(alpha.index).fillna(0.0)

    print(f"\n  {'method':<22}{'CAGR':>8}{'Sharpe':>9}{'maxDD':>8}")
    for nm, s in [("ALPHA rank (mom+lv+sec)", st(alpha)), ("LOW-VOL rank (current)", st(lowvol)),
                  ("RANDOM-20 (null, avg)", st(rand)), ("Nifty-50", st(nif))]:
        print(f"  {nm:<22}{s[0]:>7.1f}%{s[1]:>9.2f}{s[2]:>7.1f}%")

    # Information Coefficient: does alpha score rank forward 3m returns? (full + OOS back-half)
    dts = list(closes.index[::REBAL]); ics = []
    for dt in dts:
        i = closes.index.get_loc(dt)
        if i + REBAL >= len(closes):
            continue
        cols = list(rets.loc[:dt].tail(LOOK).dropna(axis=1, how="any").columns)
        sc = alpha_score(dt, cols)
        if sc is None or len(sc) < 25:
            continue
        fwd = (closes.iloc[i + REBAL] / closes.iloc[i] - 1).reindex(sc.index)
        ok = fwd.notna()
        if ok.sum() > 20:
            ics.append((dt, spearmanr(sc[ok], fwd[ok]).correlation))
    ic_all = np.nanmean([v for _, v in ics])
    half = ics[len(ics) // 2:]
    ic_oos = np.nanmean([v for _, v in half])
    print(f"\n  Information Coefficient (alpha score vs forward 3m return rank):")
    print(f"     full {ic_all:+.3f}   back-half/OOS {ic_oos:+.3f}   (|IC|<0.03 ~ no skill; >0.05 useful)")

    print("\n  VERDICT:")
    a, l, r = st(alpha)[1], st(lowvol)[1], st(rand)[1]
    beats_rand = a > r + 0.1
    beats_lv = a > l + 0.1
    print(f"     beats RANDOM?  {'YES' if beats_rand else 'NO'}  (alpha {a:.2f} vs random {r:.2f})")
    print(f"     beats LOW-VOL? {'YES' if beats_lv else 'NO'}  (alpha {a:.2f} vs low-vol {l:.2f})")
    if beats_rand and beats_lv:
        print("     -> ranking signal EXISTS over what we have -> THEN try ML (LightGBM/CatBoost), gated.")
    else:
        print("     -> simple alpha ranking does NOT beat what AEGIS already does. Do NOT add ML on")
        print("        these factors/targets; the missing edge is DATA (PIT fundamentals/news/flows).")


if __name__ == "__main__":
    main()
