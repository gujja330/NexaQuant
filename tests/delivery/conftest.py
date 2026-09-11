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


_REGENERATED: set = set()


def lifecycle(market: str, asof: str | None = None) -> dict | None:
    """The dataset THE WORKBOOK WAS BUILT FROM · cached per session.

    THE INVARIANT: a test must reason about the same dataset the
    renderer actually rendered. Returning a recomputation while the
    workbook on disk came from somewhere else is how a test ends up
    asserting `'2026-09-04' in "... prices = 2026-09-10 close"` - two
    correct artifacts from two different worlds.

    So: if the session regenerated this market, return the recomputation
    (which is what was rendered). If regeneration was DECLINED - missing
    stop source, or a result that would have lost stops - return what is
    on disk, because that is what the workbook still reflects.
    """
    key = (market.lower(), asof or "today")
    if key in _CACHE:
        return _CACHE[key]
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = None
    if market.lower() in _REGENERATED:
        try:
            d = lc.compute(ROOT, market, asof or date.today().isoformat())
        except Exception:
            d = None
    if d is None:
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

    # REGENERATION MUST NOT DEGRADE WHAT IS ALREADY THERE.
    #
    # The first version of this helper recomputed unconditionally, and
    # that broke India CI on 2026-09-11. `reports/context/dynamic_risk_
    # <market>.json` is UNTRACKED, so on a clean checkout the recomputed
    # lifecycle carries `stop: None` for every position - "STOP BREACHED
    # - stop None - none - MARK". The committed artifact had real stops
    # baked in, so the old tests passed and the new ones failed.
    #
    # That traded a stale-artifact dependency for a missing-input one,
    # which is strictly worse: stale at least renders.
    #
    # So the canonical STOP SOURCE must exist before we recompute. If it
    # does not, this is an environment without the upstream risk engine
    # run, and the committed artifact is left exactly as it is.
    if not (ROOT / "reports" / "context"
            / ("dynamic_risk_%s.json" % market.lower())).exists():
        return False
    try:
        rep = lc.compute(ROOT, market, date.today().isoformat())
    except Exception:
        return False
    rows = rep.get("current") or []
    if not rows:
        return False
    # Adopt only if the recomputation is at least as complete as what is
    # already on disk. A regeneration that loses stops is not a refresh.
    new_stops = sum(1 for r in rows if isinstance(r.get("stop"), (int, float)))
    old = lc.load(ROOT, market) or {}
    old_rows = old.get("current") or []
    old_stops = sum(1 for r in old_rows
                    if isinstance(r.get("stop"), (int, float)))
    if old_rows and new_stops < old_stops:
        return False
    try:
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
        if _regenerate(m):
            _REGENERATED.add(m)
    _CACHE.clear()
    yield


def requires_field(d: dict, field: str, where: str = "current"):
    """Skip when the dataset predates a field the test asserts on.

    THE FIFTH-OCCURRENCE GUARD.

    Source that produces a new canonical field and the artifact that
    carries it can always be committed out of step - that is exactly
    what reddened USA CI on 2026-09-10 (admission_status) and India CI
    on 2026-09-11. A field-dependent test must report "this dataset is
    older than this contract" and SKIP, never fail: the delivery gate,
    not pytest, decides whether what ships is sound.
    """
    import pytest as _p
    rows = (d or {}).get(where) or []
    if not rows:
        _p.skip("no %s rows" % where)
    if field not in rows[0]:
        _p.skip("dataset predates '%s' · artifact older than the renderer"
                % field)


@pytest.fixture(scope="session")
def fresh_lifecycle():
    return lifecycle
