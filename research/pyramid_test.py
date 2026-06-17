# research/pyramid_test.py
"""
PYRAMIDING test: add to winners while a STRONG trend continues, to capture more of the
big 42-bar high-ADX moves (which the anatomy showed hold 91% of all winning pips).

Risk is kept controlled: each add only happens after price advances another ATR AND the
shared stop is lifted to the first unit's entry (breakeven) — so the pyramid's downside
stays ~one unit of risk even with 3 units on.

Compares max_units = 1 (current) vs 2 vs 3 on BTC H4 long+short. Honest metrics: total
pips, account return (tiered risk), max drawdown.

Run: python research/pyramid_test.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params
from strategy import playbook
from strategy.smc import atr, ema
from strategy.regime import adx

SYM, TF = "BTCUSDm", "H4"
STOP_MULT, ADD_STEP, ADX_MIN = 2.0, 1.0, 25.0    # add every +1 ATR while ADX>=25


def tier(c):
    return 0.005 if c < 1.5 else (0.01 if c < 2.0 else 0.02)


def pyramid_trades(df, entries, exit_sig, a, A, side, pip, max_units):
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    av, Av, ex = a.values, A.values, exit_sig.reindex(df.index).fillna(False).values
    ent_idx = np.where(entries.reindex(df.index).fillna(False).values)[0]
    n = len(df); trades = []; busy = -1
    for i in ent_idx:
        if i <= busy or i + 1 >= n or not np.isfinite(av[i]) or av[i] <= 0:
            continue
        risk0 = STOP_MULT * av[i]
        units = [o[i + 1]]                       # entry prices
        stop = o[i + 1] - side * risk0
        last_add = o[i + 1]
        end, exitpx, reason = min(i + 1 + 300, n), None, "timeout"
        for j in range(i + 1, end):
            # add a unit on continuation (price +ADD_STEP*ATR beyond last add) in strong trend
            if len(units) < max_units and side * (c[j] - last_add) >= ADD_STEP * av[i] and Av[j] >= ADX_MIN:
                units.append(c[j]); last_add = c[j]
                stop = max(stop, units[0]) if side == 1 else min(stop, units[0])   # lock: stop->BE
            if side * (l[j] - stop) <= 0:
                exitpx, reason, end = stop, "stop", j; break
            if ex[j]:
                exitpx, reason, end = c[j], "momentum", j; break
        if exitpx is None:
            exitpx = c[end - 1]
        # total pnl across all units (each pays cost); R relative to ONE unit's risk
        pnl = sum(side * (exitpx - u) for u in units) - pip * 0 - len(units) * (0.0)
        pnl -= len(units) * (sp_cost)            # round-trip cost per unit
        trades.append({"entry_time": df.index[i + 1], "units": len(units),
                       "pips": pnl / pip, "R": pnl / risk0, "bars": end - (i + 1)})
        busy = end
    return pd.DataFrame(trades)


df = pd.read_parquet(ROOT / f"data/raw/{SYM}_{TF}.parquet").sort_index()
sp = symbol_params(SYM, df["close"]); sp_cost = sp["cost"]
reg = playbook.regime_labels(df, "adx"); a = atr(df, 14); A = adx(df, 14)
conf = playbook.confidence_size(df)


def run(max_units):
    parts = []
    for side, sd in (("long", 1), ("short", -1)):
        ev = playbook.entries(df, side=side, regime=reg)
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(pyramid_trades(df, ev, ex, a, A, sd, sp["pip_size"], max_units))
    tr = pd.concat([p for p in parts if not p.empty]).sort_values("entry_time")
    c = conf.reindex(tr["entry_time"]).fillna(1.0).values
    rk = np.array([tier(x) for x in c]); rets = rk * tr["R"].values
    eq = np.cumprod(1 + rets); peak = np.maximum.accumulate(eq)
    return (len(tr), 100 * (tr["R"] > 0).mean(), tr["pips"].sum(),
            100 * (eq[-1] - 1), 100 * np.max((peak - eq) / peak), tr["units"].mean())


print(f"PYRAMIDING test — {SYM} {TF} long+short (2021-2026), tiered risk")
print(f"  {'max units':<11}{'trades':>7}{'win%':>7}{'totpips':>10}{'return%':>9}{'maxDD%':>8}{'avgUnits':>9}")
for mu in (1, 2, 3):
    n, w, pips, ret, dd, au = run(mu)
    print(f"  {mu:<11}{n:>7}{w:>6.0f}%{pips:>10.0f}{ret:>8.0f}%{dd:>7.0f}%{au:>9.2f}")
