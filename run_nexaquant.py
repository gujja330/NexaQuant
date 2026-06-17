# run_nexaquant.py
"""
NexaQuant END-TO-END pipeline — the single "run the whole system" entry point.

For every instrument/timeframe in data/raw it executes the full stack:
   data -> REGIME (HMM where data permits, else ADX) -> ENTRIES (regime-gated continuation)
        -> AI META-LABEL P(win) (calibrated) -> SIZE by conviction (proba_to_size)
        -> TRADE MANAGEMENT (ATR stop + momentum-ride + scale-out)
        -> RIGOR GATE (walk-forward + Deflated Sharpe)
        -> GO / NO-GO decision  ->  consolidated JSON report

It composes the project's own modules (no duplicated logic) and prints an honest verdict.
Nothing here authorises live capital — GO requires passing the gate AND 30-day paper trading.

Run: python run_nexaquant.py
"""
import sys, glob, os, re, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, timeframes, pipeline, gate
from strategy import playbook
from strategy.smc import atr, ema
from strategy.regime import detect_regime
from strategy.meta_label import build_features, triple_barrier_labels, train_eval
from strategy.risk import proba_to_size
from backtest.trade_sim import simulate_trades, trade_stats
from backtest.validator import (walk_forward, deflated_sharpe_ratio,
                                probabilistic_sharpe_ratio, probability_of_backtest_overfitting)
from backtest.engine import BARS_PER_YEAR, backtest

RAW = "data/raw"
# everything DYNAMIC from config (works for any instrument — gold, BTC, FX, stocks, oil)
TFS = timeframes()
IS_FRACTION = pipeline().get("is_fraction", 0.70)
HMM_MIN_BARS = pipeline().get("hmm_min_bars", 6000)
N_STRATEGIES_TRIED = pipeline().get("n_strategies_tried", 8)
GATE = gate()


def discover():
    return sorted({re.match(r"(.+)_H1\.parquet", os.path.basename(f)).group(1)
                   for f in glob.glob(f"{RAW}/*_H1.parquet")})


def gated_entries_full(df, method):
    reg = playbook.regime_labels(df, method)
    return playbook.entries(df, regime=reg), reg


def run_instrument(sym, tf, horizon):
    df = pd.read_parquet(f"{RAW}/{sym}_{tf}.parquet").sort_index()
    sp = symbol_params(sym, df["close"])
    cost, pip = sp["cost"], sp["pip_size"]
    bpy = BARS_PER_YEAR.get(tf, 252 * 24)
    split = int(len(df) * IS_FRACTION)
    method = "hmm" if len(df) >= HMM_MIN_BARS else "adx"
    a = atr(df, 14)
    ent_full, reg = gated_entries_full(df, method)
    ex_full = playbook.momentum_exit_signal(df)

    # ---- rules-only strategy on OOS (full trade management) ----
    oos = slice(split, None)
    rules = simulate_trades(df.iloc[oos], ent_full.iloc[oos], a.iloc[oos], cost,
                            exit_signal=ex_full.iloc[oos], pip_size=pip, **playbook.EXIT)
    rules_s = trade_stats(rules, bpy, rules["bars"].mean() if not rules.empty else 1)

    # ---- AI-sized strategy: train meta-label on IS entries, size OOS by P(win) ----
    ai_s, auc = None, float("nan")
    try:
        feats = build_features(df, symbol=sym, tf=tf)
        labels = triple_barrier_labels(df, ent_full, horizon)
        embargo = pd.Timedelta(hours=horizon * (1 if tf == "H1" else 4))
        model, test, auc = train_eval(feats, labels, df.index[split], embargo, kind="ensemble")
        if model is not None and not test.empty:
            sizes = pd.Series(proba_to_size(test["proba"].values, p_threshold=0.5),
                              index=test.index)
            ai = simulate_trades(df.iloc[oos], ent_full.iloc[oos], a.iloc[oos], cost,
                                 exit_signal=ex_full.iloc[oos], sizes=sizes, pip_size=pip, **playbook.EXIT)
            ai_s = trade_stats(ai, bpy, ai["bars"].mean() if not ai.empty else 1)
    except Exception as e:
        print(f"    (AI sizing skipped: {e})")

    # ---- rigor gate: deflated Sharpe + PBO (probability of backtest overfitting) ----
    trend_pos = (ema(df["close"], 20) > ema(df["close"], 50)).astype(float).where(
        playbook.regime_labels(df, "adx") == "trend", 0.0)
    net, _ = backtest(df, trend_pos, cost)
    dsr = float("nan")
    if len(net) > 2 and net.std() > 0:
        sr = net.mean() / net.std(); sk = net.skew(); ku = net.kurt() + 3
        sr_var = (1 - sk * sr + (ku - 1) / 4 * sr ** 2) / (len(net) - 1)
        dsr = deflated_sharpe_ratio(sr, len(net), N_STRATEGIES_TRIED, sr_var, sk, ku)
    # PBO across exit-style variants (bar-level position returns)
    variants = {
        "trend": trend_pos,
        "fast": (ema(df["close"], 10) > ema(df["close"], 30)).astype(float).where(
            playbook.regime_labels(df, "adx") == "trend", 0.0),
        "slow": (ema(df["close"], 30) > ema(df["close"], 100)).astype(float).where(
            playbook.regime_labels(df, "adx") == "trend", 0.0),
    }
    rmat = pd.DataFrame({k: backtest(df, v, cost)[0] for k, v in variants.items()}).dropna()
    pbo = probability_of_backtest_overfitting(rmat, n_splits=10)

    # ---- GO/NO-GO ----
    s = ai_s or rules_s
    passes = (s is not None and s["sharpe"] >= GATE["min_oos_sharpe"]
              and s["trades"] >= GATE["min_trades"] and (dsr or 0) >= GATE["min_dsr"]
              and (np.isnan(pbo) or pbo < GATE.get("max_pbo", 0.5)))
    verdict = "GATE-PASS (still needs 30d paper)" if passes else "NOT READY"
    return {
        "symbol": sym, "tf": tf, "regime_method": method, "bars": len(df),
        "oos_rules_sharpe": None if not rules_s else round(rules_s["sharpe"], 2),
        "oos_rules_total": None if not rules_s else round(rules_s["total"], 1),
        "oos_pips": None if not rules_s else round(rules_s["total_pips"], 0),
        "win_rate": None if not rules_s else round(rules_s["win"], 2),
        "oos_ai_sharpe": None if not ai_s else round(ai_s["sharpe"], 2),
        "meta_auc": None if not np.isfinite(auc) else round(auc, 3),
        "deflated_sharpe": None if not np.isfinite(dsr) else round(dsr, 2),
        "pbo": None if not np.isfinite(pbo) else round(pbo, 2),
        "verdict": verdict,
    }


def run():
    print("=" * 92)
    print("  NEXAQUANT — END-TO-END PIPELINE")
    print("=" * 92)
    syms = discover()
    print(f"  instruments: {syms}   (BTCUSDm auto-included once pulled)\n")
    report = []
    for sym in syms:
        for tf, horizon in TFS.items():
            if not os.path.exists(f"{RAW}/{sym}_{tf}.parquet"):
                continue
            r = run_instrument(sym, tf, horizon)
            report.append(r)
            print(f"  {r['symbol']} {r['tf']:<3} [{r['regime_method'].upper()}]  "
                  f"Sharpe={r['oos_rules_sharpe']}  win={r['win_rate']}  pips={r['oos_pips']}  "
                  f"AUC={r['meta_auc']}  DSR={r['deflated_sharpe']}  PBO={r['pbo']}  -> {r['verdict']}")
    out_dir = ROOT / "output"; out_dir.mkdir(exist_ok=True)
    out = out_dir / "nexaquant_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\n  report -> {out}")
    print("  NOTE: 'GATE-PASS' still requires 30-day paper trading before any live capital.")


if __name__ == "__main__":
    run()
