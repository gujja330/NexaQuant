"""Percentile classifier · rank blended scores into action buckets."""
from __future__ import annotations


def classify(per_ticker: dict, top_pct: float = 0.20) -> dict:
    """Assign action tags based on percentile ranking within today's universe.

    Top top_pct of positive scores → STRONG_LONG
    Next → LONG
    Middle → SKIP
    Bottom → SHORT / STRONG_SHORT
    """
    scored = [(t, r["blended_score"]) for t, r in per_ticker.items()]
    if not scored:
        return per_ticker
    sorted_desc = sorted(scored, key=lambda x: -x[1])
    n = len(sorted_desc)
    n_top = max(1, int(n * top_pct))

    for i, (t, score) in enumerate(sorted_desc):
        rec = per_ticker[t]
        if score > 0.20 and i < n_top:
            rec["action"] = "STRONG_LONG"
        elif score > 0.10:
            rec["action"] = "LONG"
        elif score < -0.20 and i >= n - n_top:
            rec["action"] = "STRONG_SHORT"
        elif score < -0.10:
            rec["action"] = "SHORT"
        else:
            rec["action"] = "SKIP"
        rec["percentile_rank"] = round(1 - i / max(1, n - 1), 3)
    return per_ticker
