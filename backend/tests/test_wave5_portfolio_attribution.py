"""Wave 5 · Phase 10 · Portfolio Attribution Engine tests.

Constitution: Article 21 · 25 · 30 · 40 · 91.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.portfolio.monitoring.attribution import (  # noqa: E402
    PortfolioAttributionEngine, compute_attribution,
    ATTRIBUTION_FACTORS, SCHEMA_FINGERPRINT,
)


def test_attribution_schema_fingerprint_present():
    rep = compute_attribution("india", [], date(2026,7,27), run_utc="x")
    assert rep.schema_fingerprint == SCHEMA_FINGERPRINT
    assert rep.schema_version == "1.0.0"
    assert rep.engine == "aegis.portfolio_attribution.v1"


def test_attribution_deterministic():
    positions = [
        {"ticker": "AAA", "realized_return_pct": 5.0,
         "factor_weights": {"momentum": 0.4, "value": 0.3, "quality": 0.3}},
        {"ticker": "BBB", "realized_return_pct": -2.0,
         "factor_weights": {"momentum": -0.5, "sector": 0.2}},
    ]
    r1 = PortfolioAttributionEngine("india").run(positions, date(2026,7,27), run_utc="fixed")
    r2 = PortfolioAttributionEngine("india").run(positions, date(2026,7,27), run_utc="fixed")
    assert r1.positions == r2.positions
    assert r1.aggregate_contributions == r2.aggregate_contributions
    assert r1.total_realized_return_pct == r2.total_realized_return_pct


def test_attribution_sums_to_realized_return_per_position():
    positions = [
        {"ticker": "T1", "realized_return_pct": 10.0,
         "factor_weights": {"momentum": 0.6, "value": 0.4}},
    ]
    rep = compute_attribution("india", positions, date(2026,7,27))
    p = rep.positions[0]
    total_from_contribs = sum(p["contributions"].values())
    assert abs(total_from_contribs - 10.0) < 1e-4, \
        f"contributions must sum to realized_return; got {total_from_contribs} vs 10.0"


def test_attribution_no_signal_becomes_residual():
    positions = [
        {"ticker": "T1", "realized_return_pct": 3.0, "factor_weights": {}},
    ]
    rep = compute_attribution("india", positions, date(2026,7,27))
    contribs = rep.positions[0]["contributions"]
    assert contribs["residual"] == 3.0
    assert all(contribs[f] == 0.0 for f in ATTRIBUTION_FACTORS if f != "residual")


def test_attribution_negative_weights_reduce_contribution():
    positions = [
        {"ticker": "T1", "realized_return_pct": 4.0,
         "factor_weights": {"momentum": 1.0, "risk": -1.0}},
    ]
    rep = compute_attribution("india", positions, date(2026,7,27))
    c = rep.positions[0]["contributions"]
    # Momentum positive, risk negative — magnitudes equal so shares are +2, -2 → residual 4
    assert c["momentum"] > 0
    assert c["risk"] < 0
    total = sum(c.values())
    assert abs(total - 4.0) < 1e-4


def test_attribution_all_13_factors_in_aggregate():
    positions = [{"ticker": f"T{i}", "realized_return_pct": 1.0,
                    "factor_weights": {"momentum": 1.0}} for i in range(3)]
    rep = compute_attribution("india", positions, date(2026,7,27))
    for f in ATTRIBUTION_FACTORS:
        assert f in rep.aggregate_contributions, f"missing aggregate factor: {f}"


def test_attribution_market_required():
    try:
        PortfolioAttributionEngine("")
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty market")


def test_attribution_scales_with_position_count():
    positions = [{"ticker": f"T{i}", "realized_return_pct": 1.0,
                    "factor_weights": {"momentum": 1.0}} for i in range(50)]
    rep = compute_attribution("india", positions, date(2026,7,27))
    assert rep.n_positions == 50
    assert abs(rep.total_realized_return_pct - 50.0) < 1e-3


def test_attribution_dual_market():
    r_ind = compute_attribution("india", [], date(2026,7,27))
    r_usa = compute_attribution("usa", [], date(2026,7,27))
    assert r_ind.market == "india"
    assert r_usa.market == "usa"
    # Same engine, same fingerprint, both markets
    assert r_ind.schema_fingerprint == r_usa.schema_fingerprint
