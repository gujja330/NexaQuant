# research/exit_probe.py
"""
Does EXIT management (stop-loss / take-profit / trailing) improve the gold edge?

Same validated entries (regime-gated continuation longs), four exit styles compared
out-of-sample, net of cost:
  A. ATR stop only            (let winners run, cut losers at -1.5 ATR)
  B. ATR stop + 2R target     (fixed reward:risk)
  C. ATR stop + trailing      (ratchet stop once +1 ATR in profit)
  D. wide stop + trailing     (give room, then trail)

Reports win%, avg R-multiple, profit factor, Sharpe, max drawdown, avg bars held.

Run: python research/exit_probe.py
"""
import sys, glob, os, re
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.trade_sim import simulate_trades, trade_stats
from strategy.smc import ema, atr
from strategy.regime import detect_regime

RAW = "data/raw"
COST = {"XAUUSDm": 0.50, "BTCUSDm": 5.0}
TFS = {"H1": 24 * 252, "H4": 6 * 252}
IS_FRACTION = 0.70


def discover():
    return sorted({re.match(r"(.+)_H1\.parquet", os.path.basename(f)).group(1)
                   for f in glob.glob(f"{RAW}/*_H1.parquet")})


def show(tag, s):
    if s is None:
        print(f"    {tag:<24}(no trades)")
    else:
        print(f"    {tag:<24}{s['trades']:>4}{100*s['win']:>6.0f}{s['avgR']:>6.2f}"
              f"{s['payoff']:>7.2f}{s['avg_win']:>8.1f}{s['max_R']:>6.1f}{s['pf']:>6.2f}"
              f"{s['total']:>8.1f}{s['dd']:>7.1f}{s['sharpe']:>7.2f}")


def run():
    for sym in discover():
        cost = COST.get(sym, 0.5)
        for tf, bpy in TFS.items():
            p = f"{RAW}/{sym}_{tf}.parquet"
            if not os.path.exists(p):
                continue
            df = pd.read_parquet(p).sort_index()
            oos = df.iloc[int(len(df) * IS_FRACTION):]
            a = atr(oos, 14)
            reg, _, _ = detect_regime(oos)
            base = ((ema(oos["close"], 20) > ema(oos["close"], 50)) & (reg == "trend")).astype(bool)
            entries = base & (~base.shift(1, fill_value=False))

            # momentum-fade exit signal: trend/momentum lost when close drops below fast EMA
            mom_exit = oos["close"] < ema(oos["close"], 20)
            print("=" * 92)
            print(f"  EXIT STUDY — {sym} {tf}  (OOS, {int(entries.sum())} entries, cost=${cost})")
            print("  Goal: BIGGER PROFITS — ride momentum, protect with SL, don't choke winners")
            print("=" * 92)
            print(f"    {'exit style':<24}{'n':>4}{'win%':>6}{'avgR':>6}{'payoff':>7}{'avgWin$':>8}"
                  f"{'maxR':>6}{'PF':>6}{'tot$':>8}{'maxDD':>7}{'Shrp':>7}")
            variants = {
                "A stop only (run)":     dict(stop_mult=1.5),
                "B stop + 2R target":    dict(stop_mult=1.5, rr=2.0),
                "C breakeven + trail":   dict(stop_mult=1.5, breakeven_at=1.0, trail_trigger=2.0, trail_dist=2.5),
                "D scale-out + run":     dict(stop_mult=1.5, partial_at=1.5, partial_frac=0.5,
                                              trail_trigger=2.0, trail_dist=2.5),
                "E momentum-ride":       dict(stop_mult=2.0, exit_signal=mom_exit),
                "F momentum + scale":    dict(stop_mult=2.0, partial_at=1.5, partial_frac=0.4, exit_signal=mom_exit),
            }
            for name, kw in variants.items():
                tr = simulate_trades(oos, entries, a, cost, **kw)
                s = trade_stats(tr, bpy, tr["bars"].mean() if not tr.empty else 1)
                show(name, s)
            print()


if __name__ == "__main__":
    run()
