"""Read-only release preflight for the private daily runner."""
from datetime import date, datetime, timezone
from importlib.util import find_spec
import os
from pathlib import Path

from scripts.aegis_local_state import REGISTRY, contained, digest
from scripts.aegis_shadow.calendar import exchange_calendar
from scripts.aegis_shadow.daily import _plan
from scripts.aegis_shadow.freshness import reuse_max_age
from scripts.aegis_shadow.operations import worker_retry
from scripts.aegis_shadow.provider import policy as provider_policy
from scripts.aegis_shadow.pipeline import _json
from scripts.aegis_shadow.sandbox import launcher
from scripts.aegis_shadow.simulated_orders import BOOK


def inspect_market(root, market, now):
    errors, notices = [], []
    storage = contained(root, Path(".aegis-local/unified"))
    calendar = exchange_calendar(market, storage if storage.is_dir() else None)
    reuse_max_age(root, market)
    worker_retry(root, market)
    provider_policy(root, market)
    latest = calendar.completed(now)
    private = contained(root, Path(".aegis-local/unified/daily") / market)
    pointer = contained(root, private.relative_to(root) / "accepted.json")
    baseline, saved = root, None
    if pointer.is_file():
        saved = _json(pointer)
        baseline = contained(private, Path(saved["workspace"]))
        if saved.get("simulator_book_sha256"):
            book = contained(baseline, BOOK)
            if not book.is_file() or digest(book) != saved["simulator_book_sha256"]:
                errors.append("accepted simulator book checksum mismatch")

    lifecycle = Path(f"reports/context/canonical_lifecycle_{market}.json")
    for relative in (REGISTRY, lifecycle):
        path = contained(root, baseline.relative_to(root) / relative)
        if not path.is_file() or not path.stat().st_size:
            errors.append(f"missing bootstrap evidence: {relative}")
        elif saved is not None and digest(path) != saved.get("state_sha256", {}).get(relative.as_posix()):
            errors.append(f"accepted state checksum mismatch: {relative}")
    path = contained(root, baseline.relative_to(root) / lifecycle)
    if path.is_file():
        record = _json(path)
        if record.get("market") != market:
            errors.append("bootstrap lifecycle market mismatch")
        previous = date.fromisoformat(record["market_data_asof"])
        gap = calendar.missing(previous, latest)
        if gap:
            recovery = contained(root, Path(".aegis-local/unified/inputs") / market / "shadow_recovery.json")
            intervals = contained(recovery.parent, Path("risk_intervals.json")) if recovery.parent.is_dir() else None
            if not recovery.is_file() and not (intervals and intervals.is_file()):
                errors.append(f"recovery evidence required for {len(gap)} missed sessions")
            elif recovery.is_file():
                evidence = _json(recovery)
                if (evidence.get("market"), evidence.get("last_committed"), evidence.get("sessions"),
                        evidence.get("completed_through")) != (market, previous.isoformat(), gap, gap[-1]):
                    errors.append("retained recovery evidence does not match the missed sessions")
            if intervals and intervals.is_file():
                authority = _json(intervals)
                if (authority.get("schema"), authority.get("market")) != ("aegis.shadow.risk_intervals.v1", market):
                    errors.append("risk interval schema or market disagrees")

    asof = now.date().isoformat()
    bindings = {}
    stages = _plan(root, market, asof, bindings=bindings)
    for stage in stages:
        binding = bindings.get(stage.name)
        if binding is None:
            continue
        command = binding.command
        if command[0] == "-m":
            module = Path(*command[1].split("."))
            entrypoints = (module.with_suffix(".py"), module / "__main__.py")
        else:
            entrypoints = (Path(command[0]),)
        if not any(contained(root, entry).is_file() for entry in entrypoints) or not binding.outputs:
            (errors if stage.required else notices).append(f"unverified binding or output contract: {stage.name}")

    for relative in (Path("configs/portfolio_config.yaml"), Path("configs/risk_budget.yaml")):
        if not contained(root, relative).is_file():
            errors.append(f"required engine configuration missing: {relative}")
    for path in (storage, contained(root, Path("reports/unified") / market)):
        existing = next(candidate for candidate in (path, *path.parents) if candidate.is_dir())
        if not os.access(existing, os.W_OK):
            errors.append(f"owner account lacks write permission: {existing}")
    config = contained(root, Path(".aegis-local/unified/delivery.json"))
    if config.is_file() and _json(config).get("enabled") is True:
        errors.append("disable shadow delivery before initial release validation")
    return latest, stages, errors, notices


def run_preflight(root, markets):
    packages = ("numpy", "pandas", "pyarrow", "openpyxl", "yaml", "requests", "yfinance")
    missing = [name for name in packages if find_spec(name) is None]
    if missing:
        print(f"Missing required dependencies: {', '.join(missing)}")
    failed = bool(missing)
    try:
        launcher()
    except RuntimeError as error:
        print(f"Worker isolation preflight failed | {error}")
        failed = True
    now = datetime.now(timezone.utc)
    for market in markets:
        try:
            latest, stages, errors, notices = inspect_market(root, market, now)
        except (KeyError, OSError, RuntimeError, ValueError, TypeError) as error:
            print(f"{market} PREFLIGHT FAILED | {error}")
            failed = True
            continue
        print(f"{market} session {latest} | {sum(stage.required for stage in stages)} required / {len(stages)} planned")
        for message in (*errors, *notices):
            print(f"  {message}")
        print(f"{market} PREFLIGHT {'FAILED' if errors or missing else 'PASS'}")
        failed |= bool(errors)
    return int(failed)
