"""Read-only reconstruction of close-based risk events from frozen evidence."""
from datetime import date
from math import isfinite


def _day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError(f"expected an ISO session date, got {value!r}")
    return value


def _price(value):
    return type(value) in (int, float) and isfinite(value) and value > 0


def replay(evidence):
    """Replay a complete exchange schedule supplied by the fixture author.

    Each position carries session-keyed closes and session-keyed authorized
    levels. A level is eligible only with strictly earlier authorization.
    The caller must establish that the schedule is complete and that the
    observations and levels use the same corporate-action basis.
    """
    market = evidence["market"]
    if market not in ("india", "usa"):
        raise ValueError("unsupported market")
    through = _day(evidence["completed_through"])
    committed = _day(evidence["last_committed"])
    sessions = [_day(day) for day in evidence["sessions"]]
    if (committed > through or sessions != sorted(set(sessions))
            or any(not committed < day <= through for day in sessions)
            or (committed < through and (not sessions or sessions[-1] != through))):
        raise ValueError("invalid completed session sequence")

    events, pending = [], []
    positions = evidence["positions"]
    identities = [position["opportunity_id"] for position in positions]
    if any(not isinstance(pid, str) or not pid.strip() for pid in identities):
        raise ValueError("invalid position identity")
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate position identity")
    for position in sorted(positions, key=lambda row: row["opportunity_id"]):
        pid = position["opportunity_id"]
        admitted = _day(position["admitted"])
        closed = position.get("closed_on")
        if closed:
            closed = _day(closed)
        for session in sessions:
            if session <= admitted:
                continue
            if closed and session > closed:
                break
            bar = position["bars"].get(session) or {}
            levels = position["levels"].get(session) or {}
            known = levels.get("authorized_on")
            basis = bar.get("price_basis")
            close = bar.get("close")
            stop = levels.get("stop")
            target = levels.get("target")
            if (not _price(close) or not _price(stop) or not known
                    or not admitted <= _day(known) < session
                    or not basis or basis != levels.get("price_basis")
                    or (target is not None and not _price(target))):
                pending.append({"opportunity_id": pid, "session": session,
                                "reason": "incomplete point-in-time risk evidence"})
                break
            if close <= stop:
                rule, level = "EXIT_STOP", stop
            elif target is not None and close >= target:
                rule, level = "EXIT_TARGET", target
            else:
                continue
            events.append({
                "event_id": [market, pid, session, rule],
                "opportunity_id": pid,
                "session": session,
                "rule": rule,
                "trigger_close": close,
                "effective_level": level,
                "execution_status": "UNKNOWN",
                "mode": "SIMULATED_OBSERVATION",
            })
            break
    events.sort(key=lambda row: (row["session"], row["opportunity_id"]))
    pending.sort(key=lambda row: (row["session"], row["opportunity_id"]))
    return {"market": market, "last_committed": committed,
            "completed_through": through, "events": events, "pending": pending,
            "review_status": "INCOMPLETE_EVIDENCE" if pending else "REPLAYED"}
