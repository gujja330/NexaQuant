# research/expansion_test.py
"""
LENGTHY-CANDLE (range-expansion) edge test on BTC H4.

Your insight: long or short, a big-bodied / wide-range candle = a burst of one-sided
momentum (institutions pushing). We want to CAPTURE those moves, not the chop.

Three things tested, all long+short, tiered risk, net of cost, momentum-ride exit:
  A) BASELINE        : current playbook entries (regime-gated)
  B) +EXPANSION GATE : baseline entries, but ONLY taken when the trigger bar's BODY
                       is >= k*ATR (i.e. confirmed by a lengthy candle)
  C) PURE EXPANSION  : enter purely on a lengthy candle in the trend direction
                       (body >= k*ATR AND close beyond prior bar), no other signal.

If lengthy candles really carry the pips, (B) should lift win%/avg-pips and (C) should
stand on its own. The table decides.

Run: python research/expansion_test.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params
from strategy import playbook
from strategy.smc import atr
from strategy.regime import adx
from backtest.trade_sim import simulate_trades, trade_stats
from backtest.engine import BARS_PER_YEAR

SYM, TF = "BTCUSDm", "H4"
BODY_K = 1.5     # "lengthy" = body >= 1.5 * ATR


def tier_ret(tr, df):
    conf = playbook.confidence_size(df).reindex(tr["entry_time"]).fillna(1.0).values
    risk = np.where(conf < 1.5, 0.005, np.where(conf < 2.0, 0.01, 0.02))
    eq = np.cumprod(1 + risk * tr["R"].values)
    peak = np.maximum.accumulate(eq)
    return 100 * (eq[-1] - 1), 100 * np.max((peak - eq) / peak)


df = pd.read_parquet(ROOT / f"data/raw/{SYM}_{TF}.parquet").sort_index()
sp = symbol_params(SYM, df["close"]); pip = sp["pip_size"]
a = atr(df, 14); A = adx(df, 14); reg = playbook.regime_labels(df, "adx")
body = (df["close"] - df["open"]).abs()
big = body >= BODY_K * a                          # lengthy candle (either direction)
up = df["close"] > df["open"]


def evaluate(label, long_ent, short_ent):
    parts = []
    for side, s, ent in (("long", 1, long_ent), ("short", -1, short_ent)):
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=pip, side=s, **playbook.EXIT))
    tr = pd.concat([p for p in parts if not p.empty]).sort_values("entry_time")
    st = trade_stats(tr, BARS_PER_YEAR.get(TF, 252 * 6), tr["bars"].mean())
    ret, dd = tier_ret(tr, df)
    avg_pips = tr["pips"].mean()
    return dict(label=label, trades=st["trades"], win=100 * st["win"], pf=st["pf"],
                pips=st["total_pips"], avgpips=avg_pips, ret=ret, dd=dd)


L = playbook.entries(df, side="long", regime=reg)
S = playbook.entries(df, side="short", regime=reg)
rows = [
    evaluate("A baseline", L, S),
    evaluate("B +expansion gate", L & big.shift(1, fill_value=False),
             S & big.shift(1, fill_value=False)),
    evaluate("C pure expansion", (big & up & (reg != "range")).shift(1, fill_value=False),
             (big & ~up & (reg != "range")).shift(1, fill_value=False)),
]

print(f"LENGTHY-CANDLE edge — {SYM} {TF} long+short, tiered risk (body>={BODY_K}xATR)")
print(f"  {'variant':<20}{'trades':>7}{'win%':>6}{'PF':>6}{'totpips':>9}{'avgpips':>9}{'ret%':>7}{'maxDD%':>8}")
for r in rows:
    print(f"  {r['label']:<20}{int(r['trades']):>7}{r['win']:>5.0f}%{r['pf']:>6.2f}"
          f"{r['pips']:>9.0f}{r['avgpips']:>9.0f}{r['ret']:>6.0f}%{r['dd']:>7.0f}%")
