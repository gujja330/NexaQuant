"""Advisory entry and position-management candidates with no write authority."""
from datetime import date

from scripts.aegis_shadow.intelligence.lab import momentum_state, number


def _positive(value):
    return number(value) and value > 0


def entry(row, forecast, opportunity, *, can_reenter=False):
    close, atr, trend = (row.get(name) for name in ("signal_close", "atr14", "trend_reference"))
    flags = row.get("strategy_flags", {})
    result = {"security_id": row["security_id"], "ticker": row.get("ticker"), "horizon_sessions": row["horizon"],
              "momentum_state": momentum_state(row), "entry_action": "WATCHLIST", "zone": None,
              "invalidation": None, "reason": "Completed price, trend or forecast evidence is unavailable",
              "evidence_quality": "INSUFFICIENT"}
    if forecast is None or not all(_positive(value) for value in (close, atr, trend)):
        return result
    support = row.get("trend_support")
    floor = max(close - 2 * atr, support) if _positive(support) and support < close else close - 2 * atr
    if floor <= 0:
        return result
    lower = max(floor, min(trend, close) - atr / 2)
    upper = max(lower, min(close + atr / 2, trend + atr))
    result.update(zone=[lower, upper], invalidation=floor, evidence_quality="MODELED",
                  forecast_upside=forecast["q90"], forecast_downside=forecast["q10"],
                  expected_net_return=forecast["mean"], reward_to_risk=forecast.get("tail_reward_to_risk"))
    if forecast["mean"] <= 0 or flags.get("exhaustion") or flags.get("failed_breakout"):
        action, reason = "AVOID", "Nonpositive expected return or deteriorating trend evidence"
    elif opportunity.get("status") != "RESEARCH_CANDIDATE":
        action, reason = "WATCHLIST", "Opportunity did not qualify on risk or liquidity evidence"
    elif close > upper or (flags.get("high") and not flags.get("pullback_continuation") and not flags.get("breakout")):
        action, reason = "WAIT_FOR_PULLBACK", "Current price is extended relative to trend or momentum is mature"
    elif (flags.get("early") or flags.get("volatility_compression")) and not flags.get("breakout"):
        action, reason = "WAIT_FOR_CONFIRMATION", "Early momentum or compression lacks completed breakout confirmation"
    elif can_reenter and (flags.get("pullback_continuation") or flags.get("breakout")):
        action, reason = "REENTRY", "Earlier exit followed by new trend confirmation"
    elif flags.get("small_persistent") or forecast["q10"] < -forecast["q90"]:
        action, reason = "STAGED_ENTRY", "Persistent small momentum or wide downside warrants staged research exposure"
    else:
        action, reason = "ENTER", "Positive expected net return within the volatility-adjusted entry zone"
    result.update(entry_action=action, reason=reason)
    return result


def protection(close, prior, row, forecast, *, entry_price=None, target=None):
    atr = row.get("atr14")
    if not all(_positive(value) for value in (close, atr)):
        return {}
    widths = {"atr": close - 2 * atr, "volatility_adjusted": close - 2.5 * atr}
    chandelier, support = row.get("chandelier_high"), row.get("trend_support")
    if _positive(chandelier):
        widths["chandelier"] = chandelier - 3 * atr
    if _positive(support):
        widths["trend_structure"] = support - atr / 2
    profitable = _positive(entry_price) and close > entry_price
    near_target = _positive(target) and close + atr >= target
    flags = row.get("strategy_flags", {})
    if profitable:
        widths["profit_stage"] = close - (1 if near_target else 2) * atr
    if flags.get("exhaustion") or row.get("regime") == "BENCHMARK_NONPOSITIVE":
        widths["momentum_regime"] = close - 1.5 * atr
    if forecast is not None and -1 < forecast["q10"] < 0:
        widths["forecast_downside"] = close * (1 + forecast["q10"])
    return {kind: max(prior, value) if _positive(prior) else value for kind, value in widths.items()
            if _positive(value) and value < close and (not _positive(prior) or prior < close)}


def position(row, observation, forecast, peak, *, previous=None, previous_forecast=None, alternative=None):
    close, basis = observation.get("observed_price"), observation.get("entry_price")
    prior = observation.get("effective_stop") if observation.get("stop_effective_for_observation") is True else None
    target = observation.get("target")
    result = {"holding_action": "REVIEW", "profit_booking_action": "NONE", "exit_action": "NONE", "fraction": 0,
              "effective_stop": prior, "target_state": observation.get("target_state"),
              "target_reference": target, "target_source": observation.get("target_source"),
              "proposed_stop": None, "protection_candidates": {}, "evidence_quality": "INSUFFICIENT",
              "forecast_horizon_sessions": row.get("horizon"), "holding_review_days": observation.get("holding_horizon_days"),
              "reason": "Current price or comparable entry evidence is unavailable"}
    if not observation.get("price_current") or not all(_positive(value) for value in (close, basis)):
        return result
    if observation.get("exit_action") == "ENFORCED" or (_positive(prior) and close <= prior):
        result.update(holding_action="DEFER_TO_AUTHORITY", exit_action="AUTHORIZED_RISK_REVIEW",
                      evidence_quality="OBSERVED", reason="Effective risk authority takes precedence")
        return result
    methods = protection(close, prior, row, forecast, entry_price=basis, target=target)
    # Do not select the tightest proposal by default. That would favor a
    # close-hugging candidate even on a healthy trend.
    proposed = methods.get("atr")
    if row.get("strategy_flags", {}).get("exhaustion"):
        proposed = methods.get("momentum_regime", proposed)
    if _positive(target) and close >= target:
        proposed = methods.get("profit_stage", proposed)
    giveback = max(0, (peak - close) / basis) if _positive(peak) else None
    favorable = max(0, peak / basis - 1) if _positive(peak) else None
    result.update(proposed_stop=proposed, protection_candidates=methods, observed_return=close / basis - 1,
                  close_peak_return=favorable, giveback_from_close_peak=giveback,
                  holding_action="HOLD", evidence_quality="OBSERVED", reason="Observed position review; modeled evidence unavailable")
    if forecast is None:
        if _positive(target) and close >= target:
            result.update(profit_booking_action="REASSESS_TARGET", reason="Target observed; return forecast unavailable")
        return result
    flags = row.get("strategy_flags", {})
    cost = row.get("modeled_round_trip_cost")
    if not number(cost) or cost < 0:
        result.update(reason="Transaction cost or portfolio impact evidence unavailable")
        return result
    result["portfolio_impact"] = "UNALLOCATED_POSITION_RESEARCH"
    hold_utility = forecast["mean"] + min(0, forecast["q10"])
    previous = previous or {}
    old_quality, quality = previous.get("quality_evidence") or {}, row.get("quality_evidence") or {}
    weaker_fundamentals = any(number(old_quality.get(key)) and number(quality.get(key)) and old_quality[key] > 0 > quality[key]
                               for key in ("roe", "profit_margin"))
    weaker_regime = previous.get("regime") == "BENCHMARK_UP" and row.get("regime") == "BENCHMARK_NONPOSITIVE"
    weaker_forecast = previous_forecast is not None and previous_forecast["q50"] >= 0 > forecast["q50"]
    alternative_advantage = alternative - hold_utility - cost if number(alternative) else None
    result.update(hold_utility=hold_utility, forecast_upside=forecast["q90"], forecast_downside=forecast["q10"],
                  reward_to_risk=forecast.get("tail_reward_to_risk"), weaker_fundamentals=weaker_fundamentals,
                  weaker_regime=weaker_regime, weaker_forecast=weaker_forecast, alternative_advantage=alternative_advantage,
                  evidence_quality="MODELED", reason="Continue holding while risk-adjusted forecast supports the thesis")
    deteriorating = weaker_fundamentals or weaker_regime or weaker_forecast or flags.get("exhaustion") or flags.get("failed_breakout") or (
        number(row.get("trend_reference")) and close < row["trend_reference"])
    if hold_utility < 0 and forecast["q50"] < 0 and deteriorating:
        result.update(holding_action="EXIT_CANDIDATE", exit_action="EXIT_RESEARCH", fraction=1,
                      profit_booking_action="FULL_BOOKING" if close > basis else "NONE",
                      reason="Negative median and downside-adjusted utility with deteriorating trend")
    elif close > basis and hold_utility < 0 and (_positive(target) and close >= target or
            number(giveback) and number(row.get("daily_volatility")) and giveback > row["daily_volatility"]):
        result.update(holding_action="REDUCE_CANDIDATE", profit_booking_action="PARTIAL_BOOKING", fraction=.5,
                      reason="Weak downside-adjusted utility after target achievement or material giveback")
    elif _positive(target) and close >= target:
        tightened = _positive(proposed) and (not _positive(prior) or proposed > prior)
        result.update(profit_booking_action="TIGHTER_PROTECTION" if tightened else "REASSESS_TARGET",
                      reason="Target observed; no full closure follows solely from achievement")
    elif hold_utility < 0 and number(alternative_advantage) and alternative_advantage > 0:
        result.update(holding_action="REVIEW_OPPORTUNITY_COST",
                      reason="An eligible alternative has stronger modeled utility after switching cost")
    elif _positive(observation.get("holding_horizon_days")) and observation.get("entry_date") and observation.get("price_session"):
        held = (date.fromisoformat(observation["price_session"]) - date.fromisoformat(observation["entry_date"])).days
        if held >= observation["holding_horizon_days"]:
            result.update(holding_action="REVIEW_HORIZON", holding_age_calendar_days=held,
                          reason="Observed age reached the holding review horizon; no exit triggered by age alone")
    return result
