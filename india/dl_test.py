# india/dl_test.py
"""
DEEP LEARNING test — LSTM + Transformer + deep MLP on the monthly feature panel.
Sequence framing: for each stock, use the last 12 months of the 31 features to predict whether
it BEATS the median stock next month (balanced 50/50). Train -> Dec-2023, test 2024-01 -> 2026
(single split; monthly DL retrain is too slow). Report AUC + top-10 portfolio CAGR vs Nifty.

Honest note: DL shines with massive data; on 220 stocks x ~65 months it can overfit. We let the
OOS numbers speak. Needs torch.

Run: python india/dl_test.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.dataset import build_dataset, feature_list
from india.equity_engine import COST_BPS
from sklearn.metrics import roc_auc_score

import torch
import torch.nn as nn

torch.manual_seed(0)
FEATS = feature_list("full")
L = 12          # sequence length (months)
NF = len(FEATS)


def build_sequences(oos_start="2024-01-01"):
    df = build_dataset("M").copy()
    df["y"] = (df["fwd_ret"] > df.groupby(level="date")["fwd_ret"].transform("median")).astype(float)
    dates = sorted(df.index.get_level_values("date").unique())
    # standardize features on pre-OOS rows
    tr_mask = df.index.get_level_values("date") < pd.Timestamp(oos_start)
    mu = df.loc[tr_mask, FEATS].mean(); sd = df.loc[tr_mask, FEATS].std().replace(0, 1)
    Z = ((df[FEATS] - mu) / sd).fillna(0.0)
    Z["y"] = df["y"]; Z["fwd_ret"] = df["fwd_ret"]
    seqs = {"tr": [], "te": []}
    for sym, g in Z.groupby(level="symbol"):
        g = g.sort_index()
        dts = g.index.get_level_values("date")
        arr = g[FEATS].values
        for i in range(L - 1, len(g)):
            t = dts[i]
            y = g["y"].iloc[i]
            if not np.isfinite(y):
                continue
            window = arr[i - L + 1: i + 1]
            rec = (window.astype(np.float32), np.float32(y), t, sym, np.float32(g["fwd_ret"].iloc[i]))
            seqs["tr" if t < pd.Timestamp(oos_start) else "te"].append(rec)
    return seqs


class LSTMNet(nn.Module):
    def __init__(s):
        super().__init__(); s.lstm = nn.LSTM(NF, 48, batch_first=True); s.fc = nn.Linear(48, 1)
    def forward(s, x):
        o, _ = s.lstm(x); return s.fc(o[:, -1]).squeeze(-1)


class TransformerNet(nn.Module):
    def __init__(s):
        super().__init__(); s.proj = nn.Linear(NF, 48)
        layer = nn.TransformerEncoderLayer(48, 4, 96, batch_first=True, dropout=0.1)
        s.enc = nn.TransformerEncoder(layer, 2); s.fc = nn.Linear(48, 1)
    def forward(s, x):
        h = s.enc(s.proj(x)); return s.fc(h.mean(1)).squeeze(-1)


class DeepMLP(nn.Module):
    def __init__(s):
        super().__init__(); s.net = nn.Sequential(
            nn.Linear(NF, 128), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, 1))
    def forward(s, x):
        return s.net(x[:, -1]).squeeze(-1)         # last month only (tabular)


def train_eval(model, seqs, epochs=40):
    Xtr = torch.tensor(np.stack([r[0] for r in seqs["tr"]]))
    ytr = torch.tensor(np.array([r[1] for r in seqs["tr"]]))
    Xte = torch.tensor(np.stack([r[0] for r in seqs["te"]]))
    yte = np.array([r[1] for r in seqs["te"]])
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    lossf = nn.BCEWithLogitsLoss()
    n = len(Xtr); idx = np.arange(n)
    for ep in range(epochs):
        model.train(); np.random.shuffle(idx)
        for b in range(0, n, 512):
            bi = idx[b:b + 512]
            opt.zero_grad(); out = model(Xtr[bi]); loss = lossf(out, ytr[bi]); loss.backward(); opt.step()
    model.eval()
    with torch.no_grad():
        p = torch.sigmoid(model(Xte)).numpy()
    return p, yte


def portfolio(seqs, p, topn=10):
    te = pd.DataFrame({"date": [r[2] for r in seqs["te"]], "fwd_ret": [r[4] for r in seqs["te"]], "p": p})
    rets = [g.nlargest(topn, "p")["fwd_ret"].mean() - COST_BPS / 1e4 for _, g in te.groupby("date")]
    s = pd.Series(rets); eq = float((1 + s).prod()); yrs = len(s) * 21 / 252
    return 100 * (eq ** (1 / max(yrs, .1)) - 1), s.mean() / (s.std() + 1e-12) * np.sqrt(12)


if __name__ == "__main__":
    print("=" * 70)
    print("  DEEP LEARNING — LSTM / Transformer / deep MLP (OOS 2024-2026)")
    print("=" * 70)
    seqs = build_sequences()
    print(f"  train windows {len(seqs['tr']):,}   test windows {len(seqs['te']):,}   seq_len {L}, feats {NF}")
    print(f"  {'model':<16}{'AUC':>8}{'top10 CAGR':>13}{'Sharpe':>8}")
    print("  " + "-" * 44)
    for name, M in (("LSTM", LSTMNet), ("Transformer", TransformerNet), ("DeepMLP", DeepMLP)):
        p, yte = train_eval(M(), seqs)
        auc = roc_auc_score(yte, p)
        cagr, sh = portfolio(seqs, p)
        print(f"  {name:<16}{auc:>8.3f}{cagr:>12.1f}%{sh:>8.2f}")
    print(f"  {'NIFTY':<16}{'':>8}{10.7:>12.1f}%{0.80:>8.2f}")
    print("\n  (AUC ~0.50 = the sequence models find no signal either; >0.53 with CAGR>Nifty = real.)")
