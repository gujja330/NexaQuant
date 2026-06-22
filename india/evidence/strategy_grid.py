# india/research/strategy_grid.py
"""
THE EXPERIMENT — does concentration + regime + HRP + sector-cap beat the broad 30-stock basket?
Tests the user's A-I grid on the real backtest (Nifty-200, net of cost, ~5.5y). top-N = the N
LOWEST-VOLATILITY names (safest), then weighted by the chosen method. Sector cap = max names/sector.

Run: python india/research/strategy_grid.py
"""
import sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats


def row(tag, **kw):
    net, idx = backtest(**kw)
    s = stats(net, idx)
    print(f"  {tag:<34}{s['cagr']:>6.1f}%{s['sharpe']:>7.2f}{s['sortino']:>8.2f}{s['dd']:>7.1f}%"
          f"{s['calmar']:>7.2f} Rs{s['end']:>9,.0f}")


if __name__ == "__main__":
    print("=" * 80)
    print("  STRATEGY GRID — concentration / regime / HRP / sector-cap (Nifty-200, net, ~5.5y)")
    print("=" * 80)
    print(f"  {'strategy':<34}{'CAGR':>7}{'Sharpe':>7}{'Sortino':>8}{'maxDD':>7}{'Calmar':>7} {'Rs1L->':>10}")
    row("A: Top-30 equal", method="ew", topn=30)
    row("B: Top-20 equal", method="ew", topn=20)
    row("C: Top-15 equal", method="ew", topn=15)
    row("D: Top-10 equal", method="ew", topn=10)
    row("E: Top-10 + regime+global", method="ew", topn=10, regime="global")
    row("F: Top-10 HRP", method="hrp", topn=10)
    row("G: Top-10 HRP + regime+global", method="hrp", topn=10, regime="global")
    row("H: Top-10 HRP+regime+sectorcap2", method="hrp", topn=10, regime="global", sector_cap=2)
    row("I: Top-20 HRP+regime+sectorcap4", method="hrp", topn=20, regime="global", sector_cap=4)
    print("  " + "-" * 74)
    row("CHAMPION: HRP all + regime+global", method="hrp", regime="global")
    import numpy as np
    from india.feature_engine import load_panels
    nf = load_panels()[4].pct_change().fillna(0.0)
    print(f"  {'NIFTY-50 (benchmark)':<34}{100*((1+nf).prod()**(252/len(nf))-1):>6.1f}%"
          f"{nf.mean()/(nf.std()+1e-12)*np.sqrt(252):>7.2f}{'':>8}{'':>7}{'':>7}")
    print("\n  Read: best Sharpe + lowest maxDD wins. Concentration usually RAISES return AND drawdown;")
    print("  regime+global is the consistent lifter. Let evidence pick the operating config.")
