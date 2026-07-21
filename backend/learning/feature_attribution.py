"""Feature attribution — which top_features correlate with winners across the corpus.

Deterministic. No random state. For each feature that appears in any closed-rec's
top_features list, compute:
  - n_observations: how often the feature was in top_features across the corpus
  - avg_contribution: mean signed return of recs where the feature was in top-K
  - winner_frequency / loser_frequency
  - net_alpha: avg return when it was a winner - avg return when it was a loser

Sprint 9's AI Auditor uses this to surface "which features drive the alpha".
"""
from __future__ import annotations

import pandas as pd

from backend.learning.types import Attribution


def compute_feature_attribution(corpus: pd.DataFrame) -> list[Attribution]:
    """Return per-feature Attribution list, sorted by |net_alpha| desc."""
    if corpus is None or corpus.empty:
        return []
    if "top_features" not in corpus.columns:
        return []

    # Explode top_features into long form. top_features may be a Python list
    # OR a JSON-encoded string (parquet round-trip); handle both.
    import json as _json
    rows = []
    for _, r in corpus.iterrows():
        raw = r.get("top_features") or []
        if isinstance(raw, str):
            try: feats = _json.loads(raw)
            except Exception: feats = []
        elif isinstance(raw, (list, tuple)):
            feats = list(raw)
        else:
            continue
        for f in feats:
            rows.append({
                "feature": str(f),
                "return_pct": float(r.get("return_pct") or 0.0),
                "is_winner": bool(r.get("is_winner")),
            })
    if not rows:
        return []
    long = pd.DataFrame(rows)

    out: list[Attribution] = []
    for feat, grp in long.groupby("feature"):
        n = int(len(grp))
        winners = grp[grp["is_winner"]]
        losers  = grp[~grp["is_winner"]]
        avg_win = float(winners["return_pct"].mean()) if len(winners) else 0.0
        avg_los = float(losers["return_pct"].mean()) if len(losers) else 0.0
        net_alpha = avg_win + avg_los    # avg_los is signed negative for a genuine loss
        out.append(Attribution(
            key=feat, n_observations=n,
            avg_contribution=round(float(grp["return_pct"].mean()), 6),
            winner_frequency=round(len(winners) / n, 4) if n else 0.0,
            loser_frequency=round(len(losers) / n, 4) if n else 0.0,
            net_alpha=round(net_alpha, 6),
        ))
    out.sort(key=lambda a: abs(a.net_alpha), reverse=True)
    return out
