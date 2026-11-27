"""AEGIS AI pick model · research only, both markets.

CEO 2026-11-27: "leverage AI, make this product an AI super intelligence
for stocks".

WHAT IT IS
----------
A gradient-boosted model (LightGBM) that ranks stocks by the probability
that the LIVE exit rule - the 10-day volatility-scaled triple barrier -
ends in profit. Picks and exits are therefore one system: the model learns
to choose the trades the exit rule handles well.

WHY IT CAN WORK NOW WHEN THE META-LABEL COULD NOT
--------------------------------------------------
The 2026-09-15 meta-label was rejected on ~20-50 entry dates. This model
learns from the full price history - an entry every STEP trading days for
every stock - which is hundreds of independent dates per market.

EVIDENCE DISCIPLINE (aegis_ml_discovery_guardrails)
--------------------------------------------------
* Point in time: every feature is computed from bars up to the decision
  date, and each is ranked across the universe on that date.
* Purged, embargoed walk-forward: the dates are cut into K contiguous
  blocks; each block is predicted by a model trained only on OTHER blocks,
  with training dates inside EMBARGO bars of the block removed, because a
  10-bar label would otherwise leak across the boundary.
* Dates are the unit of evidence, not rows.
* It must beat simple baselines (momentum, low volatility), not just random.

PRE-REGISTERED PASS RULE (fixed before results were seen)
---------------------------------------------------------
PASS only if the model's top decile beats the BEST simple baseline's top
decile on >= 60% of held-out blocks AND its per-date excess over that
baseline is positive with a sign-test p-value that survives Benjamini-
Hochberg at q=0.10 across the variants tested. Otherwise NOT SUPPORTED.

This module decides nothing in production.
"""
from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from backend.research import exit_policy_replay as R
from backend.research.exit_rule_robustness import load_universe, breadth_by_date

STEP = 5
LABEL_POLICY = {"kind": "TB", "h": 10, "k_tp": 1.0, "k_sl": 1.0}
EMBARGO = 15                  # trading days ≥ label horizon + entry spacing
K_FOLDS = 5
TOP_FRAC = 0.10
MIN_NAMES_PER_DATE = 30

FEATURES = ["ret_5", "ret_21", "ret_63", "ret_126", "ret_252", "vol_20", "vol_60",
            "atr_pct", "dist_hi_252", "dist_lo_252", "px_sma20", "px_sma50",
            "px_sma200", "rsi_14", "er_20", "vol_z", "beta_60"]
REGIME = ["breadth", "mkt_ret_21", "mkt_vol_20"]


def _rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _er(c: pd.Series, n: int = 20) -> pd.Series:
    net = (c - c.shift(n)).abs()
    path = c.diff().abs().rolling(n).sum()
    return net / path.replace(0, np.nan)


def market_series(uni: dict) -> pd.DataFrame:
    rets = pd.concat({t: df["close"].pct_change() for t, df in uni.items()}, axis=1)
    mkt = rets.mean(axis=1, skipna=True)
    return pd.DataFrame({"mkt_ret": mkt,
                         "mkt_ret_21": (1 + mkt).rolling(21).apply(np.prod, raw=True) - 1,
                         "mkt_vol_20": mkt.rolling(20).std()})


def build_dataset(root: Path, market: str, asof: str) -> pd.DataFrame:
    m = market.lower()
    uni = load_universe(root, m)
    br = breadth_by_date(uni)
    mk = market_series(uni)
    cost = R.COST_BPS.get(m, 10.0)
    rows = []
    for t, df in uni.items():
        c, v = df["close"].astype(float), df.get("volume")
        r1 = c.pct_change()
        f = pd.DataFrame(index=df.index)
        for n in (5, 21, 63, 126, 252):
            f["ret_%d" % n] = c / c.shift(n) - 1
        f["vol_20"], f["vol_60"] = r1.rolling(20).std(), r1.rolling(60).std()
        f["atr_pct"] = df["atr"] / c
        f["dist_hi_252"] = c / c.rolling(252).max() - 1
        f["dist_lo_252"] = c / c.rolling(252).min() - 1
        for n in (20, 50, 200):
            f["px_sma%d" % n] = c / c.rolling(n).mean() - 1
        f["rsi_14"], f["er_20"] = _rsi(c), _er(c)
        if v is not None:
            lv = np.log1p(v.astype(float))
            f["vol_z"] = (lv - lv.rolling(60).mean()) / lv.rolling(60).std()
        else:
            f["vol_z"] = np.nan
        mr = mk["mkt_ret"].reindex(df.index)
        f["beta_60"] = r1.rolling(60).cov(mr) / mr.rolling(60).var()
        idx = list(df.index)
        o, h, l, cl = (df[k].astype(float).tolist() for k in ("open", "high", "low", "close"))
        sig, atr = df["sigma"].tolist(), df["atr"].tolist()
        for i in range(260, len(idx) - 1, STEP):
            d = idx[i]
            if d > asof or not (sig[i] and sig[i] > 0 and atr[i] and atr[i] > 0):
                continue
            j = min(len(idx), i + 1 + LABEL_POLICY["h"])
            if j - (i + 1) < LABEL_POLICY["h"]:
                continue                        # label not yet resolved: never train on it
            ep = R.Episode(oid="", ticker=t, entry_date=d, entry=cl[i], sigma=float(sig[i]),
                           atr=float(atr[i]), o=o[i + 1:j], h=h[i + 1:j], l=l[i + 1:j],
                           c=cl[i + 1:j], dates=idx[i + 1:j], base_ret=0.0, base_days=0,
                           base_open=False)
            res = R.simulate(ep, LABEL_POLICY, cost)
            row = f.iloc[i].to_dict()
            row.update({"ticker": t, "date": d, "y_ret": res.ret, "y": int(res.ret > 0),
                        "breadth": br.get(d)})
            rows.append(row)
    ds = pd.DataFrame(rows)
    if ds.empty:
        return ds
    mk2 = mk.reindex(ds["date"].unique())
    ds["mkt_ret_21"] = ds["date"].map(mk2["mkt_ret_21"])
    ds["mkt_vol_20"] = ds["date"].map(mk2["mkt_vol_20"])
    # cross-sectional percentile ranks per date (robust to regime level shifts)
    counts = ds.groupby("date")["ticker"].transform("count")
    ds = ds[counts >= MIN_NAMES_PER_DATE].copy()
    for col in FEATURES:
        ds[col + "_r"] = ds.groupby("date")[col].rank(pct=True)
    return ds.reset_index(drop=True)


def _blocks(dates: list) -> list:
    size = math.ceil(len(dates) / K_FOLDS)
    return [dates[i:i + size] for i in range(0, len(dates), size)]


def _top_mean(df: pd.DataFrame, score: str) -> pd.Series:
    """Per date: mean outcome of the top TOP_FRAC names by `score`."""
    def top(g):
        k = max(1, int(round(len(g) * TOP_FRAC)))
        return g.nlargest(k, score)["y_ret"].mean()
    return df.groupby("date").apply(top, include_groups=False)


def _sign_p(x: np.ndarray) -> float:
    from scipy.stats import binomtest
    pos, n = int((x > 0).sum()), int((x != 0).sum())
    return 1.0 if n == 0 else binomtest(pos, n, 0.5, alternative="greater").pvalue


def walk_forward(ds: pd.DataFrame, variant: str) -> pd.DataFrame:
    """Out-of-block predictions for every row, purged and embargoed."""
    import lightgbm as lgb

    feats = [c + "_r" for c in FEATURES] + (REGIME if variant == "with_regime" else [])
    dates = sorted(ds["date"].unique())
    pos = {d: k for k, d in enumerate(dates)}
    out = []
    for b in _blocks(dates):
        lo, hi = pos[b[0]], pos[b[-1]]
        test = ds[ds["date"].isin(set(b))]
        keep = ds["date"].map(pos)
        train = ds[(keep < lo - EMBARGO) | (keep > hi + EMBARGO)]
        if train.empty or test.empty:
            continue
        mdl = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=31,
                                 min_child_samples=200, subsample=0.8, subsample_freq=1,
                                 colsample_bytree=0.8, reg_lambda=1.0, verbose=-1)
        mdl.fit(train[feats], train["y"])
        t = test[["date", "ticker", "y", "y_ret"]].copy()
        t["ai"] = mdl.predict_proba(test[feats])[:, 1]
        t["block"] = "%s..%s" % (b[0], b[-1])
        out.append(t)
    return pd.concat(out) if out else pd.DataFrame()


def evaluate(root: Path, market: str, asof: str) -> dict:
    from sklearn.metrics import roc_auc_score
    from statsmodels.stats.multitest import multipletests

    ds = build_dataset(root, market, asof)
    if ds.empty:
        return {"market": market, "verdict": "INSUFFICIENT EVIDENCE", "rows": 0}
    ds["mom_126"] = ds["ret_126_r"]
    ds["low_vol"] = 1 - ds["vol_60_r"]
    uni_mean = ds.groupby("date")["y_ret"].mean()
    base = {name: _top_mean(ds, name) for name in ("mom_126", "low_vol")}
    best_base_name = max(base, key=lambda k: (base[k] - uni_mean).mean())
    best_base = base[best_base_name]

    variants, pvals = {}, []
    for variant in ("ranks_only", "with_regime"):
        pr = walk_forward(ds, variant)
        if pr.empty:
            continue
        top = _top_mean(pr, "ai")
        bb = best_base.reindex(top.index)
        excess = (top - bb).dropna()
        blocks = pr[["date", "block"]].drop_duplicates().set_index("date")["block"]
        by_block = excess.groupby(blocks.reindex(excess.index)).mean()
        aucs = [roc_auc_score(g["y"], g["ai"]) for _, g in pr.groupby("block")
                if g["y"].nunique() == 2]
        p = _sign_p(excess.values)
        pvals.append(p)
        variants[variant] = {
            "dates": int(len(excess)),
            "ai_top_decile_mean": round(float(top.mean()), 3),
            "best_baseline": best_base_name,
            "baseline_top_decile_mean": round(float(bb.mean()), 3),
            "universe_mean": round(float(uni_mean.reindex(top.index).mean()), 3),
            "excess_vs_baseline_mean": round(float(excess.mean()), 3),
            "dates_ai_beats_baseline_pct": round(100.0 * float((excess > 0).mean()), 1),
            "blocks_ai_beats_baseline": int((by_block > 0).sum()),
            "n_blocks": int(len(by_block)),
            "auc_by_block": [round(a, 3) for a in aucs],
            "sign_test_p": p,
        }
    if pvals:
        rej = multipletests(pvals, alpha=0.10, method="fdr_bh")[0]
        for (name, v), r in zip(variants.items(), rej):
            v["bh_fdr_significant"] = bool(r)
            v["verdict"] = ("PASS" if (r and v["blocks_ai_beats_baseline"] >= math.ceil(0.6 * v["n_blocks"])
                                       and v["excess_vs_baseline_mean"] > 0)
                            else "NOT SUPPORTED")
    overall = "PASS" if any(v.get("verdict") == "PASS" for v in variants.values()) else "NOT SUPPORTED"
    return {"market": market, "asof": asof, "rows": int(len(ds)),
            "tickers": int(ds["ticker"].nunique()), "dates": int(ds["date"].nunique()),
            "first_date": str(ds["date"].min()), "last_date": str(ds["date"].max()),
            "label": LABEL_POLICY, "embargo_bars": EMBARGO, "k_folds": K_FOLDS,
            "top_frac": TOP_FRAC,
            "baselines_top_decile_mean": {k: round(float(v.mean()), 3) for k, v in base.items()},
            "universe_mean": round(float(uni_mean.mean()), 3),
            "variants": variants, "verdict": overall,
            "pass_rule": "AI top decile beats best simple baseline on >=60% of held-out "
                         "blocks, positive mean excess, sign-test p survives BH-FDR q=0.10"}
