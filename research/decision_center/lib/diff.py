"""Decision Center · overnight diff.

Compares today's snapshot to yesterday's (the most recent prior
snapshot) and classifies every material change into one of:

  NEW                 today has ticker · yesterday didn't
  REMOVED             yesterday had · today doesn't
  UPGRADED            action tier increased (e.g. Hold -> Buy)
  DOWNGRADED          action tier decreased (Buy -> Hold)
  INTELLIGENCE_UP     intelligence_score delta >= +5
  INTELLIGENCE_DOWN   intelligence_score delta <= -5
  CONFIDENCE_UP       confidence delta >= +0.05
  CONFIDENCE_DOWN     confidence delta <= -0.05
  TARGET_HIT          held position at or above target_1
  STOP_HIT            held position at or below stop_loss
  NEW_HELD            wasn't held yesterday · is held today
  EXITED              was held yesterday · not held today
  SIZING_WARNING      today's sizing_verdict is WARNING or BLOCK

Every change is deterministic — same snapshots -> same classification."""
from __future__ import annotations

from typing import Any


# Thresholds (transparent constants, no per-run tuning)
INTELLIGENCE_DELTA_MATERIAL = 5.0
CONFIDENCE_DELTA_MATERIAL    = 0.05
TARGET_PROXIMITY_PCT         = 0.02   # within 2% of target price
STOP_PROXIMITY_PCT           = 0.02


def _entries_by_ticker(snapshot: dict) -> dict[str, dict]:
    return {e["ticker"]: e for e in (snapshot.get("entries") or [])}


def _abs_delta(a, b, default=None):
    if a is None or b is None:
        return default
    try:
        return float(a) - float(b)
    except Exception:
        return default


def compute_diff(today: dict, yesterday: dict | None) -> dict:
    """Return a change register + a per-ticker change record."""
    t_by = _entries_by_ticker(today)

    if yesterday is None:
        # First run — nothing to diff
        return {
            "today_date":     today.get("date"),
            "yesterday_date": None,
            "first_run":      True,
            "changes":        [],
            "action_counts":  _count_actions(t_by.values()),
            "n_changes":      0,
            "note":           "no prior snapshot found — this is the first day of tracking",
        }

    y_by = _entries_by_ticker(yesterday)
    changes = []

    all_tickers = set(t_by.keys()) | set(y_by.keys())
    for ticker in sorted(all_tickers):
        t = t_by.get(ticker)
        y = y_by.get(ticker)

        # NEW
        if t is not None and y is None:
            changes.append(_change(ticker, "NEW", t, None,
                f"first appearance · action {t.get('action')}"))
            continue

        # REMOVED
        if t is None and y is not None:
            changes.append(_change(ticker, "REMOVED", None, y,
                f"was {y.get('action')} yesterday · absent today"))
            continue

        # Both present — classify deltas
        t_tier = t.get("action_tier", 0)
        y_tier = y.get("action_tier", 0)

        if t_tier > y_tier:
            changes.append(_change(ticker, "UPGRADED", t, y,
                f"{y.get('action')} -> {t.get('action')}"))
        elif t_tier < y_tier:
            changes.append(_change(ticker, "DOWNGRADED", t, y,
                f"{y.get('action')} -> {t.get('action')}"))

        # Held-status transitions
        if not y.get("currently_held") and t.get("currently_held"):
            changes.append(_change(ticker, "NEW_HELD", t, y,
                "entered portfolio"))
        elif y.get("currently_held") and not t.get("currently_held"):
            changes.append(_change(ticker, "EXITED", t, y,
                "removed from portfolio"))

        # Intelligence score deltas
        d_int = _abs_delta(t.get("intelligence_score"), y.get("intelligence_score"))
        if d_int is not None and abs(d_int) >= INTELLIGENCE_DELTA_MATERIAL:
            kind = "INTELLIGENCE_UP" if d_int > 0 else "INTELLIGENCE_DOWN"
            changes.append(_change(ticker, kind, t, y,
                f"intel {y.get('intelligence_score')} -> {t.get('intelligence_score')} ({d_int:+.1f})"))

        # Confidence deltas
        d_conf = _abs_delta(t.get("confidence"), y.get("confidence"))
        if d_conf is not None and abs(d_conf) >= CONFIDENCE_DELTA_MATERIAL:
            kind = "CONFIDENCE_UP" if d_conf > 0 else "CONFIDENCE_DOWN"
            changes.append(_change(ticker, kind, t, y,
                f"confidence {y.get('confidence')} -> {t.get('confidence')} ({d_conf:+.3f})"))

        # Sizing verdict warnings (only if not already flagged yesterday)
        if t.get("currently_held") and t.get("sizing_verdict") in ("WARNING", "BLOCK"):
            if y.get("sizing_verdict") not in ("WARNING", "BLOCK"):
                changes.append(_change(ticker, "SIZING_WARNING", t, y,
                    f"sizing verdict now {t.get('sizing_verdict')}"))

        # Target proximity (held only)
        if t.get("currently_held"):
            ep = t.get("entry_price"); tg = t.get("target_1"); sl = t.get("stop_loss")
            pnl = t.get("unrealised_pnl_pct")
            if ep and tg:
                # Target proximity — proxy by unrealised P&L reaching (target-entry)/entry
                # (we don't have current market price separately from entry_price
                # in the snapshot; use pnl as an approximation)
                target_pct = (tg - ep) / ep if ep > 0 else None
                if target_pct is not None and pnl is not None:
                    if pnl >= target_pct - TARGET_PROXIMITY_PCT:
                        changes.append(_change(ticker, "TARGET_HIT", t, y,
                            f"P/L {pnl:+.3f} reached target zone (target return {target_pct:+.3f})"))
            if ep and sl:
                stop_pct = (sl - ep) / ep if ep > 0 else None
                if stop_pct is not None and pnl is not None:
                    if pnl <= stop_pct + STOP_PROXIMITY_PCT:
                        changes.append(_change(ticker, "STOP_HIT", t, y,
                            f"P/L {pnl:+.3f} reached stop zone (stop return {stop_pct:+.3f})"))

    return {
        "today_date":       today.get("date"),
        "yesterday_date":   yesterday.get("date"),
        "first_run":        False,
        "n_changes":        len(changes),
        "changes":          changes,
        "action_counts":    _count_actions(t_by.values()),
        "action_counts_yesterday": _count_actions(y_by.values()),
        "counts_by_kind":   _count_by_kind(changes),
    }


def _change(ticker: str, kind: str, t: dict | None, y: dict | None,
              reason: str) -> dict:
    return {
        "ticker":               ticker,
        "kind":                 kind,
        "reason":               reason,
        "sector":               (t or y or {}).get("sector"),
        "today_action":         (t or {}).get("action"),
        "yesterday_action":     (y or {}).get("action"),
        "today_intelligence":   (t or {}).get("intelligence_score"),
        "yesterday_intelligence":(y or {}).get("intelligence_score"),
        "today_confidence":     (t or {}).get("confidence"),
        "yesterday_confidence": (y or {}).get("confidence"),
        "today_pnl_pct":        (t or {}).get("unrealised_pnl_pct"),
        "currently_held":       (t or {}).get("currently_held", False),
    }


def _count_actions(entries) -> dict:
    counts = {}
    for e in entries:
        a = e.get("action") or "unknown"
        counts[a] = counts.get(a, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def _count_by_kind(changes: list[dict]) -> dict:
    counts = {}
    for c in changes:
        k = c.get("kind")
        counts[k] = counts.get(k, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
