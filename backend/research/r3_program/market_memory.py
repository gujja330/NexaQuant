"""R3 MARKET MEMORY v1 — has AEGIS seen this situation before?

THE QUESTION
------------
Not "which indicator should we add" but: for a given pre-entry state, what
earlier situations looked structurally similar, and what happened next?

THE TEST THAT DECIDES EVERYTHING (§5)
-------------------------------------
Before any outcome statistic is worth reading, a twin has to be a real object.
If Euclidean, cosine, correlation-distance and PCA-space each return a
DIFFERENT set of historical neighbours for the same query, then "twin" is an
artefact of the metric and every downstream number describes the metric rather
than the market. So top-k overlap across methods is computed FIRST, and a low
overlap produces NO_STABLE_MEMORY_STRUCTURE regardless of how good the outcome
separation looks.

THE LEAKAGE RULE §14 MAKES EXPLICIT
-----------------------------------
Future normalisation statistics are leakage too, not just future returns. A
robust scaler fitted over the whole sample encodes the future distribution into
every historical fingerprint. So the scaler and the PCA basis are fitted on an
EARLY window only, and queries are drawn strictly after it. That costs sample
size and is the only honest arrangement.

WHAT IS ACTUALLY AVAILABLE
--------------------------
Family coverage is bounded by the substrate, not by ambition:

  A stock trajectory   FULL      price bars, 1,245 India / 1,009 USA dates
  E market             FULL      derived from the cross-section
  D peers              PROXY     discovered co-movement communities; there are
                                 no sector labels in this repo to use instead
  F intermarket        USA ONLY  macro columns are null across India
  B R2 trajectory      3 DATES   confidence/rank movement needs sealed memory
  C sector             BLOCKED   India null, USA the literal string 'Unknown'
  G portfolio          3 DATES   sealed decisions only

Families B, C and G are not fabricated to fill the fingerprint.

GOVERNANCE
----------
Research only. R3 production writes 0. Nothing here promotes anything.
"""
from __future__ import annotations

import glob
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

SCHEMA_VERSION = "aegis.r3.market_memory.v1"
SEED = 20260916
EMBARGO_DAYS = 5

# state-transition lattice (§9)
LAGS = (20, 10, 5, 3, 1, 0)

METHODS = ("euclidean", "cosine", "correlation", "pca")
TOPK = (5, 10, 20, 50)

# Overlap below this means the neighbours are a property of the metric.
STABILITY_FLOOR = 0.30


# ── FINGERPRINTS (§2, §3) ─────────────────────────────────────────────
def build_fingerprints(panel: pd.DataFrame) -> dict:
    """Four representations kept SEPARATE (§3) rather than fused into a score.

    raw         level features as measured
    normalized  robust-scaled, scaler fitted on the early window only
    trajectory  the state at each lag in the lattice
    transition  the CHANGE between consecutive lags
    """
    stock = ["ret_1d", "ret_5d", "ret_10d", "ret_20d", "ret_60d",
             "vol_20", "vol_60", "vol_ratio", "dd_60", "pos_60",
             "skew_20", "kurt_20", "slope_20", "vol_ratio_5v20"]
    stock = [c for c in stock if c in panel.columns]
    return {"raw_columns": stock,
            "families": {
                "A_stock_trajectory": {"status": "FULL", "columns": stock},
                "B_r2_trajectory": {"status": "BLOCKED_DEPTH",
                                    "reason": "confidence/rank movement needs sealed "
                                              "memory; 3 dates exist"},
                "C_sector": {"status": "BLOCKED_DATA",
                             "reason": "India null, USA literally 'Unknown'"},
                "D_peers": {"status": "PROXY",
                            "reason": "discovered co-movement community, "
                                      "leave-target-out"},
                "E_market": {"status": "FULL",
                             "reason": "derived from the cross-section"},
                "F_intermarket": {"status": "PARTIAL_USA_ONLY",
                                  "reason": "macro columns null across India"},
                "G_portfolio": {"status": "BLOCKED_DEPTH",
                                "reason": "sealed decisions only, 3 dates"}}}


def add_market_family(panel: pd.DataFrame) -> pd.DataFrame:
    """Family E. Cross-sectional state per date, joined back to every row.

    Computed from the same date only, so it adds no future information.
    """
    g = panel.groupby("date")
    md = pd.DataFrame({
        "mkt_median_ret20": g["ret_20d"].median(),
        "mkt_dispersion_ret20": g["ret_20d"].std(),
        "mkt_breadth_pos": g["ret_20d"].apply(lambda s: float((s > 0).mean()) * 100.0),
        "mkt_median_vol20": g["vol_20"].median(),
        "mkt_median_dd60": g["dd_60"].median(),
    })
    p = panel.merge(md, left_on="date", right_index=True, how="left")
    # divergence: the stock against its own market, known at t
    p["div_ret20_vs_mkt"] = p["ret_20d"] - p["mkt_median_ret20"]
    p["div_vol20_vs_mkt"] = p["vol_20"] - p["mkt_median_vol20"]
    return p


MARKET_COLS = ["mkt_median_ret20", "mkt_dispersion_ret20", "mkt_breadth_pos",
               "mkt_median_vol20", "mkt_median_dd60",
               "div_ret20_vs_mkt", "div_vol20_vs_mkt"]


def transition_frame(panel: pd.DataFrame, cols: list,
                     lags=LAGS) -> pd.DataFrame:
    """§9 state transitions: the same state observed at T-20..T0.

    Built with groupby-shift on a per-ticker basis, so a lag never reaches
    across ticker boundaries, and never reaches forward.
    """
    p = panel.sort_values(["ticker", "date"]).copy()
    out = {}
    base = [c for c in cols if c in p.columns]
    for lg in lags:
        for c in base:
            out["%s_T%d" % (c, lg)] = p.groupby("ticker")[c].shift(lg)
    t = pd.DataFrame(out, index=p.index)
    # change-of-state fingerprint: consecutive differences along the lattice
    for i in range(len(lags) - 1):
        a, b = lags[i], lags[i + 1]
        for c in base:
            t["d_%s_%d_%d" % (c, a, b)] = t["%s_T%d" % (c, b)] - t["%s_T%d" % (c, a)]
    return pd.concat([p, t], axis=1)


# ── REPRESENTATION, FITTED ON THE PAST ONLY (§14) ─────────────────────
@dataclass
class Representation:
    columns: list
    center: np.ndarray
    scale: np.ndarray
    pca_components: Optional[np.ndarray]
    pca_mean: Optional[np.ndarray]
    fit_date_max: str
    fit_rows: int

    def normalize(self, X: np.ndarray) -> np.ndarray:
        return (X - self.center) / self.scale

    def pca(self, Xn: np.ndarray) -> np.ndarray:
        if self.pca_components is None:
            return Xn
        return (Xn - self.pca_mean) @ self.pca_components.T


def fit_representation(panel: pd.DataFrame, columns: list, fit_mask: np.ndarray,
                       n_components: int = 8) -> Representation:
    """Robust scaler + PCA basis fitted ONLY on the early window.

    A scaler fitted over the whole sample would encode the future distribution
    into every historical fingerprint - leakage that never shows up as a future
    return and so survives the obvious checks.
    """
    from sklearn.decomposition import PCA
    X = panel.loc[fit_mask, columns].to_numpy(dtype=float)
    ok = np.isfinite(X).all(axis=1)
    X = X[ok]
    med = np.median(X, axis=0)
    q1, q3 = np.percentile(X, 25, axis=0), np.percentile(X, 75, axis=0)
    iqr = np.where((q3 - q1) > 1e-9, q3 - q1, 1.0)
    Xn = (X - med) / iqr
    k = min(n_components, Xn.shape[1])
    p = PCA(n_components=k, random_state=SEED).fit(Xn)
    return Representation(
        columns=list(columns), center=med, scale=iqr,
        pca_components=p.components_, pca_mean=p.mean_,
        fit_date_max=str(pd.Timestamp(panel.loc[fit_mask, "date"].max()).date()),
        fit_rows=int(ok.sum()))


# ── MULTI-METHOD TWIN SEARCH (§4) ─────────────────────────────────────
def _neighbours(Q: np.ndarray, P: np.ndarray, metric: str, k: int,
                chunk: int = 100) -> np.ndarray:
    """Indices of the k nearest pool rows for each query under one metric.

    Distances are computed by the dot-product identity and selected with
    argpartition. The naive broadcast is O(n_query x n_pool x d) and asked for
    5.8 GiB on a 600 x 61,575 x 21 problem; this is O(n_query x n_pool) and runs
    in chunks so peak memory stays bounded whatever the pool size.
    """
    k = int(min(k, P.shape[0]))
    if metric == "euclidean":
        A, B = Q, P
    elif metric == "cosine":
        A = Q / (np.linalg.norm(Q, axis=1, keepdims=True) + 1e-12)
        B = P / (np.linalg.norm(P, axis=1, keepdims=True) + 1e-12)
    elif metric == "correlation":
        qc = Q - Q.mean(axis=1, keepdims=True)
        pc = P - P.mean(axis=1, keepdims=True)
        A = qc / (np.linalg.norm(qc, axis=1, keepdims=True) + 1e-12)
        B = pc / (np.linalg.norm(pc, axis=1, keepdims=True) + 1e-12)
    else:
        raise ValueError(metric)

    bsq = (B ** 2).sum(1)
    out = np.empty((A.shape[0], k), dtype=int)
    for s in range(0, A.shape[0], chunk):
        a = A[s:s + chunk]
        # cosine/correlation are unit-norm here, so squared euclidean on the
        # normalised vectors is a monotone function of the intended distance
        d = (a ** 2).sum(1)[:, None] + bsq[None, :] - 2.0 * (a @ B.T)
        part = np.argpartition(d, k - 1, axis=1)[:, :k]
        rows = np.arange(part.shape[0])[:, None]
        out[s:s + chunk] = part[rows, np.argsort(d[rows, part], axis=1)]
    return out


def twin_search(panel: pd.DataFrame, rep: Representation,
                query_idx: np.ndarray, pool_idx: np.ndarray,
                k: int = 50) -> dict:
    """Neighbours under each method, with the two exclusions that make a twin
    a twin: a different ticker, and a date far enough in the past.
    """
    cols = rep.columns
    X = panel[cols].to_numpy(dtype=float)
    dates = panel["date"].to_numpy()
    ticks = panel["ticker"].to_numpy()

    Xn = rep.normalize(X)
    Xp = rep.pca(Xn)

    res: dict = {}
    for method in METHODS:
        M = Xp if method == "pca" else Xn
        metric = "euclidean" if method in ("euclidean", "pca") else method
        out = np.full((len(query_idx), k), -1, dtype=int)
        # pool is shared, so mask per query by date and ticker afterwards
        cand = _neighbours(M[query_idx], M[pool_idx], metric, min(len(pool_idx), k * 12))
        for i, qi in enumerate(query_idx):
            limit = dates[qi] - np.timedelta64(EMBARGO_DAYS, "D")
            keep = []
            for j in cand[i]:
                pid = pool_idx[j]
                if ticks[pid] == ticks[qi] or dates[pid] >= limit:
                    continue
                keep.append(pid)
                if len(keep) >= k:
                    break
            out[i, :len(keep)] = keep
        res[method] = out
    return res


# ── TWIN STABILITY — THE DECIDING TEST (§5) ───────────────────────────
def twin_stability(twins: dict, topk=TOPK) -> dict:
    """Top-k Jaccard overlap between every pair of methods.

    This runs BEFORE any outcome statistic. If the methods disagree, the
    neighbours belong to the metric and nothing downstream is about the market.
    """
    methods = list(twins.keys())
    n_q = len(next(iter(twins.values())))
    out: dict = {"top_k": {}, "methods": methods, "n_queries": int(n_q)}
    for k in topk:
        pair_scores: dict = {}
        for a in range(len(methods)):
            for b in range(a + 1, len(methods)):
                ma, mb = methods[a], methods[b]
                vals = []
                for i in range(n_q):
                    A = {int(x) for x in twins[ma][i][:k] if x >= 0}
                    B = {int(x) for x in twins[mb][i][:k] if x >= 0}
                    if not A or not B:
                        continue
                    vals.append(len(A & B) / len(A | B))
                if vals:
                    pair_scores["%s|%s" % (ma, mb)] = round(float(np.mean(vals)), 4)
        allv = list(pair_scores.values())
        out["top_k"][str(k)] = {
            "pairwise_jaccard": pair_scores,
            "mean": round(float(np.mean(allv)), 4) if allv else None,
            "min": round(float(np.min(allv)), 4) if allv else None,
            "max": round(float(np.max(allv)), 4) if allv else None,
        }
    means = [v["mean"] for v in out["top_k"].values() if v["mean"] is not None]
    stable = bool(means) and min(means) >= STABILITY_FLOOR
    out["stability_floor"] = STABILITY_FLOOR
    out["verdict"] = "STABLE_TWINS" if stable else "NO_STABLE_MEMORY_STRUCTURE"
    out["reason"] = ("" if stable else
                     "Different similarity methods return largely different "
                     "historical neighbours for the same query, so a twin is a "
                     "property of the metric rather than of the market.")
    return out


def consensus_twins(twins: dict, min_methods: int = 3, k: int = 50) -> list:
    """Neighbours that MORE THAN ONE method agrees on.

    If consensus sets come back empty, that is itself the finding.
    """
    methods = list(twins.keys())
    n_q = len(twins[methods[0]])
    cons = []
    for i in range(n_q):
        cnt: dict = {}
        for m in methods:
            for x in twins[m][i][:k]:
                if x >= 0:
                    cnt[int(x)] = cnt.get(int(x), 0) + 1
        cons.append(sorted([x for x, c in cnt.items() if c >= min_methods]))
    return cons
