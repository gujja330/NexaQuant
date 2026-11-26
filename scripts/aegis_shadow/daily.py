"""Independent daily orchestration for copied, guarded workspaces."""
import ast
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from scripts.aegis_local_state import Attempt, REGISTRY, _hold_lock, contained, digest, validate_held_actions
from scripts.aegis_shadow.pipeline import Stage, _atomic, _execute, _json
from scripts.aegis_shadow.publication import SHEETS, notify, publish


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
    "aegis_r1_producer_audit": "reports/audit/r1_producer_audit_{market}_{asof}.json",
    "r3_shadow": "reports/research/r3/shadow/summary_{market}.json",
}


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
                      not record.get("optional", False), record.get("timeout_s") or 900,
                      check_update=name != "recommendation_ssot")


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
    for pattern in binding.inputs:
        if not _artifacts(work, (pattern,), asof):
            raise ValueError(f"required artifact is absent: {pattern}")
    before = {pattern: _fingerprints(_artifacts(work, (pattern,), asof))
              for pattern in binding.outputs}
    command = [sys.executable, "-I", "-B", "-X", "utf8", str(work / "scripts/aegis_shadow/worker.py"),
               *binding.command]
    log = contained(context["logs"], Path(f"{binding.name}.log"))
    with log.open("xb") as stream:
        result = subprocess.run(command, cwd=work, env=context["env"], stdout=stream,
                                stderr=subprocess.STDOUT, timeout=binding.timeout)
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
    if not before:
        raise RuntimeError("engine completed without a verifiable output contract")


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
    from backend.research.evidence.trading_calendars import is_trading_day
    from scripts.check_data_freshness import NSE_HOLIDAYS_2026

    if previous > latest or latest.year != 2026 or previous.year != 2026:
        raise ValueError("checkpoint outside reviewed 2026 calendar coverage")
    gap = []
    for offset in range(1, (latest - previous).days):
        day = previous + timedelta(days=offset)
        is_session = (day.weekday() < 5 and day not in NSE_HOLIDAYS_2026) if market == "india" else (
            is_trading_day(day, "usa"))
        if is_session:
            gap.append(day.isoformat())
    return gap


def _completed_session(market):
    from backend.research.evidence.trading_calendars import completed_nyse_session
    from scripts.check_data_freshness import completed_nse_session

    now = datetime.now(timezone.utc)
    return completed_nse_session(now) if market == "india" else completed_nyse_session(now)


def _checkpoint(context):
    market = context["market"]
    latest = _completed_session(market)
    context["session"] = latest.isoformat()
    if not context.get("previous_session"):
        raise ValueError("no prior lifecycle checkpoint")
    previous = date.fromisoformat(context["previous_session"])
    gap = _missing_sessions(market, previous, latest)
    if gap:
        evidence = contained(context["storage"], Path("inputs") / market / "shadow_recovery.json")
        if not evidence.is_file():
            raise ValueError(f"historical risk evidence required for missed sessions: {', '.join(gap)}")
        _atomic(context["work"], ".shadow-recovery-input.json", evidence.read_bytes())
        _run_binding(context, Binding(
            "historical_risk_replay",
            ("-m", "scripts.aegis_shadow.recover_daily", market, previous.isoformat(), *gap),
            outputs=(".shadow-recovery-result.json",),
        ))


def _binding_stage(binding, dependencies=()):
    return Stage(binding.name, lambda context: _run_binding(context, binding),
                 dependencies, binding.required)


def _workbook(context):
    from io import BytesIO

    from backend.delivery.sheets.workbook_two import build_two_sheet_workbook

    report = build_two_sheet_workbook(context["work"], context["market"], context["asof"])
    workbook = report["workbook"]
    try:
        if report["lifecycle_stale"]:
            raise ValueError("workbook lifecycle is stale")
        for sheet in workbook.worksheets:
            sheet["A1"] = f"SHADOW | {sheet['A1'].value}"
        for sheet, name in zip(workbook.worksheets, SHEETS[1:]):
            sheet.title = name
        summary = workbook.create_sheet(SHEETS[0], 0)
        summary.append(["AEGIS NEW", "SHADOW"])
        summary.append(["Market", context["market"].upper()])
        summary.append(["Report date", context["asof"]])
        summary.append(["Completed market session", context["session"]])
        summary.append(["Previous lifecycle session", context.get("previous_session")])
        recovered = contained(context["work"], Path(".shadow-recovery-result.json"))
        if recovered.is_file():
            summary.append(["Simulated recovery events", len(_json(recovered)["events"])])
        summary.append(["CURRENT records", report["current_rows"]])
        summary.append(["EXIT HISTORY records", report["exit_rows"]])
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
    from backend.recommendation.ssot.guard import verify_published

    market, work = context["market"], context["work"]
    reports = "reports" if market == "india" else "usa/reports"
    lifecycle = _json(contained(work, Path(f"reports/context/canonical_lifecycle_{market}.json")))
    if lifecycle.get("asof") != context["asof"] or lifecycle.get("market_data_asof") != context["session"]:
        raise ValueError("lifecycle dates disagree with completed session")
    current, exits = lifecycle["current"], lifecycle["exits"]
    position_ids = [row.get("position_id") for row in current]
    if not current or not all(position_ids) or len(set(position_ids)) != len(position_ids):
        raise ValueError("CURRENT must hold distinct, traceable positions")
    for row in current:
        price_session = row.get("market_data_asof")
        if price_session != context["session"]:
            raise ValueError(f"CURRENT price session mismatch: {row.get('ticker')}")
        for field in ("entry_price", "current_price", "stop", "target"):
            price = row.get(field)
            if price is None and field in ("stop", "target"):
                continue
            if not isinstance(price, (int, float)) or not isfinite(price) or price <= 0:
                raise ValueError(f"invalid {field} for {row.get('ticker')}")
    valid_ssot, evidence = verify_published(work, market, context["asof"])
    if not valid_ssot:
        raise ValueError(f"sealed recommendation output failed validation: {evidence}")
    exit_audit = _json(contained(work, Path(
        f"reports/audit/dynamic_exit_decisions_{market}_{context['asof']}.json")))
    if any(row.get("action") == "SKIP" for row in exit_audit["decisions"]):
        raise ValueError("held-position exit evaluation contains unresolved skips")
    backend = _json(contained(work, Path(f"{reports}/backend_validation_summary.json")))
    if backend.get("verdict") != "PASS" or backend.get("counts", {}).get("FAIL") != 0:
        raise ValueError("backend datasets did not pass")
    portfolio = _json(contained(work, Path(f"{reports}/portfolio_v3.json")))
    snapshot = portfolio["snapshot"]
    if portfolio.get("asof") != context["asof"]:
        raise ValueError("portfolio dates disagree")
    gross = sum(abs(r["weight"]) for r in snapshot["positions"])
    reserve = snapshot["cash_reserve_target"]
    if (not isfinite(gross) or not 0 <= reserve <= 1
            or gross > 1 - reserve + 1e-5
            or not isclose(snapshot["cash_pct"] + gross, 1.0, abs_tol=1e-5)):
        raise ValueError("portfolio exposure or cash violates its contract")
    context["attempt"].validate_history()
    if market == "india":
        validate_held_actions(context["baseline"], work, context["asof"])
    workbook = load_workbook(contained(context["output"], Path("shadow.xlsx")), read_only=True)
    try:
        if workbook.sheetnames != SHEETS:
            raise ValueError("workbook sheet contract failed")
        for sheet, expected in zip(workbook.worksheets[1:], (len(current), len(exits))):
            if not str(sheet["A1"].value).startswith("SHADOW | "):
                raise ValueError(f"workbook is missing its shadow label: {sheet.title}")
            if sheet.max_row is None or sheet.max_row <= expected:
                raise ValueError(f"workbook sheet dimensions cannot hold lifecycle rows: {sheet.title}")
    finally:
        workbook.close()


def _plan(root, market, asof):
    source = root / ("scripts/aegis_daily_v2.py" if market == "india" else "usa/scripts/usa_daily.py")
    inventory = list(_inventory(source, market))
    stages = []
    frontier = ()

    def bind(binding, dependencies=None):
        nonlocal frontier
        deps = frontier if dependencies is None else dependencies
        stages.append(_binding_stage(binding, deps))
        if binding.required:
            frontier = (binding.name,)

    def stage(name, action, dependencies=None):
        nonlocal frontier
        stages.append(Stage(name, action, frontier if dependencies is None else dependencies))
        frontier = (name,)

    def lifecycle():
        nonlocal frontier
        recommendation_ready = frontier
        stage("session_checkpoint", _checkpoint, ())
        bind(Binding("registry", ("-m", "backend.delivery.lifecycle.registry_materializer", "--market", market,
                                  "--asof", asof),
                     outputs=(f"reports/context/registry_materialization_{market}.json",)),
             (*recommendation_ready, "session_checkpoint"))
        bind(Binding("dynamic_risk", ("scripts/run_dynamic_risk_v2.py", "--market", market, "--asof", asof),
                     outputs=(f"reports/context/dynamic_risk_{market}.json",)))
        bind(Binding("dynamic_exits", ("scripts/apply_dynamic_exits.py", "--market", market, "--asof", asof,
                                        "--enforce"),
                     outputs=(f"reports/audit/dynamic_exit_decisions_{market}_{{asof}}.json",)))
        bind(Binding("canonical_lifecycle", ("-m", "backend.delivery.lifecycle.canonical_daily_lifecycle",
                                             "--market", market, "--asof", asof),
                     outputs=(f"reports/context/canonical_lifecycle_{market}.json",)))

    if market == "india":
        bind(Binding("refresh_prices", ("india/refresh_data.py", "--reconcile-final-bars"),
                     outputs=("reports/context/india_price_availability.json",), check_update=False))
        bind(Binding("freshness", ("scripts/check_data_freshness.py",),
                     outputs=("reports/context/india_price_availability.json",), check_update=False))
        bind(Binding("market_cap", ("-m", "india.nse_market_cap"),
                     outputs=("india/reports/nse_market_cap/*.json",), required=False, check_update=False))
        bind(Binding("runner1", ("india/recommendation_generator.py",),
                     outputs=("reports/AEGIS_LATEST.xlsx",)))
    for binding in inventory:
        if market == "india" and binding.name == "aegis_r1_producer_audit":
            lifecycle()
        bind(binding)

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
        extra = {"multi_layer_forward_outcomes", "monthly_rollups", "r3_canonical_daily_shadow"}
        for binding in _inventory(root / "scripts/aegis_daily_v2.py", market):
            if binding.name in extra:
                bind(binding)

    folder = f"reports/research/{market}"
    bind(Binding("outcomes", ("scripts/build_outcome_dataset.py", f"--{market}-only"),
                 outputs=(f"{folder}/outcome_dataset_summary.json",)))
    bind(Binding("attribution", ("scripts/run_attribution.py", f"--{market}-only"),
                 outputs=(f"{folder}/attribution_analysis.json",)))
    stage("workbook", _workbook)
    reports = "reports" if market == "india" else "usa/reports"
    bind(Binding("backend_validation", (f"{market}/backend_validation/run.py",),
                 outputs=(f"{reports}/backend_validation_summary.json",)))
    if market == "usa":
        bind(Binding("ops_check", ("usa/scripts/usa_ops_check.py",),
                     outputs=("usa/reports/ops_check.json",)))
    stage("certify", _certify)
    known = set()
    for item in stages:
        if item.name in known or not set(item.requires).issubset(known):
            raise ValueError(f"invalid dependency order or duplicate stage: {item.name}")
        known.add(item.name)
    if "session_checkpoint" not in known:
        raise ValueError("market inventory has no lifecycle binding")
    return tuple(stages)


def _run_market(root, storage, market, *, force=False):
    from scripts.aegis_workbook_continuity import discover

    private = contained(storage, Path(market))
    private.mkdir(exist_ok=True)
    with _hold_lock(contained(private, Path("daily.lock")), market):
        prior_workbook = discover(root, market, "new")
        if prior_workbook:
            print(f"{market} last verified shadow workbook {prior_workbook['workbook']} "
                  f"(session {prior_workbook['market_data_asof']})")
        pointer = contained(private, Path("accepted.json"))
        baseline = root
        asof = date.today().isoformat()
        protected = (REGISTRY, Path(f"reports/context/canonical_lifecycle_{market}.json"))
        if pointer.is_file():
            saved = _json(pointer)
            baseline = contained(private, Path(saved["workspace"]))
            if (not force and prior_workbook and saved.get("asof") == prior_workbook["asof"] == asof
                    and saved.get("market_data_asof") == prior_workbook["market_data_asof"]
                    == _completed_session(market).isoformat()
                    and saved.get("workbook_sha256") == prior_workbook["sha256"]
                    and all((path := contained(baseline, rel)).is_file()
                            and digest(path) == saved.get("state_sha256", {}).get(rel.as_posix())
                            for rel in protected)):
                print(f"{market} reusing verified shadow workbook {prior_workbook['workbook']}")
                print(f"{market} shadow Telegram {notify(root, prior_workbook)}")
                return True
        before = {path: digest(artifact) for path in protected
                  if (artifact := contained(baseline, path)).is_file()}
        attempt = Attempt(baseline, private, market, asof)
        for path, expected in before.items():
            if any(digest(contained(source, path)) != expected for source in (baseline, attempt.workspace)):
                raise ValueError(f"bootstrap source changed while it was being copied: {path}")
        stages = _plan(attempt.workspace, market, asof)
        output = attempt.folder
        logs = contained(output, Path("logs"))
        logs.mkdir()
        context = {"market": market, "asof": asof, "work": attempt.workspace,
                   "baseline": baseline, "output": output, "attempt": attempt, "logs": logs,
                   "storage": storage.parent,
                   "env": _worker_env(attempt.workspace)}
        baseline_lifecycle = contained(attempt.workspace, Path(f"reports/context/canonical_lifecycle_{market}.json"))
        if baseline_lifecycle.is_file():
            context["previous_session"] = _json(baseline_lifecycle).get("market_data_asof")
        print(f"{market} isolated workspace {attempt.workspace.relative_to(root)}", flush=True)
        results = _execute(context, stages)
        passed = results["certify"]["status"] == "PASS"
        incomplete = results["session_checkpoint"]["status"] != "PASS"
        status = "SHADOW_CERTIFIED" if passed else ("SHADOW_INCOMPLETE" if incomplete else "SHADOW_FAILED")
        summary = {"market": market, "asof": asof, "market_data_asof": context.get("session"),
                   "mode": "SHADOW", "status": status, "stages": results}
        _atomic(output, "summary.json", json.dumps(summary, indent=2).encode())
        attempt.status(status, market_data_asof=context.get("session"))
        if passed:
            publication = publish(root, output, summary)
            _atomic(private, pointer.name, json.dumps({
                "workspace": attempt.workspace.relative_to(private).as_posix(),
                "market_data_asof": context["session"], "asof": asof,
                "workbook_sha256": publication["sha256"],
                "state_sha256": {rel.as_posix(): digest(contained(attempt.workspace, rel))
                                 for rel in protected},
            }).encode())
            print(f"{market} workbook {publication['workbook']}")
            print(f"{market} shadow Telegram {notify(root, publication)}")
        print(f"{market} {status}", flush=True)
        return passed


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
