"""Failure clustering — group losing recs by signature.

Sprint 6 baseline: bucket losers by dominant regime + dominant error_bucket +
top-feature intersection. Deterministic — no k-means with random init.

When Sprint 9 lands, this can be upgraded to true clustering (k-means with
seeded init OR DBSCAN with fixed eps) — the interface stays identical.
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

from backend.learning.types import FailureCluster, ErrorBucket


def cluster_failures(corpus: pd.DataFrame, min_cluster_size: int = 3) -> list[FailureCluster]:
    """Return a list of FailureCluster from the losing rows in the corpus.

    Deterministic bucketing:
      cluster_key = (regime_at_rec, error_bucket)
    """
    if corpus is None or corpus.empty:
        return []
    if "is_winner" not in corpus.columns:
        return []

    losers = corpus[~corpus["is_winner"].astype(bool)]
    if losers.empty:
        return []

    clusters: dict[tuple, list[dict]] = {}
    for _, r in losers.iterrows():
        key = (
            str(r.get("regime_at_rec", "unknown") or "unknown"),
            str(r.get("error_bucket", ErrorBucket.UNCLASSIFIED.value)),
        )
        clusters.setdefault(key, []).append(r.to_dict())

    import json as _json
    out: list[FailureCluster] = []
    for idx, (key, members) in enumerate(sorted(clusters.items())):
        if len(members) < min_cluster_size:
            continue
        # Dominant features across the cluster — top_features may be list OR JSON string
        feat_counter: Counter = Counter()
        for m in members:
            raw = m.get("top_features") or []
            if isinstance(raw, str):
                try: feats = _json.loads(raw)
                except Exception: feats = []
            elif isinstance(raw, (list, tuple)):
                feats = list(raw)
            else:
                feats = []
            feat_counter.update(str(f) for f in feats)
        top_feats = dict(feat_counter.most_common(5))

        step = _recommended_step(key[0], key[1])
        out.append(FailureCluster(
            cluster_id=idx,
            n_members=len(members),
            dominant_features=top_feats,
            dominant_error_bucket=key[1],
            representative_tickers=[m["ticker"] for m in members[:5]],
            recommended_step=step,
        ))
    return out


def _recommended_step(regime: str, bucket: str) -> str:
    """Non-recommendation proposal for operator review (never emits buy/sell)."""
    if bucket == ErrorBucket.UNDERESTIMATED_VOL.value:
        return (f"regime={regime} · underestimated vol pattern — consider raising "
                 f"vol_multiplier or tightening confidence_gate; propose via promotion_gate")
    if bucket == ErrorBucket.REGIME_CHANGE.value:
        return (f"regime={regime} · regime-change failures — consider adding regime-shift "
                 f"detector to Feature Store; propose via promotion_gate")
    if bucket == ErrorBucket.SURPRISE_EARNINGS.value:
        return (f"earnings-surprise blindspot — review earn_days_to_next feature weighting")
    return f"regime={regime} · {bucket} — cluster surfaced for operator review"
