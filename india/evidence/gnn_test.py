# india/gnn_test.py
"""
GRAPH NEURAL NETWORK test — a 2-layer GCN (pure torch, no torch-geometric).

The GNN idea: stocks influence each other, so aggregate each stock's features with its CORRELATED
neighbours before predicting. Per month: nodes = stocks, edges = trailing-120d return correlation.
Predict 'beat the median next month'. Train -> Dec-2023, test 2024-2026.

If letting stocks 'talk to their neighbours' doesn't lift AUC above ~0.50, the relationship
structure adds no selection signal either.

Run: python india/gnn_test.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from india.dataset import build_dataset, feature_list
from india.feature_engine import load_panels
from india.equity_engine import COST_BPS
from sklearn.metrics import roc_auc_score
import torch
import torch.nn as nn

torch.manual_seed(0)
FEATS = feature_list("full")
NF = len(FEATS)


def build_graphs(oos_start="2024-01-01"):
    df = build_dataset("M").copy()
    df["y"] = (df["fwd_ret"] > df.groupby(level="date")["fwd_ret"].transform("median")).astype(float)
    closes = load_panels()[0]
    dret = closes.pct_change()
    tr_mask = df.index.get_level_values("date") < pd.Timestamp(oos_start)
    mu, sd = df.loc[tr_mask, FEATS].mean(), df.loc[tr_mask, FEATS].std().replace(0, 1)
    months = sorted(df.index.get_level_values("date").unique())
    graphs = []
    for dt in months:
        g = df.xs(dt, level="date")
        g = g.dropna(subset=["y"])
        syms = [s for s in g.index if s in closes.columns]
        if len(syms) < 20:
            continue
        X = ((g.loc[syms, FEATS] - mu) / sd).fillna(0.0).values.astype(np.float32)
        y = g.loc[syms, "y"].values.astype(np.float32)
        fwd = g.loc[syms, "fwd_ret"].values.astype(np.float32)
        # adjacency from trailing 120d return correlation
        win = dret[syms].loc[:dt].tail(120)
        C = win.corr().fillna(0.0).values
        C = np.clip(C, 0, None)                       # keep positive correlations
        np.fill_diagonal(C, 1.0)
        D = np.diag(1.0 / np.sqrt(C.sum(1) + 1e-9))
        A = (D @ C @ D).astype(np.float32)            # symmetric-normalized
        graphs.append((torch.tensor(X), torch.tensor(A), torch.tensor(y), fwd, dt))
    return graphs


class GCN(nn.Module):
    def __init__(s, h=48):
        super().__init__(); s.w1 = nn.Linear(NF, h); s.w2 = nn.Linear(h, h); s.out = nn.Linear(h, 1)
        s.act = nn.ReLU(); s.drop = nn.Dropout(0.3)
    def forward(s, X, A):
        h = s.act(A @ s.w1(X)); h = s.drop(h)
        h = s.act(A @ s.w2(h)); return s.out(h).squeeze(-1)


if __name__ == "__main__":
    print("=" * 64)
    print("  GRAPH NEURAL NETWORK (GCN) — stocks aggregate correlated neighbours")
    print("=" * 64)
    graphs = build_graphs()
    tr = [g for g in graphs if g[4] < pd.Timestamp("2024-01-01")]
    te = [g for g in graphs if g[4] >= pd.Timestamp("2024-01-01")]
    print(f"  train graphs {len(tr)}   test graphs {len(te)}   nodes/graph ~{graphs[-1][0].shape[0]}")
    model = GCN(); opt = torch.optim.Adam(model.parameters(), lr=5e-3, weight_decay=1e-4)
    lossf = nn.BCEWithLogitsLoss()
    for ep in range(60):
        model.train()
        for X, A, y, _, _ in tr:
            opt.zero_grad(); loss = lossf(model(X, A), y); loss.backward(); opt.step()
    model.eval()
    ally, allp, rets = [], [], []
    with torch.no_grad():
        for X, A, y, fwd, dt in te:
            p = torch.sigmoid(model(X, A)).numpy()
            ally += list(y.numpy()); allp += list(p)
            k = min(10, len(p)); top = np.argsort(p)[-k:]
            rets.append(fwd[top].mean() - COST_BPS / 1e4)
    auc = roc_auc_score(ally, allp)
    s = pd.Series(rets); eq = float((1 + s).prod()); yrs = len(s) * 21 / 252
    cagr = 100 * (eq ** (1 / max(yrs, .1)) - 1)
    print(f"\n  GCN  AUC {auc:.3f}   top10 CAGR {cagr:.1f}%   Rs1L -> Rs{eq*1e5:,.0f}")
    print(f"  NIFTY            CAGR 10.7%   Rs1L -> Rs126,000")
    print(f"\n  AUC ~0.50 => neighbour/correlation structure adds no selection signal either.")
