"""The advisory notice must never occupy the FIRST token of `reason`.

CEO 2026-10-27 · REGRESSION GUARD for a self-inflicted contract break.

`reason`'s leading dot-separated token is a PARSED CONTRACT - consumers
read today's signal from it, and
tests/research/test_opportunity_funnel.py::test_no_new_row_lacks_a_buy_signal
asserts a NEW row's leading token is BUY-family.

The R2-India advisory notice was first implemented as a PREPEND, which
made that token read "⚠ ADVISORY" instead of the signal. Nothing failed
immediately: every CURRENT row at the time was ACTIVE or ACTIVE+, which
that assertion does not cover. It surfaced only when EXIDEIND became the
first NEW admission after the change.

So this guard does not depend on a NEW row happening to exist today.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.delivery.governance import advisory_state as adv

ROOT = Path(__file__).resolve().parents[2]
DOT = "\u00b7"


def _first(reason: str) -> str:
    return str(reason or "").split(DOT)[0].strip()


def test_notice_is_appended_not_prepended():
    """Unit-level · independent of whatever today's book contains."""
    out = adv.decorate_reason("india", "R2", "BUY %s held 3d %s stop ATR"
                              % (DOT, DOT))
    assert _first(out) == "BUY", (
        "the notice moved to the front of `reason` · the leading token is a "
        "parsed contract and consumers read the signal from it. Got %r"
        % _first(out))
    assert "ADVISORY" in out, "the notice must still be carried"


def test_decoration_is_idempotent():
    once = adv.decorate_reason("india", "R2", "BUY %s held 3d" % DOT)
    twice = adv.decorate_reason("india", "R2", once)
    assert once == twice
    assert twice.count("ADVISORY") == 1


def test_empty_reason_still_yields_the_notice():
    out = adv.decorate_reason("india", "R2", "")
    assert "ADVISORY" in out


def test_non_advisory_rows_are_untouched():
    for market, engine in (("usa", "R2"), ("india", "R1"),
                           ("india", "MOMENTUM")):
        src = "BUY %s held 1d" % DOT
        assert adv.decorate_reason(market, engine, src) == src, (
            "%s/%s was decorated · only R2 India is advisory today"
            % (market, engine))


@pytest.mark.parametrize("market", ("india", "usa"))
def test_live_new_rows_keep_a_signal_first(market):
    """Belt and braces against the shipped artifact."""
    p = ROOT / "reports" / "context" / ("canonical_lifecycle_%s.json" % market)
    if not p.exists():
        pytest.skip("no lifecycle for %s" % market)
    d = json.loads(p.read_text(encoding="utf-8"))
    bad = [r["ticker"] for r in (d.get("current") or [])
           if r.get("action") == "NEW"
           and "ADVISORY" in _first(r.get("reason", ""))]
    assert not bad, (
        "NEW rows whose leading token is the advisory notice: %s" % bad)
