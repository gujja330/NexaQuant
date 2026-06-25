# india/dynamic_engine.py
"""
DYNAMIC DISCOVERY ENGINE (AEGIS v3 — Phase 1) — the honest answer to "is Top-N really dynamic?"

The trap: scanning history and announcing "today's optimal = 11 stocks" is NOT intelligence — it is
curve-fitting wearing an intelligence costume. 11 isn't the future; it's the number that *would have*
maximised the PAST. So we do the only honest test:

  WALK-FORWARD. At each rebalance, the engine chooses N using ONLY past cycles (trailing Sharpe over a
  rolling window). It then lives with that choice on the UNSEEN next cycle. We compound that adaptive
  path and ask the one question that matters:

      Did adapting N beat the FIXED default (15) OUT-OF-SAMPLE, after a trial-count penalty (DSR)?

If yes -> we adopt dynamic, and today's number is real evidence. If no -> the engine says so out loud:
"fixed N is robust; dynamic adds no edge today." Dynamic that can't beat fixed OOS is a curve-fit.

This is the TEMPLATE for the whole layered vision (holding, rebalance, sector, fundamentals): every
knob/layer earns "dynamic" status the same way — beat fixed/baseline out-of-sample, or stay honest.

Scope today: PRICE-only, portfolio level (the validated thing). Selection alpha is ~random (RQS 0.5);
this tests whether *sizing the basket* adapts, not whether we can pick winners.

Run: python india/dynamic_engine.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import select_names, weights_for, LOOKBACK
from india.feature_engine import load_panels
from india.data_nse import NIFTY200
from india.validation import deflated_sharpe

CAD = 21                                    # monthly decision cadence (cycle = hold one cadence)
GRID = [3, 5, 8, 11, 15, 20, 25]            # candidate basket sizes the engine is allowed to choose
DEFAULT_N = 15                              # the current FIXED production choice (the thing to beat)
WINDOW = 12                                 # trailing cycles used to score each N (causal)
WARMUP = 12                                 # cycles before the engine is allowed to adapt
SECTOR_CAP = 2


def cycle_table():
    """Causal per-cycle forward returns for every N in GRID. Row = rebalance date, col = N.
    Selection at date i uses only trailing data; return is the next-CAD-day HRP portfolio return."""
    closes, _, _, _, idx, _, _ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change()
    dates, port, nif = [], {n: [] for n in GRID}, []
    for i in range(LOOKBACK, len(closes) - CAD, CAD):
        hist = rets.iloc[i - LOOKBACK:i].dropna(axis=1, how="any")
        if hist.shape[1] < 30:
            continue
        fwd = (closes.iloc[i + CAD] / closes.iloc[i] - 1)
        dates.append(closes.index[i]); nif.append(float(idx.iloc[i + CAD] / idx.iloc[i] - 1))
        for n in GRID:
            sel = select_names(hist, n, sector_cap=SECTOR_CAP)
            if len(sel) < 2:
                port[n].append(np.nan); continue
            w = weights_for("hrp", hist[sel]); w = w / w.sum()
            port[n].append(float((w * fwd.reindex(w.index)).sum()))
    df = pd.DataFrame(port, index=pd.DatetimeIndex(dates))
    return df, pd.Series(nif, index=df.index)


def _sharpe(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return x.mean() / (x.std() + 1e-12) if len(x) >= 4 else -np.inf


def walk_forward(tab):
    """At each cycle t (>=WARMUP) pick N* = best trailing-WINDOW Sharpe using only cycles < t.
    Returns the adaptive realized-return series and the chosen-N path. Fully causal."""
    adaptive, chosen = [], []
    for t in range(len(tab)):
        if t < WARMUP:
            n_star = DEFAULT_N
        else:
            past = tab.iloc[max(0, t - WINDOW):t]
            scores = {n: _sharpe(past[n]) for n in GRID}
            n_star = max(scores, key=scores.get)
        chosen.append(n_star)
        adaptive.append(tab[n_star].iloc[t])
    return pd.Series(adaptive, index=tab.index), pd.Series(chosen, index=tab.index)


def summarize(name, cyc, nif):
    cyc = cyc.dropna()
    eq = (1 + cyc).cumprod()
    yrs = len(cyc) * CAD / 252
    cagr = 100 * (eq.iloc[-1] ** (1 / yrs) - 1)
    dd = 100 * ((eq.cummax() - eq) / eq.cummax()).max()
    shp = _sharpe(cyc) * np.sqrt(252 / CAD)
    win = 100 * (cyc > 0).mean()
    beat = 100 * (cyc.values > nif.reindex(cyc.index).values).mean()
    return dict(name=name, cagr=cagr, sharpe=shp, dd=dd, win=win, beat=beat,
                med=100 * cyc.median(), n=len(cyc))


def verdict():
    tab, nif = cycle_table()
    fixed = tab[DEFAULT_N]
    adapt, chosen = walk_forward(tab)

    F = summarize(f"Fixed N={DEFAULT_N}", fixed, nif)
    A = summarize("Adaptive N (walk-forward)", adapt, nif)
    # trial-count-penalised: DSR of the adaptive cycle returns, discounted for |GRID| searched knobs
    dsr = deflated_sharpe(adapt.dropna().values, n_trials=len(GRID), ppy=252 / CAD)

    # does dynamic genuinely beat fixed OUT-OF-SAMPLE? (Sharpe is the risk-honest bar)
    edge = A["sharpe"] - F["sharpe"]
    robust = edge > 0.10 and (np.isnan(dsr["dsr"]) or dsr["dsr"] > 0.90)

    # today's trailing-best N (the live recommendation candidate)
    today_n = max({n: _sharpe(tab[n].iloc[-WINDOW:]) for n in GRID}.items(), key=lambda kv: kv[1])[0]

    print("=" * 80)
    print("  AEGIS DYNAMIC ENGINE — is 'Top-N' genuinely dynamic, or is fixed-N robust?")
    print("  Walk-forward: N chosen from PAST cycles only, judged on the UNSEEN next cycle.")
    print("=" * 80)
    print(f"  grid {GRID} · cadence {CAD}d · trailing window {WINDOW} cycles · {F['n']} cycles tested\n")
    print(f"  {'Strategy':<28}{'CAGR':>7}{'Sharpe':>8}{'MaxDD':>8}{'Win%':>7}{'BeatN%':>8}{'Med%':>7}")
    for S in (F, A):
        print(f"  {S['name']:<28}{S['cagr']:>6.1f}%{S['sharpe']:>8.2f}{S['dd']:>7.1f}%"
              f"{S['win']:>6.0f}%{S['beat']:>7.0f}%{S['med']:>+7.1f}")
    print(f"\n  OOS Sharpe edge (adaptive - fixed): {edge:+.2f}")
    print(f"  Deflated Sharpe of adaptive path  : {dsr['dsr']:.3f}  (penalised for {len(GRID)} trials)")
    nsw = (chosen != chosen.shift()).sum()
    print(f"  Adaptive switched N {nsw} times; range {chosen.min()}-{chosen.max()}, "
          f"most-used {chosen.value_counts().idxmax()}")

    print("\n  " + ("-" * 76))
    if robust:
        print(f"  VERDICT: ADOPT DYNAMIC. Adapting N beats fixed OOS (+{edge:.2f} Sharpe, DSR ok).")
        print(f"  Today's evidence-backed basket size: {today_n} stocks.")
    else:
        print("  VERDICT: KEEP FIXED N. Dynamic does NOT beat fixed out-of-sample (edge "
              f"{edge:+.2f} Sharpe).")
        print(f"  Trailing-best today is {today_n}, but it is NOT robust — production stays N={DEFAULT_N}.")
        print("  This is the engine being honest: a knob earns 'dynamic' only by OOS evidence, and")
        print("  on price data alone, basket-SIZE timing has no edge (same lesson as factor lift).")
    print("  " + ("-" * 76))
    print("\n  TEMPLATE: holding period, rebalance cadence, sector priority and (later) fundamentals/")
    print("  news plug into THIS same walk-forward gate — beat fixed/baseline OOS, or stay honest.")
    return dict(fixed=F, adaptive=A, edge=edge, dsr=dsr["dsr"], robust=robust, today_n=today_n,
                chosen=chosen)


if __name__ == "__main__":
    verdict()
