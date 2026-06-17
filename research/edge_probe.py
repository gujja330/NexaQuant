# validation_lab/edge_probe.py
"""
Honest, cost-aware, leakage-free edge probe for XAUUSDm (gold).

Goal: find out whether ANY simple, well-known edge survives realistic costs and
out-of-sample testing on the H1/H4 data already in the repo -- BEFORE any RL.

Discipline enforced here:
  * Leakage-free: signal uses data up to close of bar t; trade executes at OPEN of bar t+1.
  * Cost-aware: every position change pays a round-trip cost (spread + slippage) in $/oz.
  * Honest split: parameters are NOT optimized. First 70% = in-sample (IS),
    last 30% = out-of-sample (OOS). We only believe an edge if OOS holds up.
  * Statistical sanity: we report trade count, expectancy, profit factor, Sharpe,
    max drawdown -- not just win rate.

Run:  python validation_lab/edge_probe.py
"""

import numpy as np
import pandas as pd

DATA = {
    "H1": "data/raw/XAUUSDm_H1.parquet",
    "H4": "data/raw/XAUUSDm_H4.parquet",
}

# Realistic round-trip cost in $/oz (entry+exit spread + slippage).
# Gold on a retail mini account: ~$0.30-0.50 spread per side is typical.
# We test a base case and a sensitivity range.
COST_BASE = 0.50          # $/oz round trip, base assumption
COST_SENSITIVITY = [0.30, 0.50, 1.00]

BARS_PER_YEAR = {"H1": 24 * 252, "H4": 6 * 252}   # ~trading hours/year for annualizing
IS_FRACTION = 0.70


# ---------- indicators (all causal: use only past/current bar) ----------
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


# ---------- strategies: return a target position series in {-1,0,+1} ----------
# Each is computed on bar t (causal). Execution shift to t+1 happens in backtest().
def strat_ema_trend(df, fast=20, slow=50, long_short=True):
    sig = np.where(ema(df["close"], fast) > ema(df["close"], slow), 1, -1 if long_short else 0)
    return pd.Series(sig, index=df.index)

def strat_donchian(df, n=20, long_short=True):
    hi = df["high"].rolling(n).max().shift(1)   # prior N-bar high (shift avoids using current bar's high)
    lo = df["low"].rolling(n).min().shift(1)
    pos = pd.Series(np.nan, index=df.index)
    pos[df["close"] > hi] = 1
    pos[df["close"] < lo] = -1 if long_short else 0
    return pos.ffill().fillna(0)

def strat_rsi_meanrev(df, n=14, lo=30, hi=70):
    r = rsi(df["close"], n)
    pos = pd.Series(np.nan, index=df.index)
    pos[r < lo] = 1     # oversold -> long
    pos[r > hi] = -1    # overbought -> short
    pos[(r > 50) & (r < 60)] = 0   # exit longs back toward mean
    return pos.ffill().fillna(0)

def strat_trend_filter_pullback(df, trend_n=200, rsi_n=14, lo=40):
    """Long-only: only buy dips (RSI<lo) while above long EMA (uptrend). Classic, robust."""
    up = df["close"] > ema(df["close"], trend_n)
    r = rsi(df["close"], rsi_n)
    pos = pd.Series(np.nan, index=df.index)
    pos[up & (r < lo)] = 1
    pos[r > 55] = 0
    pos[~up] = 0
    return pos.ffill().fillna(0)

STRATS = {
    "EMA trend 20/50 L/S":      lambda df: strat_ema_trend(df, 20, 50, True),
    "EMA trend 20/50 long-only":lambda df: strat_ema_trend(df, 20, 50, False),
    "Donchian 20 L/S":          lambda df: strat_donchian(df, 20, True),
    "RSI mean-rev 14":          lambda df: strat_rsi_meanrev(df, 14, 30, 70),
    "Trend pullback (long)":    lambda df: strat_trend_filter_pullback(df),
}


def backtest(df, target_pos, cost_rt, bars_per_year):
    """
    Event-accurate, leakage-free.
    target_pos: desired position decided at close of bar t.
    We hold that position over bar t+1 (enter at t+1 open), so realized position
    series is target_pos.shift(1). Cost charged whenever position changes.
    Returns per-bar $ PnL on 1 oz notional, and a trade ledger.
    """
    px_open = df["open"]
    pos = target_pos.shift(1).fillna(0)                 # position actually held during each bar
    # bar PnL for holding `pos` from this bar's open to next bar's open
    nxt_open = px_open.shift(-1)
    bar_ret = (nxt_open - px_open)                      # $/oz move open->open
    gross = pos * bar_ret

    pos_change = pos.diff().abs().fillna(pos.abs())     # units of position turned over
    cost = pos_change * cost_rt                          # $ cost per oz traded (round trip on full flip = 2*... handled by abs diff over time)
    net = (gross - cost).dropna()

    # trade ledger: group by contiguous non-flat position
    trades = []
    cur_sign = 0
    entry_px = None
    entry_t = None
    for t, p in pos.items():
        if p != cur_sign:
            if cur_sign != 0 and entry_px is not None:
                exit_px = px_open.get(t, np.nan)
                pnl = cur_sign * (exit_px - entry_px) - cost_rt
                trades.append({"entry": entry_t, "exit": t, "side": cur_sign, "pnl": pnl})
            cur_sign = p
            entry_px = px_open.get(t, np.nan) if p != 0 else None
            entry_t = t if p != 0 else None
    tr = pd.DataFrame(trades)
    return net, tr


def stats(net, tr, bars_per_year, notional):
    if len(net) == 0 or tr is None or tr.empty:
        return None
    eq = net.cumsum()
    dd = (eq.cummax() - eq).max()
    mu, sd = net.mean(), net.std()
    sharpe = (mu / sd) * np.sqrt(bars_per_year) if sd > 0 else 0.0
    wins = tr["pnl"] > 0
    gross_win = tr.loc[wins, "pnl"].sum()
    gross_loss = -tr.loc[~wins, "pnl"].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else np.inf
    return {
        "trades": len(tr),
        "win_rate": wins.mean(),
        "expectancy_$": tr["pnl"].mean(),
        "profit_factor": pf,
        "total_$": eq.iloc[-1],
        "max_dd_$": dd,
        "sharpe_ann": sharpe,
        "ret_on_notional_%": 100 * eq.iloc[-1] / notional,
    }


def run():
    for tf, path in DATA.items():
        df = pd.read_parquet(path).sort_index()
        notional = df["close"].iloc[0]   # 1 oz ~ price; return % is on ~1oz notional
        split = int(len(df) * IS_FRACTION)
        is_df, oos_df = df.iloc[:split], df.iloc[split:]
        bpy = BARS_PER_YEAR[tf]
        print("\n" + "=" * 96)
        print(f"  {tf}   bars={len(df)}   {df.index[0].date()} -> {df.index[-1].date()}   "
              f"IS={len(is_df)} / OOS={len(oos_df)}   cost=${COST_BASE}/oz round trip")
        print("=" * 96)
        hdr = f"{'strategy':<28}{'seg':<5}{'trades':>7}{'win%':>7}{'exp$':>8}{'PF':>6}{'tot$':>9}{'maxDD$':>8}{'Sharpe':>8}"
        print(hdr)
        print("-" * 96)
        for name, fn in STRATS.items():
            for seg, seg_df in (("IS", is_df), ("OOS", oos_df)):
                tp = fn(seg_df)
                net, tr = backtest(seg_df, tp, COST_BASE, bpy)
                s = stats(net, tr, bpy, notional)
                if s is None:
                    print(f"{name:<28}{seg:<5}{'(no trades)':>7}")
                    continue
                print(f"{name:<28}{seg:<5}{s['trades']:>7}{100*s['win_rate']:>6.1f}{s['expectancy_$']:>8.2f}"
                      f"{s['profit_factor']:>6.2f}{s['total_$']:>9.1f}{s['max_dd_$']:>8.1f}{s['sharpe_ann']:>8.2f}")
            print()

    # ---- THE decisive check: does the winner beat just holding gold? ----
    print("=" * 96)
    print("  BUY-AND-HOLD BENCHMARK vs winner (EMA trend long-only)  -- is it skill or just gold beta?")
    print("=" * 96)
    print(f"{'tf/seg':<10}{'B&H tot$':>10}{'B&H Sharpe':>12}{'B&H maxDD$':>12}    "
          f"{'EMA tot$':>10}{'EMA Sharpe':>12}{'EMA maxDD$':>12}")
    print("-" * 96)
    for tf in DATA:
        df = pd.read_parquet(DATA[tf]).sort_index()
        bpy = BARS_PER_YEAR[tf]
        split = int(len(df) * IS_FRACTION)
        for seg, seg_df in (("IS", df.iloc[:split]), ("OOS", df.iloc[split:])):
            # buy & hold: position always +1
            bh_pos = pd.Series(1.0, index=seg_df.index)
            bh_net, bh_tr = backtest(seg_df, bh_pos, COST_BASE, bpy)
            bh_eq = bh_net.cumsum()
            bh_dd = (bh_eq.cummax() - bh_eq).max()
            bh_sh = (bh_net.mean() / bh_net.std()) * np.sqrt(bpy) if bh_net.std() > 0 else 0
            # EMA long-only
            tp = strat_ema_trend(seg_df, 20, 50, False)
            e_net, e_tr = backtest(seg_df, tp, COST_BASE, bpy)
            es = stats(e_net, e_tr, bpy, df["close"].iloc[0])
            print(f"{tf+'/'+seg:<10}{bh_eq.iloc[-1]:>10.1f}{bh_sh:>12.2f}{bh_dd:>12.1f}    "
                  f"{es['total_$']:>10.1f}{es['sharpe_ann']:>12.2f}{es['max_dd_$']:>12.1f}")

    # cost sensitivity on the actual winner (EMA long-only, H1 OOS)
    print("\n" + "=" * 96)
    print("  COST SENSITIVITY  (EMA trend long-only, H1, OOS only)")
    print("=" * 96)
    df = pd.read_parquet(DATA["H1"]).sort_index()
    oos = df.iloc[int(len(df) * IS_FRACTION):]
    for c in COST_SENSITIVITY:
        tp = strat_ema_trend(oos, 20, 50, False)
        net, tr = backtest(oos, tp, c, BARS_PER_YEAR["H1"])
        s = stats(net, tr, BARS_PER_YEAR["H1"], df["close"].iloc[0])
        if s:
            print(f"  cost=${c:<5} trades={s['trades']:>4}  win%={100*s['win_rate']:>5.1f}  "
                  f"exp=${s['expectancy_$']:>6.2f}  PF={s['profit_factor']:>4.2f}  "
                  f"total=${s['total_$']:>7.1f}  Sharpe={s['sharpe_ann']:>5.2f}")


if __name__ == "__main__":
    run()
