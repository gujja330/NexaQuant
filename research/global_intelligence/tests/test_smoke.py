"""DEV017 v0.1 smoke tests. Fast; no network access required."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from global_intelligence.lib import catalog, confidence, schema


PASS = 0
FAIL = 0


def _check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def test_catalog():
    s = catalog.summary()
    _check("catalog has variables", s["total_variables"] >= 20,
            detail=f"got {s['total_variables']}")
    _check("catalog covers 5 categories", len(s["by_category"]) == 5)
    v = catalog.by_key("equity_index.us.spx.close")
    _check("catalog.by_key returns spec", v.yfinance_ticker == "^GSPC")
    try:
        catalog.by_key("does.not.exist")
        _check("unknown key raises KeyError", False)
    except KeyError:
        _check("unknown key raises KeyError", True)


def test_schema():
    obs = schema.RawObservation(
        variable_key="test.foo", asof_utc="2026-07-17T00:00:00.000Z",
        value=100.5, unit="USD", source_id="test", code_sha="deadbeef",
    )
    _check("observation_id is set", obs.observation_id is not None and len(obs.observation_id) > 10)
    _check("checksum is deterministic",
            obs.checksum == schema.RawObservation(
                variable_key="test.foo", asof_utc="2026-07-17T00:00:00.000Z",
                value=100.5, unit="USD", source_id="test", code_sha="deadbeef"
            ).checksum)

    dm = schema.DerivedMetric(
        metric_key="test.derived", asof_utc="2026-07-17T00:00:00.000Z",
        value=42.0, unit="%", formula_key="test", formula_version="v1.0",
        code_sha="deadbeef",
    )
    _check("derived id + timestamp set",
            dm.metric_id is not None and dm.computed_at_utc is not None)


def test_confidence():
    _check("c_source Tier 1 = 1.0", confidence.c_source(1) == 1.00)
    _check("c_source Tier 2 = 0.85", confidence.c_source(2) == 0.85)
    _check("c_source Tier 3 = 0.70", confidence.c_source(3) == 0.70)

    # Freshness
    now = "2026-07-17T12:00:00.000Z"
    _check("fresh daily = 1.0",
            confidence.c_freshness("2026-07-17T12:00:00.000Z", "daily", now) == 1.0)
    _check("3-day-old daily still 1.0 (weekend allowance)",
            confidence.c_freshness("2026-07-14T12:00:00.000Z", "daily", now) == 1.0)

    stale = confidence.c_freshness("2026-05-01T12:00:00.000Z", "daily", now)
    _check("far-past daily returns 0", stale == 0.0, detail=f"got {stale}")

    _check("c_completeness clamped",
            confidence.c_completeness(3, 4) == 0.75
            and confidence.c_completeness(5, 4) == 1.0)

    combined = confidence.combine(0.85, 1.0, 1.0, 1.0)
    _check("combine multiplies", abs(combined - 0.85) < 1e-9)

    _check("tier_from_downstream High", confidence.tier_from_downstream(0.95) == "High")
    _check("tier_from_downstream Medium", confidence.tier_from_downstream(0.75) == "Medium")
    _check("tier_from_downstream Low", confidence.tier_from_downstream(0.55) == "Low")
    _check("tier_from_downstream VeryLow", confidence.tier_from_downstream(0.3) == "VeryLow")
    _check("tier_from_downstream Failed", confidence.tier_from_downstream(0.0) == "Failed")


def main() -> int:
    print("=" * 70)
    print("  DEV017 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_catalog()
    print()
    test_schema()
    print()
    test_confidence()
    print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
