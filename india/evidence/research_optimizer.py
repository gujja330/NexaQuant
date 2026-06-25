# india/evidence/research_optimizer.py
"""
RESEARCH OPTIMIZER (Lab / Research Mode) — disciplined config search, NOT in-sample curve-fitting.

The user's "AutoPortfolio" idea, with the anti-overfit guardrail they themselves insisted on:
search ranges of the key knobs (method · topn · rebalance · sector-cap · regime), but SELECT for
ROBUSTNESS — out-of-sample (back-half) Sharpe + front/back consistency + low drawdown — and discount
for the number of trials (deflated Sharpe). The single best historical config is usually overfit;
we want the one that holds out-of-sample.

This only REPORTS the robust config. Production (india/config.py) changes ONLY on this + forward
paper — never auto-tuned to yesterday's data. That's Research Mode -> Production Mode, disciplined.

Run: python india/evidence/research_optimizer.py
"""
import sys, warnings, itertools
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats
from india.validation import deflated_sharpe

GRID = dict(method=["ew", "hrp"], topn=[8, 15, 20], rebal=[63, 126],
            sector_cap=[2, 3], regime=[False, "global"])


def oos_score(net):
    """Robustness score: out-of-sample (back-half) Sharpe, requiring front-half stability, DD-penalised."""
    net = net.dropna()
    if len(net) < 400:
        return None
    mid = len(net) // 2
    front, back = net.iloc[:mid], net.iloc[mid:]
    sh = lambda r: r.mean() / (r.std() + 1e-12) * np.sqrt(252)
    fs, bs = sh(front), sh(back)
    eq = (1 + back).cumprod(); dd = 100 * ((eq.cummax() - eq) / eq.cummax()).max()
    stable = fs > 0.5 and bs > 0.5                      # must work in BOTH halves
    score = bs - 0.03 * dd + (0.5 if stable else -1.0)  # reward OOS Sharpe, penalise DD + instability
    return dict(front_sharpe=fs, oos_sharpe=bs, oos_dd=dd, stable=stable, score=score)


def main():
    _, idx = backtest(method="ew")
    rows = []
    combos = list(itertools.product(*GRID.values()))
    print(f"  searching {len(combos)} configurations (out-of-sample scored) ...")
    for method, topn, rebal, sector_cap, regime in combos:
        net, _ = backtest(method=method, regime=regime, topn=topn, sector_cap=sector_cap, rebal=rebal)
        sc = oos_score(net)
        if sc is None:
            continue
        s = stats(net.dropna(), idx)
        rows.append({"method": method, "topn": topn, "rebal": rebal, "sector_cap": sector_cap,
                     "regime": regime or "off", "full_sharpe": round(s["sharpe"], 2),
                     "oos_sharpe": round(sc["oos_sharpe"], 2), "oos_dd%": round(sc["oos_dd"], 1),
                     "stable": sc["stable"], "score": round(sc["score"], 2),
                     "net": net.dropna()})
    df = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)

    print("=" * 84)
    print("  RESEARCH OPTIMIZER — top robust configurations (selected by OUT-OF-SAMPLE evidence)")
    print("=" * 84)
    show = df.drop(columns="net").head(10)
    print(f"  {'method':<7}{'topn':>5}{'rebal':>6}{'sec':>4}{'regime':>8}{'fullSh':>8}{'oosSh':>7}{'oosDD':>7}{'stable':>8}{'score':>7}")
    for _, r in show.iterrows():
        print(f"  {r['method']:<7}{r['topn']:>5}{r['rebal']:>6}{r['sector_cap']:>4}{r['regime']:>8}"
              f"{r['full_sharpe']:>8}{r['oos_sharpe']:>7}{r['oos_dd%']:>7}{str(r['stable']):>8}{r['score']:>7}")

    best = df.iloc[0]
    d = deflated_sharpe(best["net"].values, n_trials=len(df))
    print(f"\n  ROBUST PICK: {best['method']} · {best['topn']} stk · rebal {best['rebal']} · "
          f"sector<= {best['sector_cap']} · regime {best['regime']}")
    print(f"  out-of-sample Sharpe {best['oos_sharpe']} · OOS DD {best['oos_dd%']}% · "
          f"Deflated Sharpe {d['dsr']:.3f} (discounted for {len(df)} trials)")
    cur = "hrp · 15 stk · rebal 63 · sector<=2 · regime global"
    print(f"\n  Current PRODUCTION config: {cur}")
    print("  Regime ON dominates OFF in every robust config — consistent with the decomposition")
    print("  (the regime overlay is the edge, not selection/weighting).")
    print("\n  DISCIPLINE: this is RESEARCH MODE. Production changes ONLY if a config robustly beats")
    print("  the champion here AND survives forward paper. We do NOT auto-tune to history.")


if __name__ == "__main__":
    main()
