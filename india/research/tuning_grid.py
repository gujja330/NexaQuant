# india/research/tuning_grid.py
"""
TUNING GRID — evidence for the 'arbitrary' choices: sector cap (1/2/3/4/none) and position count
x rebalance frequency. On the v2.1 champion (HRP + regime + global). Let evidence pick, not me.

Run: python india/research/tuning_grid.py
"""
import sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats


def line(tag, **kw):
    net, idx, turn, names = backtest("hrp", regime="global", with_turnover=True, **kw)
    s = stats(net, idx)
    print(f"  {tag:<26}{s['cagr']:>6.1f}%{s['sharpe']:>7.2f}{s['sortino']:>8.2f}{s['dd']:>7.1f}%"
          f"{turn:>8.1f}{names:>7.0f}")


if __name__ == "__main__":
    print("=" * 78)
    print("  TUNING GRID — sector cap & position count (HRP+regime+global, quarterly)")
    print("=" * 78)
    print("  -- SECTOR CAP (max stocks/sector), 15 stocks, quarterly --")
    print(f"  {'config':<26}{'CAGR':>6}{'Sharpe':>7}{'Sortino':>8}{'maxDD':>7}{'turn':>8}{'names':>7}")
    for sc, name in [(1, "sector<=1"), (2, "sector<=2"), (3, "sector<=3"), (4, "sector<=4"), (None, "no cap")]:
        line(name, topn=15, sector_cap=sc, rebal=63)
    print("\n  -- POSITION COUNT x FREQUENCY (sector<=3) --")
    print(f"  {'config':<26}{'CAGR':>6}{'Sharpe':>7}{'Sortino':>8}{'maxDD':>7}{'turn':>8}{'names':>7}")
    for n in (8, 10, 12, 15, 18, 20):
        line(f"{n} stk monthly", topn=n, sector_cap=3, rebal=21)
    print("  --")
    for n in (8, 10, 12, 15, 18, 20):
        line(f"{n} stk quarterly", topn=n, sector_cap=3, rebal=63)
    print("\n  Evidence picks the sector cap + count. Champion candidate stands or is updated by this.")
