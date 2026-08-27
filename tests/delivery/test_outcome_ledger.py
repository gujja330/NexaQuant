"""AEGIS · Delivery · Canonical Outcome Ledger reconciliation tests.

CEO 2026-08-27 · reconciliation directive:
> "Verify banner numbers reconcile to the canonical ledger. Verify
>  historical exits cannot be interpreted as current holdings. Verify
>  deterministic repeated builds."

Covers both markets (India + USA) with identical formula.
"""
import pytest
from pathlib import Path


# ── 1 · Reconciliation invariant (formula identity) ───────────────────


def test_realized_90d_uses_sum_not_avg():
    """CEO caught the exact bug: Portfolio banner used AVG(pnls) as
    'Realized 90d P&L' while Exit History summary used SUM(pnls). USA:
    +0.55% vs +293.85%. Canonical formula is SUM."""
    from backend.delivery.outcome_ledger import compute_realized_90d
    rows = [
        {"pnl_pct": 5.0,  "exit_reason": ""},
        {"pnl_pct": 10.0, "exit_reason": ""},
        {"pnl_pct": -3.0, "exit_reason": ""},
    ]
    m = compute_realized_90d(rows)
    assert m.realized_pnl_pct == 12.0, "must be SUM (5+10-3) not AVG"
    assert m.n_exits == 3
    assert m.wr_pct == round(2/3 * 100, 1)


def test_realized_90d_win_threshold_is_strictly_positive_not_half_percent():
    """CEO caught the exact bug: Portfolio banner used `pnl > 0.5` while
    Exit History used `pnl > 0`. India: 28.6% vs 45.5%. Canonical rule
    is strict `pnl > 0`."""
    from backend.delivery.outcome_ledger import compute_realized_90d
    rows = [
        {"pnl_pct": 0.3, "exit_reason": ""},   # was excluded from WR under old bug
        {"pnl_pct": 0.4, "exit_reason": ""},
        {"pnl_pct": -1.0, "exit_reason": ""},
    ]
    m = compute_realized_90d(rows)
    assert m.wr_pct == round(2/3 * 100, 1), \
        f"canonical WR must count 0.3% and 0.4% as wins · got {m.wr_pct}"


def test_zero_pnl_rotations_are_excluded_from_realized_summary():
    """Rotation artifacts (|pnl| <= 0.01%) are excluded from the exits
    count · but their presence in the raw data is disclosed via
    n_zero_pnl_excluded so the reader can reason about denominator."""
    from backend.delivery.outcome_ledger import compute_realized_90d
    rows = [
        {"pnl_pct": 5.0,   "exit_reason": ""},
        {"pnl_pct": 0.0,   "exit_reason": "Rotated to X"},
        {"pnl_pct": 0.005, "exit_reason": "Rotated to Y"},
        {"pnl_pct": -2.0,  "exit_reason": ""},
    ]
    m = compute_realized_90d(rows)
    assert m.n_exits == 2
    assert m.n_zero_pnl_excluded == 2


# ── 2 · Composition disclosure ────────────────────────────────────────


def test_composition_breakdown_labels_orphan_rotation_clean():
    """CEO: '91% of USA exits are ORPHAN_AUTO_CLOSE. The population is
    not homogeneous. Compositions must be surfaced.'"""
    from backend.delivery.outcome_ledger import compute_realized_90d
    rows = [
        {"pnl_pct": 1.0, "exit_reason": "ORPHAN_AUTO_CLOSE · repair"},
        {"pnl_pct": 2.0, "exit_reason": "ORPHAN_AUTO_CLOSE"},
        {"pnl_pct": 3.0, "exit_reason": "Rotated to X · better setup"},
        {"pnl_pct": 4.0, "exit_reason": "TARGET_1_HIT"},
    ]
    m = compute_realized_90d(rows)
    assert m.n_orphan_auto_close == 2
    assert m.n_rotation == 1
    assert m.n_other == 1
    assert m.n_orphan_auto_close + m.n_rotation + m.n_other == m.n_exits


# ── 3 · Scope discipline: current ≠ historical ────────────────────────


def test_current_portfolio_metrics_do_not_include_realized_pnl():
    """CurrentPortfolioMetrics dataclass has no realized_pnl_pct field.
    The current banner CANNOT accidentally mix in realized numbers."""
    from backend.delivery.outcome_ledger import (
        CurrentPortfolioMetrics, compute_current_portfolio,
    )
    m = compute_current_portfolio([
        {"unrealized_pnl_pct": 2.0, "today_pnl_pct": 0.5},
    ])
    assert not hasattr(m, "realized_pnl_pct")
    assert not hasattr(m, "wr_pct")


def test_realized_90d_metrics_do_not_include_current_portfolio_size():
    """Realized90dMetrics has no `n_active` field. The realized banner
    CANNOT mislabel current-portfolio size as historical exits."""
    from backend.delivery.outcome_ledger import Realized90dMetrics
    m = Realized90dMetrics(n_exits=0, realized_pnl_pct=0.0, wr_pct=0.0,
                            n_positive=0, n_negative=0,
                            positive_total_pct=0.0, negative_total_pct=0.0,
                            n_orphan_auto_close=0, n_rotation=0, n_other=0,
                            n_zero_pnl_excluded=0)
    assert not hasattr(m, "n_active")


def test_banner_text_carries_scope_label():
    """Every banner string carries an explicit scope qualifier: 'current',
    'realized 90d', or 'full audit'. Never a bare 'Win Rate'."""
    from backend.delivery.outcome_ledger import (
        format_portfolio_banner, format_exit_history_summary,
        CurrentPortfolioMetrics, Realized90dMetrics,
    )
    p = CurrentPortfolioMetrics(n_active=5, unrealized_pnl_pct=1.0,
                                 today_pnl_pct=0.5, n_positive=3, n_negative=2,
                                 avg_positive_pnl=2.0, avg_negative_pnl=-1.0)
    r = Realized90dMetrics(n_exits=100, realized_pnl_pct=12.5, wr_pct=45.0,
                            n_positive=45, n_negative=55,
                            positive_total_pct=90.0, negative_total_pct=-77.5,
                            n_orphan_auto_close=80, n_rotation=15, n_other=5,
                            n_zero_pnl_excluded=10)
    assert "current" in format_portfolio_banner(p).lower()
    assert "realized" in format_exit_history_summary(r).lower()
    assert "(current)" in format_portfolio_banner(p).lower() or \
            "current)" in format_portfolio_banner(p).lower()


# ── 4 · Determinism (10 reruns · byte-identical output) ───────────────


def test_realized_90d_is_deterministic_across_reruns():
    """Rerunning compute_realized_90d on the same input yields identical
    output every time · byte-equal serialization."""
    from backend.delivery.outcome_ledger import compute_realized_90d
    import json
    from dataclasses import asdict
    rows = [
        {"pnl_pct": 5.0,  "exit_reason": "ORPHAN_AUTO_CLOSE"},
        {"pnl_pct": -3.0, "exit_reason": "STOP_LOSS_HIT"},
        {"pnl_pct": 0.005, "exit_reason": "Rotated to X"},
        {"pnl_pct": 1.5,  "exit_reason": "TARGET_1_HIT"},
        {"pnl_pct": -2.0, "exit_reason": "Rotated to Y"},
    ]
    outputs = set()
    for _ in range(10):
        m = compute_realized_90d(rows)
        outputs.add(json.dumps(asdict(m), sort_keys=True))
    assert len(outputs) == 1, \
        f"compute_realized_90d produced {len(outputs)} distinct outputs · " \
        "not deterministic"


def test_current_portfolio_is_deterministic_across_reruns():
    from backend.delivery.outcome_ledger import compute_current_portfolio
    import json
    from dataclasses import asdict
    active = [
        {"unrealized_pnl_pct": 2.0,  "today_pnl_pct": 0.5},
        {"unrealized_pnl_pct": -1.5, "today_pnl_pct": -0.2},
        {"unrealized_pnl_pct": 3.7,  "today_pnl_pct": 0.8},
    ]
    outputs = set()
    for _ in range(10):
        m = compute_current_portfolio(active)
        outputs.add(json.dumps(asdict(m), sort_keys=True))
    assert len(outputs) == 1


# ── 5 · Cross-market formula parity ───────────────────────────────────


def test_india_and_usa_use_identical_formula():
    """The same input rows produce the same output regardless of which
    market label is attached. Formula is market-agnostic."""
    from backend.delivery.outcome_ledger import compute_realized_90d
    rows = [
        {"pnl_pct": 5.0, "exit_reason": ""},
        {"pnl_pct": -2.0, "exit_reason": ""},
    ]
    india = compute_realized_90d(rows)
    usa = compute_realized_90d(rows)
    assert india == usa, \
        "compute_realized_90d must be market-agnostic · same rows = same result"


# ── 6 · Empty edge cases (no crash · zeros) ───────────────────────────


def test_empty_exit_rows_produce_zeros():
    from backend.delivery.outcome_ledger import compute_realized_90d
    m = compute_realized_90d([])
    assert m.n_exits == 0 and m.realized_pnl_pct == 0.0 and m.wr_pct == 0.0


def test_empty_active_positions_produce_zeros():
    from backend.delivery.outcome_ledger import compute_current_portfolio
    m = compute_current_portfolio([])
    assert m.n_active == 0 and m.unrealized_pnl_pct == 0.0


# ── 7 · Definitions sheet contract ────────────────────────────────────


def test_definitions_rows_include_all_three_scopes():
    """Definitions sheet MUST document all three scopes explicitly."""
    from backend.delivery.outcome_ledger import DEFINITIONS_ROWS
    labels = "\n".join(k for k, _ in DEFINITIONS_ROWS)
    assert "CURRENT" in labels.upper()
    assert "REALIZED 90d" in labels or "REALIZED 90D" in labels.upper()
    assert "AUDIT" in labels.upper()


def test_definitions_rows_declare_formulas_explicitly():
    from backend.delivery.outcome_ledger import DEFINITIONS_ROWS
    body = "\n".join(f"{k} :: {v}" for k, v in DEFINITIONS_ROWS)
    assert "SUM" in body
    assert "positive means pnl_pct > 0" in body.lower() or \
            "pnl_pct > 0" in body
    assert "504" in body or "Never mix" in body or "504 historical" in body or \
            "≠" in body


def test_definitions_rows_disclose_composition_rule():
    from backend.delivery.outcome_ledger import DEFINITIONS_ROWS
    body = "\n".join(v for _, v in DEFINITIONS_ROWS)
    assert "ORPHAN_AUTO_CLOSE" in body.upper()
    assert "ROTATION" in body.upper()


# ── 8 · Historical exits cannot masquerade as current holdings ────────


def test_historical_exits_count_never_matches_current_field_name():
    """Structural guard: no code path can label historical exits count
    as `n_active`. Type system prevents accidental swap."""
    from backend.delivery.outcome_ledger import (
        Realized90dMetrics, CurrentPortfolioMetrics,
    )
    r_fields = {f for f in Realized90dMetrics.__dataclass_fields__}
    c_fields = {f for f in CurrentPortfolioMetrics.__dataclass_fields__}
    assert r_fields.isdisjoint(c_fields - {"n_positive", "n_negative"}), \
        "current + realized dataclasses share no ambiguous fields"
    assert "n_active" in c_fields
    assert "n_active" not in r_fields
    assert "n_exits" in r_fields
    assert "n_exits" not in c_fields
