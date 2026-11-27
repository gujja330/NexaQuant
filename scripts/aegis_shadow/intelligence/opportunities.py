"""Rank research candidates using evidence, expected net return and downside."""
from math import log1p

from scripts.aegis_shadow.intelligence.lab import number


def rank(rows, session, predictions):
    source = {(row["security_id"], row["horizon"]): row for row in rows if row["session"] == session}
    sector_groups = {}
    for row in source.values():
        if row.get("sector") and number(row.get("relative_strength")):
            sector_groups.setdefault((row["sector"], row["horizon"]), []).append(row["relative_strength"])
    ranked = []
    for prediction in predictions:
        key = prediction["security_id"], prediction["horizon"]
        row = source[key]
        estimate = prediction["net_return_distribution"]
        item = {"security_id": key[0], "horizon": key[1], "status": "ABSTAIN", "regime": row.get("regime"),
                "sector": row.get("sector"), "quality_evidence": row.get("quality_evidence"),
                "strategy_flags": row.get("strategy_flags", {}), "score": None,
                "reason": prediction["reason"]}
        ranked.append(item)
        volatility, liquidity = row.get("daily_volatility"), row.get("liquidity_proxy")
        if estimate is None or not all(number(value) and value > 0 for value in (volatility, liquidity)):
            item["reason"] = item["reason"] or "Volatility or liquidity evidence unavailable"
            continue
        downside = max(0, -estimate["q10"])
        uncertainty = estimate["q90"] - estimate["q10"]
        penalty = downside + uncertainty + volatility * key[1] ** .5
        peers = sector_groups.get((row.get("sector"), key[1]), ())
        relative = row.get("relative_strength")
        sector_percentile = sum(value <= relative for value in peers) / len(peers) if len(peers) > 1 and number(relative) else None
        item.update(expected_net_return=estimate["mean"], downside=downside, uncertainty=uncertainty,
                    liquidity_proxy=liquidity, risk_penalty=penalty,
                    sector_relative_percentile=sector_percentile,
                    modeled_round_trip_cost=row.get("modeled_round_trip_cost"),
                    reward_to_risk=estimate.get("tail_reward_to_risk"))
        if estimate["mean"] <= 0:
            item.update(status="NOT_ELIGIBLE", reason="Expected net return is nonpositive")
        elif not any(value is True for value in item["strategy_flags"].values()):
            item.update(status="NOT_ELIGIBLE", reason="No supported momentum strategy signal")
        elif item["strategy_flags"].get("exhaustion") or item["strategy_flags"].get("failed_breakout"):
            item.update(status="NOT_ELIGIBLE", reason="Exhaustion or failed breakout observed")
        else:
            sector_multiplier = .5 + sector_percentile if sector_percentile is not None else 1
            item.update(status="RESEARCH_CANDIDATE", score=estimate["mean"] / penalty * log1p(liquidity) * sector_multiplier,
                        reason="Positive expected net return with liquidity and risk evidence")
    return sorted(ranked, key=lambda item: (item["horizon"], item["score"] is None, -(item["score"] or 0), item["security_id"]))
