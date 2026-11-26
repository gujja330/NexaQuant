"""Point-in-time profit capture for a frozen, explicitly simulated cohort."""
from scripts.aegis_shadow.replay import _day, _price


def profit_capture(evidence):
    """Measure simulated close exits using post-entry session highs."""
    cutoff = _day(evidence["asof"])
    rows, excluded = [], []
    seen = set()
    for episode in evidence["episodes"]:
        pid = episode["opportunity_id"]
        if not isinstance(pid, str) or not pid.strip() or pid in seen:
            raise ValueError("invalid or duplicate cohort identity")
        seen.add(pid)
        entry_day = _day(episode["entry_date"])
        exit_day = _day(episode["exit_date"]) if episode.get("exit_date") else None
        entry, exit_price = episode.get("entry_price"), episode.get("exit_price")
        highs = episode.get("highs") or {}
        sessions = [_day(day) for day in episode.get("sessions", [])]
        basis = episode.get("price_basis")
        if (episode.get("mode") != "SIMULATED" or episode.get("side") != "LONG"
                or episode.get("exit_observation") != "SESSION_CLOSE"
                or not exit_day or not entry_day < exit_day <= cutoff
                or not _price(entry) or not _price(exit_price) or not basis
                or not sessions or sessions != sorted(set(sessions))
                or sessions[-1] != exit_day or sessions[0] <= entry_day
                or any(not _price(highs.get(day, {}).get("high"))
                       or highs[day].get("price_basis") != basis for day in sessions)):
            excluded.append(pid)
            continue
        peak = max(entry, exit_price, *(highs[day]["high"] for day in sessions))
        realized = (exit_price / entry - 1.0) * 100
        favorable = (peak / entry - 1.0) * 100
        rows.append({
            "opportunity_id": pid,
            "simulated_return_pct": realized,
            "observed_favorable_return_pct": favorable,
            "giveback_pp": favorable - realized,
            "peak_profit_capture_pct": 100 * realized / favorable if favorable else None,
        })
    return {"asof": cutoff, "mode": "SIMULATED_RESEARCH", "episodes": rows,
            "excluded_ids": excluded}
