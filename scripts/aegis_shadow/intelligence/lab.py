"""Point-in-time distribution forecasts and matched, cost-aware holdouts."""
from collections import defaultdict
from datetime import date
from math import isfinite
from statistics import mean


def number(value):
    return type(value) in (float, int) and isfinite(value)


def day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("expected ISO session date")
    return value


def validate(document, market):
    if (document.get("schema"), document.get("market")) != ("aegis.shadow.research_panel.v1", market):
        raise ValueError("research panel market or schema mismatch")
    if not document.get("source") or not document.get("benchmark_id"):
        raise ValueError("reviewed panel and benchmark identities are required")
    seen = set()
    for row in document["rows"]:
        session, observed = (day(row[key]) for key in ("session", "observed_on"))
        key = (row["security_id"], session, row["horizon"])
        if (not isinstance(row["security_id"], str) or not row["security_id"].strip() or key in seen
                or observed > session or day(row.get("available_on", session)) < observed
                or type(row["horizon"]) is not int or row["horizon"] < 1
                or not isinstance(row.get("universe_version"), str) or not row["universe_version"].strip()
                or type(row.get("eligible")) is not bool):
            raise ValueError("duplicate or invalid point-in-time identity")
        seen.add(key)
        if "outcome" in row:
            outcome = row["outcome"]
            if not session < day(outcome["matured_on"]) <= day(outcome["available_on"]):
                raise ValueError("invalid outcome chronology")
            for field in ("gross_return", "benchmark_return", "round_trip_cost"):
                if not number(outcome.get(field)) or outcome[field] < -1:
                    raise ValueError(f"invalid return evidence: {field}")
            if outcome["round_trip_cost"] < 0:
                raise ValueError("round-trip cost must be nonnegative")
    return document["rows"]


def momentum_state(row):
    short, medium, long = (row.get(key) for key in ("momentum_short", "momentum_medium", "momentum_long"))
    if not all(number(value) for value in (short, medium, long)):
        return None
    if long > 0 and short < 0:
        return "EXHAUSTION_CANDIDATE"
    if short > medium > long >= 0:
        return "ACCELERATING"
    if short > 0 and medium <= 0:
        return "EARLY"
    return "ESTABLISHED" if min(short, medium, long) > 0 else "UNCONFIRMED"


def group(row):
    state = momentum_state(row)
    regime = row.get("regime")
    if not state or not isinstance(regime, str) or not regime:
        return None
    return row["horizon"], regime, state


def _distribution(returns):
    ordered = sorted(returns)
    def quantile(q):
        index = (len(ordered) - 1) * q
        lower = int(index)
        return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (index - lower)

    return {"observations": len(ordered), "q10": quantile(.1), "q50": quantile(.5), "q90": quantile(.9),
            "mean": mean(ordered), "probability_positive_net": sum(value > 0 for value in ordered) / len(ordered)}


def forecasts(rows, session, minimum, *, train_before=None, include_ineligible=False):
    training = defaultdict(list)
    for row in rows:
        outcome = row.get("outcome")
        key = group(row)
        if row["eligible"] and key and outcome and outcome["available_on"] < min(session, train_before or session):
            training[key].append(outcome["gross_return"] - outcome["round_trip_cost"])
    output = []
    for row in rows:
        if (row["session"] != session or row.get("available_on", session) > session
                or (not row["eligible"] and not include_ineligible)):
            continue
        key = group(row)
        history = training.get(key, ())
        estimate = _distribution(history) if len(history) >= minimum else None
        if estimate:
            lower, upper = estimate["q10"], estimate["q90"]
            estimate["tail_reward_to_risk"] = upper / abs(lower) if lower < 0 < upper else None
        output.append({"security_id": row["security_id"], "horizon": row["horizon"], "group": key,
                       "classification": "RESEARCH_ESTIMATE" if estimate else "ABSTAIN",
                       "reason": None if estimate else "Insufficient matched point-in-time evidence",
                       "net_return_distribution": estimate})
    return output


def evaluate(rows, start, end, known_through, minimum, *, frozen=False):
    start, end, known_through = map(day, (start, end, known_through))
    if not start <= end <= known_through:
        raise ValueError("invalid holdout interval")
    outcomes = {(row["security_id"], row["session"], row["horizon"]): row["outcome"] for row in rows
                if "outcome" in row and row["outcome"]["available_on"] <= known_through}
    medium = {(row["security_id"], row["session"], row["horizon"]): row.get("momentum_medium") for row in rows}
    scores = defaultdict(list)
    abstained = unavailable = 0
    for session in sorted({row["session"] for row in rows if start <= row["session"] <= end}):
        for prediction in forecasts(rows, session, minimum, train_before=start if frozen else None):
            estimate = prediction["net_return_distribution"]
            key = (prediction["security_id"], session, prediction["horizon"])
            outcome = outcomes.get(key)
            if estimate is None:
                abstained += 1
            elif outcome is None:
                unavailable += 1
            else:
                net = outcome["gross_return"] - outcome["round_trip_cost"]
                scores[prediction["horizon"]].append((net, outcome["benchmark_return"], estimate, medium[key] > 0))
    metrics = {}
    for horizon, items in sorted(scores.items()):
        selected = [(net, benchmark) for net, benchmark, est, _ in items if est["q50"] > 0]
        momentum = [net for net, _, _, positive_medium in items if positive_medium]
        metrics[str(horizon)] = {"scored": len(items), "selected": len(selected),
                                 "brier_positive_net": mean((est["probability_positive_net"] - (net > 0)) ** 2 for net, _, est, _ in items),
                                 "central_80_coverage": mean(est["q10"] <= net <= est["q90"] for net, _, est, _ in items),
                                 "momentum_baseline_selected": len(momentum),
                                 "mean_momentum_baseline_net": mean(momentum) if momentum else None,
                                 "mean_selected_net": mean(net for net, _ in selected) if selected else None,
                                 "mean_matched_benchmark": mean(benchmark for _, benchmark in selected) if selected else None}
    return {"classification": "RESEARCH_ONLY", "metrics_by_horizon": metrics, "abstained": abstained,
            "outcome_unavailable": unavailable}
