"""Which engines' picks are ACTIONABLE, and which are advisory only.

CEO 2026-10-27 · R2 INDIA MOVED TO ADVISORY.

WHY
---
Three months of live operation (2026-08-04 -> 2026-10-23) produced 143
closed India trades. Measured, with every P&L recomputed from prices:

    win rate        18.9%
    mean per trade  -2.49%
    sum             -355.7pp
    profit factor   0.21

The decisive test was the counterfactual: hold every entry for a fixed
horizon with NO stop and NO target, and compare to NIFTY.

    10d   alpha +0.22%   beats index 48.2%
    20d   alpha -0.23%   beats index 46.5%
    30d   alpha -1.53%   beats index 35.9%

So this is not an exit-policy problem. The selection has no measured
edge in this regime, and the gap WIDENS with holding period. An earlier
reading of "entries work, exits destroy them" was wrong - it rested on
the open book being 62.8% green, which is survivorship: the losers had
already been removed by the stop.

Two supporting findings:

  - the confidence score is uninformative and slightly INVERTED. All 112
    scored trades sat below 60; winners averaged 31.4, losers 33.7.
  - 55 of 116 losses (47%) were re-entries into a name that had just
    stopped the system out. A cooldown replay recovers +93.5pp of that -
    and still leaves the book at -262pp, which is why a cooldown is a
    defect fix and not a rescue.

WHAT THIS CHANGES, AND WHAT IT DOES NOT
---------------------------------------
Delivery is UNCHANGED. The workbook still ships, Telegram still sends,
every sheet keeps its columns, the lifecycle keeps NEW/ACTIVE/ACTIVE+/
EXIT exactly as locked. Nothing is disabled and no operator-visible
feature is removed.

What changes is one string: the advisory notice is prepended to the
`reason` field that every CURRENT row already carries. That field is
already used for precisely this purpose on R1 rows ("R1 ADVISORY ·
suggested stop only · never auto-exited"), so this introduces no new
column, no banner-formula change and no scope-label change - the XLSX
and delivery-layer locks are untouched.

Scoring, ranking, eligibility, thresholds, stops and exits are NOT
modified. The engine keeps producing exactly what it produced
yesterday; the sheet simply stops implying the operator should act on it.

TO REVERSE
----------
Set R2_INDIA_ADVISORY_ONLY = False. That is the whole switch. It should
be reversed when - and only when - frozen-selection out-of-sample
evidence clears the gate recorded in
docs/AEGIS/PLAN_EVIDENCE_FIRST_2026-10-26.md:

    by 2026-12-31, with >=20 clean date units per market and selection
    frozen, positive OOS alpha with a beat-index rate above 55%
"""
from __future__ import annotations

# ── the switches ─────────────────────────────────────────────────────
R2_INDIA_ADVISORY_ONLY = True

# CEO 2026-10-27 · USA · BUILT, OFF, AND RECOMMENDED ON.
#
# USA was held back from the India decision because its 30-day horizon
# was the one candidate with a pulse: alpha +0.98%, beats the index
# 59.9%. Measured properly the same day, it fails BOTH null tests:
#
#   within the names the system picks   p = 0.546
#   vs the full 904-ticker universe     p = 0.704
#   date-block CI95 [-0.50, +3.00]      includes zero
#
# 70% of random draws from the whole market, on the SAME entry dates,
# did as well or better. The positive alpha is the days the system was
# in the market, not the names it chose. There is no selection edge.
#
# This flag is left FALSE because switching it changes operator-visible
# delivery for a market the CEO has not yet ruled on, and standing
# policy is that such a change is presented, never made silently. The
# recommendation is to set it True.
R2_USA_ADVISORY_ONLY = False

NOTICE = ("⚠ ADVISORY · NOT ACTIONABLE · no measured edge "
          "(3mo: 18.9% win · -2.49%/trade · 30d alpha -1.53% vs NIFTY) · "
          "under review to 2026-12-31")

NOTICE_USA = ("⚠ ADVISORY · NOT ACTIONABLE · no selection edge "
              "(30d alpha indistinguishable from random: p=0.70 vs full "
              "universe) · under review to 2026-12-31")

# Kept machine-readable so a report can cite the basis rather than
# restating it, and so the numbers cannot drift from the decision.
BASIS = {
    "decided_utc": "2026-10-27",
    "window": "2026-08-04..2026-10-23",
    "closed_trades": 143,
    "entry_date_units": 30,
    "win_rate_pct": 18.9,
    "mean_pct_per_trade": -2.49,
    "sum_pp": -355.7,
    "profit_factor": 0.21,
    "alpha_30d_pct": -1.53,
    "beat_index_30d_pct": 35.9,
    "review_gate": "2026-12-31 · >=20 date units · OOS alpha>0 · beat>55%",
    "plan": "docs/AEGIS/PLAN_EVIDENCE_FIRST_2026-10-26.md",
}


def is_advisory(market: str, engine: str) -> bool:
    """True when this engine's picks must not read as actionable."""
    m = str(market or "").strip().lower()
    e = str(engine or "").strip().upper()
    if e != "R2":
        return False
    if m == "india":
        return bool(R2_INDIA_ADVISORY_ONLY)
    if m == "usa":
        return bool(R2_USA_ADVISORY_ONLY)
    return False


def decorate_reason(market: str, engine: str, reason: str) -> str:
    """Prepend the advisory notice · idempotent, so a re-run cannot
    stack two copies of it onto the same row."""
    if not is_advisory(market, engine):
        return reason
    r = reason or ""
    if "ADVISORY · NOT ACTIONABLE" in r:
        return r
    notice = NOTICE_USA if str(market).strip().lower() == "usa" else NOTICE
    return "%s · %s" % (notice, r) if r else notice
