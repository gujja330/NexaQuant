import json
from datetime import datetime
from pathlib import Path

import pytest

from scripts.aegis_local_state import digest
from scripts.aegis_shadow.closed_outcomes import collect
from scripts.aegis_shadow.closed_learning import evaluate
from scripts.aegis_shadow.effective_risk import _target_authority, calculate, stop_levels
from scripts.aegis_shadow.provider import PriceCircuit, ProviderCircuitOpen
from scripts.aegis_shadow.risk_intervals import resolve
from scripts.aegis_shadow.simulated_orders import roll_opening, rollover_diff, simulate


def write(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


POLICY = {"atr_multiplier": 2, "high_vol_scale": 1.5, "high_vol_atr_pct": 3,
          "trailing_lift_min_pct": 5, "monotonic": True}


def test_target_authority_requires_review_before_observation_close(tmp_path):
    cutoff = datetime.fromisoformat("2026-11-25T21:00:00+00:00")
    target = dict(episode_id="one", ticker="BRK.B", source="fixture", authority_id="review-1", target=110,
                  effective_from="2026-11-25", effective_through="2026-11-27")
    write(tmp_path, ".shadow-exit-authority.json", {"market": "usa", "schema": "aegis.shadow.exit_authority.v1",
          "targets": [dict(target, authorized_utc="2026-11-25T20:59:59+00:00"),
                      dict(target, episode_id="late", authorized_utc="2026-11-25T21:01:00+00:00")]})
    assert set(_target_authority(tmp_path, "usa", "2026-11-25", cutoff)) == {"one"}
    assert not _target_authority(tmp_path, "usa", "2026-11-30", cutoff)


def test_atr_candidate_lifts_against_prior_and_never_resets_authorized_floor():
    assert stop_levels(110, 2, 100, 98, POLICY) == (106, "trailing")
    assert stop_levels(100, 2, 90, 98, POLICY) == (98, "held")
    assert stop_levels(100, 2, 90, 98, dict(POLICY, monotonic=False)) == (96, "atr")
    assert stop_levels(110, 2, None, 98, POLICY) == (106, "atr")


def test_risk_engine_uses_only_completed_bars_and_promotes_prior_proposal(tmp_path, monkeypatch):
    import pandas as pd
    from backend.research import opportunity_registry

    episode = opportunity_registry.Opportunity(opportunity_id="brk-episode", ticker="BRK.B", market="usa",
                                               runner="R2", created_date="2026-10-30")
    monkeypatch.setattr(opportunity_registry, "load_all", lambda _: {})
    monkeypatch.setattr(opportunity_registry, "active_opportunities", lambda _: [episode])
    write(tmp_path, "configs/opportunity_registry.yaml", {"risk_engine": dict(POLICY, monotonic_stops={"usa": True})})
    index = pd.bdate_range("2026-10-30", periods=20)
    close = [100 + step for step in range(19)] + [500]
    path = tmp_path / "usa/data/raw/us/BRK.B_D1.parquet"
    path.parent.mkdir(parents=True)
    pd.DataFrame({"close": close, "high": [x + 1 for x in close], "low": [x - 1 for x in close]}, index=index).to_parquet(path)
    output = tmp_path / "reports/context/dynamic_risk_usa.json"
    first, second, future = (index[i].date().isoformat() for i in (-3, -2, -1))
    calculate(tmp_path, "usa", first, first, None, second, now=datetime.fromisoformat(first + "T22:00:00+00:00"))
    proposal = json.loads(output.read_text())["updates"][0]
    assert proposal["current_price"] == 117
    assert not proposal["effective_for_observation"]
    calculate(tmp_path, "usa", second, second, first, future, now=datetime.fromisoformat(second + "T22:00:00+00:00"))
    accepted = json.loads(output.read_text())["updates"][0]
    assert accepted["current_price"] == 118
    assert accepted["effective_for_observation"]
    assert accepted["new_stop"] == proposal["proposed_stop"]
    assert accepted["proposal_type"] == "trailing"
    calculate(tmp_path, "usa", second, second, first, future)
    assert json.loads(output.read_text())["updates"][0] == accepted


def test_circuit_defers_provider_calls_until_cooldown():
    now, hits = [0], []
    circuit = PriceCircuit({"attempts": 1, "timeout_seconds": 5, "failure_threshold": 2,
                            "cooldown_seconds": 30, "backoff_seconds": 0}, clock=lambda: now[0])

    def failed(*, timeout):
        hits.append(timeout)
        raise TimeoutError("offline")

    for _ in range(2):
        with pytest.raises(TimeoutError):
            circuit.call(failed)
    with pytest.raises(ProviderCircuitOpen):
        circuit.call(failed)
    assert hits == [5, 5]
    now[0] = 30
    assert circuit.call(lambda **_: "healthy") == "healthy"
    assert circuit.consecutive == 0


def test_simulated_orders_use_prior_quantities_and_are_deterministic():
    market, session, previous = "usa", "2026-11-25", "2026-11-24"
    opening = dict(market=market, opening_session=previous, mark_session=session, source="fixture", cash=800,
                   shares={"BRK.B": 2}, opening_prices={"BRK.B": 100},
                   close_prices={"BRK.B": 100, "ACN": 100}, cost_basis={"BRK.B": 70}, episodes={"BRK.B": "prior"})
    portfolio = dict(market=market, asof=session, snapshot={"cash_reserve_target": 0.5, "positions": [
        {"ticker": "BRK.B", "weight": .1, "sector": "Finance"}, {"ticker": "ACN", "weight": .2, "sector": "Tech"}]})
    diff = dict(market=market, asof=session, instructions=[{"ticker": "ACN", "action": "OPEN", "new_weight": .2},
                                                        {"ticker": "BRK.B", "action": "DECREASE", "new_weight": .1}])
    args = (opening, portfolio, diff, {"ACN": "new"}, market, session, session, previous,
            {"commission_bps": 0, "min_slippage_bps": 0}, {"per_ticker_cap": .25, "per_sector_cap": .25}, "policy", "decision")
    results = simulate(*args)
    assert results == simulate(*args)
    assert results["ending_shares"] == {"BRK.B": 1, "ACN": 2}
    assert results["ending_cash"] == 700
    assert results["ending_equity"] == 1000
    assert results["realized_pnl"] == 30
    book = {key: value for key, value in results.items() if key.startswith("ending_")}
    book.update(schema="aegis.shadow.simulator_book.v1", market=market, session=session)
    following = "2026-11-27"
    carried = roll_opening(book, market, session, following, lambda *_: 100)
    carried["close_prices"] = {"BRK.B": 100, "ACN": 100}
    later = dict(portfolio, asof=following)
    next_diff = rollover_diff(carried, later, 0)
    repeat = simulate(carried, later, next_diff, {}, market, following, following, session,
                      args[-4], args[-3], "policy", "next-decision")
    assert not repeat["fills"]
    assert repeat["ending_cash"] == 700
    assert repeat["ending_shares"] == results["ending_shares"]
    with pytest.raises(ValueError, match="prior simulated mark"):
        roll_opening(book, market, session, following, lambda *_: 50)


def test_closed_corpus_requires_confirmed_fills_and_separates_simulation(tmp_path):
    market, day, entry = "usa", "2026-11-25", "2026-11-20"
    artifact = write(tmp_path, "entry.json", {"market": market, "ticker": "BRK.B", "episode_id": "confirmed",
                     "decision_session": entry, "features": {"rank": 2}, "recommendation_id": "rec",
                     "model_version": "model", "policy_version": "policy"})
    exits = [dict(position_id=pid, exit_date=day, entry_date=entry, ticker="BRK.B", record_type=kind)
             for pid, kind in (("confirmed", "REALIZED EXIT"), ("paper", "SIMULATED OBSERVATION"),
                               ("unverified", "UNCONFIRMED STOP EXIT"))]
    reviewed = {"market": market, "outcomes": [{"episode_id": "confirmed", "ticker": "BRK.B", "outcome_session": day,
                "execution_status": "CONFIRMED", "source": "fixture", "entry_fill_price": 100, "exit_fill_price": 110,
                "entry_reference": {"path": Path(artifact.name).as_posix(), "sha256": digest(artifact)}}]}
    corpus = collect(tmp_path, market, day, exits, reviewed)
    assert [row["episode_id"] for row in corpus["confirmed"]] == ["confirmed"]
    assert [row["episode_id"] for row in corpus["simulated_observations"]] == ["paper"]
    assert [row["episode_id"] for row in corpus["excluded"]] == ["unverified"]
    report = evaluate(corpus, market, day)
    assert report["confirmed_consumed"] == 1
    assert report["simulated_excluded"] == 1
    assert report["groups"][0]["mean_gross_return_pct"] == pytest.approx(10)
    assert report["groups"][0]["brier_score"] is None


def test_risk_interval_requires_dated_identity_and_explicit_carry_forward():
    interval = dict(episode_id="one", ticker="BRK.B", source="fixture", revision_id="r1", policy_version="v1",
                    price_basis="raw", stop=95, target=120, authorized_utc="2026-11-20T20:00:00+00:00",
                    effective_from="2026-11-23", effective_through="2026-11-25", carry_forward_authorized=True)
    document = {"market": "usa", "schema": "aegis.shadow.risk_intervals.v1", "intervals": [interval]}
    assert resolve(document, "usa", "one", "BRK.B", "2026-11-24")["target"] == 120
    assert resolve(document, "usa", "one", "BRK.B", "2026-11-27") is None
    with pytest.raises(ValueError, match="identity mismatch"):
        resolve(document, "usa", "one", "BRK.A", "2026-11-24")
    interval["carry_forward_authorized"] = False
    with pytest.raises(ValueError, match="carry-forward"):
        resolve(document, "usa", "one", "BRK.B", "2026-11-24")
