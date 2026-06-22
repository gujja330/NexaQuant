# india/evidence/probability_matrix.py
"""
TEST (scientific-discipline phase): is the Probability Surface REGIME-CONDITIONAL?

The shipped Probability Surface is UNCONDITIONAL — P(+) by horizon, ignoring market state. The honest
question (user's Test 1 + Test 3): does P(profit) depend on the REGIME at entry, and does that
support the Confidence Engine's assumed `confidence = min(regime, horizon)`?

We classify every entry date by regime exposure (Strong >=0.90 / Neutral 0.65-0.90 / Weak <0.65),
then measure P(+) and median gain for each (horizon x regime) cell — WITH sample counts, because
long horizons in a rare regime have few independent windows (overlap caveat).

This is evidence, not a feature. Promotion to the Confidence Engine only if the matrix is populated
and the pattern is real. Run: python india/evidence/probability_matrix.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest
from india.feature_engine import load_panels

HORIZONS = [("1W", 5), ("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252)]


def regime_state_series():
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
    state = pd.cut(scale, [-1, 0.65, 0.90, 9], labels=["Weak", "Neutral", "Strong"])
    return state


def main():
    net, idx = backtest(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)
    net = net.dropna()
    eq = (1 + net).cumprod()
    state = regime_state_series().reindex(eq.index)

    print("=" * 72)
    print("  TEST — PROBABILITY SURFACE x REGIME  (champion, conditional P(profit))")
    print("=" * 72)
    states = ["Strong", "Neutral", "Weak"]
    print(f"  {'horizon':<9}" + "".join(f"{s:>16}" for s in states) + f"{'unconditional':>16}")
    matrix = {}
    for label, h in HORIZONS:
        fwd = (eq.shift(-h) / eq - 1)
        row = []
        for s in states:
            mask = (state == s) & fwd.notna()
            n = int(mask.sum())
            if n >= 20:
                p = 100 * (fwd[mask] > 0).mean()
                row.append(f"{p:.0f}% (n={n})")
                matrix[(label, s)] = (p, n)
            else:
                row.append(f"-- (n={n})")
                matrix[(label, s)] = (None, n)
        uncond = 100 * (fwd.dropna() > 0).mean()
        print(f"  {label:<9}" + "".join(f"{c:>16}" for c in row) + f"{uncond:>15.0f}%")

    print("\n  Does the data support `confidence = min(regime, horizon)`?")
    checks = []
    # (a) at SHORT horizon, even Strong regime should NOT be high-confidence
    s1w = matrix.get(("1W", "Strong"), (None, 0))[0]
    if s1w is not None:
        ok = s1w < 70
        checks.append(("Strong regime + 1W stays low (<70%)", f"{s1w:.0f}%", ok))
    # (b) at CORE horizon, Weak should be lower than Strong
    w6, s6 = matrix.get(("6M", "Weak"), (None, 0))[0], matrix.get(("6M", "Strong"), (None, 0))[0]
    if w6 is not None and s6 is not None:
        checks.append(("6M: Weak < Strong", f"{w6:.0f}% vs {s6:.0f}%", w6 < s6))
    for name, val, ok in checks:
        print(f"     [{'OK ' if ok else 'NO '}] {name}: {val}")
    if not checks:
        print("     (insufficient populated cells to judge — thin samples; see counts above)")
    print("\n  CAVEAT: windows overlap (autocorrelated) and some regime cells are thin -> treat as")
    print("  directional evidence, not precise probabilities. This is why it stays a TEST until")
    print("  forward data thickens the rare cells. Verdict drives Confidence Engine promotion.")


if __name__ == "__main__":
    main()
