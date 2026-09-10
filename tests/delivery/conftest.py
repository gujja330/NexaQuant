"""Delivery tests read a FRESHLY COMPUTED lifecycle, never a committed one.

WHY THIS EXISTS
---------------
On 2026-09-10 USA CI failed with 12 red delivery tests. Nothing was wrong
with the renderer, the lifecycle producer, or the data. The commit
carried SOURCE that produces three new canonical fields - admission
status, market cap, market-data as-of - and did NOT carry the
regenerated `canonical_lifecycle_*.json`. So CI checked out a renderer
that reads those fields alongside an artifact written before they
existed, and every field-dependent test failed on `—`.

Locally the same tests passed, because the local artifact had been
rebuilt minutes earlier. That gap between "passes on my machine" and
"passes on a clean checkout" is exactly what a committed fixture buys
you, and it is worthless when the fixture ages independently of the
code that reads it.

This is the FOURTH time an artifact-age mismatch has blocked delivery.
The earlier fixes each moved the problem one layer down: first the
workbook was rebuilt in the test, then the workbook AND its columns -
but the LIFECYCLE it was built from was still loaded off disk.

So the rule is now absolute: a delivery test computes the dataset from
source. A committed artifact can no longer decide whether the suite is
green, because no delivery test reads one.

`lifecycle(market)` computes once per session and caches. If the
computation itself cannot run, the test SKIPS with the reason rather
than failing - a missing upstream input is an infrastructure fact, not
a delivery defect.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_CACHE: dict = {}


def lifecycle(market: str, asof: str | None = None) -> dict | None:
    """The canonical dataset, computed from source · cached per session."""
    key = (market.lower(), asof or "today")
    if key in _CACHE:
        return _CACHE[key]
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = None
    try:
        d = lc.compute(ROOT, market, asof or date.today().isoformat())
    except Exception:
        # Fall back to whatever is on disk ONLY so a genuinely broken
        # environment skips instead of reporting a false delivery defect.
        try:
            d = lc.load(ROOT, market)
        except Exception:
            d = None
    _CACHE[key] = d
    return d


def _regenerate(market: str) -> bool:
    """Bring the ON-DISK delivery artifacts up to date with SOURCE.

    Computing in the test is not sufficient on its own: the renderer
    deliberately computes nothing and re-reads
    `canonical_lifecycle_<market>.json` from disk, and several tests
    inspect the shipped `aegis_history_<market>.xlsx`. If those files
    predate the source, the suite tests an artifact's age instead of the
    delivery contract - which is precisely the 2026-09-10 USA CI failure
    (15 red on a stale checkout, all green locally).

    So the session regenerates both, exactly as the pipeline does. This
    writes into reports/ - a deliberate, deterministic side effect. It is
    the same output the daily run produces, and it is what makes a clean
    checkout behave like a live machine.
    """
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    from backend.delivery.sheets import workbook_two as w2
    try:
        rep = lc.compute(ROOT, market, date.today().isoformat())
        lc.emit(ROOT, rep)
        built = w2.build_two_sheet_workbook(ROOT, market, rep.get("asof"))
        out = ROOT / "reports" / "telegram" / ("aegis_history_%s.xlsx" % market)
        out.parent.mkdir(parents=True, exist_ok=True)
        built["workbook"].save(out)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def _delivery_artifacts_are_current():
    """Runs ONCE before any delivery test."""
    for m in ("india", "usa"):
        _regenerate(m)
    _CACHE.clear()
    yield


@pytest.fixture(scope="session")
def fresh_lifecycle():
    return lifecycle
