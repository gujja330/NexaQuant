from datetime import date, time, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from scripts.aegis_shadow.intelligence.assembly import mature, rows_for_session
from scripts.aegis_shadow.intelligence.integration import emit, review
from scripts.aegis_shadow.intelligence.lab import evaluate, forecasts, validate
from scripts.aegis_shadow.intelligence.models import fit_predict
from scripts.aegis_shadow.intelligence.management import entry, position, protection
from scripts.aegis_shadow.intelligence.strategy_replay import evaluate_management, simulate


def row(symbol, session, *, return_=None, disclosed=None):
    item = dict(security_id=symbol, session=session, observed_on=session, horizon=5, eligible=True,
                universe_version="reviewed", regime="recovery", momentum_short=.05,
                momentum_medium=.03, momentum_long=.01)
    if return_ is not None:
        item["outcome"] = dict(matured_on=disclosed, available_on=disclosed, gross_return=return_,
                               round_trip_cost=.01, benchmark_return=.02)
    return item


@pytest.mark.parametrize("market", ("india", "usa"))
def test_walk_forward_excludes_labels_unavailable_on_forecast_day(market):
    rows = [row("one", "2026-11-02", return_=.03, disclosed="2026-11-09"),
            row("two", "2026-11-03", return_=.07, disclosed="2026-11-10"),
            row("late", "2026-11-19", return_=2, disclosed="2026-11-26"),
            row("test", "2026-11-26", return_=.06, disclosed="2026-12-03")]
    panel = dict(schema="aegis.shadow.research_panel.v1", market=market, source="fixture",
                 benchmark_id="local-market-benchmark", rows=rows)
    prediction = forecasts(validate(panel, market), "2026-11-26", 2)[0]
    assert prediction["net_return_distribution"]["observations"] == 2
    assert prediction["net_return_distribution"]["q50"] == pytest.approx(.04)
    metrics = evaluate(rows, "2026-11-26", "2026-11-26", "2026-12-03", 2)["metrics_by_horizon"]["5"]
    assert metrics["mean_selected_net"] == pytest.approx(.05)
    assert metrics["mean_matched_benchmark"] == pytest.approx(.02)
    assert metrics["momentum_baseline_selected"] == 1
    assert forecasts(rows, "2026-11-26", 4)[0]["classification"] == "ABSTAIN"


def test_position_review_excludes_prospective_stop_from_giveback():
    positions = {"episode": dict(entry_price=100, observed_price=125, price_current=True,
                                 effective_stop=118, stop_effective_for_observation=False)}
    assert review(positions)[0]["profit_giveback_pp"] is None
    positions["episode"]["stop_effective_for_observation"] = True
    assert review(positions)[0]["profit_giveback_pp"] == pytest.approx(7)


def history():
    calendar = [(date(2026, 7, 1) + timedelta(days=i)).isoformat() for i in range(67)]
    bars = {}
    for index, session in enumerate(calendar):
        price = 100 + index / 10 + (index % 3) / 20
        bars[session] = {"open": price - .01, "close": price, "high": price + .1, "low": price - .1, "volume": 500}
    return calendar, bars


def test_labels_mature_only_after_horizon_and_reject_revised_basis():
    calendar, bars = history()
    signal, exit_ = calendar[60], calendar[65]
    rows = rows_for_session("usa", signal, signal, ["BRK.B"], {"BRK.B": bars}, bars, "version", (5,), .001, calendar)
    assert len(rows) == 1
    assert "outcome" not in mature(rows, {"BRK.B": bars}, bars, calendar, calendar[64], calendar[64])[0]
    label = mature(rows, {"BRK.B": bars}, bars, calendar, exit_, exit_)[0]["outcome"]
    assert label["entry_session"] == calendar[61]
    assert label["gross_return"] == pytest.approx(bars[exit_]["close"] / bars[calendar[61]]["open"] - 1)
    revised = dict(bars, **{signal: dict(bars[signal], close=50)})
    assert mature(rows, {"BRK.B": revised}, bars, calendar, exit_, exit_)[0]["label_status"] == "PRICE_BASIS_RECONCILIATION_REQUIRED"


@pytest.mark.parametrize("market", ["india", "usa"])
def test_daily_research_builds_panel_without_manual_input(tmp_path, monkeypatch, market):
    calendar, bars = history()
    session = calendar[60]
    work, storage = tmp_path / "work", tmp_path / "storage"
    work.mkdir()
    storage.mkdir()
    universe = work / ("reports/context/security_master_india.json" if market == "india" else "usa/reports/universe.json")
    universe.parent.mkdir(parents=True)
    symbol = "ITC" if market == "india" else "BRK.B"
    evidence = dict(session=session, configured=[symbol]) if market == "india" else dict(tickers=[{"symbol": symbol}])
    universe.write_text(json.dumps(evidence), encoding="utf-8")
    config = work / "configs/execution_config.yaml"
    config.parent.mkdir()
    config.write_text(json.dumps({"market_defaults": {market: {"commission_bps": 1, "min_slippage_bps": 2}}}), encoding="utf-8")
    monkeypatch.setattr("scripts.aegis_shadow.intelligence.assembly._series", lambda *_: bars)
    monkeypatch.setattr("scripts.aegis_shadow.intelligence.integration.read", lambda *_: {"positions": {}})
    context = {"work": work, "storage": storage, "market": market, "session": session, "asof": session,
               "calendar": SimpleNamespace(closes={date.fromisoformat(day): time(16) for day in calendar}, timezone=timezone.utc)}
    emit(context)
    folder = work / "reports/research/intelligence" / market
    prepared = json.loads((folder / "prepared_panel.json").read_text())
    assert len(prepared["rows"]) == 3
    assert all(row["security_id"] == f"{market}:{symbol}" for row in prepared["rows"])
    report = json.loads((folder / "strategy_research.json").read_text())
    assert report["forecast_status"] == "INSUFFICIENT_EVIDENCE"
    assert len(report["opportunities"]) == 3
    assert len(report["entry_candidates"]) == 3
    emit(context)
    assert json.loads((folder / "prepared_panel.json").read_text()) == prepared
    assert len(list((folder / "management_history" / session).glob("*.json"))) == 1


def test_model_challengers_cannot_see_holdout_label():
    def model_row(symbol, session, value, *, return_=None, disclosed=None):
        item = row(symbol, session, return_=return_, disclosed=disclosed)
        item.update(momentum_short=value, relative_strength=value, daily_volatility=.02, liquidity_proxy=1000)
        return item

    session = "2026-11-26"
    known = [model_row(f"training-{i}", "2026-11-10", i / 100, return_=i / 100 - .02,
                       disclosed="2026-11-20") for i in range(6)]
    observed = model_row("test", session, .03, return_=.5, disclosed="2026-12-03")
    baseline = fit_predict(known + [observed], session, 4)
    revised = dict(observed, outcome=dict(observed["outcome"], gross_return=5))
    assert baseline == fit_predict(known + [revised], session, 4)
    assert baseline[0]["pairwise_rank_score"] is not None
    assert baseline[0]["calibrated_probability_positive_net"] is None


def management_signal(ticker):
    signal = row(ticker, "2026-11-23")
    return dict(signal, ticker=ticker, horizon=3, signal_close=100, atr14=2, trend_reference=100,
                trend_support=96, modeled_round_trip_cost=.01, daily_volatility=.02,
                strategy_flags={"accelerating": True}, chandelier_high=103)


@pytest.mark.parametrize("market,ticker", [("india", "ITC"), ("usa", "BRK.B")])
def test_daily_signal_to_delayed_partial_booking_and_exit(market, ticker):
    signal = management_signal(ticker)
    signal["security_id"] = f"{market}:{ticker}"
    opening_forecast = dict(mean=.06, q10=-.03, q50=.05, q90=.10)
    plan = entry(signal, opening_forecast, {"status": "RESEARCH_CANDIDATE"})
    assert plan["entry_action"] == "ENTER"
    last_session = "2026-11-27" if market == "usa" else "2026-11-26"
    path = [{"session": "2026-11-24", "open": 100, "high": 106, "low": 99, "close": 105},
            {"session": "2026-11-25", "open": 106, "high": 107, "low": 104, "close": 106},
            {"session": last_session, "open": 105.5, "high": 106, "low": 104, "close": 105}]
    observations = {"2026-11-24": (signal, dict(mean=.01, q10=-.05, q50=.01, q90=.10)),
                    "2026-11-25": (dict(signal, strategy_flags={"exhaustion": True}),
                                   dict(mean=-.02, q10=-.10, q50=-.03, q90=.05))}
    result = simulate(signal, plan, path, observations, "managed")
    types = [event["type"] for event in result["events"]]
    assert types == ["ENTRY", "PROPOSED_STOP", "PARTIAL_NEXT_OPEN", "PROPOSED_STOP", "EXIT_RESEARCH_NEXT_OPEN"]
    assert result["events"][1]["effective_from"] == "2026-11-25"
    assert result["events"][2]["price"] == 106
    assert result["events"][4]["price"] == 105.5
    assert result["net_return"] == pytest.approx((105.75 / 100) * .995 / 1.005 - 1)
    assert not any(event["type"] == "PARTIAL_NEXT_OPEN" for event in
                   simulate(signal, plan, path, observations, "managed_no_partial")["events"])


def test_target_touch_alone_defers_to_holding_and_effective_stop_overrides_research():
    signal = management_signal("BRK.B")
    evidence = dict(price_current=True, observed_price=110, entry_price=100, target=105,
                    effective_stop=106, stop_effective_for_observation=True)
    forecast = dict(mean=.04, q10=-.01, q50=.03, q90=.08)
    decision = position(signal, evidence, forecast, 110)
    assert decision["exit_action"] == "NONE"
    assert decision["proposed_stop"] >= 106
    assert all(level >= 106 for level in protection(110, 106, signal, forecast).values())
    assert position(signal, dict(evidence, observed_price=104), forecast, 110)["exit_action"] == "AUTHORIZED_RISK_REVIEW"


def test_holdout_consumes_mature_strategy_paths():
    signal = management_signal("test")
    past = [dict(row(f"historical-{i}", "2026-11-02", return_=.06, disclosed="2026-11-10"), horizon=3) for i in range(2)]
    signal["liquidity_proxy"] = 1e7
    signal["outcome"] = {"entry_session": "2026-11-24", "matured_on": "2026-11-26", "available_on": "2026-11-26",
                         "gross_return": .05, "benchmark_return": .02, "round_trip_cost": .01}
    signal["execution_path"] = [{"session": day, "open": price, "high": price + 3, "low": price - 1, "close": price + 1}
                                for day, price in [("2026-11-24", 100), ("2026-11-25", 102), ("2026-11-26", 104)]]
    report = evaluate_management(past + [signal], "2026-11-23", "2026-11-23", "2026-11-26", 2, frozen=True)
    assert report["metrics_by_horizon"]["3"]["paired"] == 1
    assert report["metrics_by_horizon"]["3"]["mean_paired_benchmark"] == .02
