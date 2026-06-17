# backtest/trade_sim.py
"""
Event-driven trade simulator with EXPLICIT exit management — because how you EXIT
(stop-loss, take-profit, trailing stop) usually matters more than how you enter.

Long-only (extend for shorts), leakage-free:
  * enter at NEXT bar open after an entry signal
  * initial stop  = entry - stop_mult * ATR(entry bar)
  * take-profit   = entry + rr * (stop distance)        [optional]
  * trailing stop : once price runs +trail_trigger*ATR in profit, ratchet the stop to
                    (high-water-mark - trail_dist*ATR); never moves down
  * exit on stop / TP / trailing / timeout, whichever hits first (stop checked before
    TP within a bar = conservative worst-case)
  * every trade charged round-trip cost; records R-multiple, bars held, exit reason
"""
import numpy as np
import pandas as pd


def simulate_trades(df, entries, atr, cost_rt, stop_mult=1.5, rr=None,
                    trail_trigger=None, trail_dist=None, breakeven_at=None,
                    partial_at=None, partial_frac=0.5, exit_signal=None,
                    sizes=None, pip_size=0.1, max_bars=200, side=1):
    """Long-only (side=1) trade-management sim. Supports, in combination:
      stop_mult     : initial stop = entry - stop_mult*ATR  (always on; SL is non-negotiable)
      rr            : full take-profit at rr*risk           (optional)
      breakeven_at  : move stop to entry once +breakeven_at*ATR in profit (protect capital)
      trail_trigger/trail_dist : ratchet stop to (HWM - trail_dist*ATR) after +trigger*ATR
      partial_at/partial_frac  : bank `frac` of size at +partial_at*R, move stop to BE,
                                 then let the REMAINDER run for BIGGER PROFITS
    Returns trades with pnl, R-multiple, bars, exit reason."""
    o, h, l, c = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    a = atr.values
    # vol-dependent slippage: cost rises when ATR is elevated vs its median (research:
    # frictions fire hardest exactly when stops trigger during vol spikes)
    a_med = pd.Series(a, index=df.index).rolling(200, min_periods=14).median().values
    exit_sig = (exit_signal.reindex(df.index).fillna(False).values
                if exit_signal is not None else None)
    sz = (sizes.reindex(df.index).fillna(0.0).values
          if sizes is not None else None)            # per-entry AI size multiplier
    ent_idx = np.where(entries.reindex(df.index).fillna(False).values)[0]
    n = len(df)
    trades = []
    busy_until = -1
    for i in ent_idx:
        if i <= busy_until or i + 1 >= n or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        size = 1.0 if sz is None else float(sz[i])     # AI conviction multiplier
        if size <= 0:                                   # P(win) below threshold -> skip
            continue
        entry = o[i + 1]
        risk = stop_mult * a[i]
        stop = entry - side * risk
        init_stop = stop                      # the SL the trade is placed with
        tp = entry + side * rr * risk if rr else None
        hwm = entry
        realized = 0.0           # banked PnL from partial scale-out ($/oz, full-size units)
        remaining = 1.0
        exit_px, reason, end = None, "timeout", min(i + 1 + max_bars, n)
        for j in range(i + 1, end):
            hwm = max(hwm, h[j]) if side == 1 else min(hwm, l[j])
            gain = side * (hwm - entry)
            if breakeven_at and gain >= breakeven_at * a[i]:
                stop = max(stop, entry) if side == 1 else min(stop, entry)
            if trail_trigger and trail_dist and gain >= trail_trigger * a[i]:
                stop = max(stop, hwm - side * trail_dist * a[i]) if side == 1 \
                    else min(stop, hwm + trail_dist * a[i])
            # partial scale-out: bank some, protect, let rest run
            if partial_at and remaining == 1.0 and side * (h[j] - (entry + side * partial_at * risk)) >= 0:
                ppx = entry + side * partial_at * risk
                realized += partial_frac * side * (ppx - entry)
                remaining = 1.0 - partial_frac
                stop = max(stop, entry) if side == 1 else min(stop, entry)
            if side * (l[j] - stop) <= 0:
                exit_px, reason, end = stop, "stop/trail", j; break
            if tp is not None and side * (h[j] - tp) >= 0:
                exit_px, reason, end = tp, "target", j; break
            # momentum-fade exit: ride the trend while momentum holds, leave when it dies
            if exit_sig is not None and exit_sig[j]:
                exit_px, reason, end = c[j], "momentum", j; break
        if exit_px is None:
            exit_px = c[end - 1]
        net_price = realized + remaining * side * (exit_px - entry)   # price captured / unit
        unit_pnl = net_price - cost_rt
        trades.append({"entry_time": df.index[i + 1], "exit_time": df.index[end - 1],
                       "side": "long" if side == 1 else "short",
                       "entry_px": round(entry, 3), "sl_px": round(init_stop, 3),
                       "exit_px": round(float(exit_px), 3), "reason": reason,
                       "pips": round(net_price / pip_size, 1),
                       "pnl": round(size * unit_pnl, 2), "R": round(unit_pnl / risk, 2),
                       "size": round(size, 2), "bars": end - (i + 1),
                       "win": bool(unit_pnl > 0)})
        busy_until = end
    return pd.DataFrame(trades)


def trade_stats(tr, bars_per_year, avg_bars):
    if tr is None or tr.empty:
        return None
    pnl = tr["pnl"]
    eq = pnl.cumsum()
    dd = (eq.cummax() - eq).max()
    wins = pnl > 0
    win_pnl, loss_pnl = pnl[wins], pnl[~wins]
    gl = -loss_pnl.sum()
    pf = win_pnl.sum() / gl if gl > 0 else np.inf
    avg_win = win_pnl.mean() if wins.any() else 0.0
    avg_loss = loss_pnl.mean() if (~wins).any() else 0.0
    payoff = abs(avg_win / avg_loss) if avg_loss != 0 else np.inf   # bigger-profit lever
    tpy = bars_per_year / max(avg_bars, 1)
    sharpe = (pnl.mean() / pnl.std()) * np.sqrt(tpy) if pnl.std() > 0 else 0.0
    pips = tr["pips"] if "pips" in tr else pd.Series(dtype=float)
    return dict(trades=len(tr), wins=int(wins.sum()), losses=int((~wins).sum()),
                win=wins.mean(), exp=pnl.mean(), avgR=tr["R"].mean(),
                pf=pf, total=eq.iloc[-1], dd=dd, sharpe=sharpe, avg_bars=tr["bars"].mean(),
                avg_win=avg_win, avg_loss=avg_loss, payoff=payoff,
                max_R=tr["R"].max(), skew=pnl.skew(),
                total_pips=pips.sum() if len(pips) else 0.0,
                avg_win_pips=pips[wins].mean() if wins.any() and len(pips) else 0.0,
                avg_loss_pips=pips[~wins].mean() if (~wins).any() and len(pips) else 0.0)
