# research/mtf_edge_probe.py
"""
Multi-timeframe TOP-DOWN edge probe for gold (XAUUSDm).

Workflow being tested (the professional / requested approach):
    BIAS   from higher timeframes  (W1, D1)   -> "which direction am I allowed to trade?"
    ENTRY  on a lower timeframe     (H1 here)  -> "when exactly do I get in?"

Until M5/M15 are pulled from MT5, H1 stands in as the execution timeframe.
The whole point: does aligning entries WITH the higher-timeframe trend improve
risk-adjusted performance (Sharpe / drawdown) over trading H1 alone?

Leakage control: higher-TF state is shifted one bar (use only the last CLOSED
HTF bar) and joined onto H1 with merge_asof (each H1 bar sees only past HTF info).
Trades still execute at next-H1-open. Costs charged per position change.

Run: python research/mtf_edge_probe.py
"""
import numpy as np
import pandas as pd

RAW = "data/raw"
COST = 0.50                       # $/oz round trip
BARS_PER_YEAR = 24 * 252
IS_FRACTION = 0.70


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def load(tf):
    return pd.read_parquet(f"{RAW}/XAUUSDm_{tf}.parquet").sort_index()


def htf_bias(tf, fast, slow):
    """Boolean uptrend on a higher timeframe, shifted 1 bar = last CLOSED bar only."""
    df = load(tf)
    up = (ema(df["close"], fast) > ema(df["close"], slow)).shift(1)
    return up.rename(f"up_{tf}").to_frame()


def join_htf(h1_index, htf_frame):
    """Leakage-safe as-of join: each H1 bar gets the most recent prior HTF value."""
    left = pd.DataFrame(index=h1_index).reset_index().rename(columns={"index": "time"})
    if left.columns[0] != "time":
        left = left.rename(columns={left.columns[0]: "time"})
    right = htf_frame.reset_index().rename(columns={htf_frame.index.name or "index": "time"})
    merged = pd.merge_asof(left.sort_values("time"), right.sort_values("time"),
                           on="time", direction="backward")
    return merged.set_index("time")


def backtest(df, target_pos, cost_rt):
    px_open = df["open"]
    pos = target_pos.shift(1).fillna(0)
    bar_ret = px_open.shift(-1) - px_open
    gross = pos * bar_ret
    cost = pos.diff().abs().fillna(pos.abs()) * cost_rt
    net = (gross - cost).dropna()
    # trade ledger
    trades, cur, ep, et = [], 0, None, None
    for t, p in pos.items():
        if p != cur:
            if cur != 0 and ep is not None:
                xp = px_open.get(t, np.nan)
                trades.append({"pnl": cur * (xp - ep) - cost_rt})
            cur = p
            ep = px_open.get(t, np.nan) if p != 0 else None
            et = t if p != 0 else None
    return net, pd.DataFrame(trades)


def stats(net, tr, notional):
    if len(net) == 0 or tr.empty:
        return None
    eq = net.cumsum()
    dd = (eq.cummax() - eq).max()
    sh = (net.mean() / net.std()) * np.sqrt(BARS_PER_YEAR) if net.std() > 0 else 0
    wins = tr["pnl"] > 0
    gl = -tr.loc[~wins, "pnl"].sum()
    pf = (tr.loc[wins, "pnl"].sum() / gl) if gl > 0 else np.inf
    return dict(trades=len(tr), win=wins.mean(), exp=tr["pnl"].mean(), pf=pf,
                total=eq.iloc[-1], dd=dd, sharpe=sh, ret_pct=100 * eq.iloc[-1] / notional)


def build_signals(h1):
    """Return dict of {variant_name: target_pos series} all long-only."""
    base_up = ema(h1["close"], 20) > ema(h1["close"], 50)      # H1 entry trigger
    d1 = join_htf(h1.index, htf_bias("D1", 20, 50))["up_D1"].astype("boolean").fillna(False).astype(bool)
    w1 = join_htf(h1.index, htf_bias("W1", 5, 10))["up_W1"].astype("boolean").fillna(False).astype(bool)

    return {
        "H1 only (baseline)":        pd.Series(np.where(base_up, 1, 0), index=h1.index),
        "H1 + D1 bias":             pd.Series(np.where(base_up & d1, 1, 0), index=h1.index),
        "H1 + D1 + W1 bias (top-down)": pd.Series(np.where(base_up & d1 & w1, 1, 0), index=h1.index),
    }


def run():
    h1 = load("H1")
    notional = h1["close"].iloc[0]
    split = int(len(h1) * IS_FRACTION)
    sigs = build_signals(h1)

    print("=" * 100)
    print("  TOP-DOWN MULTI-TIMEFRAME PROBE  (gold, H1 execution, long-only, cost=$0.50/oz)")
    print("  Does higher-TF alignment improve risk-adjusted return vs H1 alone?")
    print("=" * 100)
    print(f"{'variant':<32}{'seg':<5}{'trades':>7}{'win%':>7}{'exp$':>8}{'PF':>6}"
          f"{'tot$':>9}{'maxDD$':>8}{'Sharpe':>8}{'ret%':>7}")
    print("-" * 100)
    for name, pos in sigs.items():
        for seg, sl in (("IS", slice(0, split)), ("OOS", slice(split, None))):
            seg_df = h1.iloc[sl]
            net, tr = backtest(seg_df, pos.iloc[sl], COST)
            s = stats(net, tr, notional)
            if s:
                print(f"{name:<32}{seg:<5}{s['trades']:>7}{100*s['win']:>6.1f}{s['exp']:>8.2f}"
                      f"{s['pf']:>6.2f}{s['total']:>9.1f}{s['dd']:>8.1f}{s['sharpe']:>8.2f}{s['ret_pct']:>7.1f}")
        print()


if __name__ == "__main__":
    run()
