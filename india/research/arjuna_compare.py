# india/arjuna_compare.py
"""
Nifty-100 vs Nifty-200 — same equal-weight strategy, head-to-head (net of cost, full window).
Tests whether broadening the universe to 200 helps the basket (more breadth) or just adds noise.

Run: python india/arjuna_compare.py
"""
import sys, warnings
from pathlib import Path

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from india.data_nse import UNIVERSE
from india.arjuna_strategy import backtest, stats

# stock symbols (clean, no index), in list order: first 100 = Nifty-100, all = Nifty-200
STOCKS = [s.replace(".NS", "").replace("^", "") for s in UNIVERSE if not s.startswith("^")]
NIFTY100 = STOCKS[:100]
NIFTY200 = STOCKS

UNIVERSES = {"Nifty-100": NIFTY100, "Nifty-200": NIFTY200}


def row(name, net):
    s = stats(net)
    print(f"  {name:<34}{s['total']:>+7.0f}%{s['sharpe']:>8.2f}{s['dd']:>8.1f}%   Rs{s['end']:>11,.0f}")


if __name__ == "__main__":
    print("=" * 80)
    print("  NIFTY-100 vs NIFTY-200 — same equal-weight strategy (full window, net of cost)")
    print("=" * 80)
    for uname, syms in UNIVERSES.items():
        print(f"\n  === {uname} ({len(syms)} names) ===")
        print(f"  {'variant':<34}{'total':>8}{'Sharpe':>8}{'maxDD':>8}   {'Rs1L ->':>13}")
        row("EW-ALL (own all, hold)", backtest("all", universe=syms)[0])
        row("EW-30 quality screen", backtest("quality", 30, universe=syms)[0])
        row("EW-30 quality + VIX de-risk", backtest("quality", 30, vix_derisk=True, universe=syms)[0])
        row("EW-50 quality + VIX de-risk", backtest("quality", 50, vix_derisk=True, universe=syms)[0])
    print("\n  Verdict prints above — compare EW-ALL and the EW-30/50 practical baskets across universes.")
