"""Resolve reviewed historical stop and target authority by episode and session."""
from datetime import date, datetime
from math import isfinite
from zoneinfo import ZoneInfo


def _positive(value):
    return type(value) in (int, float) and isfinite(value) and value > 0


def resolve(document, market, episode, ticker, session):
    if (document.get("schema"), document.get("market")) != ("aegis.shadow.risk_intervals.v1", market):
        raise ValueError("historical risk interval market or schema mismatch")
    zone = ZoneInfo({"india": "Asia/Kolkata", "usa": "America/New_York"}[market])
    session_date = date.fromisoformat(session)
    candidates = []
    for row in document["intervals"]:
        if row.get("episode_id") != episode:
            continue
        first, last = (date.fromisoformat(row[field]) for field in ("effective_from", "effective_through"))
        if first > last:
            raise ValueError("historical risk interval has reversed bounds")
        if not first <= session_date <= last:
            continue
        if (row.get("ticker") != ticker or not row.get("source") or not row.get("revision_id")
                or not row.get("policy_version") or not row.get("price_basis") or not _positive(row.get("stop"))
                or "target" not in row or (row["target"] is not None and not _positive(row["target"]))):
            raise ValueError("incomplete historical risk authority or security identity mismatch")
        if first != last and row.get("carry_forward_authorized") is not True:
            raise ValueError("multi-session risk authority lacks approved carry-forward")
        stamp = datetime.fromisoformat(row["authorized_utc"])
        if stamp.utcoffset() is None or stamp.astimezone(zone).date() >= first:
            raise ValueError("historical risk authority must precede the first covered session")
        candidates.append(dict(row, authorized_on=stamp.astimezone(zone).date().isoformat()))
    if len(candidates) > 1:
        raise ValueError("overlapping historical risk authority for an episode")
    return candidates[0] if candidates else None
