# research/confidence_sizing_test.py
"""
TEST: does increasing lot size when we're CONFIDENT actually help — or just lever up risk?

On the robust config (BTC H4, regime-aware LONG+SHORT), compare three sizing schemes
year-by-year (OOS, net of cost):
  A. FLAT          : same size every trade (baseline)
  B. ADX-confidence: size scales with trend strength (stronger trend -> bigger, capped 3x)
  C. AI-confidence : size scales with the meta-label P(win) (calibrated conviction)

Key read: scaling size raises RETURN, but only helps if it ALSO raises SHARPE (risk-adjusted).
If Sharpe is flat/worse, confidence-scaling is just leverage (more return AND more drawdown),
not skill. Honest verdict printed per scheme.

Run: python research/confidence_sizing_test.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, pipeline
from strategy import playbook
from strategy.smc import atr
from strategy.regime import adx
from strategy.meta_label import build_features, triple_barrier_labels, train_eval
from strategy.risk import proba_to_size
from backtest.trade_sim import simulate_trades, trade_stats
from backtest.engine import BARS_PER_YEAR

RAW = ROOT / "data" / "raw"
SYM, TF, HORIZON = "BTCUSDm", "H4", 12


def adx_confidence(df, cap=3.0):
    """Size 1x..cap scaled by trend strength (ADX): more confident in stronger trends."""
    a = adx(df, 14)
    return (1.0 + ((a - 25.0) / 15.0).clip(0, cap - 1)).fillna(1.0)


def run():
    df = pd.read_parquet(RAW / f"{SYM}_{TF}.parquet").sort_index()
    sp = symbol_params(df["close"].name and SYM, df["close"]); bpy = BARS_PER_YEAR[TF]
    reg = playbook.regime_labels(df, "hmm")
    a = atr(df, 14)
    lent = playbook.entries(df, side="long", regime=reg)
    lex = playbook.momentum_exit_signal(df, side="long")
    adx_size = adx_confidence(df)

    # AI confidence: train meta-label on pre-2024, predict, map P(win)->size multiplier
    ai_size = pd.Series(1.0, index=df.index)
    try:
        feats = build_features(df, symbol=SYM, tf=TF)
        labels = triple_barrier_labels(df, lent, HORIZON)
        split = df.index[int(len(df) * 0.5)]
        _, test, auc = train_eval(feats, labels, split, pd.Timedelta(hours=HORIZON * 4), kind="ensemble")
        if not test.empty:
            # scale 0.5x..3x by conviction (not skip) so we always trade but size by P(win)
            m = (0.5 + 3.0 * (test["proba"] - 0.5).clip(0, 1)).clip(0.5, 3.0)
            ai_size.loc[test.index] = m
            print(f"  (meta-label AUC={auc:.3f})")
    except Exception as e:
        print(f"  (AI sizing unavailable: {e})")

    schemes = {"A flat": None, "B ADX-confidence": adx_size, "C AI-confidence": ai_size}
    years = sorted(df.index.year.unique())[1:]
    print("=" * 86)
    print(f"  CONFIDENCE SIZING — {SYM} {TF} long (regime-gated), OOS by year")
    print("=" * 86)
    print(f"    {'scheme':<18}{'tot ret%':>10}{'Sharpe':>9}{'maxDD%':>9}{'verdict'}")
    base_sharpe = None
    for name, sizes in schemes.items():
        eq, peak, dd, rets, sh_acc = 1.0, 1.0, 0.0, [], []
        all_tr = []
        for ty in years:
            mask = df.index.year == ty
            if mask.sum() < 50:
                continue
            tr = simulate_trades(df[mask], lent[mask], a[mask], sp["cost"], exit_signal=lex[mask],
                                 sizes=(sizes[mask] if sizes is not None else None),
                                 pip_size=sp["pip_size"], side=1, **playbook.EXIT)
            if not tr.empty:
                all_tr.append(tr)
        if not all_tr:
            print(f"    {name:<18}(no trades)"); continue
        tr = pd.concat(all_tr)
        notional = df["close"].iloc[int(len(df) * 0.2)]
        s = trade_stats(tr, bpy, tr["bars"].mean())
        ret = 100 * s["total"] / notional
        if name.startswith("A"):
            base_sharpe = s["sharpe"]
            verdict = "(baseline)"
        else:
            verdict = "HELPS (Sharpe up)" if s["sharpe"] > base_sharpe + 0.05 else \
                      "just leverage (Sharpe flat/down)"
        print(f"    {name:<18}{ret:>10.1f}{s['sharpe']:>9.2f}{100*s['dd']/notional:>8.1f}%   {verdict}")
    print("\n  NOTE: bigger size on confident trades only adds VALUE if Sharpe rises; otherwise")
    print("        it's leverage (scales profit AND drawdown together). The verdict column says which.")


if __name__ == "__main__":
    run()
