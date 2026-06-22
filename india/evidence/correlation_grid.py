# india/research/correlation_grid.py
"""
CORRELATION GRID (+ turnover + Retail Score) — does capping correlated clusters help?
Tests correlation-cluster cap {none, 2, 3} x position count, on the QUARTERLY champion
(HRP + regime + global, sector<=3). Reports Sharpe/Sortino/maxDD + turnover + Retail Score.

RetailScore = Sharpe - 0.01*names - 0.03*turnover  (rewards manageable, low-churn baskets).
Run: python india/research/correlation_grid.py
"""
import sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats

REBAL = 63   # quarterly (promoted)


def main():
    print("=" * 90)
    print("  CORRELATION GRID — cluster cap {none/2/3} x position count (QUARTERLY, HRP+regime+global)")
    print("=" * 90)
    print(f"  {'config':<28}{'CAGR':>6}{'Sharpe':>7}{'Sortino':>8}{'maxDD':>7}{'turn/yr':>8}{'~names':>7}{'Retail':>8}")
    rows = []
    for n in (8, 10, 15):
        for cc, cname in [(None, "no cap"), (3, "corr<=3"), (2, "corr<=2")]:
            net, idx, turn, names = backtest("hrp", regime="global", topn=n, sector_cap=3,
                                             corr_cap=cc, rebal=REBAL, with_turnover=True)
            s = stats(net, idx)
            retail = s["sharpe"] - 0.01 * names - 0.03 * turn
            rows.append((f"{n} stk, {cname}", s, turn, names, retail))
            print(f"  {n} stk, {cname:<20}{s['cagr']:>5.1f}%{s['sharpe']:>7.2f}{s['sortino']:>8.2f}"
                  f"{s['dd']:>6.1f}%{turn:>8.1f}{names:>7.0f}{retail:>8.2f}")
    print("  " + "-" * 84)
    best = max(rows, key=lambda r: r[4])
    print(f"  BEST RETAIL SCORE: {best[0]}  (Sharpe {best[1]['sharpe']:.2f}, DD {best[1]['dd']:.1f}%, "
          f"turn {best[2]:.1f}/yr, ~{best[3]:.0f} names)")
    print("\n  Turnover note: quarterly already low. Correlation cap = risk control; keep if it cuts")
    print("  drawdown/turnover at ~no Sharpe cost (low-vol selection rarely clusters, so effect is small).")


if __name__ == "__main__":
    main()
