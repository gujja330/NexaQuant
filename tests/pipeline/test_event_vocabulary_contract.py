"""Producer -> consumer event-vocabulary contract.

WHY THIS EXISTS
---------------
2026-09-16. India delivery blocked on I18 for two consecutive CI runs.

`apply_dynamic_exits` writes the registry close reason as

    EXIT_STOP · trigger crossed <date> · stop_source=... · enforced_on=...

The presentation humanizer `_normalize_exit_reason` tested for "_stop_", which
does not occur in "exit_stop ·" (the underscore is followed by a space). So
EXIT_STOP fell through to the default branch, which stripped arrows and ticker
suffixes but left the middots -- three of them -- and I18 blocks at two.

EXIT_TARGET carried the identical latent defect and had simply never fired.
EXIT_HORIZON passed only by accident, because an unrelated rule matches the
word "horizon".

THE REAL DEFECT WAS NOT THE MISSING MAPPINGS
--------------------------------------------
The humanizer was a PARTIAL function. Any producer token without an explicit
mapping reached a default that could emit jargon -- and that default rewrote
"->" as "·", INCREASING the middot count and manufacturing the very violation
I18 exists to catch. Measured before the fix: 4 of 8 realistic unmapped strings
rendered as I18-blocking text.

So these tests assert two different things:

  1. every token production can actually emit renders clean, and
  2. the humanizer is TOTAL -- tokens that do not exist yet also render clean.

The second is what stops this class of failure returning. A new producer event
must never be able to take delivery down.

These tests do NOT weaken I18. The validator still inspects the rendered sheet.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _normalize():
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.build_aegis_3sheet_workbook import _normalize_exit_reason
    return _normalize_exit_reason


def _is_jargon(s: str) -> bool:
    """The exact I18 rule, mirrored from xlsx_validator.check_no_jargon_in_exit_reasons.

    Kept as a literal copy on purpose: if I18 changes, this test should be
    updated deliberately rather than silently tracking it.
    """
    u = s.upper()
    return (s.count("·") >= 2
            or "→" in s
            or ".NS" in s or ".BO" in s
            or "alpha" in s.lower()
            or "ORPHAN_" in u or "AUTO_" in u or "TRIGGER_" in u
            or "_HIT" in u or "TRAIL_" in u or "MISSING_" in u)


# The composite shape apply_dynamic_exits actually writes.
COMPOSITE = ("%s · trigger crossed 2026-09-16 · "
             "stop_source=dynamic_risk_v2:india · enforced_on=2026-09-16")

# Tokens that production code can put into a close/exit reason. Sourced by
# scanning event=/reason=/status= literals across backend/, scripts/, india/.
PRODUCER_TOKENS = [
    # scripts/apply_dynamic_exits.py + lifecycle_state_machine.py
    "EXIT_STOP", "EXIT_TARGET", "EXIT_HORIZON", "ROTATE_IN", "ROTATE_OUT",
    # backend/research/p0_exit_bridge_replay.py
    "STOP_HIT", "TARGET_HIT", "HORIZON_EXPIRED", "ROTATION", "ADMIN",
    "MANUAL", "RETIRED", "OTHER", "UNSPECIFIED",
    # backend/research/mr_orphan_closer.py
    "ORPHAN_AUTO_CLOSE",
    # backend/research/profit_protection.py
    "STOP_LOSS_HIT", "TIME_EXIT_LOSER", "DEEP_LOSS", "RANK_COLLAPSE",
    "BETTER_REPLACEMENT", "HARD_GAIN_CAP", "RAPID_APPRECIATION",
    "RISK_ESCALATION", "SECTOR_LEADERSHIP", "TAKE_PROFIT_EARLY",
    "MARKET_REGIME_BUFFER",
    # backend/research/mr_evidence_layer.py
    "TIME_STOP_5D_EXIT_AT_HORIZON", "TRAIL_10_STOPPED_OUT",
    "TRAIL_10_LOCKED_GAIN", "TRAIL_10_HELD_TO_HORIZON",
]


@pytest.mark.parametrize("token", PRODUCER_TOKENS)
def test_bare_producer_token_renders_clean(token):
    out = _normalize()(token)
    assert not _is_jargon(out), (
        "producer token %r renders as I18-blocking text %r" % (token, out))


@pytest.mark.parametrize("token", PRODUCER_TOKENS)
def test_composite_producer_string_renders_clean(token):
    """The shape apply_dynamic_exits actually writes -- this is the exact
    string that took India delivery down on 2026-09-16."""
    out = _normalize()(COMPOSITE % token)
    assert not _is_jargon(out), (
        "composite reason for %r renders as I18-blocking text %r" % (token, out))


def test_the_three_dynamic_exit_events_are_explicitly_mapped():
    """Not merely non-jargon -- actually translated to operator language."""
    n = _normalize()
    assert n(COMPOSITE % "EXIT_STOP") == "Stop-loss triggered"
    assert n(COMPOSITE % "EXIT_TARGET") == "Target hit"
    assert n(COMPOSITE % "EXIT_HORIZON") == "Holding horizon reached"


@pytest.mark.parametrize("raw", [
    "EXIT",
    "SOMETHING_NEW_HIT",                       # a token that does not exist yet
    "FUTURE_EVENT · detail a · detail b",
    "exit → target → done",
    "RELIANCE.NS rotated out",
    "MISSING_FROM_SIGNALS · day 3",
    "Closed via TRAIL_10 logic",
    "Registry-sync · aegis_history had EXIT status",
    "SOME_CODE · a=1 · b=2 · c=3",
])
def test_humanizer_is_total(raw):
    """The fallback must be safe BY CONSTRUCTION.

    A producer event added tomorrow, with no mapping written for it, must
    degrade to readable text -- never block delivery.
    """
    out = _normalize()(raw)
    assert not _is_jargon(out), "unmapped input %r rendered as jargon %r" % (raw, out)
    assert out, "humanizer returned empty for %r" % raw


def test_fallback_does_not_manufacture_middots():
    """The pre-fix default rewrote the arrow AS a middot, which could push a
    string from one middot to two and cause the block it was meant to prevent."""
    out = _normalize()("a → b → c → d")
    assert out.count("·") < 2, "arrow substitution re-introduced middots: %r" % out


def test_live_lifecycles_have_no_jargon():
    """End-to-end: whatever is on disk right now must satisfy I18."""
    import json
    checked = 0
    for market in ("india", "usa"):
        p = ROOT / "reports" / "context" / ("canonical_lifecycle_%s.json" % market)
        if not p.exists():
            continue
        checked += 1
        d = json.loads(p.read_text(encoding="utf-8"))
        bad = [(e.get("ticker"), e.get("exit_reason"))
               for e in d.get("exits", [])
               if e.get("exit_reason") and _is_jargon(str(e["exit_reason"]))]
        assert not bad, "%s lifecycle has I18 jargon rows: %s" % (market, bad[:5])
    if not checked:
        pytest.skip("no canonical lifecycle on disk")
