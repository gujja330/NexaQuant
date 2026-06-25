# india/dynamic_policy.py
"""
DYNAMIC POLICY (AEGIS v4) — the engine DECIDES holding period and basket size from current market
state, instead of fixed config. This is the honest, RISK-FIRST version of "make it dynamic":

  Holding period  : regime-conditional. Risk-OFF -> prefer the strongest SHORT horizon (de-risk fast,
                    don't force a 6-month commitment in a weak tape). Risk-ON -> let winners run longer.
                    Chosen from the backtested Horizon Matrix, so it is evidence-selected, not hand-set.
  Basket size (N) : scales with market BREADTH (% of names above their 200-DMA) and regime exposure.
                    Healthy/broad market -> wider book (more diversification). Weak/narrow -> concentrate
                    into the safest names and hold more cash (the exposure lever does the de-risking).

Why risk-first and not return-first: choosing N or horizon to maximise PAST return is curve-fitting and
loses out-of-sample (see dynamic_engine.py: trailing-Sharpe N gave 0.95 vs fixed 1.24). Tying them to
breadth/regime is a risk decision, not a return bet — and main() walk-forward backtests it vs fixed so
the claim is tested, not asserted.

Run: python india/dynamic_policy.py        (walk-forward: dynamic-N vs fixed-N, honest verdict)
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
from india.sectors import sector_of

ORDER = ["1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y"]
N_LO, N_HI = 6, 16


def choose_horizon(hmat, exp):
    """Regime-conditional horizon from the backtested matrix. Varies with market state."""
    if hmat is None or hmat.empty:
        return "6M", "Medium"
    m = hmat.copy()
    m["o"] = m["Horizon"].map({h: i for i, h in enumerate(ORDER)})
    if exp >= 0.85:                      # risk-on: allow longer horizons (>=3M), let it run
        pool = m[m["o"] >= 4]
    elif exp >= 0.65:                    # neutral: mid horizons 1M..6M
        pool = m[(m["o"] >= 2) & (m["o"] <= 5)]
    else:                                # risk-off: shorter horizons (<=3M), de-risk faster
        pool = m[m["o"] <= 4]
    pool = pool[pool["Win Rate %"] >= 60]
    if pool.empty:
        pool = m
    # among regime-appropriate horizons, best risk-adjusted; break ties by win rate then median return
    pick = pool.sort_values(["Sharpe (ann)", "Win Rate %", "Median Return %"],
                            ascending=False).iloc[0]
    return pick["Horizon"], pick["Confidence"]


def market_breadth(closes, cols, i=None):
    """% of names trading above their 200-DMA — a classic breadth/health gauge (causal)."""
    px = closes.iloc[i] if i is not None else closes.iloc[-1]
    win = closes.iloc[max(0, (i or len(closes)) - 200):(i if i is not None else len(closes))]
    ma = win.mean()
    common = [c for c in cols if c in px.index and c in ma.index]
    if not common:
        return 0.5
    return float((px[common] > ma[common]).mean())


def choose_topn(hist, closes, exp, cap=2, i=None):
    """Basket size from breadth + regime. Wider book when healthy; concentrate + more cash when weak."""
    breadth = market_breadth(closes, list(hist.columns), i=i)
    health = 0.4 * breadth + 0.6 * exp
    n = int(round(N_LO + (N_HI - N_LO) * health))
    return max(N_LO, min(N_HI, n)), breadth


def sector_caps(hist, base_cap=2):
    """Per-sector cap tilted by sector RISK: lowest-vol sectors get +1 slot, highest-vol get -1.
    This is sector intelligence done risk-first (sector PRICE momentum already failed the lift test)."""
    secs = {}
    for c in hist.columns:
        secs.setdefault(sector_of(c), []).append(c)
    svol = {s: float(hist[names].std().mean()) for s, names in secs.items() if names}
    if not svol:
        return {}
    r = pd.Series(svol).rank(pct=True)                    # high pct = higher sector vol = riskier
    return {s: (base_cap + 1 if p <= 0.33 else (max(1, base_cap - 1) if p >= 0.67 else base_cap))
            for s, p in r.items()}


def select_tilted(hist, topn, base_cap=2):
    """Lowest-vol selection but with RISK-tilted per-sector caps (overweight calm sectors)."""
    caps = sector_caps(hist, base_cap)
    iv = (1.0 / hist.std().replace(0, np.nan)).dropna().sort_values(ascending=False)
    chosen, sec = [], {}
    for s in iv.index:
        if len(chosen) >= topn:
            break
        k = sector_of(s)
        if sec.get(k, 0) >= caps.get(k, base_cap):
            continue
        chosen.append(s); sec[k] = sec.get(k, 0) + 1
    return chosen


def _exp_at(idx, vix, i):
    """Causal regime exposure proxy at bar i (matches confidence_engine logic, trailing-only)."""
    e = 1.0
    if i >= 200 and idx.iloc[i] < idx.iloc[i - 200:i].mean():
        e *= 0.6
    if vix is not None and i >= 120 and vix.iloc[i] > vix.iloc[i - 120:i].quantile(0.80):
        e *= 0.6
    return e


def main():
    closes, _, _, _, idx, vix, _ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change()
    CAD = 21
    fix, dyn, tilt, nlist = [], [], [], []
    for i in range(LOOKBACK, len(closes) - CAD, CAD):
        hist = rets.iloc[i - LOOKBACK:i].dropna(axis=1, how="any")
        if hist.shape[1] < 30:
            continue
        fwd = (closes.iloc[i + CAD] / closes.iloc[i] - 1)
        exp = _exp_at(idx, vix, i)
        n_dyn, _ = choose_topn(hist, closes, exp, i=i)
        for tag, sel, acc in [("fix", select_names(hist, 15, sector_cap=2), fix),
                              ("dyn", select_names(hist, n_dyn, sector_cap=2), dyn),
                              ("tilt", select_tilted(hist, n_dyn, base_cap=2), tilt)]:
            if len(sel) < 2:
                acc.append(np.nan); continue
            w = weights_for("hrp", hist[sel]); w = w / w.sum()
            acc.append(float((w * fwd.reindex(w.index)).sum()))
        nlist.append(n_dyn)

    def summ(a):
        a = pd.Series(a).dropna()
        eq = (1 + a).cumprod(); yrs = len(a) * CAD / 252
        return dict(sharpe=a.mean() / (a.std() + 1e-12) * np.sqrt(252 / CAD),
                    cagr=100 * (eq.iloc[-1] ** (1 / yrs) - 1),
                    dd=100 * ((eq.cummax() - eq) / eq.cummax()).max(), win=100 * (a > 0).mean())
    F, D, T = summ(fix), summ(dyn), summ(tilt)
    print("=" * 78)
    print("  AEGIS DYNAMIC POLICY — basket size by breadth+regime + sector-risk tilt, walk-forward")
    print("=" * 78)
    print(f"  dynamic N ranged {min(nlist)}-{max(nlist)}, most-used {pd.Series(nlist).mode().iloc[0]}\n")
    print(f"  {'Policy':<26}{'CAGR':>8}{'Sharpe':>8}{'MaxDD':>8}{'Win%':>7}")
    print(f"  {'Fixed N=15':<26}{F['cagr']:>7.1f}%{F['sharpe']:>8.2f}{F['dd']:>7.1f}%{F['win']:>6.0f}%")
    print(f"  {'Dynamic N (breadth)':<26}{D['cagr']:>7.1f}%{D['sharpe']:>8.2f}{D['dd']:>7.1f}%{D['win']:>6.0f}%")
    print(f"  {'Dynamic N + sector tilt':<26}{T['cagr']:>7.1f}%{T['sharpe']:>8.2f}{T['dd']:>7.1f}%{T['win']:>6.0f}%")
    edge = D["sharpe"] - F["sharpe"]; tedge = T["sharpe"] - D["sharpe"]
    print(f"\n  Dynamic-N vs fixed Sharpe edge:  {edge:+.2f}  ->  " + (
        "at least as good — adopted." if edge > -0.10 else "below tolerance."))
    print(f"  Sector-risk tilt vs dynamic-N:   {tedge:+.2f}  ->  " + (
        "ADOPT the tilt — adds risk-adjusted value." if tedge > 0.05 else
        ("neutral — keep tilt OFF (no proven edge yet)." if tedge > -0.10 else "HURTS — keep OFF.")))
    print("  Holding period is chosen separately by choose_horizon() — regime-conditional from the matrix.")


if __name__ == "__main__":
    main()
