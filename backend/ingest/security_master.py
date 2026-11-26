"""Validated constituent versions and provider identity, separate from position state."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

from backend.ingest.ticker_health import yahoo_symbol
from backend.shared.atomic_io import write_bytes_atomic, write_text_atomic


_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.&-]{0,24}")


def normalize(symbols):
    values = [symbol.strip().upper() for symbol in symbols
              if isinstance(symbol, str)]
    if len(values) != len(symbols) or any(not _SYMBOL.fullmatch(symbol) for symbol in values):
        raise ValueError("invalid constituent symbol")
    if len(set(values)) != len(values):
        raise ValueError("duplicate constituent symbol")
    return sorted(values)


def update(folder, market, index, seed, fetch, *, now=None, bounds=(1, 1000),
           max_change=0.12, refresh_after=timedelta(days=1), stale_after=timedelta(days=7)):
    """Observe a verified reference candidate. This never changes position state."""
    clock = (lambda: now) if now is not None else (lambda: datetime.now(timezone.utc))
    now = clock()
    active = folder / f"{index}.json"
    baseline = {"market": market, "index": index, "members": normalize(seed), "observed_utc": None}
    last = baseline
    if active.is_file():
        try:
            retained = json.loads(active.read_text(encoding="utf-8"))
            if retained["market"] != market or retained["index"] != index:
                raise ValueError("retained constituent identity mismatch")
            normalize(retained["members"])
            stamp = datetime.fromisoformat(retained["observed_utc"])
            if stamp.tzinfo is None or stamp > now:
                raise ValueError("active version has an invalid observation time")
            last = retained
        except (OSError, ValueError, TypeError, KeyError):
            verified = []
            for path in (folder / "versions").glob(f"{index}-*.json"):
                try:
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != path.stem.removeprefix(index + "-"):
                        continue
                    record = json.loads(raw)
                    if record.get("market") != market or record.get("index") != index:
                        continue
                    stamp = datetime.fromisoformat(record["observed_utc"])
                    if stamp.tzinfo is not None and stamp <= now:
                        normalize(record["members"])
                        verified.append((stamp, record))
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    continue
            if verified:
                last = max(verified, key=lambda item: item[0])[1]
    observed = last["observed_utc"]
    age = now - datetime.fromisoformat(observed) if observed else None
    attempt = folder / f"{index}.status.json"
    if age is not None and timedelta() <= age < refresh_after:
        return last, {"status": "RETAINED_VERIFIED", "observed_utc": observed}
    if attempt.is_file():
        try:
            previous_attempt = json.loads(attempt.read_text(encoding="utf-8"))
            tried = datetime.fromisoformat(previous_attempt["attempted_utc"])
            if timedelta() <= now - tried < timedelta(hours=1):
                return last, previous_attempt
        except (OSError, ValueError, TypeError, KeyError):
            pass

    candidate = None
    try:
        candidate = fetch()
        members = normalize(candidate["members"])
        timestamp = datetime.fromisoformat(candidate["observed_utc"])
        if not timedelta() <= clock() - timestamp <= stale_after:
            raise ValueError("source observation outside freshness window")
        if timestamp.tzinfo is None or candidate["market"] != market or candidate["index"] != index:
            raise ValueError("source identity mismatch")
        if observed and timestamp < datetime.fromisoformat(observed):
            raise ValueError("source observation predates the active verified version")
        if not bounds[0] <= len(members) <= bounds[1]:
            raise ValueError("constituent population outside approved bounds")
        before, after = set(last["members"]), set(members)
        added, removed = sorted(after - before), sorted(before - after)
        if len(added) + len(removed) > max_change * max(len(before), 1):
            raise ValueError("unexplained constituent change exceeds review threshold")
        last = dict(candidate, members=members, added=added, removed=removed)
        payload = json.dumps(last, sort_keys=True, indent=2).encode()
        version = hashlib.sha256(payload).hexdigest()
        write_bytes_atomic(folder / "versions" / f"{index}-{version}.json", payload)
        write_bytes_atomic(active, payload)
        status = {"status": "VERIFIED", "observed_utc": last["observed_utc"], "version": version}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        status = {"status": "STALE_FALLBACK" if age is None or age > stale_after else "FALLBACK",
                  "observed_utc": observed, "reason": str(exc), "rejected": candidate}
    status["attempted_utc"] = now.isoformat()
    write_text_atomic(attempt, json.dumps(status, indent=2))
    return last, status


def populations(root, market, configured, monitored, benchmarks, pending=()):
    """Canonical symbols remain registry keys. Provider codes are a separate view."""
    configured, monitored = set(configured), set(monitored)
    watch = configured | monitored | set(benchmarks) | set(pending)
    return {
        "configured": sorted(configured), "monitored": sorted(monitored),
        "held_outside_configured": sorted(monitored - configured),
        "benchmarks": sorted(set(benchmarks)), "pending": sorted(set(pending)),
        "provider_symbols": {symbol: yahoo_symbol(root, market, symbol) for symbol in sorted(watch)},
    }
