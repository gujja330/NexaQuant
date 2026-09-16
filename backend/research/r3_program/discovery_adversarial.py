"""R3 AI DISCOVERY LAB v1 — falsification tests.

WHY THIS FILE EXISTS SEPARATELY
-------------------------------
The discovery pass produced two apparent candidates. Both failed here, and
neither failure was visible from the discovery statistic alone:

  USA latent states, rank_corr +0.8   The correlation is Spearman over
                                      n_states POINTS. Sweeping the seed alone
                                      turns +0.8 into -0.2 on identical data,
                                      and the discovered state has a median run
                                      length of ONE sample - it changes at every
                                      observation. A state that never persists
                                      is a noise label, not a regime.

  USA graph stability, ARI 0.42       Persistence is real and enormous: z = 52.8
                                      against a shuffled null. But the ledger
                                      hypothesis was "stable enough to carry
                                      information", which silently merges two
                                      claims. Structure was confirmed;
                                      information was not, and the community
                                      term collapses to zero once the market is
                                      subtracted.

So these are not optional extras. A discovery statistic computed once, on one
seed, with no null to compare against, is a number - not a finding.
"""
from __future__ import annotations

import glob
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from backend.research.r3_program.discovery_lab import _read_bars, BARS_GLOB


# ── 1 · SEED / HYPERPARAMETER ROBUSTNESS ──────────────────────────────
def latent_state_robustness(panel: pd.DataFrame, outcome: str = "fwd_20d",
                            states=(3, 4, 5, 6),
                            seeds=(20260916, 7, 42, 1234, 99)) -> dict:
    """Sweep the two arbitrary choices and report the whole distribution.

    Reporting one configuration would be choosing a result.
    """
    import backend.research.r3_program.discovery_lab as dl
    import backend.research.r3_program.discovery_experiments as dx

    rows = []
    old = dl.SEED
    for ns in states:
        for sd in seeds:
            dl.SEED, dx.SEED = sd, sd
            try:
                ls = dx.latent_states(panel, n_states=ns, outcome=outcome)
                rows.append({"n_states": ns, "seed": sd,
                             "rank_corr": ls.get("train_test_rank_corr"),
                             "n_transitions": ls.get("n_transitions"),
                             "median_run_length": ls.get("median_run_length_samples")})
            except Exception as e:
                rows.append({"n_states": ns, "seed": sd, "rank_corr": None,
                             "error": str(e)[:80]})
    dl.SEED = dx.SEED = old
    rc = pd.Series([r["rank_corr"] for r in rows if r.get("rank_corr") is not None])
    runs = pd.Series([r["median_run_length"] for r in rows
                      if r.get("median_run_length") is not None])
    sign_flips = bool(len(rc) and rc.min() < 0 < rc.max())
    persists = bool(len(runs) and runs.median() > 2)
    return {
        "n_configs": len(rows), "configs": rows,
        "rank_corr_mean": None if rc.empty else round(float(rc.mean()), 4),
        "rank_corr_median": None if rc.empty else round(float(rc.median()), 4),
        "rank_corr_min": None if rc.empty else round(float(rc.min()), 4),
        "rank_corr_max": None if rc.empty else round(float(rc.max()), 4),
        "sign_flips_across_configs": sign_flips,
        "median_run_length_samples": None if runs.empty else float(runs.median()),
        "state_persists": persists,
        "verdict": ("ROBUST" if (not sign_flips and persists) else "FRAGILE"),
        "reason": ("Rank correlation changes sign across seeds and/or the state "
                   "changes at nearly every observation, so the apparent ordering "
                   "is not a property of the data."
                   if (sign_flips or not persists) else
                   "Ordering held across every seed and the state persists."),
        "caveat": ("Spearman here is computed over n_states POINTS. At 3-4 states "
                   "it can only take a handful of values and carries almost no "
                   "information regardless of its magnitude."),
    }


# ── 2 · NULL TEST FOR GRAPH PERSISTENCE ───────────────────────────────
def _communities(ret: pd.DataFrame, dates, lookback: int = 60, top: int = 6):
    import networkx as nx
    from networkx.algorithms import community as nxcom
    from sklearn.metrics import adjusted_rand_score
    prev, aris, mods = None, [], []
    for dt in dates:
        w = ret.loc[ret.index <= dt].tail(lookback).dropna(
            axis=1, thresh=int(lookback * 0.8))
        if w.shape[1] < 20:
            continue
        C = w.corr()
        G = nx.Graph()
        G.add_nodes_from(C.columns)
        for t in C.columns:
            s = C[t].drop(labels=[t]).sort_values(ascending=False)
            for peer, r in s.head(top).items():
                if np.isfinite(r) and r > 0:
                    G.add_edge(t, peer, weight=float(r))
        if G.number_of_edges() == 0:
            continue
        comms = list(nxcom.greedy_modularity_communities(G, weight="weight"))
        mods.append(float(nxcom.modularity(G, comms, weight="weight")))
        a = {n: i for i, c in enumerate(comms) for n in c}
        if prev is not None:
            sh = set(a) & set(prev)
            if len(sh) > 20:
                aris.append(adjusted_rand_score([a[n] for n in sh],
                                                [prev[n] for n in sh]))
        prev = a
    return (float(np.median(aris)) if aris else None,
            float(np.median(mods)) if mods else None)


def graph_null_test(root: Path, market: str, n_null: int = 5,
                    max_tickers: int = 200, n_dates: int = 60,
                    seed: int = 7) -> dict:
    """Is community persistence above chance?

    The null shuffles each stock's returns independently in time. That destroys
    co-movement while preserving every stock's own return distribution, so any
    surviving persistence is an artefact of the graph construction rather than
    real structure.
    """
    files = sorted(glob.glob(str(Path(root) / BARS_GLOB[market])))[:max_tickers]
    ser = {}
    for fp in files:
        t = Path(fp).stem.replace("_D1", "").lstrip("_").upper()
        d = _read_bars(fp)
        if d is not None:
            ser[t] = d["close"].astype(float)
    if len(ser) < 30:
        return {"status": "INSUFFICIENT_TICKERS", "n": len(ser)}
    px = pd.DataFrame(ser).sort_index()
    ret = np.log(px).diff()
    dates = sorted(ret.index)[-720::12][-n_dates:]

    real_ari, real_mod = _communities(ret, dates)
    rng = np.random.default_rng(seed)
    nulls, nmods = [], []
    for _ in range(n_null):
        sh = ret.copy()
        for c in sh.columns:
            v = sh[c].to_numpy()
            m = np.isfinite(v)
            vv = v[m].copy()
            rng.shuffle(vv)
            v[m] = vv
            sh[c] = v
        a, mo = _communities(sh, dates)
        if a is not None:
            nulls.append(a)
            nmods.append(mo)
    if not nulls or real_ari is None:
        return {"status": "NO_SNAPSHOTS"}
    nb = np.array(nulls)
    z = (real_ari - nb.mean()) / (nb.std() if nb.std() > 1e-9 else np.nan)
    return {"status": "OK", "market": market,
            "real_ari_median": round(real_ari, 4),
            "real_modularity_median": round(real_mod, 4),
            "null_ari_mean": round(float(nb.mean()), 4),
            "null_ari_sd": round(float(nb.std()), 4),
            "null_modularity_mean": round(float(np.mean(nmods)), 4),
            "z_vs_null": None if not np.isfinite(z) else round(float(z), 2),
            "structure_above_chance": bool(np.isfinite(z) and z > 3),
            "note": ("Above-chance persistence establishes that the STRUCTURE is "
                     "real. It says nothing about whether the structure predicts "
                     "anything - that is a separate test.")}


# ── 3 · DOES DISCOVERED STRUCTURE CARRY INFORMATION? ──────────────────
def community_information_test(root: Path, market: str, max_tickers: int = 250,
                               stride: int = 10, horizon: int = 20) -> dict:
    """Leave-target-out predictive test on DISCOVERED communities.

    This is a genuinely new hypothesis rather than a reopened one: the rejected
    sector family used LABELS, which do not exist in this repo (India null, USA
    the literal string 'Unknown'). Here the grouping is discovered from
    co-movement instead.

    The decisive column is `peer_minus_mkt`. A community term that only works
    before the market is subtracted is market beta wearing a community label.
    """
    import networkx as nx
    from networkx.algorithms import community as nxcom

    files = sorted(glob.glob(str(Path(root) / BARS_GLOB[market])))[:max_tickers]
    ser = {}
    for fp in files:
        t = Path(fp).stem.replace("_D1", "").lstrip("_").upper()
        d = _read_bars(fp)
        if d is not None:
            ser[t] = d["close"].astype(float)
    if len(ser) < 30:
        return {"status": "INSUFFICIENT_TICKERS", "n": len(ser)}
    px = pd.DataFrame(ser).sort_index()
    ret = np.log(px).diff()
    fwd = (px.shift(-horizon) / px - 1.0) * 100.0      # outcome, never an input
    trail = (px / px.shift(20) - 1.0) * 100.0          # known at t

    dates = list(ret.index)[-900::stride]
    rows = []
    for dt in dates:
        w = ret.loc[ret.index <= dt].tail(60).dropna(axis=1, thresh=48)
        if w.shape[1] < 30:
            continue
        C = w.corr()
        G = nx.Graph()
        G.add_nodes_from(C.columns)
        for t in C.columns:
            s = C[t].drop(labels=[t]).sort_values(ascending=False)
            for peer, r in s.head(6).items():
                if np.isfinite(r) and r > 0:
                    G.add_edge(t, peer, weight=float(r))
        if G.number_of_edges() == 0:
            continue
        comms = list(nxcom.greedy_modularity_communities(G, weight="weight"))
        tr, fw = trail.loc[dt], fwd.loc[dt]
        mkt = float(np.nanmedian(tr.reindex(C.columns)))
        for c in comms:
            mem = [n for n in c if n in tr.index and np.isfinite(tr.get(n, np.nan))]
            if len(mem) < 4:
                continue
            vals = tr[mem]
            tot = float(vals.sum())
            for n in mem:
                f = fw.get(n, np.nan)
                if not np.isfinite(f):
                    continue
                peer_excl = (tot - float(vals[n])) / (len(mem) - 1)   # LEAVE-TARGET-OUT
                rows.append({"date": dt, "ticker": n,
                             "peer_trail20_excl": peer_excl,
                             "own_trail20": float(tr[n]), "mkt_trail20": mkt,
                             "peer_minus_mkt": peer_excl - mkt,
                             "fwd": float(f)})
    if not rows:
        return {"status": "NO_ROWS"}
    d = pd.DataFrame(rows)
    cut = d["date"].quantile(0.65)
    trm = d["date"] <= cut
    tem = d["date"] > cut + pd.Timedelta(days=5)

    def rc(x, col):
        s = x[[col, "fwd"]].dropna()
        return (round(float(s[col].corr(s["fwd"], method="spearman")), 4)
                if len(s) > 100 else None)

    out = {"status": "OK", "market": market, "rows": int(len(d)),
           "tickers": int(d["ticker"].nunique()), "dates": int(d["date"].nunique()),
           "train_dates": int(d.loc[trm, "date"].nunique()),
           "test_dates": int(d.loc[tem, "date"].nunique()),
           "horizon_bars": horizon}
    for col in ("peer_trail20_excl", "peer_minus_mkt", "own_trail20", "mkt_trail20"):
        out[col] = {"train_rho": rc(d[trm], col), "test_rho": rc(d[tem], col)}
    pm = out["peer_minus_mkt"]
    informative = (pm["train_rho"] is not None and pm["test_rho"] is not None
                   and np.sign(pm["train_rho"]) == np.sign(pm["test_rho"])
                   and abs(pm["test_rho"]) > 0.05)
    out["carries_information"] = bool(informative)
    out["verdict"] = "INFORMATIVE" if informative else "NO_INCREMENTAL_INFORMATION"
    out["reason"] = ("" if informative else
                     "Once the market term is subtracted the community effect is "
                     "indistinguishable from zero and does not hold its sign out "
                     "of sample.")
    return out
