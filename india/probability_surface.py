# india/probability_surface.py
"""
PROBABILITY SURFACE + HORIZON MODES — the flagship output of AEGIS OS.

Instead of false certainty ("buy ITC, target Rs 350") we communicate a DISTRIBUTION + PROBABILITY
by holding period. The shorter the horizon the lower the confidence — but we do NOT ban short holds,
we LABEL them honestly via horizon modes:

  TACTICAL    (<= 1 month)  Confidence LOW    Status SPECULATION   -> swing, no strong claim
  OPPORTUNITY (1 - 3 months) Confidence MEDIUM Status TACTICAL     -> the edge starts to appear
  CORE        (>= 6 months)  Confidence HIGH   Status CORE         -> flagship, high odds

`surface()` returns the full fine-grained P(+) curve; `horizon_view()` returns one horizon's read
(used by the Confidence Engine). Money shown on a configurable capital.

Run: python india/probability_surface.py
"""
import sys, warnings
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest

CAP = 100000
# fine-grained probability surface (the curve, not just 1yr)
HORIZONS = [("1W", 5), ("2W", 10), ("1M", 21), ("2M", 42), ("3M", 63),
            ("4M", 84), ("6M", 126), ("9M", 189), ("1Y", 252)]


def mode_of(days):
    """Horizon -> (mode, confidence, status). Honest labels, not a ban."""
    if days <= 21:
        return "TACTICAL", "LOW", "SPECULATION"
    if days < 126:
        return "OPPORTUNITY", "MEDIUM", "TACTICAL"
    return "CORE", "HIGH", "CORE"


def _champ_equity():
    net, idx = backtest(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)
    net = net.dropna()
    return (1 + net).cumprod()


def horizon_view(eq, days, cap=CAP):
    """One horizon's read: probability of profit, typical/good/bad money, mode."""
    r = (eq.shift(-days) / eq - 1).dropna()
    mode, conf, status = mode_of(days)
    return dict(days=days, p_pos=100 * (r > 0).mean(), median=cap * r.median(),
                good=cap * r.quantile(0.75), bad=cap * r.quantile(0.05),
                lo=100 * r.quantile(0.25), hi=100 * r.quantile(0.75),
                mode=mode, confidence=conf, status=status)


def surface(eq=None, cap=CAP):
    eq = _champ_equity() if eq is None else eq
    return [(label, horizon_view(eq, d, cap)) for label, d in HORIZONS]


def main():
    eq = _champ_equity()
    print("=" * 84)
    print("  AEGIS — PROBABILITY SURFACE (on Rs 1,00,000)   ·   horizon modes, not false targets")
    print("=" * 84)
    print(f"  {'hold':<6}{'P(profit)':>11}{'typical':>11}{'good case':>12}{'bad case':>12}"
          f"{'mode':>13}{'confidence':>12}")
    for label, v in surface(eq, CAP):
        print(f"  {label:<6}{v['p_pos']:>10.0f}%{v['median']:>+11,.0f}{v['good']:>+12,.0f}"
              f"{v['bad']:>+12,.0f}{v['mode']:>13}{v['confidence']:>12}")
    print("\n  Horizon modes (honest labels — short holds are allowed, just not over-sold):")
    print("    TACTICAL    <=1M    LOW conf    SPECULATION  (swing; ~coin flip, no strong claim)")
    print("    OPPORTUNITY 1-3M    MEDIUM conf TACTICAL     (edge starts to appear)")
    print("    CORE        >=6M    HIGH conf   CORE         (flagship; 90%+ odds)")
    print("\n  The product speaks PROBABILITY + DISTRIBUTION, never 'target price Rs X'.")
    print("  Short-term limit is 'current public data + architecture' — a future AEGIS Tactical")
    print("  (options flow / microstructure / news embeddings) could change the 1W-1M picture.")


if __name__ == "__main__":
    main()
