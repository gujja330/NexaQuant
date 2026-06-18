# research/lot_size_sim.py
"""
DOLLAR-TERMS lot-size study on a small account (default $10) — BTC H4, last 3 years.

Answers, honestly and in $ (not just %):
  * What does a FIXED 0.01 / 0.02 / 0.04 / 0.05 lot do to a $10 account over 3 years?
  * Does it BLOW UP (a single stop bigger than the balance = margin call / ruin)?
  * WHEN should we step the lot up (0.02/0.04/0.05)? -> only on HIGH-CONFIDENCE trades
    (strong ADX + lengthy-candle), which is what our strategy's confidence tiers already do.
  * How does that compare to our actual %-risk COMPOUNDING sizing?

CONTRACT ASSUMPTION (critical): $ P&L = pips * PIP_VALUE_PER_LOT * lots.
  - Standard BTCUSD account: ~1.0 $/pip per 1.0 lot  -> set PIP_VALUE_PER_LOT = 1.0
  - Exness CENT account     : ~1/100 of that          -> set PIP_VALUE_PER_LOT = 0.01  (default)
The live bot reads the REAL value from MT5 symbol_info, so production is always exact.

Run: python research/lot_size_sim.py            # cent-account assumption, $10 start
     python research/lot_size_sim.py 1.0 100    # standard account, $100 start
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
from backtest.trade_sim import simulate_trades

SYM, TF = "BTCUSDm", "H4"
PIP_VALUE_PER_LOT = float(sys.argv[1]) if len(sys.argv) > 1 else 0.01   # cent account default
START = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
YEARS_BACK = 3
MIN_LOT, MAX_LOT = 0.01, 0.05


def get_trades():
    df = pd.read_parquet(ROOT / f"data/raw/{SYM}_{TF}.parquet").sort_index()
    sp = symbol_params(SYM, df["close"]); a = atr(df, 14)
    reg = playbook.regime_labels(df, "adx")
    parts = []
    for side, s in (("long", 1), ("short", -1)):
        ent = playbook.entries(df, side=side, regime=reg)
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=s, **playbook.EXIT))
    tr = pd.concat([p for p in parts if not p.empty]).sort_values("entry_time").reset_index(drop=True)
    conf = playbook.confidence_size(df).reindex(tr["entry_time"]).fillna(1.0).values
    last_yr = df.index.year.max()
    keep = pd.to_datetime(tr["entry_time"]).dt.year >= (last_yr - YEARS_BACK + 1)
    tr = tr[keep].reset_index(drop=True); conf = conf[keep.values]
    return tr, conf


def simulate(tr, lots_per_trade):
    """Sequential $ account. Each trade: pnl$ = pips * PIP_VALUE_PER_LOT * lots.
    Ruin if a loss exceeds the balance (can't cover the stop). Fixed lot = NO compounding."""
    eq = START; peak = START; curve = [START]; ruined_at = None
    for i, row in tr.iterrows():
        lots = lots_per_trade[i]
        pnl = row["pips"] * PIP_VALUE_PER_LOT * lots
        eq += pnl
        if eq <= 0 and ruined_at is None:
            ruined_at = i + 1; eq = 0.0; curve.append(eq); break
        peak = max(peak, eq); curve.append(eq)
    curve = np.array(curve)
    dd = float(np.max((np.maximum.accumulate(curve) - curve) / np.maximum.accumulate(curve))) * 100
    return {"final": eq, "ret": 100 * (eq - START) / START, "dd": dd, "ruined_at": ruined_at}


def conf_step_lots(conf):
    """When to size UP: base 0.01; x2 if conf>=1.5; x4 if conf>=2.0 — capped at MAX_LOT.
    This is the FIXED-LOT equivalent of our confidence risk tiers (size up only when the
    setup is strong: high ADX + lengthy-candle boost)."""
    mult = np.where(conf >= 2.0, 4, np.where(conf >= 1.5, 2, 1))
    return np.clip(MIN_LOT * mult, MIN_LOT, MAX_LOT)


def risk_compound_lots(tr):
    """Our ACTUAL method for reference: risk a % of CURRENT equity (compounding), tiered by
    confidence. Returns realised $ curve (lots implied, not fixed)."""
    eq = START; peak = START; curve = [START]; ruined = None
    conf = playbook.confidence_size  # noqa
    for i, row in tr.iterrows():
        risk_frac = row["risk_frac"]
        pnl = eq * risk_frac * row["R"]     # R already net of cost
        eq += pnl
        if eq <= 0 and ruined is None:
            ruined = i + 1; eq = 0.0; curve.append(eq); break
        peak = max(peak, eq); curve.append(eq)
    curve = np.array(curve)
    dd = float(np.max((np.maximum.accumulate(curve) - curve) / np.maximum.accumulate(curve))) * 100
    return {"final": eq, "ret": 100 * (eq - START) / START, "dd": dd, "ruined_at": ruined}


tr, conf = get_trades()
tr["risk_frac"] = np.where(conf < 1.5, 0.005, np.where(conf < 2.0, 0.01, 0.02))
n = len(tr)
print(f"LOT-SIZE STUDY — {SYM} {TF}, last {YEARS_BACK}y, {n} trades")
print(f"  assumption: ${PIP_VALUE_PER_LOT:.2f}/pip per 1.0 lot ({'CENT' if PIP_VALUE_PER_LOT<0.5 else 'STANDARD'} acct), start ${START:.2f}")
print(f"  avg win/loss in pips: +{tr.loc[tr['pips']>0,'pips'].mean():.0f} / {tr.loc[tr['pips']<0,'pips'].mean():.0f}\n")

print(f"  {'scheme':<22}{'final$':>10}{'return%':>10}{'maxDD%':>9}{'ruin?':>16}")
for lot in (0.01, 0.02, 0.04, 0.05):
    r = simulate(tr, np.full(n, lot))
    ruin = f"RUINED@trade {r['ruined_at']}" if r["ruined_at"] else "survived"
    print(f"  fixed {lot:<16}{r['final']:>10.2f}{r['ret']:>10.0f}{r['dd']:>8.0f}%{ruin:>16}")
# confidence-stepped (size up only on strong setups)
cs = conf_step_lots(conf); rs = simulate(tr, cs)
ruin = f"RUINED@trade {rs['ruined_at']}" if rs["ruined_at"] else "survived"
print(f"  {'conf-stepped .01-.05':<22}{rs['final']:>10.2f}{rs['ret']:>10.0f}{rs['dd']:>8.0f}%{ruin:>16}")
print(f"      (avg lot {cs.mean():.3f}; bigger lots used on {100*(cs>MIN_LOT).mean():.0f}% of trades = the high-conf ones)")
# our actual compounding %-risk method
rc = risk_compound_lots(tr)
ruin = f"RUINED@trade {rc['ruined_at']}" if rc["ruined_at"] else "survived"
print(f"  {'%-risk COMPOUNDING':<22}{rc['final']:>10.2f}{rc['ret']:>10.0f}{rc['dd']:>8.0f}%{ruin:>16}")
print("      (this is what the bot actually does: risk 0.5/1/2% of CURRENT balance, tiered by confidence)")
