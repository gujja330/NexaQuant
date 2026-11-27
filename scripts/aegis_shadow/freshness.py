"""Optional per-market freshness limit for same-session reuse."""
from datetime import datetime, timedelta
from pathlib import Path

from scripts.aegis_local_state import contained
from scripts.aegis_shadow.pipeline import _json


def reuse_max_age(root, market):
    path = contained(root, Path(".aegis-local/unified/inputs") / market / "refresh_policy.json")
    if not path.is_file():
        return None
    policy = _json(path)
    age = policy.get("max_same_session_age_minutes")
    if policy.get("market") != market or type(age) is not int or not 1 <= age <= 1440:
        raise ValueError("invalid market refresh policy or freshness window")
    return timedelta(minutes=age)


def refresh_due(age, stamp, now):
    if age is None:
        return False
    if not stamp:
        return True
    observed = datetime.fromisoformat(stamp)
    return observed.utcoffset() is None or not timedelta() <= now - observed < age
