"""Decision Center · watchlist candidates.

Surfaces recommendations that are close to becoming Buy but haven't
crossed the threshold yet. Also identifies positions that need
attention (Exit Center)."""
from __future__ import annotations


# Thresholds
BUY_INTEL_THRESHOLD    = 70    # from fusion decision_thresholds
NEAR_BUY_MIN_INTEL     = 60    # 60-70 is "near buy"
NEAR_BUY_MAX_INTEL     = 70


def watchlist_candidates(today_snapshot: dict, yesterday_snapshot: dict | None = None,
                            n: int = 15) -> list[dict]:
    """Return recommendations currently below Buy threshold but rising."""
    entries = today_snapshot.get("entries") or []
    y_by = {}
    if yesterday_snapshot:
        y_by = {e["ticker"]: e for e in yesterday_snapshot.get("entries") or []}

    candidates = []
    for e in entries:
        intel = e.get("intelligence_score")
        action = e.get("action")
        # Skip already-Buy / Strong-Buy / Accumulate
        if action in ("Strong-Buy", "Buy", "Accumulate"):
            continue
        if intel is None:
            continue
        # In the "near buy" zone
        if not (NEAR_BUY_MIN_INTEL <= intel < NEAR_BUY_MAX_INTEL):
            continue
        y = y_by.get(e["ticker"])
        prev_intel = (y or {}).get("intelligence_score") if y else None
        trend = (intel - prev_intel) if (prev_intel is not None) else None

        candidates.append({
            "ticker":             e.get("ticker"),
            "sector":             e.get("sector"),
            "current_action":     action,
            "intelligence_score": intel,
            "yesterday_intelligence": prev_intel,
            "intel_trend":        round(trend, 2) if trend is not None else None,
            "gap_to_buy":         round(BUY_INTEL_THRESHOLD - intel, 2),
            "confidence":         e.get("confidence"),
            "entry_price":        e.get("entry_price"),
            "target_1":           e.get("target_1"),
        })

    # Prefer rising candidates + closer to threshold
    candidates.sort(key=lambda c: (
        -(c["intel_trend"] or 0),
        c["gap_to_buy"],
    ))
    return candidates[:n]
