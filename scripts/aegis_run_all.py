"""Run the local AEGIS pipeline for India, USA, or both markets."""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import date as _date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


_ROOT = Path(__file__).resolve().parents[1]
_PYTHON = sys.executable
sys.path.insert(0, str(_ROOT))

from scripts.aegis_local_state import (
    Attempt, RunInProgress, contained, digest, locked, note_operation, recover,
    require_clean_publication_state, state_root, validate_held_actions,
)
from backend.shared.out_root import subprocess_env


def _run(cmd: list[str], *, cwd: Path = _ROOT, timeout: int = 5400,
         receipt: dict | None = None) -> tuple[bool, float]:
    """Run a subprocess · stream output live · return (ok, elapsed_seconds)."""
    env = subprocess_env(cwd)
    env["PYTHONPATH"] = str(cwd)
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    runtime = state_root(cwd) if cwd == _ROOT else cwd
    runtime.mkdir(exist_ok=True)
    temporary = contained(runtime, Path(".aegis-tmp"))
    temporary.mkdir(exist_ok=True)
    env.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    if cwd != _ROOT:
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
            env.pop(key, None)
        env["GIT_CEILING_DIRECTORIES"] = str(cwd.parent)
    for key in list(env):
        if key.startswith(("TELEGRAM_", "GITHUB_")) or key in {"SEND_FORCE_STALE", "PRICE_GUARD_OVERRIDE", "AEGIS_ALLOW_STALE"}:
            env.pop(key)
    credentials = _ROOT / ".env.angel"
    if credentials.is_file():
        for line in credentials.read_text(encoding="utf-8-sig").splitlines():
            key, _, value = line.partition("=")
            if key.strip().startswith("ANGEL_"):
                env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    print(f"  $ {' '.join(cmd)}")
    t0 = time.time()
    try:
        result = subprocess.run(cmd, cwd=str(cwd), env=env, check=False, timeout=timeout)
        ok = result.returncode == 0
        if receipt is not None:
            receipt["returncode"] = result.returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"  [failed] {error}")
        if receipt is not None:
            receipt["error"] = str(error)
        ok = False
    return ok, time.time() - t0


def _complete_delivery(market: str, asof: str, storage: Path, attempt_folder: Path,
                       details: dict) -> dict:
    from backend.shared.atomic_io import write_text_atomic
    from scripts.telegram_command_center_send import send_certified_workbook

    dated = _ROOT / "reports" / "telegram" / f"aegis_{market}_{asof}.xlsx"
    receipt = send_certified_workbook(market, asof, dated, details["sha256"], storage)
    print(f"  Telegram {market}: verified message {receipt['message_id']} · {dated}")
    details.update(status="delivered", telegram=receipt)
    write_text_atomic(attempt_folder / "attempt.json", json.dumps(details, indent=2) + "\n")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                       description=__doc__)
    ap.add_argument("--market", choices=["india", "usa", "both"], required=True,
                    help="run and deliver the certified daily report for the selected market(s)")
    ap.add_argument("--skip-refresh", action="store_true", help="skip standalone India refresh (USA refresh is part of USA daily)")
    ap.add_argument("--skip-regen", action="store_true", help="reuse existing recommendations and SSoT artifacts")
    ap.add_argument("--skip-xlsx", action="store_true", help="skip workbook generation and retain staged outputs only")
    ap.add_argument("--skip-research", action="store_true", help="skip shared P0 and P1 research refresh")
    delivery = ap.add_mutually_exclusive_group()
    delivery.add_argument("--send", action="store_true", help=argparse.SUPPRESS)
    delivery.add_argument("--dry-run", action="store_true",
                       help="build and validate workbooks in staging")
    delivery.add_argument("--no-send", action="store_true",
                          help="publish certified local outputs without Telegram delivery")
    ap.add_argument("--preview-only", action="store_true",
                       help="preview the Telegram message without running the pipeline")
    ap.add_argument("--stage-only", action="store_true", help="validate in isolation and retain staged outputs")
    ap.add_argument("--force-rerun", action="store_true", help="recompute instead of reusing a verified report")
    ap.add_argument("--repeat-from-run", metavar="RUN_ID",
                    help="stage an India repeat from a completed same-day staged run")
    ap.add_argument("--recover-only", action="store_true", help="finish recovery from interrupted publication")
    ap.add_argument("--force-stale", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--asof", default=_date.today().isoformat(),
                       help="execution date (only the current date is supported)")
    ap.add_argument("--open-xlsx", action="store_true",
                       help="open the XLSX in Excel when done (Windows only)")
    args = ap.parse_args()
    isolated = args.stage_only or args.dry_run
    if isolated and args.recover_only:
        ap.error("--recover-only cannot be combined with isolation flags")
    if args.force_stale:
        ap.error("stale workbooks cannot be delivered")
    if args.repeat_from_run and (
        not args.stage_only or args.market != "india" or args.preview_only or args.skip_regen
        or args.skip_refresh or args.skip_xlsx or args.skip_research or args.recover_only
    ):
        ap.error("--repeat-from-run requires a complete India-only --stage-only run")
    if args.asof != _date.today().isoformat():
        ap.error("the live pipeline only supports today's date")

    markets = ["india", "usa"] if args.market == "both" else [args.market]
    results: list[tuple[str, str, float]] = []
    attempts: dict[Path, Attempt] = {}

    def run_stage(name: str, command: list[str], *, cwd: Path = _ROOT, ready: bool = True) -> bool:
        cmd = [_PYTHON, *command]
        receipt = {"command": cmd, "returncode": None}
        if ready and cwd in attempts:
            note_operation(attempts[cwd].storage, name)
        ok, elapsed = _run(cmd, cwd=cwd, receipt=receipt) if ready else (False, 0.0)
        status = ("PASS" if ok else "FAIL") if ready else "BLOCKED"
        results.append((name, status, elapsed))
        if cwd in attempts:
            attempts[cwd].record_stage(name, status, elapsed, **receipt)
        return ok

    def run_market(market: str, attempt: Attempt) -> bool:
        print(f"\nAEGIS {market.upper()} | asof={args.asof}", flush=True)
        cwd = attempt.workspace
        ready = True
        if market == "india" and not args.skip_refresh:
            ready = run_stage("refresh:india", ["india/refresh_data.py", "--reconcile-final-bars"], cwd=cwd)
            ready = run_stage("freshness:india", ["scripts/check_data_freshness.py"], cwd=cwd, ready=ready)
            ready = run_stage("market-cap:india", ["-m", "india.nse_market_cap"], cwd=cwd, ready=ready)
        if not args.skip_regen:
            if market == "india":
                ready = run_stage("regen:india:R1", ["india/recommendation_generator.py"], cwd=cwd, ready=ready)
                ready = run_stage("regen:india:v2", [
                    "scripts/aegis_daily_v2.py", "--continue", "--strict-local-exit",
                    "--india-only-registry", "--two-sheet-local",
                ], cwd=cwd, ready=ready)
                ready = run_stage("backend-final:india", [
                    "india/backend_validation/run.py",
                ], cwd=cwd, ready=ready)
                ready = run_stage("artifacts:india", [
                    "scripts/ci_artifact_integrity.py", "--market", "india",
                ], cwd=cwd, ready=ready)
            else:
                ready = run_stage("regen:usa", ["usa/scripts/usa_daily.py"], cwd=cwd, ready=ready)
                ready = run_stage("ops:usa", ["usa/scripts/usa_ops_check.py"], cwd=cwd, ready=ready)
                ready = run_stage("feature-snapshot:usa", [
                    "scripts/ci_build_feature_snapshot.py", "--market", "usa",
                ], cwd=cwd, ready=ready)
                ready = run_stage("universe-selection:usa", [
                    "scripts/ci_universe_selection.py", "--market", "usa", "--strict",
                ], cwd=cwd, ready=ready)
            ready = run_stage(f"ssot-verify:{market}", [
                "-m", "backend.recommendation.ssot.guard", "--market", market,
                "--asof", args.asof, "--verify-only",
            ], cwd=cwd, ready=ready)
            if market == "usa":
                ready = run_stage("registry:usa", [
                    "-m", "backend.delivery.lifecycle.registry_materializer", "--market", market,
                ], cwd=cwd, ready=ready)
                ready = run_stage("dynamic-risk:usa", [
                    "scripts/run_dynamic_risk_v2.py", "--market", market,
                ], cwd=cwd, ready=ready)
                ready = run_stage("dynamic-exits:usa", [
                    "scripts/apply_dynamic_exits.py", "--market", market, "--enforce",
                ], cwd=cwd, ready=ready)
            ready = run_stage(f"contract:{market}", [
                "-m", "backend.pipeline.contract.runner", "--market", market,
                "--asof", args.asof, "--trigger", "manual",
            ], cwd=cwd, ready=ready)
            ready = run_stage(f"self-heal:{market}", [
                "scripts/ci_selfheal_lifecycle.py", "--market", market, "--asof", args.asof,
            ], cwd=cwd, ready=ready)
        if not args.skip_xlsx:
            preflight = ["scripts/ci_delivery_preflight.py", "--market", market, "--asof", args.asof]
            if not args.skip_regen:
                ready = run_stage(f"preflight:{market}", [
                    *preflight, "--phase", "pre", "--report-only",
                ], cwd=cwd, ready=ready)
            ready = run_stage(f"xlsx:{market}", [
                "scripts/telegram_command_center_send.py", "--market", market, "--build-only",
            ], cwd=cwd, ready=ready)
            if not args.skip_regen:
                ready = run_stage(f"postflight:{market}", [
                    *preflight, "--phase", "post",
                ], cwd=cwd, ready=ready)
        return ready

    if args.preview_only:
        for market in markets:
            run_stage(f"preview:{market}", [
                "scripts/telegram_command_center_send.py", "--market", market, "--dry-run", "--with-message",
            ])
    else:
        try:
            with locked(_ROOT, args.market) as storage:
                if isolated:
                    require_clean_publication_state(storage)
                else:
                    recover(_ROOT, storage)
                if args.recover_only:
                    return 0
                missing = [name for name in ("numpy", "pandas", "pyarrow", "openpyxl", "yaml", "requests", "yfinance")
                           if importlib.util.find_spec(name) is None]
                if missing:
                    raise RuntimeError(f"Python environment {sys.executable} is missing: {', '.join(missing)}")
                from scripts.aegis_workbook_continuity import discover

                previous_workbooks = {market: discover(_ROOT, market) for market in markets}
                for market, previous in previous_workbooks.items():
                    if previous:
                        print(f"  last verified {market} workbook: {previous['workbook']} "
                              f"(market session {previous['market_data_asof']})")
                    else:
                        print(f"  no verified {market} workbook found; retaining registry history")
                production = not (args.stage_only or args.dry_run or args.no_send or args.skip_xlsx or
                                  args.skip_regen or args.skip_refresh or args.skip_research)
                if production and not args.force_rerun:
                    reusable = []
                    for market in markets:
                        previous = previous_workbooks[market]
                        if not previous or previous["asof"] != args.asof or not previous.get("research_published"):
                            break
                        if market == "india":
                            from scripts.check_data_freshness import completed_nse_session

                            expected = completed_nse_session()
                        else:
                            from datetime import datetime, timezone
                            from backend.research.evidence.trading_calendars import completed_nyse_session

                            expected = completed_nyse_session(datetime.now(timezone.utc))
                        if previous["market_data_asof"] != expected.isoformat():
                            break
                        reusable.append((market, contained(_ROOT, Path(previous["receipt"]))))
                    if len(reusable) == len(markets):
                        for market, receipt_file in reusable:
                            details = json.loads(receipt_file.read_text(encoding="utf-8"))
                            print(f"  reusing verified {market} workbook for {details['market_data_asof']}")
                            _complete_delivery(market, args.asof, storage, receipt_file.parent, details)
                        return 0
                seed_root = _ROOT
                if args.repeat_from_run:
                    run_id = args.repeat_from_run
                    prior = (storage / run_id).resolve()
                    if prior.parent != storage.resolve() or prior.name != run_id:
                        raise RuntimeError("invalid prior staging run ID")
                    metadata_file = prior / "attempt.json"
                    if not metadata_file.is_file():
                        raise RuntimeError(f"no staging receipt for {run_id}")
                    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                    if (metadata.get("scope") != "india" or metadata.get("asof") != args.asof
                            or metadata.get("status") != "completed"):
                        raise RuntimeError("repeat requires a completed same-day India staging run")
                    seed_root = prior / "work"
                    if not seed_root.is_dir():
                        raise RuntimeError("prior staging workspace is missing")
                    validate_held_actions(_ROOT, seed_root, args.asof)
                    print(f"  repeat baseline: {prior.name}", flush=True)
                completed = []
                for market in markets:
                    attempt = None
                    try:
                        attempt = Attempt(seed_root, storage, market, args.asof)
                        attempts[attempt.workspace] = attempt
                        print(f"  workspace: {attempt.workspace}", flush=True)
                        if not run_market(market, attempt):
                            attempt.status("failed")
                            continue
                        if args.skip_xlsx:
                            attempt.validate_history()
                            attempt.status("completed")
                            completed.append(attempt)
                            continue
                        workbook = Path(f"reports/telegram/aegis_history_{market}.xlsx")
                        dated = workbook.with_name(f"aegis_{market}_{args.asof}.xlsx")
                        if digest(attempt.workspace / workbook) != digest(attempt.workspace / dated):
                            raise RuntimeError("validated workbook and dated workbook differ")
                        attempt.validate_history()
                        if market == "india":
                            validate_held_actions(seed_root, attempt.workspace, args.asof)
                        attempt.status("completed", workbook=dated.as_posix(),
                                       repeat_from_run=args.repeat_from_run)
                        completed.append(attempt)
                    except Exception as error:
                        # A blocked rollback stops both markets until recovery
                        # can verify the live files again.
                        if not isolated:
                            recover(_ROOT, storage)
                        if attempt:
                            attempt.status("failed", error=str(error))
                        print(f"  {market}: {error}")
                        results.append((f"publication:{market}", "FAIL", 0.0))

                if not args.skip_research:
                    if any(status != "PASS" for _, status, _ in results):
                        results.extend((f"research:{name}", "BLOCKED", 0.0) for name in ("p0", "p1"))
                    else:
                        attempt = Attempt(seed_root, storage, "research", args.asof)
                        attempts[attempt.workspace] = attempt
                        for market_attempt in completed:
                            for path in market_attempt.changed_files():
                                dst = attempt.workspace / path
                                dst.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(market_attempt.workspace / path, dst)
                        research_scope = [f"--{markets[0]}-only"] if len(markets) == 1 else []
                        ready = run_stage("research:p0", ["scripts/build_outcome_dataset.py", *research_scope],
                                          cwd=attempt.workspace)
                        ready = run_stage("research:p1", ["scripts/run_attribution.py", *research_scope],
                                          cwd=attempt.workspace, ready=ready)
                        attempt.status("completed" if ready else "failed")
                        if ready and not (args.stage_only or args.dry_run or args.skip_xlsx or
                                          args.skip_regen or args.skip_refresh):
                            for market_attempt in completed:
                                if market_attempt.scope == "india":
                                    from scripts.check_data_freshness import completed_nse_session

                                    path = market_attempt.workspace / "reports/context/canonical_lifecycle_india.json"
                                    certified_session = json.loads(path.read_text(encoding="utf-8"))["market_data_asof"]
                                    if certified_session != completed_nse_session().isoformat():
                                        raise RuntimeError(f"NSE session advanced during certification: {certified_session}")
                                    from india.price_availability import unavailable_prices

                                    held = [ticker for ticker, data in unavailable_prices(market_attempt.workspace, args.asof).items()
                                            if data["held"]]
                                    if held:
                                        print(f"DEGRADED India report. Held-price review required for {', '.join(held)}. "
                                              f"Review workbook: {market_attempt.workspace / 'reports/telegram' / f'aegis_india_{args.asof}.xlsx'}")
                                        results.append(("held price review:india", "FAIL", 0.0))
                                        return 1
                            note_operation(storage, "publication")
                            attempt.publish(certified=True, related=tuple(completed))
                            for market_attempt in completed:
                                dated = Path(f"reports/telegram/aegis_{market_attempt.scope}_{args.asof}.xlsx")
                                if args.open_xlsx and sys.platform == "win32":
                                    os.startfile(str(_ROOT / dated))
                            for market_attempt in completed:
                                market = market_attempt.scope
                                dated = Path(f"reports/telegram/aegis_{market}_{args.asof}.xlsx")
                                lifecycle_path = _ROOT / "reports" / "context" / f"canonical_lifecycle_{market}.json"
                                lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8"))
                                market_attempt.status("certified", workbook=dated.as_posix(),
                                                      sha256=digest(_ROOT / dated), research_published=True,
                                                      market_data_asof=lifecycle.get("market_data_asof"))
                            if not args.no_send:
                                for market_attempt in completed:
                                    started = time.monotonic()
                                    market = market_attempt.scope
                                    try:
                                        note_operation(storage, f"telegram:{market}")
                                        details = json.loads((market_attempt.folder / "attempt.json").read_text(encoding="utf-8"))
                                        _complete_delivery(market, args.asof, storage, market_attempt.folder, details)
                                        status = "PASS"
                                    except (OSError, RuntimeError) as error:
                                        print(f"  Telegram {market}: {error}", file=sys.stderr)
                                        status = "FAIL"
                                    results.append((f"telegram:{market}", status, time.monotonic() - started))
        except RunInProgress as error:
            print(error, file=sys.stderr)
            return 1
        except (OSError, RuntimeError) as error:
            traceback.print_exc()
            print(f"  local state protection: {error!r}; pid={os.getpid()}; "
                  f"winerror={getattr(error, 'winerror', None)}; path={getattr(error, 'filename', None)}")
            results.append(("state protection", "FAIL", 0.0))

    print("\nAEGIS stage results")
    for name, status, elapsed in results:
        print(f"  {status:<8} {name:<28} {elapsed:6.1f}s")
    return int(any(status != "PASS" for _, status, _ in results))


if __name__ == "__main__":
    sys.exit(main())
