# india/research/position_grid.py
"""
POSITION GRID — is a small retail basket (5/6/8/10..) nearly as good as the full HRP (32)?
Backtests position counts with HRP + regime + global, net of cost, full window, and reports the
full metric set + turnover + avg #names. Answers: what's the RETAIL sweet spot (manageable count
with Sharpe close to the institutional 32-stock champion)?

Run: python india/research/position_grid.py
"""
import sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats


def main():
    print("=" * 86)
    print("  POSITION GRID — how few stocks can match the full HRP? (HRP+regime+global, net, ~5.5y)")
    print("=" * 86)
    print(f"  {'basket':<16}{'CAGR':>6}{'Sharpe':>7}{'Sortino':>8}{'maxDD':>7}{'Calmar':>7}{'turn/yr':>8}{'~names':>7} {'Rs1L->':>10}")
    rows = []
    for tag, topn, sc in [("Top-5", 5, None), ("Top-6", 6, None), ("Top-8", 8, None),
                          ("Top-10", 10, None), ("Top-15", 15, None), ("Top-20", 20, None),
                          ("Top-30", 30, None), ("Top-10 +sectorcap2", 10, 2),
                          ("Full HRP (champ)", None, None)]:
        net, idx, turn, names = backtest("hrp", regime="global", topn=topn, sector_cap=sc, with_turnover=True)
        s = stats(net, idx)
        rows.append((tag, s, turn, names))
        print(f"  {tag:<16}{s['cagr']:>5.1f}%{s['sharpe']:>7.2f}{s['sortino']:>8.2f}{s['dd']:>6.1f}%"
              f"{s['calmar']:>7.2f}{turn:>8.1f}{names:>7.0f} Rs{s['end']:>9,.0f}")

    # retail score: Sharpe with a small penalty for more names (manageability)
    print("\n  RETAIL SCORE = Sharpe - 0.01*names (rewards manageable baskets):")
    scored = sorted(rows, key=lambda r: r[1]["sharpe"] - 0.01 * r[3], reverse=True)
    for tag, s, turn, names in scored[:4]:
        print(f"    {tag:<18} Sharpe {s['sharpe']:.2f}  maxDD {s['dd']:.1f}%  ~{names:.0f} names  "
              f"-> retail score {s['sharpe']-0.01*names:.2f}")
    print("\n  Read: full HRP wins on raw Sharpe, but a 6-10 name basket may win on RETAIL practicality")
    print("  (Sharpe close, far fewer trades). Pick what YOU can actually rebalance monthly.")


if __name__ == "__main__":
    main()
