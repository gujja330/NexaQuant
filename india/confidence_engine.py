# india/confidence_engine.py
"""
AEGIS CONFIDENCE ENGINE (Future 3 / AEGIS OS building block).

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
from india.evidence.monte_carlo import sim
from india.probability_surface import surface, horizon_view, mode_of

CFG = dict(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)
HORIZON_DAYS = 126     # default read = 6 months (CORE mode); change to see TACTICAL/OPPORTUNITY
CAP = 100000


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

    # horizon-aware read for the requested holding period
    hv = horizon_view(eq, HORIZON_DAYS, CAP)
    hlabel = f"{HORIZON_DAYS//21} months" if HORIZON_DAYS >= 21 else f"{HORIZON_DAYS} days"
    # confidence = WEAKER of regime + horizon mode. NOTE: this is a deliberately CONSERVATIVE
    # heuristic, not a measured fact. The conditional test (evidence/probability_matrix.py) found
    # weak-regime entries actually had HIGHER forward odds (de-risk + buy-the-dip) — but those cells
    # are bull-period/small-sample artifacts, so we under-promise on purpose until forward data.
    rank = {"Low": 0, "Medium": 1, "High": 2}
    eff_conf = min([conf, hv["confidence"]], key=lambda x: rank[x.title()])

    print("=" * 56)
    print("  AEGIS CONFIDENCE ENGINE")
    print("=" * 56)
    print(f"  Horizon:           {hlabel}   ->   mode {hv['mode']} ({hv['status']})")
    print(f"  Regime:            {regime}  (market exposure {exp:.0%})")
    print(f"  Confidence:        {eff_conf}   (weaker of regime + horizon mode)")
    print(f"  P(positive):       {hv['p_pos']:.0f}%   at this horizon")
    print(f"  Expected gain:     Rs{hv['median']:+,.0f}   (bad case Rs{hv['bad']:+,.0f}) on Rs{CAP:,.0f}")
    print(f"  Expected CAGR:     {cagr_lo:.0f}-{cagr_hi:.0f}%   (realistic band, survivorship-haircut)")
    print(f"  Expected drawdown: ~{exp_dd:.0f}%   (typical worst dip)")
    print(f"  Recovery:          {med_rec} days median")
    print(f"  Worst underwater:  ~{worst_uw_mo} months (rare, once-a-cycle)")
    print(f"  Worst month seen:  {worst_m:.0f}%")
    print(f"  Tail risk:         {tail}")
    print(f"  Review:            Quarterly")
    print("-" * 56)
    print("  PROBABILITY SURFACE (odds of profit by hold, on Rs 1,00,000):")
    for label, v in surface(eq, CAP):
        bar = "#" * int(v["p_pos"] / 5)
        print(f"    {label:<4}{v['p_pos']:>4.0f}%  {bar:<20} {v['mode']}")
    print("=" * 56)
    print("  Expectation + probability read, NOT a prediction of winners or a target price.")


if __name__ == "__main__":
    main()
