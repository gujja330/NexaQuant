"""Independent daily orchestration for copied, guarded workspaces."""
import ast
from copy import copy
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp
from time import perf_counter

from scripts.aegis_local_state import Attempt, REGISTRY, _files, _hold_lock, contained, digest, validate_held_actions
from scripts.aegis_shadow.calendar import exchange_calendar
from scripts.aegis_shadow.closed_outcomes import emit as closed_outcomes
from scripts.aegis_shadow.closed_learning import emit as closed_learning
from scripts.aegis_shadow.commit import finish as finish_commit, prepare as prepare_commit
from scripts.aegis_shadow.execution_accounting import audit as execution_accounting
from scripts.aegis_shadow.evidence_archive import retain as retain_evidence
from scripts.aegis_shadow.freshness import refresh_due, reuse_max_age
from scripts.aegis_shadow.identity import dependencies, sync_dependencies
from scripts.aegis_shadow.intelligence.integration import emit as strategy_research
from scripts.aegis_shadow.learning_observations import emit as open_episode_research
from scripts.aegis_shadow.operations import run_with_timeout_retry, worker_retry
from scripts.aegis_shadow.pipeline import Stage, _atomic, _execute, _json
from scripts.aegis_shadow.position_history import read as position_history, record as record_positions
from scripts.aegis_shadow.provider import policy as provider_policy
from scripts.aegis_shadow.publication import SCHEMA, SHEETS, delivery_status, notify
from scripts.aegis_shadow.recover_daily import annotate_lifecycle
from scripts.aegis_shadow.sandbox import launcher, worker_command
from scripts.aegis_shadow.simulated_orders import BOOK, emit as simulated_orders
from scripts.aegis_shadow.stage_cache import regime_cache, reuse_regime, seal_regime


@dataclass(frozen=True)
class Binding:
    name: str
    command: tuple
    inputs: tuple = ()
    outputs: tuple = ()
    required: bool = True
    timeout: int = 900
    check_update: bool = True


_EXCLUDED = {
    "telegram", "aegis_3sheet_workbook", "five_sheet_workbook_audit",
    "aegis_provenance_companion", "aegis_overlap_classifier", "aegis_visual_signoff",
    "aegis_final_reconciler", "aegis_local_certification", "aegis_determinism_hash",
    "registry_materializer", "dynamic_risk_v2_both_markets", "dynamic_exit_bridge",
    "canonical_daily_lifecycle",
}
_REQUIRED_KEYS = {"name", "script", "module", "script_args", "requires", "produces",
                  "optional", "timeout_s"}
_SCOPED_OUTPUTS = {
    "multi_layer_momentum_ledger": "reports/research/multi_layer/momentum_ledger_{market}_{asof}.json",
    "multi_layer_stress_regime": "reports/research/multi_layer/stress_regime_{market}_{asof}.json",
    "multi_layer_crash_resilience": "reports/research/multi_layer/crash_resilience_{market}_{asof}.json",
    "multi_layer_runner_india": "reports/research/multi_layer/evidence_{market}_{asof}.json",
    "multi_layer_runner_usa": "reports/research/multi_layer/evidence_{market}_{asof}.json",
    "aegis_r1_producer_audit": "reports/audit/r1_producer_audit_{market}_{asof}.json",
    "r3_shadow": "reports/research/r3/shadow/summary_{market}.json",
}
_REQUIRED_DAILY = {"feature_store", "feature_intelligence", "model_factory",
                   "recommendation_intelligence", "risk_engine", "portfolio_engine"}


def _inventory(path, market):
    """Reuse legacy stage bindings as data without executing either orchestrator."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "STEPS" for target in statement.targets
        ):
            definitions = statement.value.elts
            break
    else:
        raise ValueError(f"STEPS missing in {path.name}")
    for definition in definitions:
        record = {key.value: ast.literal_eval(value)
                  for key, value in zip(definition.keys, definition.values)
                  if isinstance(key, ast.Constant) and key.value in _REQUIRED_KEYS}
        name = record["name"]
        if name in _EXCLUDED or name in {"backend_validation", "ops_check"}:
            continue
        args = tuple(record.get("script_args", ()))
        other = "usa" if market == "india" else "india"
        if "--market" in args and args[args.index("--market") + 1] == other:
            continue
        shared = "both" in args or name == "monthly_rollups"
        if name == "monthly_rollups":
            args = ("--market", market)
        elif shared:
            args = tuple(market if arg == "both" else arg for arg in args)
        command = ("-m", record["module"]) if record.get("module") else (record["script"],)
        if any("telegram" in part.lower() or part.startswith("--send") for part in (*command, *args)):
            continue
        inputs = tuple(p for p in record.get("requires", ()) if not shared or f"_{other}" not in p)
        outputs = tuple(p for p in record.get("produces", ()) if not shared or f"_{other}" not in p)
        if name in _SCOPED_OUTPUTS:
            outputs = (_SCOPED_OUTPUTS[name].replace("{market}", market),)
        yield Binding(name, command + args, inputs, outputs,
                      name in _REQUIRED_DAILY or not record.get("optional", False), record.get("timeout_s") or 900)


def _artifacts(root, patterns, asof):
    files = set()
    for pattern in patterns:
        rel = Path(pattern.replace("{asof}", asof).replace("{month}", asof[:7]))
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"invalid artifact pattern: {pattern}")
        for candidate in root.glob(rel.as_posix()):
            safe = contained(root, candidate.relative_to(root))
            if safe.is_file() and safe.stat().st_size:
                files.add(safe)
    return files


def _fingerprints(files):
    return {path: (path.stat().st_mtime_ns, path.stat().st_size) for path in files}


def _run_binding(context, binding):
    work, asof = context["work"], context["asof"]
    cache = None
    if binding.name == "research_market_regime":
        cache = regime_cache(context, binding)
        if not context.get("force") and reuse_regime(cache, context["market"], context["session"]):
            if context["mode"] == "FULL":
                context["mode"] = "INCREMENTAL"
            return "REUSED"
    for pattern in binding.inputs:
        if not _artifacts(work, (pattern,), asof):
            raise ValueError(f"required artifact is absent: {pattern}")
    before = {pattern: _fingerprints(_artifacts(work, (pattern,), asof))
              for pattern in binding.outputs}
    command = [sys.executable, "-I", "-B", "-X", "utf8", str(work / "scripts/aegis_shadow/worker.py"),
               *binding.command]
    if binding.name in {"dynamic_risk", "dynamic_exits"}:
        session = context["session"]
        command.append(session)
        calendar = context["calendar"]
        date_key = date.fromisoformat(session)
        cutoff = datetime.combine(date_key, calendar.closes[date_key], calendar.timezone)
        command.extend(("--observation-close", cutoff.isoformat()))
        if binding.name == "dynamic_risk":
            previous = max((day.isoformat() for day in context["calendar"].closes if day.isoformat() < session), default=None)
            if previous:
                command.extend(("--previous", previous))
            following = min((day.isoformat() for day in context["calendar"].closes if day.isoformat() > session), default=None)
            if following:
                command.extend(("--next-session", following))
    if binding.name == "recommendation_ssot":
        market = context["market"]
        reports = "reports" if market == "india" else "usa/reports"
        snapshot = contained(work, Path(reports) / "recommendations_history" / market / f"{asof}.json")
        command.extend(("--asof", asof))
        if snapshot.is_file():
            checksum = digest(snapshot)
            folder = contained(work, snapshot.parent.relative_to(work) / "superseded" / asof)
            folder.mkdir(parents=True, exist_ok=True)
            archive = contained(folder, Path(f"{checksum}.json"))
            if not archive.exists():
                _atomic(folder, archive.name, snapshot.read_bytes())
            if digest(archive) != checksum:
                raise ValueError("private recommendation archive checksum mismatch")
            command.append("--force")
    def invoke(number):
        suffix = "" if number == 1 else f".retry-{number}"
        log = contained(context["logs"], Path(f"{binding.name}{suffix}.log"))
        env = context["env"]
        if binding.name in {"refresh_prices", "refresh_market_data"}:
            env = dict(env, AEGIS_SHADOW_PRICE_PROVIDER=json.dumps(context["provider_policy"]))
        with log.open("xb") as stream:
            result = subprocess.run(worker_command(context["sandbox"], work, command), cwd=work, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=binding.timeout)
        return result, log

    # The regime producer replaces its own isolated research artifact. A
    # timeout in a lifecycle writer can leave side effects and is never retried here.
    attempts, delay = context.get("worker_retry", (1, 0)) if cache is not None else (1, 0)
    result, log = run_with_timeout_retry(invoke, attempts, delay, on_timeout=lambda number: print(
        f"{context['market']} {binding.name} WORKER_TIMEOUT (attempt {number}/{attempts})", flush=True))
    if result.returncode:
        raise RuntimeError(f"engine exit {result.returncode}; see {log.name}")
    for pattern, previous in before.items():
        current = _fingerprints(_artifacts(work, (pattern,), asof))
        if not current:
            raise RuntimeError(f"declared output absent: {pattern}")
        if binding.check_update and current == previous:
            sealed = "{asof}" in pattern and pattern.endswith(".parquet") and len(current) == 1
            if not sealed:
                raise RuntimeError(f"declared output did not change: {pattern}")
        if binding.name in {"research_market_regime", "multi_layer_stress_regime", "multi_layer_crash_resilience"}:
            for path in current:
                report = _json(path)
                if report.get("error") or (binding.name == "research_market_regime" and not report.get("regimes")):
                    raise ValueError(f"research evidence unavailable for {binding.name}")
    if not before:
        raise RuntimeError("engine completed without a verifiable output contract")
    if cache is not None:
        seal_regime(cache, context["market"], context["session"])


def _worker_env(work):
    runtime = contained(work, Path(".shadow-runtime"))
    runtime.mkdir(exist_ok=True)
    env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE",
                                              "COMSPEC", "PATH", "PATHEXT") if name in os.environ}
    for key in ("TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                "XDG_CACHE_HOME", "MPLCONFIGDIR"):
        env[key] = str(runtime)
    return env


def _missing_sessions(market, previous, latest):
    return exchange_calendar(market).missing(previous, latest)


def _checkpoint(context):
    market = context["market"]
    latest = date.fromisoformat(context["session"])
    if not context.get("previous_session"):
        raise ValueError("no prior lifecycle checkpoint")
    previous = date.fromisoformat(context["previous_session"])
    gap = context["calendar"].missing(previous, latest)
    context["missed_sessions"] = gap
    if gap:
        context["mode"] = "GAP_RECOVERY"


def _recover_gap(context):
    market = context["market"]
    gap = context["missed_sessions"]
    if gap:
        evidence = contained(context["storage"], Path("inputs") / market / "shadow_recovery.json")
        intervals = contained(context["work"], Path(".shadow-risk-intervals.json"))
        if not evidence.is_file() and not intervals.is_file():
            raise ValueError(f"historical risk evidence required for missed sessions: {', '.join(gap)}")
        payload = evidence.read_bytes() if evidence.is_file() else json.dumps({
            "market": market, "last_committed": context["previous_session"], "sessions": gap,
            "completed_through": gap[-1], "positions": [],
        }).encode()
        _atomic(context["work"], ".shadow-recovery-input.json", payload)
        _run_binding(context, Binding(
            "historical_risk_replay",
            ("-m", "scripts.aegis_shadow.recover_daily", market, context["previous_session"], *gap),
            outputs=(".shadow-recovery-result.json",),
        ))
        recovered = contained(context["work"], Path(".shadow-recovery-result.json"))
        context["recovered_events"] = len(_json(recovered)["events"])
        context["recovered_sessions"] = gap


def _binding_stage(binding, dependencies=()):
    return Stage(binding.name, lambda context: _run_binding(context, binding),
                 dependencies, binding.required)


def _shadow_table(sheet, header, rows, columns, market):
    from math import isfinite
    from openpyxl.utils import get_column_letter

    headers = {cell.value: cell.column for cell in sheet[header] if cell.value}
    for label in columns:
        index = len(headers) + 1
        cell = sheet.cell(header, index, label)
        cell._style = copy(sheet.cell(header, index - 1)._style)
        headers[label] = index
        sheet.column_dimensions[get_column_letter(index)].width = max(18, len(label) + 2)
    currency = '"₹"' if market == "india" else '"$"'
    for number, row in enumerate(rows, header + 1):
        for label, field in columns.items():
            value = row.get(field)
            sheet.cell(number, headers[label], value if value is not None else "UNAVAILABLE")
        for label in ("Entry Price", "Last Price", "Exit Price", "Stop", "Target", "Original Stop", "Observation Price",
                      "Previous Effective Stop", "Proposed Stop", "Research Trailing Stop"):
            if label in headers:
                cell = sheet.cell(number, headers[label])
                if type(cell.value) in (float, int):
                    cell.number_format = currency + "#,##0.00"
        for label in ("Research Upside", "Research Downside"):
            if label in headers:
                cell = sheet.cell(number, headers[label])
                if type(cell.value) in (float, int):
                    cell.number_format = "0.00%"
        pnl = row.get("pnl_pct" if header == 7 else "realized_pnl_pct")
        cell = sheet.cell(number, headers["P&L %"])
        if type(pnl) in (float, int) and isfinite(pnl):
            cell.value = pnl / 100
            cell.number_format = "0.00%;-0.00%;0.00%"
            font = copy(cell.font)
            font.color = "FF166534" if pnl > 0 else "FF991B1B" if pnl < 0 else "FF334155"
            cell.font = font
        else:
            cell.value = "UNAVAILABLE"
    sheet.freeze_panes = f"C{header + 1}"
    sheet.auto_filter.ref = f"A{header}:{get_column_letter(len(headers))}{header + len(rows)}"
    for entry in sheet.iter_rows(min_row=header + len(rows) + 1, max_col=1):
        cell = entry[0]
        if isinstance(cell.value, str) and cell.value.startswith("P&L is shown in percentage points."):
            cell.value = "P&L cells use Excel percentage formatting."


def _holding_sessions(entry, end, calendar):
    try:
        first, last = date.fromisoformat(entry), date.fromisoformat(end)
        if not calendar.start <= first <= calendar.end or not calendar.start <= last <= calendar.end:
            return None
        return sum(first < day <= last for day in calendar.closes)
    except (TypeError, ValueError):
        return None


def _workbook(context):
    from io import BytesIO

    from backend.delivery.sheets.workbook_two import build_two_sheet_workbook

    work, market = context["work"], context["market"]
    report = build_two_sheet_workbook(work, market, context["asof"])
    workbook = report["workbook"]
    try:
        if report["lifecycle_stale"]:
            raise ValueError("workbook lifecycle is stale")
        for sheet in workbook.worksheets:
            sheet["A1"] = f"SHADOW | {sheet['A1'].value}"
        for sheet, name in zip(workbook.worksheets, SHEETS[1:]):
            sheet.title = name
        lifecycle = _json(contained(work, Path(f"reports/context/canonical_lifecycle_{market}.json")))
        calendar = context["calendar"]
        positions = position_history(work, market, context["session"])["positions"]
        research = {}
        if context.get("strategy_research_ready"):
            research = _json(contained(work, Path(f"reports/research/intelligence/{market}/strategy_research.json")))
            if (research.get("market"), research.get("session"), research.get("classification")) != (
                    market, context["session"], "RESEARCH_ONLY"):
                raise ValueError("strategy research market, session or authority mismatch")
        management = {item["episode_id"]: item for item in research.get("management_reviews", [])}
        current = [dict(row, holding_sessions=_holding_sessions(row.get("entry_date"), context["session"], calendar),
                        holding_horizon_days=positions[row["position_id"]]["holding_horizon_days"],
                        stop_type=positions[row["position_id"]]["stop_type"],
                        stop_reason=positions[row["position_id"]]["stop_reason"],
                        proposed_stop=positions[row["position_id"]].get("proposed_stop"),
                        proposal_effective_from=positions[row["position_id"]].get("proposal_effective_from"),
                        previous_effective_stop=positions[row["position_id"]]["previous_effective_stop"],
                        first_target_reached_session=positions[row["position_id"]]["first_target_reached_session"])
                   for row in lifecycle["current"]]
        for row in current:
            signal = management.get(row["position_id"], {})
            row.update({f"research_{key}": signal.get(key) for key in (
                "momentum_state", "forecast_upside", "forecast_downside", "proposed_stop", "profit_booking_action",
                "holding_action", "exit_action", "reason", "evidence_quality", "forecast_horizon_sessions", "reward_to_risk")})
        exits = [dict(row, holding_sessions=_holding_sessions(row.get("entry_date"), row.get("exit_date"), calendar))
                 for row in lifecycle["exits"]]
        _shadow_table(workbook[SHEETS[1]], 7, current, {
            "Holding Sessions": "holding_sessions",
            "Holding Horizon (Days)": "holding_horizon_days", "Stop Type": "stop_type", "Stop Reason": "stop_reason",
            "Previous Effective Stop": "previous_effective_stop", "First Target Reached Session": "first_target_reached_session",
            "Proposed Stop": "proposed_stop", "Proposal Effective From": "proposal_effective_from",
            "Holding Review": "holding_review", "Decision Score": "decision_score",
            "Evidence Quality": "evidence_quality", "Source": "source",
            "Research Momentum": "research_momentum_state",
            "Research Forecast Horizon": "research_forecast_horizon_sessions",
            "Research Upside": "research_forecast_upside", "Research Downside": "research_forecast_downside",
            "Research Reward to Risk": "research_reward_to_risk",
            "Research Trailing Stop": "research_proposed_stop", "Research Booking": "research_profit_booking_action",
            "Research Holding": "research_holding_action", "Research Exit": "research_exit_action",
            "Research Reason": "research_reason", "Research Evidence": "research_evidence_quality",
        }, market)
        _shadow_table(workbook[SHEETS[2]], 4, exits, {
            "Holding Sessions": "holding_sessions",
            "Trigger Session": "trigger_session", "Observation Price": "observation_price",
            "Execution Status": "execution_status", "Recovered During Gap": "recovered_during_gap",
            "Recovery Detected (UTC)": "recovery_detected_utc", "Policy Version": "policy_version",
        }, market)
        summary = workbook.create_sheet(SHEETS[0], 0)
        summary.append(["AEGIS NEW", "SHADOW"])
        summary.append(["Market", context["market"].upper()])
        summary.append(["Runner", "new"])
        summary.append(["Execution mode", context["mode"]])
        summary.append(["Report date", context["asof"]])
        summary.append(["Report timestamp (UTC)", datetime.now(timezone.utc).isoformat()])
        summary.append(["Completed market session", context["session"]])
        summary.append(["Previous lifecycle session", context.get("previous_session")])
        summary.append(["Previous verified workbook", context.get("previous_workbook")])
        summary.append(["Missed sessions", len(context.get("missed_sessions", ()))])
        summary.append(["Recovered sessions", len(context.get("recovered_sessions", ()))])
        summary.append(["Simulated recovery events", context.get("recovered_events", 0)])
        summary.append(["Engine stages attempted", context["executed_engines"]])
        summary.append(["Engine stages reused", context["reused_engines"]])
        summary.append(["CURRENT records", report["current_rows"]])
        summary.append(["EXIT HISTORY records", report["exit_rows"]])
        for name, field in (("New admissions", "new"), ("Stop breach marks", "breach_exits"),
                            ("Stale inputs", "stale_inputs")):
            summary.append([name, lifecycle.get("counts", {}).get(field)])
        reports = "reports" if market == "india" else "usa/reports"
        backend = _json(contained(work, Path(reports) / "backend_validation_summary.json"))
        summary.append(["Backend dataset verdict", backend.get("verdict")])
        if research:
            summary.append(["Research forecast status", research["forecast_status"]])
            summary.append(["Research estimates", sum(row["classification"] == "RESEARCH_ESTIMATE" for row in research["forecasts"])])
            summary.append(["Research abstentions", sum(row["classification"] == "ABSTAIN" for row in research["forecasts"])])
            summary.append(["Ranked research candidates", sum(row["status"] == "RESEARCH_CANDIDATE" for row in research.get("opportunities", []))])
            entries = research.get("entry_candidates", [])
            summary.append(["Research entry observations", len(entries)])
            summary.append(["Research position reviews", len(management)])
            visible = sorted((item for item in entries if item.get("zone") and item.get("score") is not None),
                             key=lambda item: (-item["score"], item["security_id"], item["horizon_sessions"]))[:10]
            if visible:
                summary.append(["Research-only entry", "Candidate action", "Zone low", "Zone high", "Invalidation",
                                "Horizon sessions", "Forecast upside", "Forecast downside", "Reward to risk", "Reason"])
                for item in visible:
                    summary.append([item.get("ticker") or item["security_id"], item["entry_action"], *item["zone"],
                                    item["invalidation"], item["horizon_sessions"], item["forecast_upside"],
                                    item["forecast_downside"], item["reward_to_risk"], item["reason"]])
                    for col in (7, 8):
                        summary.cell(summary.max_row, col).number_format = "0.00%"
                    for col in (3, 4, 5):
                        summary.cell(summary.max_row, col).number_format = '"₹"#,##0.00' if market == "india" else '"$"#,##0.00'
                summary.column_dimensions["J"].width = 65
        universe_path = contained(work, Path("usa/reports/universe.json" if market == "usa" else
                                            "reports/context/security_master_india.json"))
        if universe_path.is_file():
            security = _json(universe_path)
            master = security.get("security_master", {}) if market == "usa" else security
            summary.append(["Universe", security.get("active_universe", security.get("policy"))])
            summary.append(["Universe reference observation", master.get("observation_utc")])
            summary.append(["Universe reference status", master.get("source_status")])
            if "held_outside_configured" in master:
                summary.append(["Held outside current membership", len(master["held_outside_configured"])])
        summary.freeze_panes = "B2"
        summary.column_dimensions["A"].width = 34
        summary.column_dimensions["B"].width = 24
        from openpyxl.styles import Font
        summary["A1"].font = summary["B1"].font = Font(bold=True)
        with BytesIO() as stream:
            workbook.save(stream)
            _atomic(context["output"], "shadow.xlsx", stream.getvalue())
    finally:
        workbook.close()


def _certify(context):
    from math import isclose, isfinite
    from openpyxl import load_workbook
    import yaml
    from backend.delivery.lifecycle.canonical_daily_lifecycle import blocking_freshness
    from backend.recommendation.ssot.guard import verify_published

    market, work = context["market"], context["work"]
    book = contained(work, BOOK)
    if (context.get("simulator_book_sha256") or context.get("simulator_ready")) and (
            not book.is_file() or _json(book).get("session") != context["session"]
            or digest(book) != context.get("simulator_ready")):
        raise ValueError("enabled shadow simulator did not close the completed session")
    reports = "reports" if market == "india" else "usa/reports"
    lifecycle = _json(contained(work, Path(f"reports/context/canonical_lifecycle_{market}.json")))
    if (lifecycle.get("market"), lifecycle.get("asof"), lifecycle.get("market_data_asof")) != (
            market, context["asof"], context["session"]):
        raise ValueError("lifecycle dates disagree with completed session")
    if gaps := blocking_freshness(lifecycle["input_freshness"]):
        raise ValueError(f"required lifecycle inputs are stale: {', '.join(gaps)}")
    risk = _json(contained(work, Path(f"reports/context/dynamic_risk_{market}.json")))
    if (risk.get("market"), risk.get("asof")) != (market, context["asof"]):
        raise ValueError("dynamic risk disagrees with run market or date")
    current, exits = lifecycle["current"], lifecycle["exits"]
    tracked = position_history(work, market, context["session"])["positions"]
    position_ids = [row.get("position_id") for row in current]
    if not current or not all(position_ids) or len(set(position_ids)) != len(position_ids):
        raise ValueError("CURRENT must hold distinct, traceable positions")
    if set(tracked) != set(position_ids):
        raise ValueError("daily position history coverage disagrees with CURRENT")
    if violations := [pid for pid, row in tracked.items() if row["monotonic_violation"]]:
        raise ValueError(f"authorized monotonic stop policy violated for {', '.join(violations)}")
    for row in current:
        price_session = row.get("market_data_asof")
        if price_session != context["session"]:
            raise ValueError(f"CURRENT price session mismatch: {row.get('ticker')}")
        for field in ("entry_price", "current_price", "stop", "target"):
            price = row.get(field)
            if price is None and (field == "target" or (field == "stop" and row.get("engine") != "R2")):
                continue
            if type(price) not in (int, float) or not isfinite(price) or price <= 0:
                raise ValueError(f"invalid {field} for {row.get('ticker')}")
    valid_ssot, evidence = verify_published(work, market, context["asof"])
    if not valid_ssot:
        raise ValueError(f"sealed recommendation output failed validation: {evidence}")
    exit_audit = _json(contained(work, Path(
        f"reports/audit/dynamic_exit_decisions_{market}_{context['asof']}.json")))
    if (exit_audit.get("market"), exit_audit.get("asof")) != (market, context["asof"]):
        raise ValueError("exit decisions disagree with run market or date")
    if any(row.get("action") == "SKIP" for row in exit_audit["decisions"]):
        raise ValueError("held-position exit evaluation contains unresolved skips")
    if risk.get("schema") == "aegis.shadow.effective_risk.v1":
        if risk.get("calculation_session") != context["session"] or risk.get("unavailable"):
            raise ValueError("point-in-time stop evidence is incomplete")
        stops = {row["opportunity_id"]: row["new_stop"] for row in risk["updates"]}
        evaluations = {row["opportunity_id"]: row for row in exit_audit["decisions"]}
        for row in current:
            if row.get("engine") == "R2":
                pid = row["position_id"]
                if row["stop"] != stops.get(pid) or row["stop"] != evaluations.get(pid, {}).get("stop_price"):
                    raise ValueError(f"exit evaluator and report disagree on the stop for {pid}")
    backend = _json(contained(work, Path(f"{reports}/backend_validation_summary.json")))
    if backend.get("verdict") != "PASS" or backend.get("counts", {}).get("FAIL") != 0:
        raise ValueError("backend datasets did not pass")
    if market == "usa" and _json(contained(work, Path(reports) / "ops_check.json")).get("verdict") != "HEALTHY":
        raise ValueError("USA operations check did not pass")
    portfolio = _json(contained(work, Path(f"{reports}/portfolio_v3.json")))
    snapshot = portfolio["snapshot"]
    if any((document.get("market"), document.get("asof")) != (market, context["asof"])
           for document in (portfolio, snapshot)):
        raise ValueError("portfolio market or date disagrees")
    weights = [row["weight"] for row in snapshot["positions"]]
    symbols = [row["ticker"] for row in snapshot["positions"]]
    gross, net = sum(map(abs, weights)), sum(weights)
    reserve = snapshot["cash_reserve_target"]
    config = yaml.safe_load(contained(work, Path("configs/risk_budget.yaml")).read_text(encoding="utf-8"))
    budget = config["market_defaults"][market]
    sectors = {}
    for row in snapshot["positions"]:
        sector = row.get("sector")
        if sector and sector not in {"Unknown", "UNKNOWN"}:
            sectors[sector] = sectors.get(sector, 0.0) + abs(row["weight"])
    if (not isfinite(gross) or not 0 <= reserve <= 1 or len(set(symbols)) != len(symbols)
            or snapshot.get("n_positions") != len(symbols)
            or (not budget["enable_shorts"] and any(weight < 0 for weight in weights))
            or any(abs(weight) > budget["per_ticker_cap"] + 1e-5 for weight in weights)
            or any(weight > budget["per_sector_cap"] + 1e-5 for weight in sectors.values())
            or not isclose(net, snapshot["total_weight"], abs_tol=1e-5)
            or gross > 1 - reserve + 1e-5
            or not isclose(snapshot["cash_pct"] + gross, 1.0, abs_tol=1e-5)):
        raise ValueError("portfolio exposure or cash violates its contract")
    workbook_path = contained(context["output"], Path("shadow.xlsx"))
    checksum = digest(workbook_path)
    workbook = load_workbook(workbook_path, read_only=True)
    try:
        if workbook.sheetnames != SHEETS:
            raise ValueError("workbook sheet contract failed")
        for sheet, header, rows in zip(workbook.worksheets[1:], (7, 4), (current, exits)):
            if not str(sheet["A1"].value).startswith("SHADOW | "):
                raise ValueError(f"workbook is missing its shadow label: {sheet.title}")
            headings = next(sheet.iter_rows(min_row=header, max_row=header, values_only=True))
            identity = headings.index("Position ID")
            pnl = headings.index("P&L %")
            actual = sheet.iter_rows(min_row=header + 1, max_row=header + len(rows), values_only=True)
            for cells, row in zip(actual, rows, strict=True):
                if cells[identity] != (row.get("position_id") or None):
                    raise ValueError(f"workbook position identity disagrees with lifecycle: {sheet.title}")
                expected = row.get("pnl_pct" if header == 7 else "realized_pnl_pct")
                if isinstance(expected, (int, float)) and (
                        type(cells[pnl]) not in (int, float) or not isclose(cells[pnl], expected / 100, abs_tol=1e-12)):
                    raise ValueError(f"workbook P&L disagrees with lifecycle: {sheet.title}")
    finally:
        workbook.close()
    if digest(workbook_path) != checksum:
        raise ValueError("shadow workbook changed during certification")
    context["workbook_sha256"] = checksum


def _verify_history(context):
    state = _files(context["work"], context["market"])
    context["attempt"].validate_history(state)
    context["history_state"] = state
    if context["market"] == "india":
        validate_held_actions(context["baseline"], context["work"], context["asof"])


def _plan(root, market, asof, *, bindings=None):
    source = root / ("scripts/aegis_daily_v2.py" if market == "india" else "usa/scripts/usa_daily.py")
    inventory = list(_inventory(source, market))
    stages = []
    frontier = ()

    def bind(binding, dependencies=None):
        nonlocal frontier
        deps = frontier if dependencies is None else dependencies
        stages.append(_binding_stage(binding, deps))
        if bindings is not None:
            bindings[binding.name] = binding
        if binding.required:
            frontier = (binding.name,)

    def stage(name, action, dependencies=None):
        nonlocal frontier
        stages.append(Stage(name, action, frontier if dependencies is None else dependencies))
        frontier = (name,)

    def lifecycle():
        bind(Binding("registry", ("-m", "backend.delivery.lifecycle.registry_materializer", "--market", market,
                                  "--asof", asof),
                     outputs=(f"reports/context/registry_materialization_{market}.json",)),
             (*frontier, "session_checkpoint", "history_recovery"))
        bind(Binding("dynamic_risk", ("-m", "scripts.aegis_shadow.effective_risk", "risk", market, asof),
                     outputs=(f"reports/context/dynamic_risk_{market}.json",)))
        bind(Binding("dynamic_exits", ("-m", "scripts.aegis_shadow.effective_risk", "exits", market, asof),
                     outputs=(f"reports/audit/dynamic_exit_decisions_{market}_{{asof}}.json",)))
        bind(Binding("canonical_lifecycle", ("-m", "backend.delivery.lifecycle.canonical_daily_lifecycle",
                                             "--market", market, "--asof", asof),
                     outputs=(f"reports/context/canonical_lifecycle_{market}.json",)))
        stage("recovery_provenance", annotate_lifecycle)
        stage("position_history", record_positions)

    def research_regime(price_stage):
        bind(Binding("research_market_regime", ("-m", "backend.research.mr_market_regime", "--market", market),
                     outputs=(f"reports/research/mr_market_regime_{market}.json",), required=False), (price_stage,))

    stage("session_checkpoint", _checkpoint)
    # Safe data collection can still run if the private lifecycle checkpoint
    # needs recovery evidence. Decision writers have an explicit dependency.
    frontier = ()
    if market == "india":
        bind(Binding("refresh_prices", ("india/refresh_data.py", "--reconcile-final-bars"),
                     outputs=("reports/context/india_price_availability.json",), check_update=False))
        bind(Binding("freshness", ("scripts/check_data_freshness.py",),
                     outputs=("reports/context/india_price_availability.json",), check_update=False))
        stages.append(Stage("history_recovery", _recover_gap, ("session_checkpoint",)))
        bind(Binding("market_cap", ("-m", "india.nse_market_cap"),
                     outputs=("india/reports/nse_market_cap/*.json",), required=False, check_update=False))
        bind(Binding("runner1", ("india/recommendation_generator.py",),
                     outputs=("reports/AEGIS_LATEST.xlsx",)))
    for binding in inventory:
        if market == "india" and binding.name == "aegis_r1_producer_audit":
            lifecycle()
        if market == "india" and binding.name == "multi_layer_stress_regime":
            research_regime("freshness")
        if binding.name == "recommendation_ssot":
            bind(binding, (*frontier, "session_checkpoint", "history_recovery"))
        elif market == "india" and binding.name in {"multi_layer_stress_regime", "multi_layer_crash_resilience"}:
            bind(binding, ("research_market_regime",))
        elif binding.name.startswith("ingest_"):
            if market == "usa":
                deps = ("build_universe",) if "usa/reports/universe.json" in binding.inputs else ()
            else:
                deps = ("refresh_prices",) if binding.name in {"ingest_fundamentals", "ingest_corporate_actions"} else ()
            bind(binding, deps)
        else:
            bind(binding)
        if market == "usa" and binding.name == "refresh_market_data":
            stages.append(Stage("history_recovery", _recover_gap, ("session_checkpoint",)))

    if market == "usa":
        bind(Binding("feature_snapshot", ("scripts/ci_build_feature_snapshot.py", "--market", market,
                                          "--asof", asof),
                     outputs=(f"features/{market}/{{asof}}.parquet",)))
        bind(Binding("universe_selection", ("scripts/ci_universe_selection.py", "--market", market,
                                            "--strict", "--asof", asof),
                     outputs=("reports/universe/selection_applied_usa.json",)))
        lifecycle()
    # Apply the same measurement and rollup bindings to USA using its data.
    if market == "usa":
        research_regime("refresh_market_data")
        extra = {"multi_layer_momentum_ledger", "multi_layer_stress_regime", "multi_layer_crash_resilience",
                 "multi_layer_runner_usa", "multi_layer_forward_outcomes", "monthly_rollups", "r3_canonical_daily_shadow"}
        predecessors = {
            "multi_layer_momentum_ledger": "short_term_momentum_producer_usa",
            "multi_layer_stress_regime": "research_market_regime",
            "multi_layer_crash_resilience": "research_market_regime",
            "multi_layer_forward_outcomes": "multi_layer_momentum_ledger",
        }
        for binding in _inventory(root / "scripts/aegis_daily_v2.py", market):
            if binding.name in extra:
                dependency = predecessors.get(binding.name)
                if binding.name in {"multi_layer_stress_regime", "multi_layer_crash_resilience"}:
                    bind(binding, (dependency,))
                else:
                    bind(binding, (*frontier, dependency) if dependency else None)

    folder = f"reports/research/{market}"
    stages.append(Stage("open_episode_research", open_episode_research, ("position_history",), required=False))
    stages.append(Stage("closed_outcome_corpus", closed_outcomes, ("recovery_provenance",), required=False))
    stages.append(Stage("closed_outcome_learning", closed_learning, ("closed_outcome_corpus",), required=False))
    research_inputs = ("refresh_prices",) if market == "india" else ("build_universe", "refresh_market_data")
    stages.append(Stage("strategy_research", strategy_research, ("position_history", *research_inputs), required=False))
    stages.append(Stage("execution_accounting", execution_accounting, ("execution_simulator",), required=False))
    stages.append(Stage("simulated_orders", simulated_orders, ("portfolio_engine", "position_history"), required=False))
    bind(Binding("outcomes", ("scripts/build_outcome_dataset.py", f"--{market}-only"),
                 outputs=(f"{folder}/outcome_dataset_summary.json",)))
    bind(Binding("attribution", ("scripts/run_attribution.py", f"--{market}-only"),
                 outputs=(f"{folder}/attribution_analysis.json",)))
    reports = "reports" if market == "india" else "usa/reports"
    bind(Binding("backend_validation", (f"{market}/backend_validation/run.py",),
                 outputs=(f"{reports}/backend_validation_summary.json",)))
    if market == "usa":
        bind(Binding("ops_check", ("usa/scripts/usa_ops_check.py",),
                     outputs=("usa/reports/ops_check.json",)))
    required = tuple(item.name for item in stages if item.required)
    stage("history_integrity", _verify_history, ("position_history",))
    workbook_dependencies = ("history_integrity", "backend_validation")
    stage("workbook", _workbook, workbook_dependencies)
    stage("certify", _certify, (*required, "history_integrity", "workbook"))
    known = set()
    for item in stages:
        if item.name in known or not set(item.requires).issubset(known):
            raise ValueError(f"invalid dependency order or duplicate stage: {item.name}")
        known.add(item.name)
    if "session_checkpoint" not in known:
        raise ValueError("market inventory has no lifecycle binding")
    return tuple(stages)


def _report_state(work, market, checksums=None):
    if checksums is None:
        checksums = _files(work, market)
    state = {rel.as_posix(): value for rel, value in checksums.items()}
    for rel in (BOOK, Path(".shadow-recovery-result.json"), Path(".shadow-position-history.json"),
                Path(f"reports/research/intelligence/{market}/strategy_research.json"),
                Path(f"reports/research/intelligence/{market}/prepared_panel.json"),
                Path(f"reports/research/{market}/outcome_dataset_summary.json"),
                Path(f"reports/research/{market}/attribution_analysis.json")):
        path = contained(work, rel)
        if path.is_file():
            state[rel.as_posix()] = digest(path)
    return state


def _certification_state(work, market, asof):
    reports = "reports" if market == "india" else "usa/reports"
    paths = [f"{reports}/backend_validation_summary.json", f"{reports}/portfolio_v3.json",
             f"reports/research/intelligence/{market}/prepared_panel.json",
             f"{reports}/recommendations.json", f"{reports}/recommendations_history/{market}/{asof}.json",
             "reports/context/ssot_health.json", f"reports/context/dynamic_risk_{market}.json",
             f"reports/audit/dynamic_exit_decisions_{market}_{asof}.json"]
    if market == "usa":
        paths.extend(("usa/reports/ops_check.json", "usa/reports/universe.json"))
    else:
        paths.append("reports/context/security_master_india.json")
    return {name: digest(path) if (path := contained(work, Path(name))).is_file() else None for name in paths}


def _retain_run_evidence(context, summary):
    work, market, asof = (context[key] for key in ("work", "market", "asof"))
    bindings = {}
    _plan(work, market, asof, bindings=bindings)
    names = {"build_universe", "refresh_prices", "refresh_market_data", "ingest_fundamentals",
             "ingest_corporate_actions", "market_intelligence", "feature_snapshot", "feature_store",
             "feature_intelligence", "recommendation_ssot", "dynamic_risk", "dynamic_exits",
             "canonical_lifecycle", "risk_engine", "portfolio_engine", "execution_simulator",
             "outcomes", "attribution", "research_market_regime", "backend_validation", "ops_check"}
    contracts = {name: bindings[name].outputs for name in names & bindings.keys()}
    contracts["position_history"] = (".shadow-position-history.json",)
    contracts["open_episode_research"] = (f"reports/research/{market}/shadow_open_episode_research.json",)
    contracts["simulated_orders"] = (f"reports/research/{market}/shadow_simulated_orders.json",)
    contracts["closed_outcome_corpus"] = (f"reports/research/{market}/shadow_closed_corpus.json",)
    contracts["closed_outcome_learning"] = (f"reports/research/{market}/shadow_closed_learning.json",)
    contracts["strategy_research"] = (f"reports/research/intelligence/{market}/strategy_research.json",
                                      f"reports/research/intelligence/{market}/prepared_panel.json",
                                      f"reports/research/intelligence/{market}/management_history/{context['session']}/*.json")
    artifacts = {name: _artifacts(work, patterns, asof) for name, patterns in contracts.items()
                 if summary["stages"].get(name, {}).get("status") == "PASS"}
    if "simulated_orders" in artifacts and (book := contained(work, BOOK)).is_file():
        artifacts["simulated_orders"].add(book)
    if "position_history" in artifacts:
        history = position_history(work, market, context["session"])
        artifacts["position_history"].add(contained(work, Path(history["observation_path"])))
    return retain_evidence(context["storage"], work, summary, artifacts)


def _deliver(root, publication):
    try:
        return notify(root, publication), None
    except Exception as error:
        return "DELIVERY_FAILURE", type(error).__name__


def _resume_report(root, private, receipt_path, live, saved, market, asof, session, prior_workbook, *, max_age=None):
    if not receipt_path.is_file():
        return None
    try:
        receipt = _json(receipt_path)
        if refresh_due(max_age, receipt.get("prepared_utc"), datetime.now(timezone.utc)):
            return None
        if (receipt.get("market"), receipt.get("asof"), receipt.get("session"),
                receipt.get("dependencies")) != (market, asof, session, live):
            return None
        rel = Path(receipt["workspace"])
        if len(rel.parts) != 2 or rel.name != "work":
            return None
        work = contained(private, rel)
        accepted = receipt["workspace"] == saved.get("workspace")
        if accepted and prior_workbook and prior_workbook["sha256"] == saved.get("workbook_sha256"):
            return None
        if not accepted and receipt.get("baseline_workspace") != saved.get("workspace"):
            return None
        # A first attempt is seeded from live lifecycle state. Its original
        # history proof is reusable only while those protected files agree.
        if not accepted and not saved:
            for name, checksum in receipt["bootstrap_state"].items():
                path = contained(root, Path(name))
                if not path.is_file() or digest(path) != checksum:
                    return None
        if receipt["state"] != _report_state(work, market):
            return None
        if receipt["private_source"] != dependencies(work, market)["source_config"]:
            return None
        stages = _plan(work, market, asof)
        results = receipt["stages"]
        if set(results) != {stage.name for stage in stages[:-2]} or any(
                results[stage.name]["status"] != "PASS" for stage in stages[:-2] if stage.required):
            return None
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"{market} retained report checkpoint rejected | {error}", flush=True)
        return None
    output = Path(mkdtemp(prefix="report-", dir=work.parent))
    context = dict(receipt["report_context"], market=market, asof=asof, session=session, work=work,
                   output=output, mode="REPORT_ONLY" if accepted else "RESUME")
    return context, stages, results


def _compute_report_inputs(root, private, baseline, live, saved, protected, market, asof, session, prior, calendar, force):
    before = {path: digest(artifact) for path in protected
              if (artifact := contained(baseline, path)).is_file()}
    attempt = Attempt(baseline, private, market, asof)
    work = attempt.workspace
    for path, expected in before.items():
        if any(digest(contained(source, path)) != expected for source in (baseline, work)):
            raise ValueError(f"bootstrap source changed while it was being copied: {path}")
    if baseline != root:
        sync_dependencies(root, work, market, live, saved.get("dependencies", {}), session=session)
    authority = contained(root, Path(".aegis-local/unified/inputs") / market / "exit_authority.json")
    evidence = authority.read_bytes() if authority.is_file() else json.dumps({
        "schema": "aegis.shadow.exit_authority.v1", "market": market, "targets": []}).encode()
    _atomic(work, ".shadow-exit-authority.json", evidence)
    intervals = contained(root, Path(".aegis-local/unified/inputs") / market / "risk_intervals.json")
    private_intervals = contained(work, Path(".shadow-risk-intervals.json"))
    if intervals.is_file():
        _atomic(work, private_intervals.name, intervals.read_bytes())
    elif private_intervals.is_file():
        _atomic(work, private_intervals.name, json.dumps({
            "schema": "aegis.shadow.risk_intervals.v1", "market": market, "intervals": [],
        }).encode())
    stages = _plan(work, market, asof)
    output = attempt.folder
    logs = contained(output, Path("logs"))
    logs.mkdir()
    context = {"market": market, "asof": asof, "work": work, "baseline": baseline,
               "output": output, "attempt": attempt, "logs": logs, "storage": private.parent.parent,
               "session": session, "calendar": calendar, "force": force,
               "worker_retry": worker_retry(root, market),
               "sandbox": launcher(),
               "provider_policy": provider_policy(root, market),
               "mode": "FULL", "previous_workbook": prior and prior["workbook"],
               "simulator_book_sha256": saved.get("simulator_book_sha256"),
               "env": _worker_env(work)}
    lifecycle = contained(work, Path(f"reports/context/canonical_lifecycle_{market}.json"))
    if lifecycle.is_file():
        context["previous_session"] = _json(lifecycle).get("market_data_asof")
    print(f"{market} isolated workspace {work.relative_to(root)}", flush=True)
    results = _execute(context, stages[:-2])
    if all(results[stage.name]["status"] == "PASS" for stage in stages[:-2] if stage.required):
        receipt = {
            "market": market, "asof": asof, "session": session, "dependencies": live,
            "prepared_utc": datetime.now(timezone.utc).isoformat(),
            "workspace": work.relative_to(private).as_posix(), "baseline_workspace": saved.get("workspace"),
            "bootstrap_state": {rel.as_posix(): checksum for rel, checksum in before.items()},
            "private_source": dependencies(work, market)["source_config"],
            "state": _report_state(work, market, context["history_state"]), "stages": results,
            "report_context": {key: context[key] for key in (
                "previous_workbook", "previous_session", "missed_sessions", "recovered_sessions", "recovered_events",
                "simulator_book_sha256", "simulator_ready"
            ) if key in context},
        }
        _atomic(private, "report-ready.json", json.dumps(receipt).encode())
    return context, stages, results


def _run_market(root, storage, market, *, force=False):
    from scripts.aegis_workbook_continuity import discover

    launcher()
    started = perf_counter()
    private = contained(storage, Path(market))
    private.mkdir(exist_ok=True)
    with _hold_lock(contained(private, Path("daily.lock")), market):
        def validate_pending(work, expected):
            if _report_state(work, market) != expected:
                raise ValueError("pending commit artifacts changed after certification")

        recovered_publication = finish_commit(root, private, market, validate_pending)
        if recovered_publication:
            print(f"{market} recovered interrupted publication {recovered_publication['workbook']}")
        prior_workbook = discover(root, market, "new")
        if prior_workbook:
            print(f"{market} last verified shadow workbook {prior_workbook['workbook']} "
                  f"(session {prior_workbook['market_data_asof']})")
        pointer = contained(private, Path("accepted.json"))
        baseline = root
        asof = date.today().isoformat()
        calendar = exchange_calendar(market, storage.parent)
        session = calendar.completed(datetime.now(timezone.utc)).isoformat()
        print(f"{market} new | completed session {session}", flush=True)
        live = dependencies(root, market)
        saved = {}
        protected = (REGISTRY, Path(f"reports/context/canonical_lifecycle_{market}.json"))
        if pointer.is_file():
            saved = _json(pointer)
            baseline = contained(private, Path(saved["workspace"]))
            if not baseline.is_dir():
                raise ValueError("accepted private workspace is missing")
            if any(not (path := contained(baseline, rel)).is_file()
                   or digest(path) != saved.get("state_sha256", {}).get(rel.as_posix())
                   for rel in protected):
                raise ValueError("accepted private lifecycle state disagrees with its checkpoint")
            if saved.get("simulator_book_sha256") and digest(contained(baseline, BOOK)) != saved["simulator_book_sha256"]:
                raise ValueError("accepted simulator book checksum mismatch")
        reasons = _reuse_blockers(saved, prior_workbook, live, asof, session, force)
        max_age = reuse_max_age(root, market)
        if prior_workbook and refresh_due(max_age, prior_workbook.get("published_utc"), datetime.now(timezone.utc)):
            reasons.append("configured market refresh is due")
        if not reasons and saved.get("certification_state") != _certification_state(baseline, market, asof):
            reasons.append("private certification inputs changed")
        if not reasons:
            try:
                position_history(baseline, market, session)
            except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
                reasons.append(f"private position history not verified ({error})")
        if not reasons:
            try:
                delivery = delivery_status(root, prior_workbook)
            except (KeyError, OSError, RuntimeError, TypeError, ValueError):
                delivery = "DELIVERY_FAILURE"
            mode = "DELIVERY_ONLY" if delivery in {"PENDING", "FAILED"} else "FAST_REUSE"
            print(f"{market} {mode} | {prior_workbook['workbook']}")
            delivery, _ = _deliver(root, prior_workbook)
            print(f"{market} stages executed=0 reused={saved['passed_stages']} "
                  f"| Telegram {delivery} | {perf_counter() - started:.2f}s", flush=True)
            return True
        ready = contained(private, Path("report-ready.json"))
        resume = None if force else _resume_report(root, private, ready, live, saved, market, asof, session,
                                                  prior_workbook, max_age=max_age)
        reused = 0
        if resume:
            context, stages, engine_results = resume
            reused = sum(result["status"] == "PASS" for result in engine_results.values())
            print(f"{market} {context['mode']} | retained engine outputs verified | {'; '.join(reasons)}", flush=True)
        else:
            print(f"{market} FULL | {'; '.join(reasons)}", flush=True)
            _atomic(private, ready.name, b"{}")
            context, stages, engine_results = _compute_report_inputs(
                root, private, baseline, live, saved, protected, market, asof, session, prior_workbook, calendar, force)
            reused = sum(result.get("execution") == "REUSED" for result in engine_results.values())
        output, work = context["output"], context["work"]
        context["storage"] = storage.parent
        context["calendar"] = calendar
        context["strategy_research_ready"] = engine_results.get("strategy_research", {}).get("status") == "PASS"
        context["reused_engines"] = reused
        context["executed_engines"] = 0 if resume else sum(
            result.get("execution") == "EXECUTED" for result in engine_results.values())
        results = _execute(context, stages[-2:], prior=engine_results)
        blocked = sum(result["status"] == "BLOCKED" for result in results.values())
        executed = sum(result.get("execution") == "EXECUTED" for result in (
            (results[stage.name] for stage in stages[-2:]) if resume else results.values()))
        elapsed = round(perf_counter() - started, 3)
        passed = results["certify"]["status"] == "PASS"
        if passed and (dependencies(root, market) != live or calendar.completed(datetime.now(timezone.utc)).isoformat() != session):
            passed = False
            results["certify"].update(status="FAIL", reason="live dependencies or completed session changed during run")
        if results["certify"]["status"] == "FAIL" or (resume and not passed):
            _atomic(private, ready.name, b"{}")
        incomplete = any(results[name]["status"] != "PASS" for name in ("session_checkpoint", "history_recovery"))
        any_evidence = any(result["status"] == "PASS" for name, result in results.items()
                           if name != "session_checkpoint")
        status = ("SHADOW_CERTIFIED" if passed else "SHADOW_INCOMPLETE" if incomplete else
                  "SHADOW_DEGRADED" if any_evidence else "SHADOW_FAILED")
        summary = {"market": market, "asof": asof, "market_data_asof": context.get("session"),
                   "mode": context["mode"], "status": status, "stages": results,
                   "workbook_sha256": context.get("workbook_sha256") if passed else None,
                   "executed_stages": executed, "reused_stages": reused,
                   "blocked_stages": blocked, "runtime_seconds": elapsed,
                   "previous_workbook": context.get("previous_workbook"),
                   "previous_session": context.get("previous_session"),
                   "missed_sessions": context.get("missed_sessions", []),
                   "recovered_sessions": context.get("recovered_sessions", [])}
        try:
            summary["historical_evidence"] = _retain_run_evidence(context, summary)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            summary["historical_evidence"] = {"error": str(error)}
        _atomic(output, "summary.json", json.dumps(summary, indent=2).encode())
        if "attempt" in context:
            context["attempt"].status(status, market_data_asof=session)
        if passed:
            state = {
                "workspace": work.relative_to(private).as_posix(),
                "market_data_asof": context["session"], "asof": asof,
                "market": market, "runner": "new", "schema": SCHEMA,
                "workbook_sha256": summary["workbook_sha256"],
                "simulator_book_sha256": context.get("simulator_ready"),
                "dependencies": live,
                "certification_state": _certification_state(work, market, asof),
                "passed_stages": sum(result["status"] == "PASS" for result in results.values()),
                "state_sha256": {rel.as_posix(): digest(contained(work, rel)) for rel in protected},
            }
            try:
                prepare_commit(private, work, output, state, _report_state(work, market))
                publication = finish_commit(root, private, market, validate_pending)
            except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
                summary.update(status="SHADOW_FAILED", publication_failure=str(error))
                _atomic(output, "summary.json", json.dumps(summary, indent=2).encode())
                if "attempt" in context:
                    context["attempt"].status("SHADOW_FAILED", market_data_asof=session)
                print(f"{market} PUBLICATION_FAILURE | {error}", flush=True)
                return False
            print(f"{market} workbook {publication['workbook']}")
            delivery, error = _deliver(root, publication)
            if error:
                summary["delivery_error"] = error
            summary["delivery"] = delivery
            _atomic(output, "summary.json", json.dumps(summary, indent=2).encode())
            print(f"{market} shadow Telegram {delivery}")
        print(f"{market} {status} | stages total={len(results)} executed={executed} "
              f"reused={reused} blocked={blocked} | {elapsed:.2f}s", flush=True)
        return passed


def _reuse_blockers(saved, publication, live, asof, session, force):
    reasons = []
    if force:
        reasons.append("forced recomputation")
    if not publication:
        reasons.append("no verified publication")
    elif any(saved.get(field) != publication.get(field) for field in ("runner", "market", "schema", "workbook")) or (
            publication.get("schema") != SCHEMA or saved.get("workbook_sha256") != publication.get("sha256")):
        reasons.append("publication differs from accepted checkpoint")
    if not publication or (saved.get("asof"), saved.get("market_data_asof"),
                           publication["asof"], publication["market_data_asof"]) != (asof, session, asof, session):
        reasons.append("report date or completed session differs")
    old = saved.get("dependencies", {})
    for group, current in live.items():
        previous = old.get(group, {})
        changed = sorted(name for name in current.keys() | previous.keys()
                         if current.get(name) != previous.get(name))
        if changed:
            suffix = f", plus {len(changed) - 4} more" if len(changed) > 4 else ""
            reasons.append(f"{group} changed ({', '.join(changed[:4])}{suffix})")
    if "passed_stages" not in saved or any(group not in old for group in live):
        reasons.append("accepted checkpoint has no versioned execution evidence")
    return reasons


def run_daily(root, markets, *, force=False):
    storage = contained(root, Path(".aegis-local/unified/daily"))
    storage.mkdir(parents=True, exist_ok=True)
    failed = False
    for market in markets:
        try:
            if not _run_market(root, storage, market, force=force):
                failed = True
        except Exception as error:
            print(f"{market} SHADOW_FAILED {error}", flush=True)
            failed = True
    return int(failed)
