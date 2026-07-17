"""UX030 · notification priority + grouping rules.

Priorities:
- CRITICAL  — stop-loss hit, regime flip to Risk-Off, high-conviction exit signal
- HIGH      — new Strong-Buy, portfolio grade change, promotion recommended
- MEDIUM    — new Buy, weekly review, drift warning
- LOW       — Watchlist additions, sector rotation notes
- SILENT    — batched into the daily summary; do not send standalone

Grouping:
- All CRITICAL messages send immediately, one message per alert.
- HIGH messages coalesce to at most one message per 30 minutes.
- MEDIUM messages roll up into the Daily Executive Summary.
- LOW/SILENT never send standalone.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PRIORITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "SILENT"]


PRIORITY_MAP = {
    # Trading signals
    "buy_strong":          "HIGH",
    "buy":                 "MEDIUM",
    "accumulate":          "MEDIUM",
    "exit":                "CRITICAL",
    "reduce":              "HIGH",
    "sell":                "CRITICAL",

    # Portfolio events
    "stop_loss_hit":       "CRITICAL",
    "target_hit":          "HIGH",
    "portfolio_grade_change":       "HIGH",
    "cash_below_min":      "HIGH",

    # Regime
    "regime_flip_to_off":  "CRITICAL",
    "regime_flip_to_on":   "HIGH",
    "regime_neutral":      "MEDIUM",

    # Strategy
    "champion_promoted":   "HIGH",
    "champion_hold":       "LOW",
    "drift_detected":      "MEDIUM",

    # Digest
    "daily_summary":       "MEDIUM",
    "weekly_review":       "MEDIUM",
    "monthly_review":      "HIGH",

    # Info
    "confidence_update":   "LOW",
    "watchlist_add":       "LOW",
    "info":                "SILENT",
}


@dataclass
class NotificationDecision:
    priority:      str
    send_now:      bool
    coalesce_group: str | None
    reason:        str


def classify(event_type: str, meta: dict | None = None) -> NotificationDecision:
    meta = meta or {}
    p = PRIORITY_MAP.get(event_type, "LOW")

    if p == "CRITICAL":
        return NotificationDecision(p, True, None, "critical event: send immediately")
    if p == "HIGH":
        return NotificationDecision(p, True, "high_30min",
                                        "high priority; coalesce within 30min window")
    if p == "MEDIUM":
        return NotificationDecision(p, False, "daily_summary",
                                        "roll up into daily summary")
    if p == "LOW":
        return NotificationDecision(p, False, "weekly_review",
                                        "roll up into weekly review")
    return NotificationDecision(p, False, None, "silent: log only")


def summarise_ruleset() -> dict:
    """For publish/bundle.py to emit as telegram_notification_rules.json."""
    grouped = {p: [] for p in PRIORITIES}
    for event, priority in PRIORITY_MAP.items():
        grouped[priority].append(event)
    return {
        "priorities":   PRIORITIES,
        "priority_map": PRIORITY_MAP,
        "by_priority":  grouped,
        "grouping": {
            "CRITICAL":  {"send_now": True,  "coalesce_group": None,           "window_min": 0},
            "HIGH":      {"send_now": True,  "coalesce_group": "high_30min",   "window_min": 30},
            "MEDIUM":    {"send_now": False, "coalesce_group": "daily_summary", "window_min": None},
            "LOW":       {"send_now": False, "coalesce_group": "weekly_review", "window_min": None},
            "SILENT":    {"send_now": False, "coalesce_group": None,           "window_min": None},
        },
        "governance":  "No message ever mutates state; delivery layer is advisory-only.",
    }
