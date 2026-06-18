# india/ai_meta.py
"""
AI META-LABEL for Indian equities — the honest "AI + technicals (+ fundamentals later)" layer.

Idea (Lopez de Prado meta-labeling): the strategy decides the DIRECTION (trend/breakout entry);
a machine-learning model decides P(this trade WINS), so we can FILTER weak signals and size up
strong ones. Trained on the POOLED trade set across all 25 NSE stocks (~2000 events = real data,
unlike the thin gold/BTC set), with a TIME split (train early years, test later) so there's no
look-ahead. Honest gate: we only use it if test AUC shows real skill (>~0.55); else we don't.

Features at each entry (technical): multi-horizon momentum, realized vol, ADX, RSI, distance
from EMA20 and the 200-DMA, trade side. (Fundamentals can be added once point-in-time data
exists; today they're a live snapshot only.)

Run: python india/ai_meta.py
"""
import sys, glob, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params
from strategy import playbook, breakout
from strategy.smc import atr, ema
from strategy.regime import adx
from strategy.meta_label import rsi
from backtest.trade_sim import simulate_trades

RAW = ROOT / "data" / "raw" / "india"


def features_for(df):
    """Technical feature panel aligned to df.index (causal)."""
    c = df["close"]
    f = pd.DataFrame(index=df.index)
    f["ret_20"] = c.pct_change(20)
    f["ret_60"] = c.pct_change(60)
    f["ret_120"] = c.pct_change(120)
    f["vol_20"] = c.pct_change().rolling(20).std()
    f["adx_14"] = adx(df, 14)
    f["rsi_14"] = rsi(c, 14)
    f["ema_dist"] = c / ema(c, 20) - 1.0
    f["ma200_dist"] = c / c.rolling(200).mean() - 1.0
    return f


def build_dataset():
    X, meta = [], []
    for fpath in sorted(glob.glob(str(RAW / "*_D1.parquet"))):
        sym = os.path.basename(fpath).replace("_D1.parquet", "")
        if sym == "fundamentals":
            continue
        df = pd.read_parquet(fpath).sort_index()
        sp = symbol_params(sym, df["close"]); a = atr(df, 14); reg = playbook.regime_labels(df, "adx")
        feats = features_for(df)
        for edge in ("trend", "breakout"):
            for side, sd in (("long", 1), ("short", -1)):
                ent = playbook.entries(df, side=side, regime=reg) if edge == "trend" \
                      else breakout.entries(df, side=side, n=20)
                ex = playbook.momentum_exit_signal(df, side=side)
                tr = simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=sd, **playbook.EXIT)
                if tr.empty:
                    continue
                fe = feats.reindex(pd.to_datetime(tr["entry_time"])).reset_index(drop=True)
                fe["side"] = sd
                fe["_date"] = pd.to_datetime(tr["entry_time"]).values
                fe["_win"] = (tr["R"].values > 0).astype(int)
                fe["_R"] = tr["R"].values
                X.append(fe)
    data = pd.concat(X, ignore_index=True).dropna()
    return data


def main():
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import roc_auc_score, brier_score_loss

    data = build_dataset().sort_values("_date").reset_index(drop=True)
    feat_cols = [c for c in data.columns if not c.startswith("_")]
    n = len(data); cut = int(n * 0.70)            # TIME split: train early, test late
    tr, te = data.iloc[:cut], data.iloc[cut:]
    print(f"AI META-LABEL (India) — {n} pooled trades, train {len(tr)} / test {len(te)}")
    print(f"  base win-rate: train {100*tr['_win'].mean():.1f}%  test {100*te['_win'].mean():.1f}%")

    base = HistGradientBoostingClassifier(max_depth=3, max_iter=300, learning_rate=0.05,
                                          l2_regularization=1.0, random_state=0)
    model = CalibratedClassifierCV(base, method="isotonic", cv=3)
    model.fit(tr[feat_cols], tr["_win"])
    p = model.predict_proba(te[feat_cols])[:, 1]

    auc = roc_auc_score(te["_win"], p); brier = brier_score_loss(te["_win"], p)
    print(f"\n  TEST AUC = {auc:.3f}   Brier = {brier:.3f}   "
          f"({'SKILL' if auc > 0.55 else 'no real skill yet'})")

    # does filtering by P(win) improve the book vs taking ALL test trades?
    print(f"\n  {'filter':<18}{'trades':>7}{'win%':>7}{'avgR':>7}{'sumR':>8}")
    print(f"  {'take ALL':<18}{len(te):>7}{100*te['_win'].mean():>6.0f}%{te['_R'].mean():>7.2f}{te['_R'].sum():>8.1f}")
    for thr in (0.50, 0.55, 0.60):
        m = p >= thr
        if m.sum() < 10:
            continue
        sub = te[m]
        print(f"  {'P(win) >= '+str(thr):<18}{int(m.sum()):>7}{100*sub['_win'].mean():>6.0f}%"
              f"{sub['_R'].mean():>7.2f}{sub['_R'].sum():>8.1f}")

    # feature importance (permutation-free proxy: correlation of feature with win on test)
    print("\n  top features (|corr| with win, test):")
    cor = te[feat_cols].apply(lambda s: s.corr(te["_win"])).abs().sort_values(ascending=False)
    print("   ", ", ".join(f"{k}={cor[k]:+.2f}" for k in cor.head(6).index))
    print("\n  VERDICT: use the model to filter/size ONLY if AUC>0.55 AND P(win) filtering lifts")
    print("           avgR without gutting trade count. Else keep the pure factor engine (honest).")


if __name__ == "__main__":
    main()
