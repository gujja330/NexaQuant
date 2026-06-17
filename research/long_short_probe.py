# research/long_short_probe.py
"""
Long vs Short vs Long+Short on the canonical playbook (symmetric entries + exits).

Shows the strategy is NOT hardwired long-only — it can short (bearish trend regime,
bearish structure, momentum-ride exit on the downside). On a bull sample (gold 2023-25)
shorts should bleed; on bear/range instruments shorts add the other half of the edge.

Run: python research/long_short_probe.py
"""
import sys, glob, os, re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, timeframes
from strategy import playbook
from strategy.smc import atr
from backtest.trade_sim import simulate_trades, trade_stats
from backtest.engine import BARS_PER_YEAR

RAW = ROOT / "data" / "raw"


def discover():
    return sorted({re.match(r"(.+)_H1\.parquet", os.path.basename(f)).group(1)
                   for f in glob.glob(str(RAW / "*_H1.parquet"))})


def side_trades(df, oos, sp, side):
    s = +1 if side == "long" else -1
    ent = playbook.entries(df, side=side)
    ex = playbook.momentum_exit_signal(df, side=side)
    return simulate_trades(df.iloc[oos], ent.iloc[oos], atr(df, 14).iloc[oos], sp["cost"],
                           exit_signal=ex.iloc[oos], pip_size=sp["pip_size"], side=s, **playbook.EXIT)


def run():
    for sym in discover():
        for tf in ("H1", "H4"):
            p = RAW / f"{sym}_{tf}.parquet"
            if not p.exists():
                continue
            df = pd.read_parquet(p).sort_index()
            sp = symbol_params(sym, df["close"])
            oos = slice(int(len(df) * 0.7), None)
            bpy = BARS_PER_YEAR.get(tf, 252 * 24)
            longs = side_trades(df, oos, sp, "long")
            shorts = side_trades(df, oos, sp, "short")
            both = pd.concat([longs, shorts]).sort_values("entry_time") if not (longs.empty and shorts.empty) else longs
            print("=" * 78)
            print(f"  LONG vs SHORT — {sym} {tf} (OOS, net of cost)")
            print("=" * 78)
            print(f"    {'side':<14}{'trades':>7}{'win%':>7}{'pips':>9}{'PF':>7}{'tot$':>9}{'Sharpe':>8}")
            for name, tr in (("long-only", longs), ("short-only", shorts), ("long+short", both)):
                s = trade_stats(tr, bpy, tr["bars"].mean() if not tr.empty else 1)
                if s:
                    print(f"    {name:<14}{s['trades']:>7}{100*s['win']:>6.0f}%{s['total_pips']:>9.0f}"
                          f"{s['pf']:>7.2f}{s['total']:>9.1f}{s['sharpe']:>8.2f}")
                else:
                    print(f"    {name:<14}{'(no trades)':>7}")
            print()


if __name__ == "__main__":
    run()
