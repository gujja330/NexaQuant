"""Sprint 5 regression — Portfolio Engine + AI Portfolio Analyst."""
from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.portfolio             import (                                                # noqa: E402
    PortfolioEngine, build_portfolio, compute_diversification_metrics,
    diff_portfolios, compute_cash_reserve,
)
from backend.portfolio.types       import (                                                # noqa: E402
    Position, PortfolioSnapshot, TradeAction,
)
from backend.ai import portfolio_analyst                                                    # noqa: E402


def _sample_sized_positions():
    """Sprint-4-shaped input: list of dicts with required fields."""
    return [
        {"ticker": "T1", "target_weight": 0.06,  "confidence": 0.85, "sector": "Tech",   "entry_reference": 100, "stop_loss_pct": -0.10, "action": "STRONG_BUY"},
        {"ticker": "T2", "target_weight": 0.04,  "confidence": 0.65, "sector": "Tech",   "entry_reference": 80,  "stop_loss_pct": -0.10, "action": "BUY"},
        {"ticker": "T3", "target_weight": 0.05,  "confidence": 0.70, "sector": "Health", "entry_reference": 60,  "stop_loss_pct": -0.10, "action": "BUY"},
        {"ticker": "T4", "target_weight": -0.04, "confidence": 0.60, "sector": "Energy", "entry_reference": 40,  "stop_loss_pct": -0.10, "action": "SELL"},
        {"ticker": "T5", "target_weight": 0.001, "confidence": 0.90, "sector": "Finance","entry_reference": 90,  "stop_loss_pct": -0.10, "action": "BUY"},   # below min
    ]


# ── Cash policy ────────────────────────────────────────────────
def test_cash_reserve_stress_uses_higher():
    assert compute_cash_reserve("stress", 0.05, 0.25) == 0.25
    print(f"  [OK] cash reserve: stress regime uses stress reserve (0.25)")


def test_cash_reserve_bear_midpoint():
    r = compute_cash_reserve("bear", 0.05, 0.25)
    assert 0.14 <= r <= 0.16
    print(f"  [OK] cash reserve: bear regime is midpoint ({r})")


def test_cash_reserve_default_min():
    assert compute_cash_reserve("bull", 0.05, 0.25) == 0.05
    assert compute_cash_reserve("neutral", 0.05, 0.25) == 0.05
    print(f"  [OK] cash reserve: normal regimes use min (0.05)")


# ── Construction ───────────────────────────────────────────────
def test_build_portfolio_drops_below_min():
    positions = build_portfolio(
        _sample_sized_positions(), target_n=20, min_position_size=0.01,
        cash_reserve=0.05, asof="2026-07-21", market="usa",
    )
    # T5 (0.001) should be dropped by min_position_size
    tickers = {p.ticker for p in positions}
    assert "T5" not in tickers
    print(f"  [OK] build_portfolio drops positions below min_position_size")


def test_build_portfolio_normalizes_to_target_gross():
    positions = build_portfolio(
        _sample_sized_positions(), target_n=20, min_position_size=0.001,
        cash_reserve=0.10, asof="2026-07-21", market="usa",
    )
    gross = sum(abs(p.weight) for p in positions)
    # Weights are rounded to 6dp per position; N positions → tolerance N × 1e-6
    assert abs(gross - 0.90) < 1e-4, f"expected gross≈0.90 got {gross}"
    print(f"  [OK] build_portfolio normalizes to (1 - cash_reserve) ≈ 0.90 (got {gross:.6f})")


def test_build_portfolio_top_n_cap():
    positions = build_portfolio(
        _sample_sized_positions(), target_n=2, min_position_size=0.001,
        cash_reserve=0.05, asof="2026-07-21", market="usa",
    )
    assert len(positions) == 2
    print(f"  [OK] build_portfolio respects target_n cap")


# ── Diversification ────────────────────────────────────────────
def test_diversification_effective_n_matches_1_over_hhi():
    positions = [Position(market="usa", ticker=f"T{i}", weight=0.1, sector="X")
                 for i in range(10)]
    m = compute_diversification_metrics(positions)
    assert abs(m["hhi"] - 0.1) < 1e-9
    assert abs(m["effective_n"] - 10.0) < 1e-9
    print(f"  [OK] diversification: effective_n = 1/HHI (10 uniform positions → effN=10)")


def test_diversification_sector_map():
    positions = [
        Position(market="usa", ticker="T1", weight=0.3, sector="Tech"),
        Position(market="usa", ticker="T2", weight=0.2, sector="Tech"),
        Position(market="usa", ticker="T3", weight=0.1, sector="Health"),
    ]
    m = compute_diversification_metrics(positions)
    assert abs(m["per_sector_pct"]["Tech"] - 0.5) < 1e-9
    assert abs(m["per_sector_pct"]["Health"] - 0.1) < 1e-9
    assert m["n_sectors"] == 2
    print(f"  [OK] diversification: per-sector map built correctly")


# ── Rebalance diff ─────────────────────────────────────────────
def test_diff_open_and_close():
    prior = PortfolioSnapshot(market="usa", asof=date(2026, 7, 20),
                                 positions=[Position(market="usa", ticker="A", weight=0.10)])
    curr  = PortfolioSnapshot(market="usa", asof=date(2026, 7, 21),
                                 positions=[Position(market="usa", ticker="B", weight=0.15)])
    d = diff_portfolios(prior, curr, rebalance_threshold_bps=25)
    actions = {i.ticker: i.action for i in d.instructions}
    assert actions["A"] == TradeAction.CLOSE
    assert actions["B"] == TradeAction.OPEN
    assert d.n_open == 1 and d.n_close == 1
    print(f"  [OK] diff: OPEN + CLOSE actions detected")


def test_diff_hold_when_delta_below_threshold():
    prior = PortfolioSnapshot(market="usa", asof=date(2026, 7, 20),
                                 positions=[Position(market="usa", ticker="X", weight=0.100)])
    curr  = PortfolioSnapshot(market="usa", asof=date(2026, 7, 21),
                                 positions=[Position(market="usa", ticker="X", weight=0.101)])
    d = diff_portfolios(prior, curr, rebalance_threshold_bps=25)
    x = next(i for i in d.instructions if i.ticker == "X")
    assert x.action == TradeAction.HOLD
    print(f"  [OK] diff: |Δ|≤25bps → HOLD (no trade)")


def test_diff_increase_and_decrease():
    prior = PortfolioSnapshot(market="usa", asof=date(2026, 7, 20),
                                 positions=[Position(market="usa", ticker="X", weight=0.10),
                                              Position(market="usa", ticker="Y", weight=0.05)])
    curr  = PortfolioSnapshot(market="usa", asof=date(2026, 7, 21),
                                 positions=[Position(market="usa", ticker="X", weight=0.15),
                                              Position(market="usa", ticker="Y", weight=0.01)])
    d = diff_portfolios(prior, curr, rebalance_threshold_bps=25)
    a = {i.ticker: i.action for i in d.instructions}
    assert a["X"] == TradeAction.INCREASE
    assert a["Y"] == TradeAction.DECREASE
    assert d.n_increase == 1 and d.n_decrease == 1
    print(f"  [OK] diff: INCREASE + DECREASE detected")


def test_diff_turnover_math():
    prior = PortfolioSnapshot(market="usa", asof=date(2026, 7, 20),
                                 positions=[Position(market="usa", ticker="X", weight=0.20)])
    curr  = PortfolioSnapshot(market="usa", asof=date(2026, 7, 21),
                                 positions=[Position(market="usa", ticker="Y", weight=0.20)])
    d = diff_portfolios(prior, curr, rebalance_threshold_bps=25)
    # |Δ_X| = 0.20, |Δ_Y| = 0.20 → turnover = 0.40 / 2 = 0.20
    assert abs(d.turnover_pct - 0.20) < 1e-9
    print(f"  [OK] diff: turnover_pct = sum(|Δ|)/2")


# ── End-to-end engine ──────────────────────────────────────────
def test_engine_end_to_end():
    engine = PortfolioEngine(
        _ROOT, "usa",
        target_n_positions=10, min_position_size=0.005,
        cash_reserve_min=0.05, cash_reserve_stress=0.20,
        rebalance_threshold_bps=25, regime="neutral",
        model_stamp={"model_id": "aegis.portfolio.v1", "version": "1.0.0"},
    )
    ts_map = {"T1": "Tech", "T2": "Tech", "T3": "Health", "T4": "Energy"}
    snap, diff = engine.run(_sample_sized_positions(), ts_map, asof=date(2026, 7, 21))
    assert snap.n_positions >= 3   # T5 dropped
    assert 0.90 <= sum(abs(p.weight) for p in snap.positions) <= 0.96  # gross = ~0.95
    assert snap.cash_pct >= 0.04
    assert snap.hhi > 0 and snap.effective_n > 1
    print(f"  [OK] engine end-to-end: n={snap.n_positions} gross={1-snap.cash_pct:.3f} HHI={snap.hhi:.3f}")


def test_engine_deterministic():
    engine = PortfolioEngine(
        _ROOT, "usa",
        target_n_positions=10, min_position_size=0.005,
        cash_reserve_min=0.05, cash_reserve_stress=0.20,
        rebalance_threshold_bps=25, regime="neutral",
    )
    s1, _ = engine.run(_sample_sized_positions(), None, asof=date(2026, 7, 21))
    s2, _ = engine.run(_sample_sized_positions(), None, asof=date(2026, 7, 21))
    w1 = [(p.ticker, p.weight) for p in s1.positions]
    w2 = [(p.ticker, p.weight) for p in s2.positions]
    assert w1 == w2, "engine not deterministic"
    print(f"  [OK] engine deterministic across identical calls")


def test_engine_accepts_cutoff():
    engine = PortfolioEngine(
        _ROOT, "usa",
        target_n_positions=10, min_position_size=0.005,
        cash_reserve_min=0.05, cash_reserve_stress=0.20,
        rebalance_threshold_bps=25, regime="bull",
    )
    past = date(2020, 1, 1)
    snap, _ = engine.run(_sample_sized_positions(), None, asof=past)
    assert snap.asof == past
    print(f"  [OK] engine accepts historical cutoff (walk-forward ready)")


def test_engine_cash_policy_in_stress_regime():
    engine = PortfolioEngine(
        _ROOT, "usa",
        target_n_positions=10, min_position_size=0.005,
        cash_reserve_min=0.05, cash_reserve_stress=0.20,
        rebalance_threshold_bps=25, regime="stress",
    )
    snap, _ = engine.run(_sample_sized_positions(), None, asof=date(2026, 7, 21))
    # Stress regime → cash_reserve_target should be 20%
    assert snap.cash_reserve_target == 0.20
    assert snap.cash_pct >= 0.19   # allow tiny normalization noise
    print(f"  [OK] stress regime enforces 20% cash reserve (actual={snap.cash_pct * 100:.1f}%)")


# ── AI Portfolio Analyst ───────────────────────────────────────
def test_ai_analyst_runs():
    engine = PortfolioEngine(
        _ROOT, "usa", target_n_positions=10, min_position_size=0.005,
        cash_reserve_min=0.05, cash_reserve_stress=0.20,
        rebalance_threshold_bps=25, regime="neutral",
    )
    ts_map = {"T1": "Tech", "T2": "Tech", "T3": "Health"}
    snap, diff = engine.run(_sample_sized_positions(), ts_map, asof=date(2026, 7, 21))
    out = portfolio_analyst.run(snap, diff, 8.0, 0.30, "usa", date(2026, 7, 21))
    assert out.agent == "portfolio_analyst"
    assert out.headline and out.narrative
    print(f"  [OK] AI Portfolio Analyst: {out.headline[:80]}")


def test_ai_analyst_never_promotes():
    engine = PortfolioEngine(
        _ROOT, "usa", target_n_positions=10, min_position_size=0.005,
        cash_reserve_min=0.05, cash_reserve_stress=0.20,
        rebalance_threshold_bps=25, regime="neutral",
    )
    snap, diff = engine.run(_sample_sized_positions(), None, asof=date(2026, 7, 21))
    out = portfolio_analyst.run(snap, diff, 8.0, 0.30, "usa", date(2026, 7, 21))
    forbidden = {"buy", "sell", "target_price", "recommendation",
                  "action", "promoted", "approved"}
    for f in out.findings:
        keys = set(f.keys()) if isinstance(f, dict) else set()
        leak = keys & forbidden
        assert not leak, f"AI Portfolio Analyst leaked: {leak}"
    print(f"  [OK] AI Portfolio Analyst obeys no-promotion contract")


# ── Integration ─────────────────────────────────────────────────
def test_india_runner():
    r = subprocess.run(
        [sys.executable, "india/portfolio_engine/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "reports" / "portfolio_v3.json").read_text(encoding="utf-8"))
    assert d["market"] == "india"
    assert "snapshot" in d and "config_snapshot" in d and "model_stamp" in d
    print(f"  [OK] india runner: n_positions={d['snapshot']['n_positions']}")


def test_usa_runner():
    r = subprocess.run(
        [sys.executable, "usa/research/portfolio_engine/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "usa" / "reports" / "portfolio_v3.json").read_text(encoding="utf-8"))
    assert d["market"] == "usa" and d["currency"] == "USD"
    print(f"  [OK] usa runner: n_positions={d['snapshot']['n_positions']} currency={d['currency']}")


TESTS = [
    test_cash_reserve_stress_uses_higher, test_cash_reserve_bear_midpoint, test_cash_reserve_default_min,
    test_build_portfolio_drops_below_min, test_build_portfolio_normalizes_to_target_gross,
    test_build_portfolio_top_n_cap,
    test_diversification_effective_n_matches_1_over_hhi, test_diversification_sector_map,
    test_diff_open_and_close, test_diff_hold_when_delta_below_threshold,
    test_diff_increase_and_decrease, test_diff_turnover_math,
    test_engine_end_to_end, test_engine_deterministic, test_engine_accepts_cutoff,
    test_engine_cash_policy_in_stress_regime,
    test_ai_analyst_runs, test_ai_analyst_never_promotes,
    test_india_runner, test_usa_runner,
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=" * 70)
    print("  SPRINT 5 · Portfolio Engine · Regression Tests")
    print("=" * 70)
    n_pass = 0; n_fail = 0
    for t in TESTS:
        try:
            t(); n_pass += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}"); n_fail += 1
        except Exception as e:
            print(f"  [ERR ] {t.__name__}: {type(e).__name__}: {e}"); n_fail += 1
    print()
    print(f"  {n_pass} passed, {n_fail} failed of {len(TESTS)}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
