# india/research/constraint_grid.py
"""
CONSTRAINT GRID — backtest the IMPLEMENTATION constraints (not models) and let evidence pick the
operating config: position count x sector cap x correlation-cluster cap, HRP + regime + global.
Ranks by RETAIL SCORE = Sharpe - 0.01*names - 0.03*turnover (rewards manageable, low-churn baskets).

Run: python india/research/constraint_grid.py
"""
import sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats

# (label, topn, sector_cap=max stocks/sector, corr_cap=max correlated names/cluster)
CONFIGS = [
    ("10, no caps", 10, None, None),
    ("10, sector<=2", 10, 2, None),
    ("10, sector<=3", 10, 3, None),
    ("10, corr<=2", 10, None, 2),
    ("10, sector<=2 + corr<=2", 10, 2, 2),
    ("8, sector<=2 + corr<=2", 8, 2, 2),
    ("6, sector<=2", 6, 2, None),
    ("6, sector<=2 + corr<=2", 6, 2, 2),
    ("15, sector<=3 + corr<=2", 15, 3, 2),
    ("20, sector<=4 + corr<=3", 20, 4, 3),
]


def main():
    print("=" * 88)
    print("  CONSTRAINT GRID — position count x sector cap x correlation cap (HRP+regime+global)")
    print("=" * 88)
    print(f"  {'config':<26}{'CAGR':>6}{'Sharpe':>7}{'Sortino':>8}{'maxDD':>7}{'Calmar':>7}{'turn/yr':>8}{'~names':>7}{'Retail':>8}")
    results = []
    for label, n, sc, cc in CONFIGS:
        net, idx, turn, names = backtest("hrp", regime="global", topn=n, sector_cap=sc,
                                         corr_cap=cc, with_turnover=True)
        s = stats(net, idx)
        retail = s["sharpe"] - 0.01 * names - 0.03 * turn
        results.append((label, s, turn, names, retail))
        print(f"  {label:<26}{s['cagr']:>5.1f}%{s['sharpe']:>7.2f}{s['sortino']:>8.2f}{s['dd']:>6.1f}%"
              f"{s['calmar']:>7.2f}{turn:>8.1f}{names:>7.0f}{retail:>8.2f}")
    print("  " + "-" * 82)
    best = max(results, key=lambda r: r[4])
    bestsh = max(results, key=lambda r: r[1]["sharpe"])
    print(f"  BEST RETAIL SCORE : {best[0]}  (Sharpe {best[1]['sharpe']:.2f}, DD {best[1]['dd']:.1f}%, ~{best[3]:.0f} names)")
    print(f"  BEST RAW SHARPE   : {bestsh[0]}  (Sharpe {bestsh[1]['sharpe']:.2f}, DD {bestsh[1]['dd']:.1f}%)")
    print("\n  Evidence decides the operating config. Constraints are BACKTESTED, never hardcoded.")


if __name__ == "__main__":
    main()
