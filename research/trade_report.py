# research/trade_report.py
"""
Human-readable, insightful trade report — answers: WHICH chart to trade, the exact
entry / SL / exit / trailing plan, and on backtest data HOW MANY trades won, HOW MANY
PIPS captured, and WHAT the risk was.

Fully DYNAMIC (config_loader): tests every timeframe present in data/raw for each symbol,
recommends the best one, and works unchanged for gold / BTC / FX / stocks / commodities.
M5/M15 are auto-tested the moment you pull them (data/pull_mt5.py).

Run: python research/trade_report.py
"""
import sys, glob, os, re
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, timeframes, pipeline, cfg
from strategy import playbook
from strategy.smc import atr
from backtest.trade_sim import simulate_trades, trade_stats
from backtest.engine import BARS_PER_YEAR

RAW = ROOT / "data" / "raw"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)
IS_FRACTION = pipeline().get("is_fraction", 0.70)
HMM_MIN = pipeline().get("hmm_min_bars", 6000)
MIN_TRADES = pipeline().get("gate", {}).get("min_trades", 30)


def discover():
    return sorted({re.match(r"(.+)_H1\.parquet", os.path.basename(f)).group(1)
                   for f in glob.glob(str(RAW / "*_H1.parquet"))})


def backtest_tf(sym, tf):
    p = RAW / f"{sym}_{tf}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p).sort_index()
    sp = symbol_params(sym, df["close"])
    method = "hmm" if len(df) >= HMM_MIN else "adx"
    reg = playbook.regime_labels(df, method)
    ent = playbook.entries(df, regime=reg)
    ex = playbook.momentum_exit_signal(df)
    oos = slice(int(len(df) * IS_FRACTION), None)
    tr = simulate_trades(df.iloc[oos], ent.iloc[oos], atr(df, 14).iloc[oos], sp["cost"],
                         exit_signal=ex.iloc[oos], pip_size=sp["pip_size"], **playbook.EXIT)
    s = trade_stats(tr, BARS_PER_YEAR.get(tf, 252 * 24), tr["bars"].mean() if not tr.empty else 1)
    return dict(tf=tf, method=method, df=df, trades=tr, stats=s, sp=sp)


def save_blotter(sym, tf, tr, eq0, rpt, compound):
    """Add $ account columns + write trades_<sym>_<tf>.csv. Returns enriched df."""
    tr = tr.copy()
    bal, risk_l, pnl_l, bal_l = eq0, [], [], []
    for R in tr["R"]:
        risk_d = (bal if compound else eq0) * rpt
        pnl_d = R * risk_d; bal += pnl_d
        risk_l.append(round(risk_d, 4)); pnl_l.append(round(pnl_d, 4)); bal_l.append(round(bal, 4))
    tr["risk_$"], tr["pnl_$"], tr["balance_$"] = risk_l, pnl_l, bal_l
    for c in ("entry_time", "exit_time"):       # locale-proof dates (10-Apr-2025 06:00)
        if c in tr:
            tr[c] = pd.to_datetime(tr[c]).dt.strftime("%d-%b-%Y %H:%M")
    cols = ["entry_time", "side", "entry_px", "sl_px", "exit_px", "reason", "pips", "R",
            "risk_$", "pnl_$", "balance_$", "win"]
    tr[cols].to_csv(OUT_DIR / f"trades_{sym}_{tf}.csv", index=False)
    return tr, cols


def report(sym, results):
    qualified = [r for r in results if r["stats"] and r["stats"]["trades"] >= MIN_TRADES]
    # fall back to best-available (>=5 trades) so the report is still informative, flagged honestly
    ranked = sorted(qualified or [r for r in results if r["stats"] and r["stats"]["trades"] >= 5],
                    key=lambda r: r["stats"]["sharpe"], reverse=True)
    below_min = not qualified
    print("\n" + "#" * 80)
    print(f"#  {sym}  — TRADE REPORT")
    print("#" * 80)
    print("  Timeframe scan (out-of-sample, net of cost):")
    print(f"    {'TF':<5}{'gate':<6}{'trades':>7}{'win%':>7}{'pips':>9}{'Sharpe':>8}{'maxDD$':>9}")
    for r in results:
        s = r["stats"]
        if not s:
            print(f"    {r['tf']:<5}{r['method']:<6}{'(no trades)':>7}"); continue
        print(f"    {r['tf']:<5}{r['method']:<6}{s['trades']:>7}{100*s['win']:>6.0f}%"
              f"{s['total_pips']:>9.0f}{s['sharpe']:>8.2f}{s['dd']:>9.1f}")
    # write a CSV blotter for EVERY timeframe that has trades (M5/M15 auto-export once pulled)
    acc = cfg().get("account", {})
    eq0, rpt, compound = acc.get("starting_equity", 10.0), acc.get("risk_per_trade", 0.005), acc.get("compound", True)
    saved, present = [], {r["tf"] for r in results}
    for r in results:
        if r["stats"] and not r["trades"].empty:
            save_blotter(sym, r["tf"], r["trades"], eq0, rpt, compound)
            saved.append(f"output/trades_{sym}_{r['tf']}.csv")
    if saved:
        print(f"  CSVs written -> {', '.join(saved)}")
    pending = [tf for tf in timeframes() if tf not in present]   # e.g. M5/M15 if not pulled
    if pending:
        print(f"  PENDING (need data): {', '.join(pending)} — pull via data/pull_mt5.py, "
              f"then re-run to auto-write output/trades_{sym}_<tf>.csv")
    if not ranked:
        print("\n  >> No timeframe has enough trades yet — pull more / lower-TF data (M15/M5).")
        return
    best = ranked[0]; s = best["stats"]; sp = best["sp"]
    if below_min:
        print(f"\n  !! NOTE: best TF has only {s['trades']} OOS trades (< {MIN_TRADES} gate) — "
              f"DIRECTIONAL ONLY, not yet validated. Pull M15/M5 + multi-regime data.")
    print(f"\n  >> RECOMMENDED CHART: {sym} {best['tf']}  (regime gate: {best['method'].upper()})")
    print("  " + "-" * 70)
    print("  TRADE PLAN:")
    print(f"    Direction : LONG only (regime-gated continuation)")
    print(f"    Entry     : EMA20>EMA50 + bullish structure, in a TREND regime,")
    print(f"                NOT during a volatility spike or high-impact news window")
    print(f"    Stop-loss : {playbook.EXIT['stop_mult']} x ATR(14) below entry  (hard SL)")
    print(f"    Scale-out : bank {int(playbook.EXIT['partial_frac']*100)}% at +{playbook.EXIT['partial_at']}R, move stop to breakeven")
    print(f"    Exit      : MOMENTUM-RIDE — hold while close>EMA20, exit when momentum fades")
    print(f"    pip size  : {sp['pip_size']}   round-trip cost: {sp['cost']:.4f}")
    print("  " + "-" * 70)
    print("  BACKTEST RESULT (out-of-sample):")
    print(f"    Trades            : {s['trades']}   (WON {s['wins']} / LOST {s['losses']}  -> win rate {100*s['win']:.0f}%)")
    print(f"    Net pips captured : {s['total_pips']:.0f}")
    print(f"    Avg win / loss    : +{s['avg_win_pips']:.0f} pips  /  {s['avg_loss_pips']:.0f} pips   (payoff {s['payoff']:.2f}x)")
    print(f"    Biggest winner    : {s['max_R']:.1f}R   (R = multiple of risk)")
    print(f"    Profit factor     : {s['pf']:.2f}   expectancy {s['exp']:.2f}/trade   avg {s['avgR']:.2f}R")
    print(f"    Max drawdown      : ${s['dd']:.1f}   ({s['dd']/sp['pip_size']:.0f} pips)")
    print(f"    Avg hold          : {s['avg_bars']:.0f} bars   annualised Sharpe {s['sharpe']:.2f}")
    # ---- $ ACCOUNT VIEW for the recommended chart ----
    tr, cols = save_blotter(sym, best["tf"], best["trades"], eq0, rpt, compound)
    won = tr[tr["pnl_$"] > 0]["pnl_$"]; lost = tr[tr["pnl_$"] <= 0]["pnl_$"]
    bal = tr["balance_$"].iloc[-1]
    print("\n  ACCOUNT VIEW  (start ${:.2f}, risk {:.1f}%/trade{}):".format(
        eq0, rpt * 100, ", compounding" if compound else ""))
    print(f"    Ending balance    : ${bal:.2f}   ({(bal/eq0-1)*100:+.1f}% over {len(tr)} trades)")
    print(f"    Total won / lost  : +${won.sum():.2f} / -${abs(lost.sum()):.2f}")
    print(f"    Avg win / loss    : +${won.mean() if len(won) else 0:.3f} / -${abs(lost.mean()) if len(lost) else 0:.3f}")
    print(f"    Risk per trade    : ~${eq0*rpt:.3f} at start  (you never lose > {rpt*100:.1f}% per trade)")
    stop_dist = playbook.EXIT["stop_mult"] * float(atr(best["df"], 14).iloc[-1])
    contract = 100 if "XAU" in sym else 1
    min_lot_risk = 0.01 * contract * stop_dist
    if min_lot_risk > eq0 * rpt:
        print(f"    !! FEASIBILITY     : smallest 0.01-lot risks ~${min_lot_risk:.2f}, but your budget is "
              f"${eq0*rpt:.3f}. ${eq0:.0f} is TOO SMALL for {sym} at {best['tf']} — use a")
        print(f"                         cent/nano account, a lower TF (tighter $ stop), or more capital.")
    print("\n  LAST 10 TRADES (blotter, $ on a ${:.0f} account):".format(eq0))
    with pd.option_context("display.max_columns", None, "display.width", 220):
        print(tr[cols].tail(10).to_string(index=False))
    print(f"\n  full blotter -> output/trades_{sym}_{best['tf']}.csv")


def run():
    for sym in discover():
        results = [backtest_tf(sym, tf) for tf in timeframes()]
        results = [r for r in results if r is not None]
        if results:
            report(sym, results)


if __name__ == "__main__":
    run()
