# india/confidence_engine.py
"""
ARJUNA CONFIDENCE ENGINE (Future 3 / ARJUNA OS building block).

One honest dashboard the investor reads BEFORE committing money: current regime, our confidence,
the realistic return band, odds of profit, expected pain, and the horizon to commit for. It does
not predict winners — it tells you what to expect and how sure we are.

Assembles existing, validated pieces: regime exposure (live), Monte-Carlo probability engine
(survivorship-haircut), recovery/underwater analytics, tail risk, time diversification.

Run: python india/confidence_engine.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest
from india.feature_engine import load_panels
from india.research.monte_carlo import sim

CFG = dict(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)


def current_regime():
    """Latest market-state exposure (1.0 = full risk-on, lower = de-risked) + a plain label."""
    closes, _, _, _, idx, vix, _ = load_panels()
    scale = pd.Series(1.0, index=closes.index)
    if vix is not None:
        hi = (vix > vix.rolling(120, min_periods=30).quantile(0.80)).reindex(closes.index).fillna(False)
        scale *= hi.map({True: 0.6, False: 1.0})
    below = (idx < idx.rolling(200).mean()).reindex(closes.index).fillna(False)
    scale *= below.map({True: 0.6, False: 1.0})
    try:
        from india.global_risk import global_exposure
        g = global_exposure()
        if g is not None:
            scale *= g.reindex(closes.index).ffill().fillna(1.0)
    except Exception:
        pass
    exp = float(scale.iloc[-1])
    label = "Strong" if exp >= 0.9 else ("Neutral" if exp >= 0.65 else "Weak")
    conf = "High" if exp >= 0.9 else ("Medium" if exp >= 0.55 else "Low")
    return exp, label, conf


def main():
    net, idx = backtest(**CFG)
    net = net.dropna()
    eq = (1 + net).cumprod(); uw = eq / eq.cummax() - 1

    exp, regime, conf = current_regime()

    # probability engine (1-yr, survivorship haircut)
    c, d = sim(net, 252, 0.65)
    cagr_lo, cagr_hi = 100 * np.percentile(c, 25), 100 * np.percentile(c, 75)
    p_pos = 100 * (c > 0).mean()
    exp_dd = 100 * np.median(d)

    # recovery + underwater
    is_high = uw >= -1e-9; reps = []; last = 0
    for i in range(1, len(uw)):
        if is_high.iloc[i]:
            if i - last > 1: reps.append(i - last)
            last = i
    reps = np.array(reps) if reps else np.array([0])
    med_rec = int(np.median(reps)); worst_uw_mo = int(reps.max() // 21)

    # tail
    m = (1 + net).resample("M").prod() - 1
    worst_m = 100 * m.min()
    r = net.values; cvar95 = 100 * r[r <= np.percentile(r, 5)].mean()
    tail = "Low" if cvar95 > -1.2 else ("Medium" if cvar95 > -2.0 else "High")

    # suggested horizon (first holding length with >=90% positive, in-sample)
    horizon = "1 year+"
    for label, h in [("1 month", 21), ("3 months", 63), ("6 months", 126), ("1 year", 252)]:
        if ((eq.shift(-h) / eq - 1).dropna() > 0).mean() >= 0.90:
            horizon = label + "+"; break

    print("=" * 50)
    print("  ARJUNA CONFIDENCE ENGINE")
    print("=" * 50)
    print(f"  Regime:            {regime}  (market exposure {exp:.0%})")
    print(f"  Confidence:        {conf}")
    print(f"  Expected CAGR:     {cagr_lo:.0f}-{cagr_hi:.0f}%   (realistic band, survivorship-haircut)")
    print(f"  P(positive, 1yr):  {p_pos:.0f}%")
    print(f"  Expected drawdown: ~{exp_dd:.0f}%   (typical worst dip)")
    print(f"  Recovery:          {med_rec} days median")
    print(f"  Worst underwater:  ~{worst_uw_mo} months (rare, once-a-cycle)")
    print(f"  Worst month seen:  {worst_m:.0f}%")
    print(f"  Tail risk:         {tail}")
    print(f"  Suggested horizon: {horizon}")
    print("=" * 50)
    print("  This is an expectation + confidence read, NOT a prediction of winners.")


if __name__ == "__main__":
    main()
