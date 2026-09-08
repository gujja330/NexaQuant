"""ML DISCOVERY v1 · PAIRWISE INTERACTION SCAN · CEO 2026-09-08.

> "SHAP interaction might reveal: MA200 > +8% AND confidence < 60 AND
>  volatility high AND sector weak -> severe-loss probability up. That is
>  dramatically more useful than 'MA200 distance has p=.000038'."

SHAP is not installed and must not be a prerequisite, so interactions are
found by a direct quadrant scan instead: split two features at their
medians, measure the outcome in each of the four cells, and ask whether
the joint effect exceeds what the two marginals predict.

    interaction_strength = | observed(hi,hi) - (marginal_a + marginal_b) |

A large value means the pair does something together that neither does
alone - which is exactly the conditional structure 7D hinted at, where
USA extension was harmful at low confidence and helpful at high.

EVERY CELL CARRIES ITS TICKER COUNT. The 7C lesson is burned in here:
a 61-row cell drawn from 6 tickers is not 61 pieces of evidence, and a
quadrant scan is even easier to fool than a bin. Cells below the ticker
floor are dropped, not reported with a caveat.

Output is a ranked shortlist for the Evidence Engine, never a rule.
"""
from __future__ import annotations

import math
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.interactions.v1"

MIN_CELL_ROWS = 15
MIN_CELL_TICKERS = 8      # a quadrant must span real names, not two stories


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _cell(rows: list, horizon: str) -> Optional[dict]:
    vals = [_num(r.get(horizon)) for r in rows]
    vals = [v for v in vals if v is not None]
    tick = {str(r.get("ticker") or "") for r in rows} - {""}
    if len(vals) < MIN_CELL_ROWS or len(tick) < MIN_CELL_TICKERS:
        return None
    return {
        "n": len(vals), "n_tickers": len(tick),
        "expectancy_pct": round(sum(vals) / len(vals), 3),
        "win_rate_pct": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1),
        "worst_pct": round(min(vals), 3),
    }


def scan(rows: list, features: list, horizon: str,
         top_k: int = 15) -> list:
    """Median-split quadrant scan over every feature pair."""
    from backend.research.ml_discovery.manifest import derive

    vals_by_feat = {}
    for f in features:
        vs = []
        for r in rows:
            d = derive(r)
            v = d.get(f) if f in d else r.get(f)
            vs.append(_num(v) if not isinstance(v, str) else None)
        present = sorted(v for v in vs if v is not None)
        if len(present) < MIN_CELL_ROWS * 4:
            continue
        vals_by_feat[f] = (vs, present[len(present) // 2])

    base = [_num(r.get(horizon)) for r in rows]
    base = [v for v in base if v is not None]
    if not base:
        return []
    grand = sum(base) / len(base)

    out = []
    feats = sorted(vals_by_feat)
    for i, fa in enumerate(feats):
        va, ma = vals_by_feat[fa]
        for fb in feats[i + 1:]:
            vb, mb = vals_by_feat[fb]
            quads = {"lo_lo": [], "lo_hi": [], "hi_lo": [], "hi_hi": []}
            for k, r in enumerate(rows):
                a, b = va[k], vb[k]
                if a is None or b is None:
                    continue
                quads[("hi" if a > ma else "lo") + "_"
                      + ("hi" if b > mb else "lo")].append(r)
            cells = {k: _cell(v, horizon) for k, v in quads.items()}
            if any(c is None for c in cells.values()):
                continue
            e = {k: c["expectancy_pct"] for k, c in cells.items()}
            marg_a = e["hi_lo"] - e["lo_lo"]
            marg_b = e["lo_hi"] - e["lo_lo"]
            additive = e["lo_lo"] + marg_a + marg_b
            strength = abs(e["hi_hi"] - additive)
            out.append({
                "feature_a": fa, "feature_b": fb,
                "median_a": round(ma, 4), "median_b": round(mb, 4),
                "grand_expectancy_pct": round(grand, 3),
                "cells": cells,
                "marginal_a_pp": round(marg_a, 3),
                "marginal_b_pp": round(marg_b, 3),
                "additive_prediction_pct": round(additive, 3),
                "observed_hi_hi_pct": round(e["hi_hi"], 3),
                "interaction_strength_pp": round(strength, 3),
                "min_cell_tickers": min(c["n_tickers"] for c in cells.values()),
            })
    out.sort(key=lambda d: -d["interaction_strength_pp"])
    return out[:top_k]
