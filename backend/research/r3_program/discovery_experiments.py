"""R3 AI DISCOVERY LAB v1 — the five priority experiments (§17).

A  trajectory archetypes + analogue search / failure twins
B  latent market-state discovery
C  contradiction detection
D  dynamic relational graph
E  counterfactual entry timing

Each experiment answers three questions about anything it finds, because a
cluster that fails any of them is not a discovery:

  IS IT REAL?        does it survive a chronological train/embargo/test split
  IS IT NEW?         can two ordinary indicators reproduce it
  IS IT STABLE?      does the ordering persist out of sample

Splits are over DATES, never rows. With hundreds of tickers sharing each date a
random row split puts the same day on both sides, and the test set becomes a
near-copy of the train set.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from backend.research.r3_program.discovery_lab import (
    SEED, EMBARGO_DAYS, FWD, WINDOW, SHAPE_POINTS)

SCALAR_FEATURES = ["ret_5d", "ret_10d", "ret_20d", "ret_60d", "vol_20", "vol_60",
                   "vol_ratio", "dd_60", "pos_60", "skew_20", "kurt_20",
                   "slope_20", "vol_ratio_5v20"]


def date_split(panel: pd.DataFrame, frac: float = 0.65,
               embargo_days: int = EMBARGO_DAYS):
    """Chronological TRAIN -> EMBARGO -> TEST over DATES."""
    dates = np.sort(panel["date"].unique())
    cut = pd.Timestamp(dates[int(len(dates) * frac)])
    emb_end = cut + pd.Timedelta(days=embargo_days)
    tr = panel["date"] <= cut
    te = panel["date"] > emb_end
    info = {"train_end": str(cut.date()), "test_start": str(emb_end.date()),
            "embargo_days": embargo_days,
            "n_train_dates": int(panel.loc[tr, "date"].nunique()),
            "n_test_dates": int(panel.loc[te, "date"].nunique())}
    return tr.to_numpy(), te.to_numpy(), info


def outcome_stats(s: pd.Series) -> dict:
    s = pd.Series(s).dropna()
    if len(s) == 0:
        return {"n": 0}
    return {"n": int(len(s)), "mean_pct": round(float(s.mean()), 4),
            "median_pct": round(float(s.median()), 4),
            "win_rate_pct": round(100.0 * float((s > 0).mean()), 2),
            "severe_le_m5_pct": round(100.0 * float((s <= -5).mean()), 2)}


# ── A1 · TRAJECTORY ARCHETYPES ────────────────────────────────────────
def archetypes(panel: pd.DataFrame, shape: np.ndarray, k: int = 8,
               outcome: str = "fwd_20d") -> dict:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.linear_model import LinearRegression

    tr, te, split = date_split(panel)
    km = KMeans(n_clusters=k, random_state=SEED, n_init=10).fit(shape[tr])
    lab = km.predict(shape)
    p = panel.copy()
    p["archetype"] = lab

    sil = None
    if tr.sum() > 2000:
        sil = float(silhouette_score(shape[tr][::11], lab[tr][::11]))

    # IS IT NEW? If two ordinary indicators reconstruct the shape vector, this
    # is momentum and volatility rediscovered, not latent structure.
    X = p[["ret_20d", "vol_20"]].to_numpy(dtype=float)
    ok = np.isfinite(X).all(axis=1)
    r2 = float(LinearRegression().fit(X[ok], shape[ok]).score(X[ok], shape[ok])) \
        if ok.sum() > 200 else None

    rows = []
    for a in range(k):
        m = (lab == a)
        sub = p.loc[m]
        c = km.cluster_centers_[a]
        rows.append({
            "archetype": int(a),
            "n_rows": int(m.sum()),
            "n_tickers": int(sub["ticker"].nunique()),
            "n_dates": int(sub["date"].nunique()),
            "centroid_start_to_end": round(float(c[-1] - c[0]), 3),
            "centroid_max_drawdown": round(float((c - np.maximum.accumulate(c)).min()), 3),
            "mean_vol_20": round(float(sub["vol_20"].mean()), 2),
            "mean_ret_20d": round(float(sub["ret_20d"].mean()), 2),
            "mean_dd_60": round(float(sub["dd_60"].mean()), 2),
            "train_outcome": outcome_stats(p.loc[m & tr, outcome]),
            "test_outcome": outcome_stats(p.loc[m & te, outcome]),
        })

    a_tr = [r["train_outcome"].get("mean_pct") for r in rows]
    a_te = [r["test_outcome"].get("mean_pct") for r in rows]
    pair = [(x, y) for x, y in zip(a_tr, a_te) if x is not None and y is not None]
    rank_corr = None
    if len(pair) >= 4:
        rank_corr = round(float(pd.Series([q[0] for q in pair])
                                .corr(pd.Series([q[1] for q in pair]),
                                      method="spearman")), 4)
    sp_tr = round(max(a_tr) - min(a_tr), 4) if all(v is not None for v in a_tr) else None
    sp_te = round(max(a_te) - min(a_te), 4) if all(v is not None for v in a_te) else None
    return {"k": k, "outcome": outcome, "split": split,
            "silhouette_train": None if sil is None else round(sil, 4),
            "linear_reproducibility_r2": None if r2 is None else round(r2, 4),
            "non_obvious": bool(r2 is not None and r2 < 0.5),
            "archetypes": rows, "train_test_rank_corr": rank_corr,
            "outcome_spread_train_pct": sp_tr, "outcome_spread_test_pct": sp_te,
            "labels": lab.tolist()}


# ── A2 · ANALOGUE SEARCH / FAILURE TWINS ──────────────────────────────
def analogues(panel: pd.DataFrame, shape: np.ndarray, query_idx: np.ndarray,
              k: int = 50, outcome: str = "fwd_20d",
              pool: int = 600) -> dict:
    """Historically similar PRE-state trajectories.

    Two exclusions, both load-bearing: a reference must predate the query by
    more than the embargo (so a neighbour cannot be the query's own near
    future), and must be a DIFFERENT ticker (so a stock is never its own
    analogue on an adjacent date).
    """
    from sklearn.neighbors import NearestNeighbors
    if panel.empty or len(query_idx) == 0:
        return {"status": "EMPTY"}
    nn = NearestNeighbors(n_neighbors=min(pool, len(panel))).fit(shape)
    _, ind = nn.kneighbors(shape[query_idx])
    pdate = panel["date"].to_numpy()
    ptick = panel["ticker"].to_numpy()
    oc = panel[outcome].to_numpy(dtype=float)
    res = []
    for row, qi in enumerate(query_idx):
        qd, qt = pdate[qi], ptick[qi]
        limit = qd - np.timedelta64(EMBARGO_DAYS, "D")
        keep = []
        for nid in ind[row]:
            if ptick[nid] == qt or pdate[nid] >= limit:
                continue
            keep.append(nid)
            if len(keep) >= k:
                break
        if len(keep) < 10:
            res.append({"ticker": str(qt), "date": str(pd.Timestamp(qd).date()),
                        "n_twins": len(keep), "status": "TOO_FEW_TWINS"})
            continue
        res.append({"ticker": str(qt), "date": str(pd.Timestamp(qd).date()),
                    "n_twins": len(keep),
                    "twin_tickers": int(pd.Series(ptick[keep]).nunique()),
                    "twin_dates": int(pd.Series(pdate[keep]).nunique()),
                    "twin_outcome": outcome_stats(pd.Series(oc[keep])),
                    "query_outcome_pct": (None if not np.isfinite(oc[qi])
                                          else round(float(oc[qi]), 4)),
                    "status": "OK"})
    return {"k": k, "outcome": outcome, "embargo_days": EMBARGO_DAYS,
            "n_queries": len(res), "queries": res}


def twin_discrimination(an: dict) -> dict:
    """Do twin neighbourhoods separate outcomes, or is every one the same?

    A twin set whose mean equals the unconditional mean carries no information
    however similar the shapes look.
    """
    ok = [q for q in an.get("queries", [])
          if q.get("status") == "OK" and q.get("query_outcome_pct") is not None]
    if len(ok) < 30:
        return {"status": "INSUFFICIENT_QUERIES", "n": len(ok)}
    pred = pd.Series([q["twin_outcome"]["mean_pct"] for q in ok])
    act = pd.Series([q["query_outcome_pct"] for q in ok])
    dates = pd.Series([q["date"] for q in ok])
    top = pred.quantile(0.8)
    bot = pred.quantile(0.2)
    return {"status": "OK", "n_queries": len(ok),
            "n_query_dates": int(dates.nunique()),
            "spearman_twin_mean_vs_actual": round(float(pred.corr(act, method="spearman")), 4),
            "twin_mean_dispersion_pct": round(float(pred.std()), 4),
            "actual_dispersion_pct": round(float(act.std()), 4),
            "actual_when_twins_bullish_pct": round(float(act[pred >= top].mean()), 4),
            "actual_when_twins_bearish_pct": round(float(act[pred <= bot].mean()), 4),
            "note": ("Near-zero twin-mean dispersion means the neighbourhoods are "
                     "interchangeable and the analogue carries no signal.")}


# ── B · LATENT MARKET-STATE DISCOVERY ─────────────────────────────────
def latent_states(panel: pd.DataFrame, n_states: int = 4,
                  outcome: str = "fwd_20d") -> dict:
    """Discover market states from the cross-section, then interpret them.

    The state is built from breadth, dispersion and median volatility across the
    whole market on each date - deliberately NOT from a predefined risk-on /
    risk-off label.
    """
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler

    g = panel.groupby("date")
    md = pd.DataFrame({
        "median_vol20": g["vol_20"].median(),
        "dispersion_ret20": g["ret_20d"].std(),
        "breadth_pos": g["ret_20d"].apply(lambda s: float((s > 0).mean()) * 100.0),
        "median_dd60": g["dd_60"].median(),
        "median_pos60": g["pos_60"].median(),
    }).dropna()
    if len(md) < 60:
        return {"status": "INSUFFICIENT_HISTORY", "n_dates": int(len(md))}

    cut = md.index[int(len(md) * 0.65)]
    X = StandardScaler().fit_transform(md.to_numpy())
    trm = (md.index <= cut)
    gm = GaussianMixture(n_components=n_states, random_state=SEED,
                         covariance_type="full", n_init=5).fit(X[trm])
    st = gm.predict(X)
    md["state"] = st

    smap = md["state"].to_dict()
    p = panel.copy()
    p["state"] = p["date"].map(smap)
    tr_mask = p["date"] <= cut
    te_mask = p["date"] > (pd.Timestamp(cut) + pd.Timedelta(days=EMBARGO_DAYS))

    rows = []
    for s in range(n_states):
        m = p["state"] == s
        sub = md[md["state"] == s]
        rows.append({
            "state": int(s),
            "n_dates": int(len(sub)),
            "n_rows": int(m.sum()),
            "median_vol20": round(float(sub["median_vol20"].median()), 3),
            "dispersion_ret20": round(float(sub["dispersion_ret20"].median()), 3),
            "breadth_pos_pct": round(float(sub["breadth_pos"].median()), 2),
            "median_dd60": round(float(sub["median_dd60"].median()), 3),
            "train_outcome": outcome_stats(p.loc[m & tr_mask, outcome]),
            "test_outcome": outcome_stats(p.loc[m & te_mask, outcome]),
        })
    a_tr = [r["train_outcome"].get("mean_pct") for r in rows]
    a_te = [r["test_outcome"].get("mean_pct") for r in rows]
    pair = [(x, y) for x, y in zip(a_tr, a_te) if x is not None and y is not None]
    rc = None
    if len(pair) >= 3:
        rc = round(float(pd.Series([q[0] for q in pair])
                         .corr(pd.Series([q[1] for q in pair]), method="spearman")), 4)

    # persistence: a regime that flips every day is a noise label, not a regime
    runs = (md["state"] != md["state"].shift()).cumsum()
    run_len = md.groupby(runs).size()
    return {"status": "OK", "n_states": n_states, "outcome": outcome,
            "n_dates": int(len(md)), "train_end": str(pd.Timestamp(cut).date()),
            "states": rows, "train_test_rank_corr": rc,
            "median_run_length_samples": int(run_len.median()),
            "max_run_length_samples": int(run_len.max()),
            "n_transitions": int(len(run_len) - 1),
            "state_series": {str(pd.Timestamp(k).date()): int(v) for k, v in smap.items()}}


# ── C · CONTRADICTION DETECTION ───────────────────────────────────────
def contradictions(panel: pd.DataFrame, outcome: str = "fwd_20d") -> dict:
    """Do independent evidence views AGREEING or DISAGREEING change outcomes?

    Views are built from genuinely different parts of the state: trend, position
    within range, volatility regime and participation. The question is not
    whether each predicts, but whether their CONFIGURATION does - which is the
    thing single-feature testing structurally cannot see.
    """
    p = panel.copy()
    views = {
        "trend": np.sign(p["slope_20"].fillna(0)),
        "range_position": np.where(p["pos_60"] > 50, 1.0, -1.0),
        "vol_regime": np.where(p["vol_ratio"] < 1.0, 1.0, -1.0),
        "participation": np.where(p["vol_ratio_5v20"] > 1.0, 1.0, -1.0),
    }
    V = pd.DataFrame(views, index=p.index)
    p["agree_score"] = V.sum(axis=1)          # -4 .. +4
    p["dispersion"] = V.std(axis=1)

    tr, te, split = date_split(p)
    rows = []
    for val in sorted(p["agree_score"].dropna().unique()):
        m = p["agree_score"] == val
        rows.append({
            "agree_score": int(val),
            "n_rows": int(m.sum()),
            "n_tickers": int(p.loc[m, "ticker"].nunique()),
            "n_dates": int(p.loc[m, "date"].nunique()),
            "train_outcome": outcome_stats(p.loc[m & tr, outcome]),
            "test_outcome": outcome_stats(p.loc[m & te, outcome]),
        })
    # the specific asymmetry the mandate asks about: all-agree vs conflicted
    allpos = p["agree_score"] >= 4
    allneg = p["agree_score"] <= -4
    conflict = p["agree_score"].abs() <= 1
    return {"outcome": outcome, "split": split, "by_agreement": rows,
            "aligned_positive": {
                "train": outcome_stats(p.loc[allpos & tr, outcome]),
                "test": outcome_stats(p.loc[allpos & te, outcome])},
            "aligned_negative": {
                "train": outcome_stats(p.loc[allneg & tr, outcome]),
                "test": outcome_stats(p.loc[allneg & te, outcome])},
            "conflicted": {
                "train": outcome_stats(p.loc[conflict & tr, outcome]),
                "test": outcome_stats(p.loc[conflict & te, outcome])},
            "views": list(views.keys()),
            "note": ("Agreement is NOT assumed to be good. The test is whether the "
                     "configuration separates outcomes at all, in either direction.")}


# ── D · DYNAMIC RELATIONAL GRAPH ──────────────────────────────────────
def dynamic_graph(root, market: str, dates: list, lookback: int = 60,
                  top_edges: int = 6, max_tickers: int = 200) -> dict:
    """Build a correlation graph per date from the TRAILING window only, detect
    communities, and ask whether the community structure is stable or churns.

    Nothing about sector membership is hard-coded; if communities align with
    sectors that is a finding, not an input. Edges use only bars strictly at or
    before the as_of date.
    """
    import glob
    import networkx as nx
    from networkx.algorithms import community as nxcom
    from backend.research.r3_program.discovery_lab import _read_bars, BARS_GLOB

    files = sorted(glob.glob(str(root / BARS_GLOB[market])))[:max_tickers]
    series = {}
    for fp in files:
        from pathlib import Path as _P
        t = _P(fp).stem.replace("_D1", "").lstrip("_").upper()
        d = _read_bars(fp)
        if d is not None:
            series[t] = d["close"].astype(float)
    if len(series) < 20:
        return {"status": "INSUFFICIENT_TICKERS", "n": len(series)}
    px = pd.DataFrame(series).sort_index()
    ret = np.log(px).diff()

    snaps, prev = [], None
    for dt in dates:
        dt = pd.Timestamp(dt)
        w = ret.loc[ret.index <= dt].tail(lookback)      # PIT: trailing only
        w = w.dropna(axis=1, thresh=int(lookback * 0.8))
        if w.shape[1] < 20 or len(w) < lookback * 0.8:
            continue
        C = w.corr()
        G = nx.Graph()
        G.add_nodes_from(C.columns)
        for t in C.columns:
            s = C[t].drop(labels=[t]).sort_values(ascending=False)
            for peer, r in s.head(top_edges).items():
                if np.isfinite(r) and r > 0:
                    G.add_edge(t, peer, weight=float(r))
        if G.number_of_edges() == 0:
            continue
        comms = list(nxcom.greedy_modularity_communities(G, weight="weight"))
        mod = float(nxcom.modularity(G, comms, weight="weight"))
        assign = {n: i for i, c in enumerate(comms) for n in c}
        stab = None
        if prev is not None:
            shared = set(assign) & set(prev)
            if len(shared) > 20:
                from sklearn.metrics import adjusted_rand_score
                a = [assign[n] for n in shared]
                b = [prev[n] for n in shared]
                stab = round(float(adjusted_rand_score(a, b)), 4)
        snaps.append({"date": str(dt.date()), "n_nodes": G.number_of_nodes(),
                      "n_edges": G.number_of_edges(),
                      "n_communities": len(comms), "modularity": round(mod, 4),
                      "mean_abs_corr": round(float(C.abs().mean().mean()), 4),
                      "stability_vs_prev_ari": stab,
                      "largest_community_share_pct": round(
                          100.0 * max(len(c) for c in comms) / G.number_of_nodes(), 2)})
        prev = assign
    if not snaps:
        return {"status": "NO_SNAPSHOTS"}
    ari = [s["stability_vs_prev_ari"] for s in snaps if s["stability_vs_prev_ari"] is not None]
    mods = [s["modularity"] for s in snaps]
    return {"status": "OK", "market": market, "lookback": lookback,
            "top_edges_per_node": top_edges, "n_snapshots": len(snaps),
            "date_range": "%s..%s" % (snaps[0]["date"], snaps[-1]["date"]),
            "modularity_median": round(float(np.median(mods)), 4),
            "modularity_min": round(float(np.min(mods)), 4),
            "modularity_max": round(float(np.max(mods)), 4),
            "community_stability_ari_median": (round(float(np.median(ari)), 4)
                                               if ari else None),
            "community_stability_ari_min": round(float(np.min(ari)), 4) if ari else None,
            "snapshots": snaps}


# ── E · COUNTERFACTUAL ENTRY TIMING ───────────────────────────────────
def counterfactual_entries(root, market: str, entries: pd.DataFrame,
                           offsets=(-3, -1, 0, 1, 3), horizon: int = 20) -> dict:
    """Would the same pick have worked entered a few days earlier or later?

    This separates SELECTION from TIMING. If every offset loses, the name was
    the problem; if the loss is concentrated at the actual entry offset, timing
    was. Research only - production timing is untouched.
    """
    from backend.research.r3_program.discovery_lab import _read_bars, BARS_GLOB
    import glob
    from pathlib import Path as _P

    if entries.empty:
        return {"status": "NO_ENTRIES"}
    files = {_P(f).stem.replace("_D1", "").lstrip("_").upper(): f
             for f in glob.glob(str(root / BARS_GLOB[market]))}
    rows = []
    for _, e in entries.iterrows():
        t = str(e["ticker"]).upper().replace(".NS", "").replace(".BO", "")
        fp = files.get(t)
        if not fp:
            continue
        d = _read_bars(fp)
        if d is None:
            continue
        c = d["close"].astype(float)
        try:
            i0 = int(d.index.searchsorted(pd.Timestamp(e["as_of"])))
        except Exception:
            continue
        if i0 >= len(d):
            continue
        rec = {"ticker": t, "market": market, "as_of": str(e["as_of"])}
        for off in offsets:
            i = i0 + off
            if i < 0 or i + horizon >= len(c):
                rec["off_%+d" % off] = None
                continue
            rec["off_%+d" % off] = round(
                100.0 * (float(c.iloc[i + horizon]) / float(c.iloc[i]) - 1.0), 4)
        rows.append(rec)
    if not rows:
        return {"status": "NO_MATCHED_BARS"}
    df = pd.DataFrame(rows)
    cols = ["off_%+d" % o for o in offsets]
    have = df.dropna(subset=cols)
    summary = {c: outcome_stats(have[c]) for c in cols} if len(have) else {}
    verdict = "INSUFFICIENT"
    if len(have) >= 20:
        base = have["off_+0"].mean()
        others = have[[c for c in cols if c != "off_+0"]].mean().mean()
        spread = float(abs(base - others))
        verdict = ("TIMING_SENSITIVE" if spread > 1.0 else "SELECTION_DOMINATES")
    return {"status": "OK", "market": market, "horizon_bars": horizon,
            "n_entries": int(len(df)), "n_with_all_offsets": int(len(have)),
            "n_dates": int(df["as_of"].nunique()),
            "by_offset": summary, "verdict": verdict,
            "caveat": ("A shifted entry also shifts the exit, so this measures the "
                       "entry POINT, not the full policy. Production timing is "
                       "unchanged.")}
