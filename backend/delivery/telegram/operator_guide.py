"""Operator guide · pinned message describing how to use R1 vs R2.

Per operator feedback 2026-08-06: "A simple operator guide in Telegram
would eliminate a lot of confusion for first-time users."

Not a daily send · this is a one-shot documentation delivery that goes
into the Telegram chat pinned message. Also lives as a text field in
the daily XLSX caption for onboarding clarity.
"""
from __future__ import annotations


OPERATOR_GUIDE_TEXT = """📖 HOW TO USE AEGIS DAILY REPORT

🛡 Runner 1 · Core portfolio (defensive)
   · Reviews weekly · low turnover · hold 1-3 months
   · Use as your STABLE base · 10-15 stocks
   · Exit only on EXIT/ROTATE signals or risk triggers

🚀 Runner 2 · Satellite portfolio (opportunistic)
   · Reviews daily · higher turnover · alpha-seeking
   · Use for TOP 3-5 stocks only · equal-weight 3-5% each
   · Follow BUY/HOLD/EXIT signals closely

💡 Recommended allocation
   70% Runner 1 (core)   ·   30% Runner 2 (satellite)

⚠️  DO NOT
   · Buy every R1 stock (you'll end up with 25+ names)
   · Buy every R2 stock (same overlap problem)
   · Rotate core (Runner 1) on daily basis

✅ DO
   · Rotate satellite (Runner 2) when signals shift
   · Keep core (Runner 1) stable · exit only on real triggers
   · Watch Health Score band changes (STRONG BUY → HOLD → WATCH → REVIEW → EXIT)
   · Read the Story column · it tells you what changed today
   · Check Ctx Reason column · context drag/boost with reasoning

🕒 Cadence
   · Every morning · scan XLSX · act on BUY/EXIT signals
   · Every Friday · review Recommendation History (Timeline CLI)
   · Every Saturday · rebalance core if needed

Advisory-only · PAPER · Not investment advice
"""


def render_guide() -> str:
    return OPERATOR_GUIDE_TEXT


def append_to_caption(base_caption: str, day_of_week_iso: int) -> str:
    """Append operator guide to Telegram caption on Mondays (weekly reminder)."""
    if day_of_week_iso == 1:      # Monday
        return f"{base_caption}\n\n─────\n{OPERATOR_GUIDE_TEXT}"
    return base_caption
