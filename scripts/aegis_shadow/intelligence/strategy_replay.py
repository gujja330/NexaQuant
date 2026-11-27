"""Hypothetical long-only management books for paired research comparisons."""
from collections import defaultdict
from statistics import mean

from scripts.aegis_shadow.intelligence.lab import day, forecasts, number
from scripts.aegis_shadow.intelligence.management import entry, position
from scripts.aegis_shadow.intelligence.opportunities import rank


POLICIES = ("managed", "managed_no_partial", "managed_fixed_fraction", "immediate", "fixed_stop", "atr_trailing", "fixed_target")


def simulate(signal, plan, path, observations, policy):
    if policy not in POLICIES:
        raise ValueError("unknown research policy")
    atr, cost = signal.get("atr14"), signal.get("modeled_round_trip_cost")
    if not number(atr) or atr <= 0 or not number(cost) or not 0 <= cost < 1:
        return None
    dates = [day(bar["session"]) for bar in path]
    if not dates or dates != sorted(set(dates)) or dates[0] <= signal["session"]:
        raise ValueError("research path sessions must follow the decision in chronological order")
    for bar in path:
        opening, high, low, close = (bar.get(field) for field in ("open", "high", "low", "close"))
        if not all(number(value) and value > 0 for value in (opening, high, low, close)) or not (
                low <= min(opening, close) <= max(opening, close) <= high):
            return None
    managed = policy.startswith("managed")
    action = plan["entry_action"]
    if managed and (action in {"AVOID", "WATCHLIST"} or not plan.get("zone")):
        return None
    start = None
    for index, bar in enumerate(path[:3] if managed else path[:1]):
        if not managed:
            start = index
            break
        if bar["open"] <= plan["invalidation"]:
            break
        previous = observations.get(dates[index - 1], ({}, None))[0] if index else signal
        flags = previous.get("strategy_flags", {})
        if action == "WAIT_FOR_CONFIRMATION" and not flags.get("breakout"):
            continue
        if plan["zone"][0] <= bar["open"] <= plan["zone"][1]:
            start = index
            break
    if start is None:
        return None
    bought = path[start]["open"]
    trade_cost = cost / 2
    exposure = .5 if managed and action == "STAGED_ENTRY" else 1.0
    quantity = exposure / (1 + trade_cost)
    remaining = quantity
    cash = 1 - quantity * (1 + trade_cost)
    target = bought + 2 * atr
    stop = bought - 2 * atr if managed or policy in {"fixed_stop", "atr_trailing"} else None
    if managed:
        stop = max(stop, plan["invalidation"])
    if stop is not None and stop <= 0:
        return None
    events = [{"session": dates[start], "type": "ENTRY", "price": bought, "quantity": quantity}]
    pending, peak, trough, max_equity, drawdown = None, bought, bought, 1.0, 0.0
    realized_gain, realized_loss, turnover = 0.0, 0.0, quantity
    booked = False
    for index in range(start, len(path)):
        bar = path[index]
        date, opening, close = bar["session"], bar["open"], bar["close"]
        if index > start and stop is not None and opening <= stop:
            pending = ("GAP_STOP", 1.0)
        if pending:
            reason, fraction = pending
            sell = remaining * fraction
            proceeds = sell * opening / bought
            cash += proceeds * (1 - trade_cost)
            pnl = proceeds * (1 - trade_cost) - sell * (1 + trade_cost)
            realized_gain += max(0, pnl)
            realized_loss += max(0, -pnl)
            remaining -= sell
            turnover += proceeds
            events.append({"session": date, "type": reason, "price": opening, "quantity": sell})
            booked |= fraction < 1
            pending = None
            if remaining <= 1e-12:
                break
        peak, trough = max(peak, close), min(trough, close)
        equity = cash + remaining * close / bought
        max_equity = max(max_equity, equity)
        drawdown = max(drawdown, 1 - equity / max_equity)
        if index == len(path) - 1:
            proceeds = remaining * close / bought
            cash += proceeds * (1 - trade_cost)
            pnl = proceeds * (1 - trade_cost) - remaining * (1 + trade_cost)
            realized_gain += max(0, pnl)
            realized_loss += max(0, -pnl)
            turnover += proceeds
            events.append({"session": date, "type": "HORIZON_CLOSE", "price": close, "quantity": remaining})
            break
        if stop is not None and close <= stop:
            pending = ("CLOSE_STOP_NEXT_OPEN", 1.0)
            continue
        if policy == "fixed_target" and close >= target:
            pending = ("CLOSE_TARGET_NEXT_OPEN", 1.0)
            continue
        row, forecast = observations.get(date, ({}, None))
        if policy == "atr_trailing" and number(row.get("atr14")) and row["atr14"] > 0:
            stop = max(stop, close - 2 * row["atr14"])
        elif managed:
            previous, previous_forecast = observations.get(dates[index - 1], ({}, None)) if index else (signal, None)
            decision = position(row, {"price_current": True, "observed_price": close, "entry_price": bought,
                                     "effective_stop": stop, "stop_effective_for_observation": True, "target": target},
                                forecast, peak, previous=previous, previous_forecast=previous_forecast)
            proposal = decision["proposed_stop"]
            if proposal is not None:
                stop = max(stop, proposal)
            if decision["exit_action"] == "EXIT_RESEARCH":
                pending = ("EXIT_RESEARCH_NEXT_OPEN", 1.0)
            elif not booked and policy != "managed_no_partial" and (
                    (policy == "managed_fixed_fraction" and close >= target) or
                    (policy == "managed" and decision["profit_booking_action"] == "PARTIAL_BOOKING")):
                pending = ("PARTIAL_NEXT_OPEN", .5)
        if stop is not None and policy in {"managed", "managed_no_partial", "managed_fixed_fraction", "atr_trailing"}:
            events.append({"session": date, "type": "PROPOSED_STOP", "level": stop, "effective_from": dates[index + 1]})
    drawdown = max(drawdown, 1 - cash / max_equity)
    final_price = events[-1]["price"]
    peak_gain = quantity * (peak / bought - 1)
    return {"net_return": cash - 1, "maximum_marked_drawdown": drawdown, "turnover_fraction": turnover,
            "gross_profit": realized_gain, "gross_loss": realized_loss, "holding_sessions": index - start + 1,
            "close_peak_return": peak / bought - 1, "close_trough_return": trough / bought - 1,
            "profit_capture": (cash - 1) / peak_gain if peak_gain > 0 else None,
            "giveback_pp": max(0, (peak - final_price) / bought * 100),
            "rebounded_after_exit": any(bar["close"] > final_price for bar in path[index + 1:]), "events": events}


def evaluate_management(rows, start, end, known_through, minimum, *, frozen=False):
    start, end, known_through = map(day, (start, end, known_through))
    if not start <= end <= known_through:
        raise ValueError("invalid management holdout window")
    cache = {}
    source = {(row["security_id"], row["session"], row["horizon"]): row for row in rows}

    def predictions(session):
        if session not in cache:
            cache[session] = {(item["security_id"], item["horizon"]): item for item in
                              forecasts(rows, session, minimum, train_before=start if frozen else None)}
        return cache[session]

    outcomes = defaultdict(list)
    excluded = {"unavailable_path": 0, "insufficient_forecast": 0}
    for session in sorted({row["session"] for row in rows if start <= row["session"] <= end}):
        estimates = predictions(session)
        opportunities = {(item["security_id"], item["horizon"]): item for item in rank(rows, session, estimates.values())}
        for key, estimate in estimates.items():
            symbol, horizon = key
            row = source[(symbol, session, horizon)]
            forecast = estimate["net_return_distribution"]
            label, path = row.get("outcome"), row.get("execution_path")
            if forecast is None:
                excluded["insufficient_forecast"] += 1
                continue
            if not label or not path or label["available_on"] > known_through or len(path) != horizon or (
                    path[0]["session"], path[-1]["session"]) != (label.get("entry_session"), label["matured_on"]):
                excluded["unavailable_path"] += 1
                continue
            plan = entry(row, forecast, opportunities[key])
            observations = {}
            for bar in path:
                date = bar["session"]
                current = source.get((symbol, date, horizon), {})
                if current.get("available_on", date) > date:
                    continue
                estimate_at_close = predictions(date).get(key, {}).get("net_return_distribution")
                observations[date] = current, estimate_at_close
            results = {policy: simulate(row, plan, path, observations, policy) for policy in POLICIES}
            reference = row.get("r2_reference") or {}
            r2 = (reference["net_return"] if number(reference.get("net_return")) and reference.get("source")
                  and reference.get("policy_version") and reference.get("entry_session") == label.get("entry_session")
                  and reference.get("matured_on") == label["matured_on"] and reference.get("available_on")
                  and label["matured_on"] <= day(reference["available_on"]) <= known_through else None)
            outcomes[horizon].append({"security_id": symbol, "session": session, "entry_action": plan["entry_action"],
                                     "matched_benchmark_return": label["benchmark_return"], "r2_reference_net": r2,
                                     "policies": results})
    metrics = {}
    for horizon, cohort in sorted(outcomes.items()):
        paired = [trial for trial in cohort if all(trial["policies"][name] is not None for name in POLICIES)]
        r2 = [trial for trial in paired if trial["r2_reference_net"] is not None]
        per_policy = {}
        for name in POLICIES:
            values = [trial["policies"][name] for trial in paired]
            loss = sum(item["gross_loss"] for item in values)
            captures = [item["profit_capture"] for item in values if item["profit_capture"] is not None]
            per_policy[name] = {"paired_trades": len(values), "eligible_trades": sum(
                trial["policies"][name] is not None for trial in cohort),
                "expectancy_net": mean(item["net_return"] for item in values) if values else None,
                "profit_factor": sum(item["gross_profit"] for item in values) / loss if loss > 0 else None,
                "worst_single_trade_drawdown": max((item["maximum_marked_drawdown"] for item in values), default=None),
                "mean_turnover": mean(item["turnover_fraction"] for item in values) if values else None,
                "mean_giveback_pp": mean(item["giveback_pp"] for item in values) if values else None,
                                "mean_profit_capture": mean(captures) if captures else None,
                "mean_holding_sessions": mean(item["holding_sessions"] for item in values) if values else None,
                "rebound_observations": sum(item["rebounded_after_exit"] for item in values)}
        metrics[str(horizon)] = {"evaluated": len(cohort), "paired": len(paired), "policies": per_policy,
                                 "r2_reference_pairs": len(r2), "mean_managed_minus_r2": mean(
                                     item["policies"]["managed"]["net_return"] - item["r2_reference_net"] for item in r2) if r2 else None,
                                 "mean_paired_benchmark": mean(item["matched_benchmark_return"] for item in paired) if paired else None}
    return {"classification": "HYPOTHETICAL_INDEPENDENT_TRADES", "metrics_by_horizon": metrics,
            "excluded": excluded, "trials_by_horizon": dict(outcomes)}
