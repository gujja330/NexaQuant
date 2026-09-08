"""ML DISCOVERY v1 · IMPORTANCE + STABILITY · CEO 2026-09-08.

> "The important output isn't 'Feature X has importance 0.27.' It's
>  'Feature X repeatedly ranks highly across independent folds ... and
>  survives the statistical confirmation process.'"
>
> "A feature that ranks #1 in one fold and #47 in the next isn't a
>  production feature."

So the headline number here is STABILITY, not magnitude. Three views:

  native      LightGBM split/gain importance · cheap, biased toward
              high-cardinality continuous features
  permutation measured on the HELD-OUT fold only · what actually degrades
              out-of-sample performance when the column is shuffled
  stability   rank of each feature per fold, then mean rank, rank spread,
              and how often it lands in the top quartile

A feature is reported as a candidate only when its mean rank is high AND
its spread is narrow. Anything else is noise wearing an importance bar.
"""
from __future__ import annotations

import math
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.importance.v1"

TOP_QUARTILE = 0.25
STABLE_MAX_RANK_SPREAD = 0.35   # fraction of the feature count


def native(model, names: list) -> dict:
    try:
        imp = list(model.feature_importances_)
    except Exception:
        return {}
    tot = float(sum(imp)) or 1.0
    return {n: round(float(v) / tot, 5) for n, v in zip(names, imp)}


def permutation(model, X, y, names: list, target: str,
                n_repeats: int = 5, seed: int = 20260908) -> dict:
    """Drop in held-out score when one column is shuffled.

    Computed on the TEST fold. Permutation importance on training data
    measures memorisation, which is precisely what a 37-unit cohort would
    hand back with confidence.
    """
    import numpy as np
    from backend.research.ml_discovery.models import score

    rng = np.random.default_rng(seed)
    base = score(model, X, y, target).get("value")
    if base is None:
        return {}
    out = {}
    for j, name in enumerate(names):
        drops = []
        for _ in range(n_repeats):
            Xp = X.copy()
            rng.shuffle(Xp[:, j])
            s = score(model, Xp, y, target).get("value")
            if s is not None:
                drops.append(base - s)
        out[name] = round(float(np.mean(drops)), 5) if drops else None
    return out


def _ranks(d: dict) -> dict:
    """1 = most important. Ties share the better rank deterministically."""
    items = sorted(((k, (v if v is not None else -math.inf))
                    for k, v in d.items()), key=lambda kv: -kv[1])
    return {k: i + 1 for i, (k, _) in enumerate(items)}


def stability(per_fold: list, names: list) -> dict:
    """per_fold: list of {feature: importance} · one entry per fold."""
    if not per_fold:
        return {}
    n_feat = max(1, len(names))
    ranks = {n: [] for n in names}
    for d in per_fold:
        r = _ranks({n: d.get(n) for n in names})
        for n in names:
            ranks[n].append(r[n])
    top_cut = max(1, int(n_feat * TOP_QUARTILE))

    out = {}
    for n in names:
        rs = ranks[n]
        mean_r = sum(rs) / len(rs)
        spread = (max(rs) - min(rs)) / n_feat
        out[n] = {
            "mean_rank": round(mean_r, 2),
            "best_rank": min(rs), "worst_rank": max(rs),
            "rank_spread_frac": round(spread, 3),
            "top_quartile_hits": sum(1 for x in rs if x <= top_cut),
            "n_folds": len(rs),
            "stable": bool(spread <= STABLE_MAX_RANK_SPREAD
                           and mean_r <= n_feat / 2),
        }
    return dict(sorted(out.items(), key=lambda kv: kv[1]["mean_rank"]))


def candidates(stab: dict, min_top_quartile: int = 2) -> list:
    """Features worth registering as a hypothesis · stable AND repeatedly
    near the top. Deliberately strict: this list is what the Evidence
    Engine would be asked to test, and every extra entry costs a trial."""
    return [
        {"feature": k, **v} for k, v in stab.items()
        if v["stable"] and v["top_quartile_hits"] >= min_top_quartile
    ]
