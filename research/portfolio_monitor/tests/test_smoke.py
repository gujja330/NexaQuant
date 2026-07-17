"""DEV024 smoke tests. Fast; no network required."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from portfolio_monitor.lib import holdings, alerts                                      # noqa: E402
from portfolio_monitor.compute import engine                                              # noqa: E402


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


def _make_test_holdings(with_stops: bool = True) -> dict:
    return {
        "portfolio_id": "test",
        "created_date": (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d"),
        "cash": 500000,
        "total_invested_capital": 10_000_000,
        "holdings": [
            {"ticker": "TEST_A", "shares": 100, "avg_cost": 1000,
              "target_weight": 0.20, "entry_date":
                  (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d"),
              "target_price": 1200 if with_stops else None,
              "stop_loss":     900  if with_stops else None,
              "trailing_stop": 950  if with_stops else None,
              "recommendation_type": "Strong-Buy"},
            {"ticker": "TEST_B", "shares": 50,  "avg_cost": 2000,
              "target_weight": 0.15, "entry_date":
                  (datetime.now(timezone.utc) - timedelta(days=15)).strftime("%Y-%m-%d"),
              "target_price": 2200 if with_stops else None,
              "stop_loss":     1800 if with_stops else None,
              "recommendation_type": "Buy"},
        ],
    }


def test_load_holdings():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(_make_test_holdings(), tf)
        path = Path(tf.name)
    try:
        p = holdings.load_holdings(path)
        _check("holdings load", p is not None)
        _check("portfolio has 2 positions", len(p.positions) == 2)
        _check("first ticker correct", p.positions[0].ticker == "TEST_A")
        _check("target weights preserved",
                abs(p.positions[0].target_weight - 0.20) < 1e-9)
    finally:
        path.unlink()


def test_synthesise_demo():
    recs = {
        "recommendations": [
            {"ticker": "T1", "recommendation": "Strong-Buy", "conviction_pct": 80,
              "entry_exit": {"latest_close": 100, "target_1": 110, "target_2": 120,
                              "stop_loss": 92, "trailing_stop_initial": 94}},
            {"ticker": "T2", "recommendation": "Buy", "conviction_pct": 70,
              "entry_exit": {"latest_close": 200, "target_1": 220, "target_2": 240,
                              "stop_loss": 184, "trailing_stop_initial": 188}},
            {"ticker": "T3", "recommendation": "Avoid", "conviction_pct": 30,
              "entry_exit": None},
        ]
    }
    demo = holdings.synthesise_from_recommendations(recs, "top_5_ew", capital=1_000_000)
    _check("demo has portfolio_id", "portfolio_id" in demo)
    _check("demo has 2 holdings (Avoid excluded)",
            len(demo["holdings"]) == 2, detail=f"n={len(demo['holdings'])}")
    _check("demo target_weight is 1/N",
            all(abs(h["target_weight"] - 0.5) < 1e-9 for h in demo["holdings"]))
    _check("demo preserves stops from recs",
            demo["holdings"][0]["stop_loss"] is not None)


def test_alerts_stop_loss():
    """Alert engine triggers STOP_LOSS_HIT when latest_close <= stop_loss."""
    h = holdings.Portfolio(
        portfolio_id="t", created_date="2026-07-01",
        cash=0, total_invested_capital=100,
        positions=[holdings.Position(
            ticker="X", shares=10, avg_cost=100, entry_date="2026-07-01",
            target_weight=1.0, latest_close=80, stop_loss=90,
            unrealised_pnl_pct=-20.0, days_held=15)],
    )
    a = alerts.scan(h)
    stop_alerts = [x for x in a if x.alert_type == "STOP_LOSS_HIT"]
    _check("STOP_LOSS_HIT triggered", len(stop_alerts) == 1)
    if stop_alerts:
        _check("severity is CRITICAL", stop_alerts[0].severity == "CRITICAL")


def test_alerts_target_reached():
    h = holdings.Portfolio(
        portfolio_id="t", created_date="2026-07-01",
        cash=0, total_invested_capital=100,
        positions=[holdings.Position(
            ticker="X", shares=10, avg_cost=100, entry_date="2026-07-01",
            target_weight=1.0, latest_close=120, target_price=115,
            unrealised_pnl_pct=20.0, days_held=10)],
    )
    a = alerts.scan(h)
    _check("TARGET_REACHED triggered",
            any(x.alert_type == "TARGET_REACHED" for x in a))


def test_alerts_weight_drift():
    h = holdings.Portfolio(
        portfolio_id="t", created_date="2026-07-01",
        cash=0, total_invested_capital=100,
        positions=[holdings.Position(
            ticker="X", shares=10, avg_cost=100, entry_date="2026-07-01",
            target_weight=0.10, current_weight=0.20, latest_close=110)],
    )
    a = alerts.scan(h)
    _check("WEIGHT_DRIFT triggered",
            any(x.alert_type == "WEIGHT_DRIFT" for x in a))


def test_alerts_time_exit():
    h = holdings.Portfolio(
        portfolio_id="t", created_date="2026-01-01",
        cash=0, total_invested_capital=100,
        positions=[holdings.Position(
            ticker="X", shares=10, avg_cost=100, entry_date="2026-01-01",
            target_weight=1.0, latest_close=110, days_held=95)],
    )
    a = alerts.scan(h, max_holding_days=90)
    _check("TIME_EXIT_DUE triggered when days > max",
            any(x.alert_type == "TIME_EXIT_DUE" for x in a))


def test_alerts_confidence_drop():
    h = holdings.Portfolio(
        portfolio_id="t", created_date="2026-07-01",
        cash=0, total_invested_capital=100,
        positions=[holdings.Position(
            ticker="X", shares=10, avg_cost=100, entry_date="2026-07-01",
            target_weight=1.0, latest_close=105, days_held=10)],
    )
    recs = {"X": {"recommendation": "Sell", "score": 25, "classification": "Bearish"}}
    a = alerts.scan(h, recs)
    _check("CONFIDENCE_DROP triggered on Sell rec",
            any(x.alert_type == "CONFIDENCE_DROP" for x in a))


def test_rebalance_plan_close():
    h = holdings.Portfolio(
        portfolio_id="t", created_date="2026-07-01",
        cash=0, total_invested_capital=100,
        positions=[holdings.Position(
            ticker="X", shares=10, avg_cost=100, entry_date="2026-07-01",
            target_weight=0.5, latest_close=100, current_value=1000,
            current_weight=0.5)],
    )
    h.total_portfolio_value = 2000
    plan = engine.rebalance_plan(h, {"X": {"recommendation": "Sell"}})
    _check("Sell rec produces CLOSE_POSITION",
            any(p["action"] == "CLOSE_POSITION" for p in plan))


def test_rebalance_plan_reduce():
    h = holdings.Portfolio(
        portfolio_id="t", created_date="2026-07-01",
        cash=0, total_invested_capital=100,
        positions=[holdings.Position(
            ticker="X", shares=100, avg_cost=100, entry_date="2026-07-01",
            target_weight=0.5, latest_close=100, current_value=10000,
            current_weight=0.5)],
    )
    h.total_portfolio_value = 20000
    plan = engine.rebalance_plan(h, {"X": {"recommendation": "Reduce"}})
    reduce_actions = [p for p in plan if p["action"] == "REDUCE_POSITION"]
    _check("Reduce rec produces REDUCE_POSITION",
            len(reduce_actions) == 1)
    _check("Reduce halves the position",
            reduce_actions[0]["shares_delta"] == -50 if reduce_actions else False)


def test_rebalance_plan_weight_drift():
    h = holdings.Portfolio(
        portfolio_id="t", created_date="2026-07-01",
        cash=0, total_invested_capital=100,
        positions=[holdings.Position(
            ticker="X", shares=50, avg_cost=100, entry_date="2026-07-01",
            target_weight=0.30, latest_close=100, current_value=5000,
            current_weight=0.20)],
    )
    h.total_portfolio_value = 25000
    plan = engine.rebalance_plan(h)
    _check("weight drift generates INCREASE_POSITION",
            any(p["action"] == "INCREASE_POSITION" for p in plan))


def test_alert_summariser():
    a = [
        alerts.Alert(ticker="X", alert_type="STOP_LOSS_HIT",
                       severity="CRITICAL", message="", context={}),
        alerts.Alert(ticker="Y", alert_type="TARGET_REACHED",
                       severity="INFO", message="", context={}),
        alerts.Alert(ticker="Z", alert_type="WEIGHT_DRIFT",
                       severity="WARNING", message="", context={}),
    ]
    s = alerts.summarise(a)
    _check("summary total = 3", s["total"] == 3)
    _check("severity counts",
            s["by_severity"]["CRITICAL"] == 1 and
            s["by_severity"]["WARNING"] == 1 and
            s["by_severity"]["INFO"] == 1)


def main() -> int:
    print("=" * 70)
    print("  DEV024 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_load_holdings(); print()
    test_synthesise_demo(); print()
    test_alerts_stop_loss(); print()
    test_alerts_target_reached(); print()
    test_alerts_weight_drift(); print()
    test_alerts_time_exit(); print()
    test_alerts_confidence_drop(); print()
    test_rebalance_plan_close(); print()
    test_rebalance_plan_reduce(); print()
    test_rebalance_plan_weight_drift(); print()
    test_alert_summariser(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
