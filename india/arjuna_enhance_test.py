# india/arjuna_enhance_test.py
"""
Does PICKING HARDER beat the broad equal-weight basket? Tests the user's hypotheses on Nifty-200,
net of cost, full window (~5.5y, Dec-2020 -> Jun-2026; CAGR shown):
  * fundamental REJECT filter (drop high-debt/loss-making/bottom-quality before ranking)
  * CONCENTRATION sweep: top-15 / 20 / 30 / 50
  * EQUAL vs SCORE weighting (overweight the best names)
  * VIX + Nifty-200DMA regime de-risk; sector cap
Keep only what genuinely improves CAGR/Sharpe vs the plain basket.

Run: python india/arjuna_enhance_test.py
"""
import sys, warnings
from pathlib import Path
warnings.simplefilter("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from india.arjuna_strategy import backtest, stats
from india.arjuna_compare import NIFTY200

U = NIFTY200
YEARS = 5.47


def row(name, **kw):
    s = stats(backtest("quality", universe=U, **kw)[0])
    cagr = ((1 + s["total"] / 100) ** (1 / YEARS) - 1) * 100
    print(f"  {name:<44}{s['total']:>+7.0f}%{cagr:>7.1f}%{s['sharpe']:>7.2f}{s['dd']:>7.1f}%  Rs{s['end']:>10,.0f}")


if __name__ == "__main__":
    print("=" * 88)
    print("  NIFTY-200 — does picking HARDER beat broad equal-weight? (net of cost, ~5.5y)")
    print("=" * 88)
    print(f"  {'variant':<44}{'total':>8}{'CAGR':>7}{'Sharpe':>7}{'maxDD':>7}  {'Rs1L ->':>12}")
    print("  -- concentration sweep (equal weight, +VIX+200DMA) --")
    for k in (15, 20, 30, 50):
        row(f"EW-{k} quality + regime", k=k, vix_derisk=True, trend_derisk=True)
    print("  -- add fundamental reject filter --")
    for k in (20, 30):
        row(f"EW-{k} + regime + fundamental-reject", k=k, vix_derisk=True, trend_derisk=True, reject_weak=True)
    print("  -- score-weighted (overweight the best) --")
    for k in (20, 30):
        row(f"SCORE-{k} + regime + reject", k=k, vix_derisk=True, trend_derisk=True,
            reject_weak=True, weight="score")
    print("  -- + sector cap (true diversification) --")
    row("SCORE-30 + regime + reject + sector-cap6", k=30, vix_derisk=True, trend_derisk=True,
        reject_weak=True, weight="score", sector_cap=6)
    print("\n  Compare CAGR+Sharpe; keep the simplest variant that wins. (Survivorship still inflates absolutes.)")
