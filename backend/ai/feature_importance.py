"""AI Feature Importance Agent v1.0.

Deterministic 'importance' proxy: cross-sectional dispersion (std/IQR)
tells us which features actually differentiate stocks in this snapshot.
A feature that's constant across the universe carries no information —
its 'importance' is zero. High-dispersion features are the ones driving
downstream decisions.

**Not a supervised feature-importance.** That's Sprint 9 (Learning Engine)
using outcome labels. This agent surfaces *ex-ante* usefulness for
today's snapshot only. No recommendations.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.ai.base import AgentOutput
from backend.feature_store.feature_registry import FEATURE_REGISTRY

VERSION = "v1.0"
IDENTITY = {"market", "ticker", "asof", "sector", "currency", "mi_regime"}


def run(df: pd.DataFrame, market_name: str, asof: date | None = None,
         top_k: int = 15) -> AgentOutput:
    if df is None or df.empty:
        return AgentOutput(agent="feature_importance", version=VERSION, market=market_name,
                             asof=asof or date.today(),
                             headline="No snapshot to score",
                             narrative="Feature Store snapshot empty.",
                             confidence=0.0, caveats=["Empty"])

    # Compute normalized dispersion per numeric column
    scored: list[dict] = []
    for col in df.columns:
        if col in IDENTITY: continue
        if not pd.api.types.is_numeric_dtype(df[col]): continue
        s = df[col].dropna()
        if len(s) < 10 or s.nunique() < 2:
            continue
        mu = float(s.mean()); sig = float(s.std())
        # Coefficient of variation, robust to sign
        cv = (sig / abs(mu)) if mu != 0 else sig
        iqr = float(s.quantile(0.75) - s.quantile(0.25))
        # Combine — geometric-ish mean so a column needs BOTH decent CV AND IQR
        score = round((cv * iqr) ** 0.5 if cv * iqr > 0 else 0.0, 5)
        scored.append({"feature": col, "std": round(sig, 5), "iqr": round(iqr, 5),
                          "cv": round(cv, 5), "score": score,
                          "n_non_null": int(len(s))})

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_k]

    # Category rollup
    cat_lookup = {f.name: f.category.value for f in FEATURE_REGISTRY}
    top_cats: dict[str, int] = {}
    for r in top:
        c = cat_lookup.get(r["feature"], "unknown")
        top_cats[c] = top_cats.get(c, 0) + 1
    cat_summary = ", ".join(f"{c}={n}" for c, n in
                              sorted(top_cats.items(), key=lambda kv: kv[1], reverse=True))

    lines = [f"  · {r['feature']:<30} score={r['score']:.4f}  cv={r['cv']:.3f}  iqr={r['iqr']:.4f}"
             for r in top]
    head = (f"Top {len(top)} most differentiating features by dispersion "
             f"(categories: {cat_summary})")
    narr = (head + "\n\n" + "\n".join(lines) +
            "\n\nDispersion tells us where the universe DIFFERS in this snapshot — high dispersion "
            "means the feature carries information downstream engines can act on. "
            "This is NOT outcome-based importance (that comes from the Learning Engine).")

    return AgentOutput(
        agent="feature_importance", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=head, narrative=narr,
        findings=top,
        evidence={"n_scored": len(scored), "top_categories": top_cats},
        citations=["backend/feature_store"],
        confidence=1.0 if len(scored) >= 20 else 0.6,
        caveats=["ex-ante dispersion, not outcome-based importance"],
        determinism="template",
    )
