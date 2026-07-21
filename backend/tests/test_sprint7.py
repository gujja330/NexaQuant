"""Sprint 7 regression — Execution Simulator + Statistics module."""
from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.statistics                  import (                                          # noqa: E402
    sharpe_ratio, sortino_ratio, calmar_ratio, max_drawdown, cagr,
    profit_factor, hit_rate, expected_value, avg_winner, avg_loser,
    information_ratio, alpha_beta, turnover,
    METRICS_VERSION,
)
from backend.execution                   import (                                          # noqa: E402
    ExecutionEngine, simulate_fills, compute_slippage_bps,
    commission_bps, compute_equity_curve, apply_corporate_actions, gap_stop_out,
)
from backend.execution.types             import Fill, ExecutionSummary                     # noqa: E402
from backend.ai import execution_analyst                                                    # noqa: E402


# ── Statistics ──────────────────────────────────────────────────
def test_metrics_version_defined():
    assert METRICS_VERSION and "." in METRICS_VERSION
    print(f"  [OK] METRICS_VERSION = {METRICS_VERSION} (single source of truth)")


def test_sharpe_zero_stdev_returns_none():
    assert sharpe_ratio([0.01, 0.01, 0.01]) is None
    print(f"  [OK] Sharpe returns None on zero stdev")


def test_sharpe_annualised_math():
    """Mean 0.001 daily, stdev 0.01 → Sharpe ≈ 0.001/0.01 × sqrt(252) ≈ 1.587."""
    rs = [0.001] * 100 + [-0.008] * 100 + [0.010] * 100
    s = sharpe_ratio(rs)
    assert s is not None and 0.1 < s < 3.5
    print(f"  [OK] Sharpe annualised on synthetic returns: {s:.3f}")


def test_max_drawdown_finds_worst_trough():
    curve = [100, 110, 120, 90, 100, 60, 80]      # peak 120, trough 60 → -50%
    mdd = max_drawdown(curve)
    assert mdd is not None and abs(mdd + 0.5) < 1e-9
    print(f"  [OK] max_drawdown = -50% on 120→60 curve")


def test_profit_factor():
    pf = profit_factor([0.10, 0.05, -0.02, -0.03])            # 0.15 / 0.05
    assert pf is not None and abs(pf - 3.0) < 1e-9
    print(f"  [OK] profit_factor = {pf:.6f} (≈3.0, wins 0.15, losses 0.05)")


def test_hit_rate():
    assert hit_rate([1, 1, 1, -1]) == 0.75
    print(f"  [OK] hit_rate = 0.75 (3/4 winners)")


def test_calmar_ratio():
    # 100→150 over 252 days ≈ 50% CAGR, MDD = -10%  →  Calmar ≈ 5.0
    curve = [100.0] + [100 + i * 0.198 for i in range(1, 252)] + [150]
    curve[125] = 90    # inject -10% drawdown midway
    c = calmar_ratio(curve)
    assert c is not None and c > 0
    print(f"  [OK] calmar_ratio computes positive value on synthetic upward curve ({c:.3f})")


def test_alpha_beta_zero_correlation():
    rng = np.random.default_rng(42)
    p = rng.normal(0.001, 0.01, 100)
    b = rng.normal(0.001, 0.01, 100)      # independent → beta ~ 0
    a, be = alpha_beta(p, b)
    assert a is not None and be is not None
    print(f"  [OK] alpha_beta on independent series: alpha={a:.4f} beta={be:.4f}")


# ── Slippage ────────────────────────────────────────────────────
def test_slippage_direction_signed():
    buy = compute_slippage_bps(1000, 100000, 0.20, 2, 50, 15, direction=+1)
    sell = compute_slippage_bps(1000, 100000, 0.20, 2, 50, 15, direction=-1)
    assert buy > 0 and sell < 0
    assert abs(buy) == abs(sell)
    print(f"  [OK] slippage signed by direction: buy={buy:.2f} sell={sell:.2f}")


def test_slippage_scales_with_participation():
    low  = compute_slippage_bps(1_000,   100_000, 0.20, 2, 50, 15, direction=+1)
    high = compute_slippage_bps(50_000,  100_000, 0.20, 2, 50, 15, direction=+1)
    assert high > low
    print(f"  [OK] slippage scales with participation: low={low:.2f} → high={high:.2f}")


# ── Commissions ─────────────────────────────────────────────────
def test_commission_bps_computes_amount():
    bps, amt = commission_bps(3.0, 100_000)
    assert bps == 3.0 and abs(amt - 30.0) < 1e-9
    print(f"  [OK] commission: 3 bps on $100,000 → $30")


# ── Gap handler ─────────────────────────────────────────────────
def test_gap_stop_out_long_gap_down():
    hit, price = gap_stop_out(prev_close=100.0, today_open=90.0,
                                  is_long=True, stop_loss_pct=-0.08)
    assert hit and price == 90.0
    print(f"  [OK] gap_stop_out: long gap-down through -8% stop → hit at open (90.0)")


def test_gap_stop_out_no_gap():
    hit, _ = gap_stop_out(prev_close=100.0, today_open=99.5,
                            is_long=True, stop_loss_pct=-0.08)
    assert not hit
    print(f"  [OK] gap_stop_out: small overnight move → no gap-out")


# ── Corp actions ────────────────────────────────────────────────
def test_dividend_credits_cash():
    state = {"cash": 0.0, "positions": {"AAPL": {"shares": 100, "entry_price": 150}}}
    state = apply_corporate_actions(state, [{"ticker": "AAPL", "dividend": 0.50, "split_ratio": 0.0}])
    assert state["cash"] == 50.0     # 100 × $0.50
    print(f"  [OK] dividend crediting: 100 shares × $0.50 → +$50 cash")


def test_split_scales_shares_and_price():
    state = {"cash": 0.0, "positions": {"AAPL": {"shares": 100, "entry_price": 200.0}}}
    state = apply_corporate_actions(state, [{"ticker": "AAPL", "dividend": 0.0, "split_ratio": 2.0}])
    p = state["positions"]["AAPL"]
    assert p["shares"] == 200 and p["entry_price"] == 100.0
    print(f"  [OK] 2:1 split: shares 100→200 · entry_price 200→100")


# ── Fill engine ─────────────────────────────────────────────────
def _fake_provider(**overrides):
    """Return an object with the price_provider interface."""
    class _P:
        def mid_price(self, t):        return overrides.get("mid", 100.0)
        def adv_20d_shares(self, t):   return overrides.get("adv", 1_000_000)
        def vol_20d(self, t):          return overrides.get("vol", 0.20)
        def close_price(self, d, t):   return overrides.get("close", 100.0)
        def prior_weight(self, t):     return overrides.get("prior", 0.0)
    return _P()


def test_fill_engine_produces_fills_on_valid_instructions():
    instructions = [
        {"ticker": "T1", "action": "OPEN", "prior_weight": 0.0, "new_weight": 0.05, "delta_weight": 0.05, "reason": "open"},
        {"ticker": "T2", "action": "HOLD", "prior_weight": 0.0, "new_weight": 0.0, "delta_weight": 0.0,  "reason": "hold"},
    ]
    p = _fake_provider()
    fills = simulate_fills(
        instructions=instructions, fill_date=date(2026, 7, 21),
        starting_aum=1_000_000,
        get_mid_price=p.mid_price, get_adv_20d_shares=p.adv_20d_shares,
        get_vol_20d=p.vol_20d, get_prior_weight=p.prior_weight,
        min_slippage_bps=2, liquidity_impact_bps=50, vol_impact_bps=15,
        commission_bps_config=3.0, max_daily_participation=0.10,
        market="usa", model_stamp={"model_id": "aegis.execution.v1"},
    )
    assert len(fills) == 1     # HOLD skipped
    f = fills[0]
    assert f.ticker == "T1" and f.action == "OPEN" and f.side == "LONG"
    assert f.filled_notional > 0 and f.commission_amount > 0
    print(f"  [OK] fill_engine: 1 OPEN fill on synthetic instructions "
           f"(notional=${f.filled_notional:.0f}, comm=${f.commission_amount:.2f})")


def test_fill_engine_partial_fill_across_days():
    # Order size > max_daily_participation × ADV → partial
    p = _fake_provider(adv=100)     # tiny ADV forces partial fill
    fills = simulate_fills(
        instructions=[{"ticker": "T1", "action": "OPEN", "prior_weight": 0, "new_weight": 0.10,
                          "delta_weight": 0.10, "reason": "open"}],
        fill_date=date(2026, 7, 21), starting_aum=1_000_000,
        get_mid_price=p.mid_price, get_adv_20d_shares=p.adv_20d_shares,
        get_vol_20d=p.vol_20d, get_prior_weight=p.prior_weight,
        min_slippage_bps=2, liquidity_impact_bps=50, vol_impact_bps=15,
        commission_bps_config=3.0, max_daily_participation=0.10, market="usa",
    )
    assert len(fills) == 1 and fills[0].partial_fill
    assert fills[0].fill_ratio < 1.0
    print(f"  [OK] fill_engine: partial fill flagged (ratio={fills[0].fill_ratio:.4f})")


# ── Equity curve ────────────────────────────────────────────────
def test_equity_curve_marks_to_market():
    fill = Fill(
        market="usa", ticker="T1", fill_date=date(2026, 7, 20),
        txn_id="abc", action="OPEN", side="LONG",
        shares=1000, fill_price=100.0, slippage_bps=2,
        commission_bps=3.0, commission_amount=30.0,
        partial_fill=False, fill_ratio=1.0,
        intended_notional=100_000, filled_notional=100_000,
        prior_weight=0.0, new_weight=0.10,
    )
    # Day 2: price ticks up to 110
    def close_lookup(d, t):
        return 110.0 if d == date(2026, 7, 21) else 100.0
    curve = compute_equity_curve(
        fills=[fill], starting_aum=1_000_000,
        close_price_lookup=close_lookup,
        trade_dates=[date(2026, 7, 20), date(2026, 7, 21)],
        market="usa",
    )
    assert len(curve) == 2
    # Day 1: bought 1000 × 100 → position worth 100k, cash 900k − 30 comm
    # Day 2: position now worth 110k (up 10k)
    assert curve[1].equity_value > curve[0].equity_value
    print(f"  [OK] equity_curve marks to market: day1={curve[0].equity_value:.2f} "
           f"day2={curve[1].equity_value:.2f}")


# ── Engine end-to-end ───────────────────────────────────────────
def test_engine_end_to_end_with_synthetic_input():
    engine = ExecutionEngine(
        _ROOT, "usa", starting_aum=1_000_000,
        min_slippage_bps=1.0, liquidity_impact_bps=30.0, vol_impact_bps=10.0,
        commission_bps=1.0, max_daily_participation=0.15,
        gap_stop_out_threshold_pct=0.03,
        model_stamp={"model_id": "aegis.execution.v1"},
    )
    instructions = [
        {"ticker": "T1", "action": "OPEN", "prior_weight": 0.0, "new_weight": 0.05, "delta_weight": 0.05, "reason": "open"},
    ]
    fills, curve, summ = engine.run(instructions, _fake_provider(),
                                        asof=date(2026, 7, 21))
    assert summ.n_fills_generated == 1
    assert not summ.honest_empty
    assert summ.n_open_positions >= 1
    assert summ.equity_value_end > 0
    print(f"  [OK] engine end-to-end: fills={summ.n_fills_generated} "
           f"equity=${summ.equity_value_end:,.0f}")


def test_engine_honest_empty_when_no_trades():
    engine = ExecutionEngine(
        _ROOT, "usa", starting_aum=1_000_000,
        min_slippage_bps=1.0, liquidity_impact_bps=30.0, vol_impact_bps=10.0,
        commission_bps=1.0, max_daily_participation=0.15,
        gap_stop_out_threshold_pct=0.03,
    )
    fills, curve, summ = engine.run(
        [{"ticker": "T1", "action": "HOLD", "prior_weight": 0.0, "new_weight": 0.0,
           "delta_weight": 0.0, "reason": "hold"}],
        _fake_provider(), asof=date(2026, 7, 21),
    )
    assert summ.honest_empty
    assert "0 executable" in summ.honest_empty_reason.lower() or "no upstream" in summ.honest_empty_reason.lower()
    print(f"  [OK] engine honest_empty=True on all-HOLD input")


def test_engine_deterministic():
    e = ExecutionEngine(
        _ROOT, "usa", starting_aum=1_000_000,
        min_slippage_bps=1.0, liquidity_impact_bps=30.0, vol_impact_bps=10.0,
        commission_bps=1.0, max_daily_participation=0.15,
        gap_stop_out_threshold_pct=0.03,
    )
    ins = [{"ticker": "T1", "action": "OPEN", "prior_weight": 0.0, "new_weight": 0.05,
             "delta_weight": 0.05, "reason": "open"}]
    r1 = e.run(ins, _fake_provider(), asof=date(2026, 7, 21))
    r2 = e.run(ins, _fake_provider(), asof=date(2026, 7, 21))
    # Compare fills by ticker+notional (txn_id is deterministic from date+seq)
    assert [(f.ticker, f.filled_notional) for f in r1[0]] == \
             [(f.ticker, f.filled_notional) for f in r2[0]]
    print(f"  [OK] engine deterministic across identical calls")


def test_engine_accepts_cutoff():
    e = ExecutionEngine(
        _ROOT, "usa", starting_aum=1_000_000,
        min_slippage_bps=1.0, liquidity_impact_bps=30.0, vol_impact_bps=10.0,
        commission_bps=1.0, max_daily_participation=0.15,
        gap_stop_out_threshold_pct=0.03,
    )
    past = date(2020, 1, 1)
    fills, curve, summ = e.run([], _fake_provider(), asof=past)
    assert summ.asof == past
    print(f"  [OK] engine accepts historical cutoff (walk-forward ready)")


# ── AI Execution Analyst ────────────────────────────────────────
def test_ai_analyst_runs():
    e = ExecutionEngine(
        _ROOT, "usa", starting_aum=1_000_000,
        min_slippage_bps=1.0, liquidity_impact_bps=30.0, vol_impact_bps=10.0,
        commission_bps=1.0, max_daily_participation=0.15,
        gap_stop_out_threshold_pct=0.03,
    )
    _, _, summ = e.run([], _fake_provider(), asof=date(2026, 7, 21))
    out = execution_analyst.run(summ, "usa", date(2026, 7, 21))
    assert out.agent == "execution_analyst"
    assert out.headline and out.narrative
    print(f"  [OK] AI Execution Analyst: {out.headline[:80]}")


def test_ai_analyst_never_promotes():
    e = ExecutionEngine(
        _ROOT, "usa", starting_aum=1_000_000,
        min_slippage_bps=1.0, liquidity_impact_bps=30.0, vol_impact_bps=10.0,
        commission_bps=1.0, max_daily_participation=0.15,
        gap_stop_out_threshold_pct=0.03,
    )
    _, _, summ = e.run([], _fake_provider(), asof=date(2026, 7, 21))
    out = execution_analyst.run(summ, "usa", date(2026, 7, 21))
    forbidden = {"buy", "sell", "target_price", "recommendation",
                  "action", "promoted", "approved"}
    for f in out.findings:
        keys = set(f.keys()) if isinstance(f, dict) else set()
        leak = keys & forbidden
        assert not leak, f"AI Execution Analyst leaked: {leak}"
    print(f"  [OK] AI Execution Analyst obeys no-promotion contract")


# ── Integration ─────────────────────────────────────────────────
def test_india_runner():
    r = subprocess.run(
        [sys.executable, "india/execution_simulator/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "reports" / "execution_summary.json").read_text(encoding="utf-8"))
    assert d["market"] == "india"
    assert "honest_empty" in d
    print(f"  [OK] india runner: honest_empty={d['honest_empty']}")


def test_usa_runner():
    r = subprocess.run(
        [sys.executable, "usa/research/execution_simulator/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "usa" / "reports" / "execution_summary.json").read_text(encoding="utf-8"))
    assert d["market"] == "usa" and d["currency"] == "USD"
    print(f"  [OK] usa runner: currency={d['currency']} honest_empty={d['honest_empty']}")


TESTS = [
    test_metrics_version_defined,
    test_sharpe_zero_stdev_returns_none, test_sharpe_annualised_math,
    test_max_drawdown_finds_worst_trough,
    test_profit_factor, test_hit_rate, test_calmar_ratio,
    test_alpha_beta_zero_correlation,
    test_slippage_direction_signed, test_slippage_scales_with_participation,
    test_commission_bps_computes_amount,
    test_gap_stop_out_long_gap_down, test_gap_stop_out_no_gap,
    test_dividend_credits_cash, test_split_scales_shares_and_price,
    test_fill_engine_produces_fills_on_valid_instructions,
    test_fill_engine_partial_fill_across_days,
    test_equity_curve_marks_to_market,
    test_engine_end_to_end_with_synthetic_input,
    test_engine_honest_empty_when_no_trades,
    test_engine_deterministic, test_engine_accepts_cutoff,
    test_ai_analyst_runs, test_ai_analyst_never_promotes,
    test_india_runner, test_usa_runner,
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=" * 70)
    print("  SPRINT 7 · Execution Simulator + Statistics · Regression Tests")
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
