"""Shared, frozen-input stage runner. All writes go to its private state tree."""
from dataclasses import dataclass
from datetime import date
from io import BytesIO
import json
from pathlib import Path
from subprocess import TimeoutExpired
from tempfile import NamedTemporaryFile
from time import perf_counter
from typing import Callable

from backend.shared.atomic_io import replace_with_retry
from scripts.aegis_local_state import _hold_lock, contained
from scripts.aegis_shadow.replay import replay


@dataclass(frozen=True)
class Stage:
    name: str
    action: Callable[[dict], str | None]
    requires: tuple[str, ...] = ()
    required: bool = True


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic(root, name, payload):
    target = contained(root, Path(name))
    pending = None
    try:
        with NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            pending = Path(stream.name)
            stream.write(payload)
        replace_with_retry(pending, target)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def _source(root, storage, market):
    explicit = contained(storage, Path("inputs") / market / "work")
    if explicit.is_dir():
        return explicit
    for receipt in sorted((root / ".aegis-local").glob(f"*-{market}-*/attempt.json"), reverse=True):
        safe = contained(root, receipt.relative_to(root))
        status = _json(safe).get("status")
        if status in {"completed", "certified", "delivered", "published"}:
            return contained(root, receipt.parent.relative_to(root) / "work")
    raise ValueError(f"no completed frozen {market} attempt or explicit shadow input")


def _load(context):
    market = context["market"]
    source = context["source"]
    lifecycle = _json(contained(source, Path(f"reports/context/canonical_lifecycle_{market}.json")))
    if lifecycle.get("market", "").lower() != market:
        raise ValueError("lifecycle market mismatch")
    for field in ("asof", "market_data_asof"):
        date.fromisoformat(lifecycle[field])
    if lifecycle["market_data_asof"] > lifecycle["asof"]:
        raise ValueError("market data session is after lifecycle asof")
    if not all(isinstance(lifecycle.get(key), list) for key in ("current", "exits")):
        raise ValueError("invalid lifecycle row collections")
    context["lifecycle"] = lifecycle


def _bootstrap(context):
    target = context["output"]
    existing = contained(target, Path("position_registry.jsonl"))
    raw = contained(context["source"], Path("reports/research/opportunity_registry.jsonl"))
    content = raw.read_bytes()
    rows = [json.loads(line) for line in content.splitlines() if line.strip()]
    selected = [row for row in rows if str(row.get("market", "")).lower() == context["market"]]
    if not selected:
        raise ValueError("frozen registry contains no rows for this market")
    if not existing.exists():
        lines = [json.dumps(row, ensure_ascii=False) for row in selected]
        _atomic(target, existing.name, ("\n".join(lines) + "\n").encode("utf-8"))
    preserved = [json.loads(line) for line in existing.read_bytes().splitlines() if line.strip()]
    context["positions"] = {row["opportunity_id"]: row for row in preserved}


def _fundamentals(context):
    market, source = context["market"], context["source"]
    if market == "india":
        import pandas as pd

        path = contained(source, Path("data/raw/india/fundamentals.parquet"))
        rows = pd.read_parquet(path).to_dict("records")
    else:
        path = contained(source, Path("usa/reports/fundamentals.json"))
        rows = list(_json(path)["tickers"].values())
    from backend.research.fundamentals.snapshot import _number

    if not rows:
        raise ValueError("frozen fundamentals snapshot has no records")
    summary = {"market": market, "rows": len(rows), "mode": "CURRENT_SNAPSHOT_AUDIT"}
    for field in ("eps_trailing", "eps_forward"):
        summary[field] = sum(_number(row.get(field)) is not None for row in rows)
    _atomic(context["output"], "fundamentals_coverage.json", json.dumps(summary).encode())


def _recover(context):
    output = context["output"]
    fixture = contained(context["source"], Path("shadow_recovery.json"))
    if not fixture.is_file():
        raise ValueError("shadow_recovery.json with verified sessions and risk evidence is required")
    evidence = _json(fixture)
    if (evidence.get("market") != context["market"]
            or evidence.get("completed_through") != context["lifecycle"]["market_data_asof"]):
        raise ValueError("recovery fixture does not match the frozen market session")
    eligible = {
        pid: row["created_date"] for pid, row in context["positions"].items()
        if row["created_date"] < evidence["completed_through"]
        and (not row.get("closed_date") or row["closed_date"] > evidence["last_committed"])
    }
    supplied = {row["opportunity_id"]: row["admitted"] for row in evidence["positions"]}
    if supplied != eligible and evidence["last_committed"] != evidence["completed_through"]:
        raise ValueError("recovery fixture does not cover the bootstrapped positions and entry dates")
    if evidence["last_committed"] == evidence["completed_through"] and supplied:
        raise ValueError("no-gap checkpoint must not contain replay positions")
    bounded = dict(evidence, positions=[
        dict(row, closed_on=context["positions"][row["opportunity_id"]].get("closed_date"))
        for row in evidence["positions"]
    ])
    result = replay(bounded)
    path = contained(output, Path("recovery.json"))
    prior = _json(path) if path.exists() else None
    if prior and (prior["completed_through"] > result["completed_through"]
                  or result["last_committed"] != prior["next_replay_from"]):
        if prior.get("input") == evidence:
            if prior["pending"]:
                raise ValueError("prior replay still has unresolved positions")
            return
        raise ValueError("recovery would reset or bypass the existing checkpoint")
    events = {tuple(row["event_id"]): row for row in (prior or {}).get("events", [])}
    exited = {row["opportunity_id"]: event_id for event_id, row in events.items()}
    for row in result["events"]:
        key = tuple(row["event_id"])
        previous = exited.get(row["opportunity_id"])
        if previous is not None and (previous != key or events[key] != row):
            raise ValueError("replay conflicts with an existing event")
        events[key] = row
    result["events"] = list(events.values())
    result["next_replay_from"] = (result["last_committed"] if result["pending"]
                                  else result["completed_through"])
    result["input"] = evidence
    _atomic(output, path.name, json.dumps(result, indent=2).encode())
    if result["pending"]:
        raise ValueError("some positions require earlier evidence before recovery can advance")


def _workbook(context):
    from backend.delivery.sheets.workbook_two import build_two_sheet_workbook

    result = build_two_sheet_workbook(
        context["source"], context["market"], context["lifecycle"]["asof"],
    )
    if result["lifecycle_stale"]:
        raise ValueError("frozen workbook source failed the lifecycle date check")
    with BytesIO() as stream:
        result["workbook"].save(stream)
        _atomic(context["output"], "shadow.xlsx", stream.getvalue())
    result["workbook"].close()


STAGES = (
    Stage("frozen_lifecycle", _load),
    Stage("bootstrap_registry", _bootstrap, ("frozen_lifecycle",)),
    Stage("recover_sessions", _recover, ("bootstrap_registry",)),
    Stage("fundamentals_coverage", _fundamentals, required=False),
    Stage("render_workbook", _workbook, ("frozen_lifecycle",)),
)


def _execute(context, stages=STAGES, *, prior=None):
    results = dict(prior or {})
    for stage in stages:
        start = perf_counter()
        status, reason, execution = "PASS", None, "EXECUTED"
        failure_category = None
        failed_dependencies = [dep for dep in stage.requires if results.get(dep, {}).get("status") != "PASS"]
        if failed_dependencies:
            status, reason = "BLOCKED", f"required input stages did not pass: {', '.join(failed_dependencies)}"
            execution = "BLOCKED"
            failure_category = "DEPENDENCY_FAILED"
        else:
            try:
                outcome = stage.action(context)
                if outcome == "REUSED":
                    execution = "REUSED"
                elif outcome == "RESEARCH_INSUFFICIENT_EVIDENCE":
                    status = outcome
                    failure_category = outcome
            except Exception as error:
                status, reason = "FAIL", str(error)
                if isinstance(error, (TimeoutError, TimeoutExpired)):
                    failure_category = "WORKER_TIMEOUT"
                elif isinstance(error, PermissionError):
                    failure_category = "ACCESS_DENIED"
                elif isinstance(error, FileNotFoundError):
                    failure_category = "ARTIFACT_MISSING"
                elif isinstance(error, (ValueError, KeyError, TypeError)):
                    failure_category = "ARTIFACT_OR_CONTRACT_INVALID"
                else:
                    failure_category = "STAGE_EXECUTION_FAILURE"
        print(f"{context['market']} {stage.name} {status}" + (" (reused)" if execution == "REUSED" else "")
              + (f"  {reason}" if reason else ""))
        results[stage.name] = {"status": status, "reason": reason,
                               "required": stage.required, "failure_category": failure_category,
                               "execution": execution,
                               "blocked_by": failed_dependencies,
                               "seconds": round(perf_counter() - start, 3)}
    return results


def run(root, markets):
    storage = contained(root, Path(".aegis-local/unified"))
    storage.mkdir(parents=True, exist_ok=True)
    failed = False
    for market in markets:
        try:
            output = contained(storage, Path("state") / market)
            output.mkdir(parents=True, exist_ok=True)
            with _hold_lock(contained(output, Path("run.lock")), market):
                source = _source(root, storage, market)
                print(f"{market} frozen source {source.relative_to(root)}")
                results = _execute({"market": market, "source": source, "output": output})
                ok = all(results[stage.name]["status"] == "PASS" for stage in STAGES if stage.required)
                _atomic(output, "summary.json", json.dumps({
                    "market": market, "mode": "SHADOW", "certified": False,
                    "source": source.relative_to(root).as_posix(), "stages": results,
                }, indent=2).encode())
                failed |= not ok
                print(f"{market} shadow {'completed' if ok else 'incomplete'}")
        except Exception as error:
            failed = True
            print(f"{market} shadow blocked  {error}")
    return int(failed)
