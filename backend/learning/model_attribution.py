"""Model attribution — which ensemble models drove winning vs losing recs.

For each model_id that appears in any closed-rec's top_models list:
  - How often was it in top-3?
  - What was the average signed return when it was?
  - What's the net alpha (winner_avg - |loser_avg|)?

This is the ex-post evidence feature for Sprint 9's "which models to retire"
question.
"""
from __future__ import annotations

import pandas as pd

from backend.learning.types import Attribution


def compute_model_attribution(corpus: pd.DataFrame) -> list[Attribution]:
    if corpus is None or corpus.empty:
        return []
    if "top_models" not in corpus.columns:
        return []

    # top_models may be a Python list OR a JSON-encoded string (parquet round-trip)
    import json as _json
    rows = []
    for _, r in corpus.iterrows():
        raw = r.get("top_models") or []
        if isinstance(raw, str):
            try: models = _json.loads(raw)
            except Exception: models = []
        elif isinstance(raw, (list, tuple)):
            models = list(raw)
        else:
            continue
        for m in models:
            # entries may be strings OR {model_id, score} dicts (Sprint 3 format)
            if isinstance(m, dict):
                mid = str(m.get("model_id") or "")
            else:
                mid = str(m)
            if not mid: continue
            rows.append({
                "model_id":   mid,
                "return_pct": float(r.get("return_pct") or 0.0),
                "is_winner":  bool(r.get("is_winner")),
            })
    if not rows:
        return []
    long = pd.DataFrame(rows)

    out: list[Attribution] = []
    for mid, grp in long.groupby("model_id"):
        n = int(len(grp))
        winners = grp[grp["is_winner"]]
        losers  = grp[~grp["is_winner"]]
        avg_win = float(winners["return_pct"].mean()) if len(winners) else 0.0
        avg_los = float(losers["return_pct"].mean()) if len(losers) else 0.0
        out.append(Attribution(
            key=mid, n_observations=n,
            avg_contribution=round(float(grp["return_pct"].mean()), 6),
            winner_frequency=round(len(winners) / n, 4) if n else 0.0,
            loser_frequency=round(len(losers) / n, 4) if n else 0.0,
            net_alpha=round(avg_win + avg_los, 6),
        ))
    out.sort(key=lambda a: a.net_alpha, reverse=True)
    return out
