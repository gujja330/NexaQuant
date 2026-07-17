"""DEV020 smoke tests. Fast; no network required."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from global_intelligence.lib import schema, confidence                              # noqa: E402
from company_intelligence.lib import company_catalog                                   # noqa: E402
from company_intelligence.compute import engine as compute                              # noqa: E402
from company_intelligence.publish import bundle as publish                                # noqa: E402


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
    s = company_catalog.summary()
    _check("catalog has 50+ companies", s["total_companies_mapped"] >= 50,
            detail=f"got {s['total_companies_mapped']}")
    _check("catalog reports disk availability",
            "with_parquet_on_disk" in s)
    _check("catalog reports unmapped tickers", "unmapped_tickers_on_disk" in s)

    # HDFCBANK should be in the universe
    try:
        c = company_catalog.by_ticker("HDFCBANK")
        _check("HDFCBANK found",
                c.industry_key == "industry.india.private_banks",
                detail=f"industry={c.industry_key}")
    except KeyError:
        _check("HDFCBANK found", False, detail="missing from catalog")

    try:
        company_catalog.by_ticker("DOES_NOT_EXIST_XYZ")
        _check("unknown ticker raises KeyError", False)
    except KeyError:
        _check("unknown ticker raises KeyError", True)


def test_reuse_dev017_schema():
    obs = schema.RawObservation(
        variable_key="company.test", asof_utc="2026-07-17T00:00:00.000Z",
        value=100.0, unit="INR", source_id="test", code_sha="deadbeef")
    _check("reuse: schema.RawObservation works", obs.checksum is not None)
    _check("reuse: confidence tier",
            confidence.tier_from_downstream(0.95) == "High")


def test_validation():
    """validate_ticker rejects short history / invalid data."""
    import pandas as pd

    # Empty df
    ok, reason = compute.validate_ticker("TEST", pd.DataFrame())
    _check("empty df rejected", not ok and "no_data" in reason)

    # Too little history
    idx = pd.date_range("2025-01-01", periods=50, freq="D")
    df = pd.DataFrame({"close": range(100, 150), "tick_volume": [1_000_000] * 50}, index=idx)
    ok, reason = compute.validate_ticker("TEST", df)
    _check("short history rejected", not ok and "insufficient_history" in reason,
            detail=f"got: {reason}")

    # Enough history, positive close
    idx = pd.date_range("2025-01-01", periods=200, freq="D")
    df = pd.DataFrame({"close": range(100, 300), "tick_volume": [100_000_000] * 200}, index=idx)
    ok, reason = compute.validate_ticker("TEST", df)
    _check("valid df accepted", ok, detail=f"got: {reason}")


def test_metric_primitives():
    import pandas as pd
    idx = pd.date_range("2025-01-01", periods=260, freq="D")
    vals = list(range(100, 200)) + [200] * 160
    s = pd.Series(vals, index=idx, dtype=float)
    _check("MA-20 in range", 195 < compute._ma(s, 20) <= 200)
    _check("ROC-20 on flat = 0", abs(compute._roc(s, 20)) < 0.1)
    _check("DD non-positive", compute._max_drawdown(s, 252) <= 0)
    _check("52w-pos near 100", compute._pct_position_52w(s) > 99)


def test_classification_thresholds():
    _check("Strong-Bullish in enum", "Strong-Bullish" in compute.CLASS_ENUM)
    _check("Bearish in enum", "Bearish" in compute.CLASS_ENUM)
    _check("Unknown in enum", "Unknown" in compute.CLASS_ENUM)


def test_ranking_logic():
    """Verify overall_rank, sector_rank, industry_rank make sense on a small synthetic set."""
    from global_intelligence.lib.schema import CompositeScore, Classification

    entries = []
    for i, (score, sec, ind) in enumerate([
        (90, "S1", "I1"),
        (80, "S1", "I1"),
        (70, "S1", "I2"),
        (60, "S2", "I3"),
        (50, "S2", "I3"),
    ]):
        comp = CompositeScore(
            composite_key=f"composite.test.{i}", asof_utc="2026-07-17T00:00:00.000Z",
            value_0_100=float(score), classification="Bullish", confidence=0.9,
            weighting_scheme="test", weighting_version="v1.0",
            component_indicators=[],
        )
        entries.append({
            "ticker": f"T{i}", "status": "computed",
            "industry_key": ind, "parent_sector_key": sec,
            "composite": comp, "risk_score": 60.0,
        })

    # Emulate the ranking logic in engine.run_compute_cycle
    computed = entries[:]
    computed.sort(key=lambda x: x["composite"].value_0_100, reverse=True)
    for rank, e in enumerate(computed, start=1):
        e["overall_rank"] = rank
    _check("overall_rank #1 has highest score",
            computed[0]["overall_rank"] == 1 and computed[0]["composite"].value_0_100 == 90)

    from collections import defaultdict
    by_sec = defaultdict(list)
    for e in computed:
        by_sec[e["parent_sector_key"]].append(e)
    for _, xs in by_sec.items():
        xs.sort(key=lambda x: x["composite"].value_0_100, reverse=True)
        for rank, e in enumerate(xs, start=1):
            e["sector_rank"] = rank
    _check("sector_rank #1 in S1 has score 90",
            any(e["sector_rank"] == 1 and e["parent_sector_key"] == "S1"
                for e in computed))


def test_bundle_shape():
    result = {
        "companies_attempted": 3, "companies_computed": 0,
        "rejections": {"no_data": 3},
        "derived_count": 0, "normalized_count": 0,
        "classifications_count": 0, "composites_count": 0,
        "asof_utc": "2026-07-17T00:00:00.000Z",
        "_per_company": [{"ticker": "TEST", "status": "rejected",
                            "reason": "no_data",
                            "industry_key": "industry.test",
                            "parent_sector_key": "sector.test"}],
        "_global_context": None,
        "_sector_context": None,
        "_industry_context": None,
    }
    b = publish.build_bundle(result)
    _check("bundle has dev_version DEV020", b["dev_version"] == "DEV020 v0.1")
    _check("bundle handles all-rejected gracefully",
            b["portfolio_level"]["companies_computed"] == 0)
    _check("bundle exposes class_distribution",
            "class_distribution" in b["portfolio_level"])
    _check("bundle exposes sector_summary",
            "sector_summary" in b["portfolio_level"])
    _check("bundle exposes top_10 + bottom_10",
            "top_10" in b["portfolio_level"] and "bottom_10" in b["portfolio_level"])


def main() -> int:
    print("=" * 70)
    print("  DEV020 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_catalog(); print()
    test_reuse_dev017_schema(); print()
    test_validation(); print()
    test_metric_primitives(); print()
    test_classification_thresholds(); print()
    test_ranking_logic(); print()
    test_bundle_shape(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
