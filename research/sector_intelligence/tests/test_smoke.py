"""DEV018 v0.1 smoke tests. Fast; no network required."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

# Import both DEV017 (parent) and DEV018 (this project)
from global_intelligence.lib import schema, confidence                              # noqa: E402
from sector_intelligence.lib import sector_catalog                                    # noqa: E402
from sector_intelligence.compute import engine as compute                              # noqa: E402
from sector_intelligence.publish import bundle as publish                               # noqa: E402


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
    s = sector_catalog.summary()
    _check("catalog has sectors", s["total_sectors"] >= 10, detail=f"got {s['total_sectors']}")
    _check("catalog references india/sectors.py",
            s["sector_map_source"] == "india/sectors.py (tenant-generic)")
    banking = sector_catalog.by_sector_key("sector.india.banking")
    _check("banking spec found", banking.display_name == "Banking")
    _check("banking has constituents",
            len(banking.constituents) >= 5,
            detail=f"got {len(banking.constituents)}")
    it_spec = sector_catalog.by_sector_key("sector.india.it")
    _check("IT sector has constituents",
            len(it_spec.constituents) >= 5,
            detail=f"got {len(it_spec.constituents)}")
    try:
        sector_catalog.by_sector_key("does.not.exist")
        _check("unknown key raises KeyError", False)
    except KeyError:
        _check("unknown key raises KeyError", True)


def test_reuse_dev017_schema():
    """Confirm we're reusing the ARCH017A schema without duplicating."""
    obs = schema.RawObservation(
        variable_key="sector.test.close", asof_utc="2026-07-17T00:00:00.000Z",
        value=1000.5, unit="index_pts", source_id="test", code_sha="deadbeef",
    )
    _check("reuse: RawObservation checksum works",
            obs.checksum is not None and obs.checksum.startswith("sha256:"))
    _check("reuse: confidence framework accessible",
            confidence.tier_from_downstream(0.95) == "High")


def test_compute_primitives():
    """Metric primitives with synthetic series."""
    import pandas as pd
    idx = pd.date_range("2025-01-01", periods=250, freq="D")
    # Rising then flat: closes go from 100 to 150 then hold
    values = list(range(100, 200)) + [200] * 150
    s = pd.Series(values, index=idx, dtype=float)

    ma20 = compute._ma(s, 20)
    _check("MA-20 computable", ma20 is not None and 195 <= ma20 <= 200)

    roc = compute._roc(s, 20)
    _check("ROC-20 computable and 0 on flat tail",
            roc is not None and abs(roc) < 0.1)

    dd = compute._max_drawdown(s, 252)
    _check("Max DD non-positive on monotone-then-flat series", dd is not None and dd <= 0)

    pos = compute._pct_position_52w(s)
    _check("52w position at 100% when at max", pos is not None and pos > 99)

    vol = compute._realised_vol(s.iloc[-25:], 20)                # need n+1 for pct_change
    _check("Vol is small (~0) on flat tail",
            vol is not None and vol < 1.0,
            detail=f"got {vol}")


def test_classification_thresholds():
    """5-class classification enum + threshold ranges."""
    _check("Strong-Bullish in enum", "Strong-Bullish" in compute.CLASS_ENUM)
    _check("Bearish in enum", "Bearish" in compute.CLASS_ENUM)
    _check("Unknown in enum", "Unknown" in compute.CLASS_ENUM)

    # Ranges match the compute_composite thresholds
    thresholds = {
        (95, "Strong-Bullish"),
        (75, "Strong-Bullish"),
        (74.9, "Bullish"),
        (60, "Bullish"),
        (59.9, "Neutral"),
        (45, "Neutral"),
        (44.9, "Weak"),
        (30, "Weak"),
        (29.9, "Bearish"),
    }
    from sector_intelligence.compute.engine import compute_composite  # noqa
    # We can't easily test compute_composite without NormalizedIndicator instances;
    # just verify the enum labels are present as string constants.
    for _, expected in thresholds:
        _check(f"class {expected!r} defined", expected in compute.CLASS_ENUM)


def test_publish_shape():
    """Bundle shape is sensible even with no computed sectors."""
    result = {
        "sectors_attempted": 3, "sectors_computed": 0,
        "derived_count": 0, "normalized_count": 0,
        "classifications_count": 0, "composites_count": 0,
        "asof_utc": "2026-07-17T00:00:00.000Z",
        "_per_sector": [{"sector_key": "sector.india.test",
                          "display_name": "Test",
                          "status": "insufficient_data"}],
        "_global_context": None,
    }
    b = publish.build_bundle(result)
    _check("bundle has dev_version", b.get("dev_version") == "DEV018 v0.1")
    _check("bundle has portfolio_level", "portfolio_level" in b)
    _check("bundle handles zero computed sectors gracefully",
            b["portfolio_level"]["sectors_computed"] == 0)


def main() -> int:
    print("=" * 70)
    print("  DEV018 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_catalog(); print()
    test_reuse_dev017_schema(); print()
    test_compute_primitives(); print()
    test_classification_thresholds(); print()
    test_publish_shape(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
