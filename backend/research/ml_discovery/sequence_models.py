"""R3-G Wave 1C · SEQUENCE MODELS · CEO 2026-09-08.

> "The question isn't 'Does Transformer AUC look good?' It is: does the
>  sequence model add information beyond LightGBM + simple baselines?"
>
> "If the Transformer/GRU/TCN adds nothing, we kill it."

THE QUESTION THIS ANSWERS
-------------------------
> "Can AEGIS identify, at entry, which apparently good candidates are
>  likely to reach +1R before their stop - and which ones will give back
>  their favourable excursion?"

Every target is run through the SAME five contenders so the comparison is
like-for-like:

    baseline      one-line heuristic (stop distance / volatility)
    logistic      linear, on the flattened window
    lightgbm      the incumbent tabular model
    tcn           dilated causal convolutions
    gru           recurrent state
    transformer   tiny encoder, 1 layer, 2 heads

A sequence model earns its place only by beating BOTH the baseline and
LightGBM. Anything else is killed.

MODELS ARE DELIBERATELY TINY
-----------------------------
India has 547 episodes; USA has 79. A network with more parameters than
episodes will fit them perfectly and learn nothing. Hidden widths are 16,
depth is 1-2, and the parameter count is REPORTED next to the episode
count so the ratio is visible rather than implied.

DATE CONCENTRATION IS REPORTED · CEO 2026-09-08
------------------------------------------------
> "We don't want a neural model to 'discover' a market-day effect simply
>  because many candidates occurred during the same few dates."

Ticker-disjoint folds stop a model memorising a NAME. They do nothing
about a model memorising a DAY - and this cohort has 547 episodes across
15 dates, so a single bad market day could masquerade as a learned
pattern. Every run therefore reports date concentration and episode
overlap, and a date-disjoint fold set is evaluated alongside the
ticker-disjoint one.

CAUSALITY
---------
The TCN is causal by construction (left-padded dilated convolutions); the
Transformer uses a causal mask. A sequence model that can see its own
future inside the window would post excellent numbers and mean nothing.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.sequence.v1"
FAMILY = "R3G_SEQUENCE_WAVE1C"

WINDOW = 20
SEQ_FEATURES = ["ret", "vol5", "dist_ma5", "dist_ma20", "rel_range"]
MIN_EPISODES_SEQUENCE = 200      # parameter-count discipline, not a governance gate
SEED = 20260908


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _d(v) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


# ── sequence construction · PIT-safe ────────────────────────────────────

def window_for(dates, closes, asof: date, window: int = WINDOW):
    """[window x n_features] using ONLY bars dated <= asof."""
    hi = -1
    for i, d in enumerate(dates):
        if d <= asof:
            hi = i
        else:
            break
    if hi < window + 20:
        return None
    rows = []
    for j in range(hi - window + 1, hi + 1):
        px = closes[j]
        prev = closes[j - 1]
        w5 = closes[max(0, j - 4):j + 1]
        w20 = closes[max(0, j - 19):j + 1]
        m5 = sum(w5) / len(w5)
        m20 = sum(w20) / len(w20)
        sd5 = math.sqrt(sum((c - m5) ** 2 for c in w5) / max(1, len(w5) - 1))
        rows.append([
            (px / prev - 1.0) * 100 if prev else 0.0,
            (sd5 / m5 * 100) if m5 else 0.0,
            (px / m5 - 1.0) * 100 if m5 else 0.0,
            (px / m20 - 1.0) * 100 if m20 else 0.0,
            (max(w5) - min(w5)) / m5 * 100 if m5 else 0.0,
        ])
    return rows


def build_dataset(root: Path, market: str) -> dict:
    """Episodes with a real stop, each carrying its price window."""
    from backend.research.cohort.entry_backfill import backfill
    from backend.research.cohort.exit_hazard import build_episodes
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    from backend.research.ml_discovery.temporal import _load_series

    rows = load_cohort(root, market)
    backfill(root, market, rows)
    eps = build_episodes(root, market, rows)

    cache, seqs, keep = {}, [], []
    for e in eps:
        t = e["ticker"]
        d = _d(e["entry_date"])
        if t not in cache:
            cache[t] = _load_series(root, market, t)
        s = cache[t]
        if s is None or d is None:
            continue
        w = window_for(s[0], s[1], d)
        if w is None:
            continue
        seqs.append(w)
        keep.append(e)
    return {"episodes": keep, "sequences": seqs}


def targets_for(eps: list) -> dict:
    """The multi-horizon matrix the CEO specified."""
    T = {}
    T["P_1R_before_stop"] = [1 if e["hit_1R_before_stop"] else 0 for e in eps]
    T["P_2R_before_stop"] = [1 if e["hit_2R_before_stop"] else 0 for e in eps]
    for h in (1, 3, 5, 10, 20):
        T[f"stop_hit_{h}d"] = [
            1 if (e["day_stop_hit"] is not None and e["day_stop_hit"] <= h)
            else 0 for e in eps]
    for h in (3, 5, 10, 20):
        T[f"reversal_{h}d"] = [
            1 if (e["day_reversal"] is not None and e["day_reversal"] <= h)
            else 0 for e in eps]
    return T


# ── fold construction ───────────────────────────────────────────────────

def _folds_by(keys: list, n_folds: int = 5):
    uniq = sorted(set(keys))
    if len(uniq) < n_folds:
        return []
    assign = {k: i % n_folds for i, k in enumerate(uniq)}
    out = []
    for f in range(n_folds):
        tr = [i for i, k in enumerate(keys) if assign[k] != f]
        te = [i for i, k in enumerate(keys) if assign[k] == f]
        if len(tr) > 30 and len(te) > 8:
            out.append((tr, te))
    return out


def concentration_report(eps: list) -> dict:
    """> "report date concentration and episode overlap explicitly." """
    dts = Counter(e["entry_date"] for e in eps)
    tks = Counter(e["ticker"] for e in eps)
    n = len(eps) or 1
    top_d, top_dc = (dts.most_common(1)[0] if dts else ("-", 0))
    return {
        "n_episodes": len(eps),
        "n_dates": len(dts),
        "n_tickers": len(tks),
        "episodes_per_date": round(n / max(1, len(dts)), 2),
        "top_date": top_d, "top_date_share_pct": round(top_dc / n * 100, 1),
        "top3_date_share_pct": round(
            sum(c for _, c in dts.most_common(3)) / n * 100, 1),
        "top_ticker_share_pct": round(
            (tks.most_common(1)[0][1] if tks else 0) / n * 100, 1),
        "date_concentration_warning": bool(top_dc / n > 0.25),
        "note": ("ticker-disjoint folds prevent memorising a NAME · they do "
                 "not prevent memorising a DAY, which is why the date-"
                 "disjoint fold set is evaluated alongside"),
    }


# ── metrics ─────────────────────────────────────────────────────────────

def _auc(y, p) -> Optional[float]:
    pos = [i for i, v in enumerate(y) if v == 1]
    neg = [i for i, v in enumerate(y) if v == 0]
    if not pos or not neg:
        return None
    order = sorted(range(len(p)), key=lambda i: p[i])
    rank = [0.0] * len(p)
    for r, i in enumerate(order, 1):
        rank[i] = r
    return round((sum(rank[i] for i in pos) - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)), 4)


def _brier(y, p) -> float:
    return round(sum((a - b) ** 2 for a, b in zip(y, p)) / max(1, len(y)), 4)


# ── models ──────────────────────────────────────────────────────────────

def _flat(seqs, idx):
    import numpy as np
    return np.array([[v for row in seqs[i] for v in row] for i in idx],
                    dtype=float)


def fit_logistic(seqs, y, tr, te):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    Xtr, Xte = _flat(seqs, tr), _flat(seqs, te)
    sc = StandardScaler().fit(Xtr)
    m = LogisticRegression(max_iter=2000, C=0.1)
    m.fit(sc.transform(Xtr), np.array(y)[tr])
    return list(m.predict_proba(sc.transform(Xte))[:, 1])


def fit_lightgbm(seqs, y, tr, te):
    import lightgbm as lgb
    import numpy as np
    m = lgb.LGBMClassifier(objective="binary", num_leaves=7, max_depth=3,
                           learning_rate=0.05, n_estimators=200,
                           min_child_samples=15, reg_lambda=1.0,
                           verbose=-1, random_state=SEED)
    m.fit(_flat(seqs, tr), np.array(y)[tr])
    return list(m.predict_proba(_flat(seqs, te))[:, 1])


def _torch_common(seqs, y, tr, te, build_fn, epochs: int = 60):
    import numpy as np
    import torch
    torch.manual_seed(SEED)
    X = np.array(seqs, dtype="float32")
    mu, sd = X[tr].mean((0, 1)), X[tr].std((0, 1)) + 1e-6
    X = (X - mu) / sd
    Y = np.array(y, dtype="float32")
    xtr = torch.tensor(X[tr]); ytr = torch.tensor(Y[tr])
    xte = torch.tensor(X[te])
    model, n_params = build_fn(X.shape[2])
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-3)
    pos = float(ytr.sum()); neg = float(len(ytr) - pos)
    w = torch.tensor([neg / max(1.0, pos)])
    lossf = torch.nn.BCEWithLogitsLoss(pos_weight=w)
    model.train()
    for _ in range(epochs):
        opt.zero_grad()
        out = model(xtr).squeeze(-1)
        loss = lossf(out, ytr)
        loss.backward()
        opt.step()
    model.eval()
    with torch.no_grad():
        p = torch.sigmoid(model(xte).squeeze(-1)).numpy()
    return list(p.astype(float)), n_params


def _build_tcn(n_feat):
    import torch.nn as nn

    class TCN(nn.Module):
        """Dilated CAUSAL convolutions · left padding only, so no timestep
        can see its own future."""
        def __init__(self):
            super().__init__()
            self.c1 = nn.Conv1d(n_feat, 12, 3, padding=2, dilation=1)
            self.c2 = nn.Conv1d(12, 12, 3, padding=4, dilation=2)
            self.act = nn.ReLU()
            self.head = nn.Linear(12, 1)

        def forward(self, x):
            h = x.transpose(1, 2)
            h = self.act(self.c1(h))[:, :, :x.shape[1]]
            h = self.act(self.c2(h))[:, :, :x.shape[1]]
            return self.head(h[:, :, -1])
    m = TCN()
    return m, sum(p.numel() for p in m.parameters())


def _build_gru(n_feat):
    import torch.nn as nn

    class GRU(nn.Module):
        def __init__(self):
            super().__init__()
            self.rnn = nn.GRU(n_feat, 16, batch_first=True)
            self.head = nn.Linear(16, 1)

        def forward(self, x):
            o, _ = self.rnn(x)
            return self.head(o[:, -1, :])
    m = GRU()
    return m, sum(p.numel() for p in m.parameters())


def _build_transformer(n_feat):
    import torch
    import torch.nn as nn

    class TF(nn.Module):
        """Tiny encoder with a CAUSAL mask."""
        def __init__(self):
            super().__init__()
            self.proj = nn.Linear(n_feat, 16)
            layer = nn.TransformerEncoderLayer(
                d_model=16, nhead=2, dim_feedforward=32,
                batch_first=True, dropout=0.1)
            self.enc = nn.TransformerEncoder(layer, num_layers=1)
            self.head = nn.Linear(16, 1)

        def forward(self, x):
            h = self.proj(x)
            n = x.shape[1]
            mask = torch.triu(torch.ones(n, n, dtype=torch.bool), diagonal=1)
            h = self.enc(h, mask=mask)
            return self.head(h[:, -1, :])
    m = TF()
    return m, sum(p.numel() for p in m.parameters())


MODELS = {
    "logistic": ("tabular", fit_logistic),
    "lightgbm": ("tabular", fit_lightgbm),
    "tcn": ("sequence", _build_tcn),
    "gru": ("sequence", _build_gru),
    "transformer": ("sequence", _build_transformer),
}


def run_target(seqs, eps, y, folds, allow_sequence: bool) -> dict:
    """Every contender, same folds, same target."""
    import numpy as np
    out, params = {}, {}
    # Baselines · one-line heuristics the model must beat.
    sd = [e["stop_distance_pct"] for e in eps]
    vol = [e.get("vol_20d_pct") or 0.0 for e in eps]
    for name, sign_vals in (("baseline_stop_distance", [-v for v in sd]),
                            ("baseline_volatility", vol)):
        a = [_auc([y[i] for i in te], [sign_vals[i] for i in te])
             for _, te in folds]
        a = [x for x in a if x is not None]
        out[name] = {"auc_mean": round(sum(a) / len(a), 4) if a else None,
                     "auc_folds": a}

    for name, (kind, fn) in MODELS.items():
        if kind == "sequence" and not allow_sequence:
            out[name] = {"skipped": "episodes below sequence minimum"}
            continue
        aucs, briers = [], []
        for tr, te in folds:
            if len(set(np.array(y)[tr])) < 2:
                continue
            try:
                if kind == "tabular":
                    p = fn(seqs, y, tr, te)
                else:
                    p, n_par = _torch_common(seqs, y, tr, te, fn)
                    params[name] = n_par
            except Exception as ex:
                out[name] = {"error": f"{type(ex).__name__}: {ex}"}
                break
            yt = [y[i] for i in te]
            a = _auc(yt, p)
            if a is not None:
                aucs.append(a)
                briers.append(_brier(yt, p))
        else:
            out[name] = {
                "auc_mean": round(sum(aucs) / len(aucs), 4) if aucs else None,
                "auc_folds": aucs,
                "brier_mean": round(sum(briers) / len(briers), 4) if briers else None,
                "n_params": params.get(name),
            }
    best_base = max((out[k].get("auc_mean") or 0)
                    for k in ("baseline_stop_distance", "baseline_volatility"))
    lgbm = out.get("lightgbm", {}).get("auc_mean") or 0
    verdicts = {}
    for name in ("tcn", "gru", "transformer"):
        a = out.get(name, {}).get("auc_mean")
        verdicts[name] = (
            "SKIPPED" if out.get(name, {}).get("skipped") else
            "ERROR" if out.get(name, {}).get("error") else
            "KEEP · beats LightGBM and baselines" if (a and a > lgbm and a > best_base)
            else "KILL · adds nothing beyond LightGBM/baselines")
    return {"results": out, "best_baseline_auc": round(best_base, 4),
            "lightgbm_auc": round(lgbm, 4), "sequence_verdicts": verdicts}
