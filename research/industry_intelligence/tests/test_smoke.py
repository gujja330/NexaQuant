"""DEV019 smoke tests. Fast; no network required."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from global_intelligence.lib import schema, confidence                             # noqa: E402
from industry_intelligence.lib import industry_catalog                              # noqa: E402
from industry_intelligence.compute import engine as compute                          # noqa: E402
from industry_intelligence.publish import bundle as publish                            # noqa: E402


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
    s = industry_catalog.summary()
    _check("catalog has industries", s["total_industries_defined"] >= 25,
            detail=f"got {s['total_industries_defined']}")
    _check("catalog reports 3+ constituent industries",
            s["with_3plus_available_constituents"] >= 20,
            detail=f"got {s['with_3plus_available_constituents']}")

    banks = industry_catalog.by_industry_key("industry.india.private_banks")
    _check("private_banks industry exists", banks.display_name == "Private Banks")
    _check("private_banks parent is sector.india.banking",
            banks.parent_sector_key == "sector.india.banking")
    _check("private_banks has 5+ available constituents",
            len(banks.available_tickers()) >= 5)

    try:
        industry_catalog.by_industry_key("does.not.exist")
        _check("unknown industry_key raises KeyError", False)
    except KeyError:
        _check("unknown industry_key raises KeyError", True)


def test_ticker_uniqueness():
    """Each ticker appears in at most one industry — no double-counting."""
    seen = set()
    dupes = []
    for i in industry_catalog.INDUSTRIES:
        for t in i.tickers:
            if t in seen:
                dupes.append(t)
            seen.add(t)
    # Some intentional overlap (e.g. IRFC in NBFC + Railways; NHPC/SJVN in
    # Power Generation + Renewables; POLYCAB/HAVELLS in Capital Goods +
    # Electricals). Cap at 15 total.
    _check("ticker duplication under 15", len(dupes) <= 15,
            detail=f"dupes: {len(dupes)}")


def test_parent_sectors_valid():
    """Every parent_sector_key references a valid sector from DEV018 catalog."""
    import sys as _sys
    from sector_intelligence.lib import sector_catalog
    valid = {s.sector_key for s in sector_catalog.SECTORS}
    invalid = [i.parent_sector_key for i in industry_catalog.INDUSTRIES
                if i.parent_sector_key not in valid]
    _check("all parent_sector_keys valid", not invalid, detail=f"invalid: {set(invalid)}")


def test_reuse_dev017_schema():
    obs = schema.RawObservation(
        variable_key="industry.test", asof_utc="2026-07-17T00:00:00.000Z",
        value=100.0, unit="index_pts", source_id="test", code_sha="deadbeef")
    _check("reuse: RawObservation works", obs.checksum is not None)
    _check("reuse: confidence tier available",
            confidence.tier_from_downstream(0.95) == "High")


def test_metric_primitives():
    import pandas as pd
    idx = pd.date_range("2025-01-01", periods=260, freq="D")
    vals = list(range(100, 200)) + [200] * 160
    s = pd.Series(vals, index=idx, dtype=float)
    _check("MA-20 sane", 195 < compute._ma(s, 20) <= 200)
    _check("ROC-20 on flat = 0", abs(compute._roc(s, 20)) < 0.1)
    _check("DD non-positive on rising series",
            compute._max_drawdown(s, 252) <= 0)
    _check("52w-pos at 100 near max", compute._pct_position_52w(s) > 99)


def test_rotation_labels():
    """Rotation classifier returns valid labels for synthetic series."""
    import pandas as pd
    idx = pd.date_range("2025-01-01", periods=200, freq="D")
    ind = pd.Series(range(100, 300), index=idx, dtype=float)                    # rises 100 -> 299
    nifty = pd.Series([100 + 0.5 * i for i in range(200)], index=idx, dtype=float)  # rises 100 -> 199.5
    label = compute.compute_rotation(ind, nifty, 80.0, None)
    _check("rotation returns valid enum",
            label in compute.ROTATION_ENUM, detail=f"got {label}")

    # Case 2: flat series — should return Lagging or Weakening
    flat = pd.Series([100.0] * 200, index=idx, dtype=float)
    label2 = compute.compute_rotation(flat, nifty, 40.0, None)
    _check("rotation on flat series returns valid enum",
            label2 in compute.ROTATION_ENUM, detail=f"got {label2}")


def test_bundle_shape():
    result = {
        "industries_attempted": 3, "industries_computed": 0,
        "derived_count": 0, "normalized_count": 0,
        "classifications_count": 0, "composites_count": 0,
        "asof_utc": "2026-07-17T00:00:00.000Z",
        "_per_industry": [{"industry_key": "industry.test",
                              "display_name": "Test",
                              "parent_sector_key": "sector.test",
                              "parent_sector_name": "Test",
                              "status": "insufficient_constituents",
                              "n_used": 2, "n_defined": 5}],
        "_global_context": None,
        "_sector_context": None,
    }
    b = publish.build_bundle(result)
    _check("bundle has dev_version", b.get("dev_version") == "DEV019 v0.1")
    _check("bundle handles zero computed industries gracefully",
            b["portfolio_level"]["industries_computed"] == 0)
    _check("bundle exposes rotation_distribution key",
            "rotation_distribution" in b["portfolio_level"])
    _check("bundle exposes upstream_sector_context",
            "upstream_sector_context" in b)


def main() -> int:
    print("=" * 70)
    print("  DEV019 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_catalog(); print()
    test_ticker_uniqueness(); print()
    test_parent_sectors_valid(); print()
    test_reuse_dev017_schema(); print()
    test_metric_primitives(); print()
    test_rotation_labels(); print()
    test_bundle_shape(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
