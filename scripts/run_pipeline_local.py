"""AEGIS local pipeline runner — verbose, step-by-step, single file.

Runs every stage of the AEGIS daily pipeline with clear operator output.
Same pipeline as GitHub Actions, just with human-readable progress.

Usage:
    python scripts/run_pipeline_local.py                    # full pipeline
    python scripts/run_pipeline_local.py --skip-telegram    # everything except Telegram
    python scripts/run_pipeline_local.py --skip-mon001      # skip MON001 stage
    python scripts/run_pipeline_local.py --force-send       # bypass freshcheck if Telegram refuses

Exit codes:
    0  every stage succeeded (or was skipped)
    1  at least one non-continue-on-failure stage failed
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_YAML = ROOT / "nexaquant" / "ops" / "pipelines" / "aegis_daily.yaml"


def _now_ist() -> str:
    """Current time in IST (UTC+5:30), no host-TZ dependency."""
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")


def _today_ist() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")


def _banner(msg: str) -> None:
    print()
    print("=" * 70)
    print(f"  {msg}")
    print("=" * 70)


def _mark(status: str) -> str:
    return {
        "OK": "[OK]  ",
        "FAIL": "[FAIL]",
        "SKIP": "[SKIP]",
        "WARN": "[WARN]",
        "STALE": "[STALE]",
        "TIMEOUT": "[TIME]",
    }.get(status, "[?]")


def run_stage(idx: int, total: int, name: str, cmd: list[str],
               timeout_s: int, continue_on_failure: bool) -> tuple[str, int, float]:
    """Run one stage. Returns (status_label, exit_code, elapsed_s)."""
    print()
    print("-" * 70)
    print(f"  STEP {idx}/{total}:  {name}")
    print("-" * 70)
    print(f"  command:  {' '.join(cmd)}")
    print(f"  started:  {_now_ist()}")
    print(f"  timeout:  {timeout_s}s   ·   continue_on_failure: {continue_on_failure}")
    print()

    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), timeout=timeout_s)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        print()
        print(f"  {_mark('TIMEOUT')}  killed after {elapsed:.1f}s")
        return ("TIMEOUT", -1, elapsed)
    except FileNotFoundError as e:
        elapsed = time.time() - t0
        print()
        print(f"  {_mark('FAIL')}  file not found: {e}")
        return ("FAIL", 127, elapsed)

    elapsed = time.time() - t0
    print()

    if rc == 0:
        print(f"  {_mark('OK')}    finished  {_now_ist()}   ({elapsed:.1f}s)")
        return ("OK", rc, elapsed)

    # OPS001-F sender-side freshness gate — special-cased for clearer messaging.
    if rc == 2 and name == "telegram_notify":
        print(f"  {_mark('STALE')}  finished  {_now_ist()}   ({elapsed:.1f}s)   exit 2 = REFUSED_STALE")
        print(f"           (aegis_today.csv 'Generated' field != today IST = {_today_ist()})")
        return ("STALE", rc, elapsed)

    mark = "FAIL"
    print(f"  {_mark(mark)}  finished  {_now_ist()}   ({elapsed:.1f}s)   exit {rc}")
    if continue_on_failure:
        print(f"           (continue_on_failure=true — pipeline will proceed)")
    return (mark, rc, elapsed)


def print_summary(results: list[tuple[str, str, int, float]], overall_elapsed: float) -> None:
    """results: list of (stage_name, status_label, exit_code, elapsed_s)"""
    _banner("PIPELINE SUMMARY")
    ok = 0; failed = 0; skipped = 0; stale = 0
    for name, status, rc, el in results:
        print(f"  {_mark(status)}  {name:<28}  ({el:.1f}s)  exit={rc}")
        if status == "OK":
            ok += 1
        elif status == "SKIP":
            skipped += 1
        elif status == "STALE":
            stale += 1
        else:
            failed += 1
    print()
    print(f"  Totals:  OK={ok}   FAILED={failed}   STALE={stale}   SKIPPED={skipped}")
    print(f"  Wall clock: {overall_elapsed:.1f}s ({overall_elapsed/60:.1f}min)")
    print(f"  Finished:   {_now_ist()}")


def maybe_force_send() -> int:
    """Bypass the OPS001-F freshcheck and send whatever is in aegis_today.csv."""
    _banner("FORCE-SEND (bypassing freshness check)")
    print("  Calling india/telegram_notify.py DIRECTLY (skips freshcheck wrapper).")
    print("  This sends whatever aegis_today.csv currently contains.")
    print(f"  started: {_now_ist()}")
    print()
    t0 = time.time()
    r = subprocess.run([sys.executable, str(ROOT / "india" / "telegram_notify.py")],
                       cwd=str(ROOT))
    el = time.time() - t0
    print()
    if r.returncode == 0:
        print(f"  {_mark('OK')}    force-send completed  {_now_ist()}   ({el:.1f}s)")
        return 0
    print(f"  {_mark('FAIL')}  force-send exit {r.returncode}   ({el:.1f}s)")
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="AEGIS local pipeline runner (verbose).")
    ap.add_argument("--skip-telegram", action="store_true",
                     help="Skip Telegram health check + notify stages")
    ap.add_argument("--skip-mon001", action="store_true",
                     help="Skip MON001 daily runner stage")
    ap.add_argument("--force-send", action="store_true",
                     help="If Telegram is refused as stale, bypass freshcheck and send anyway")
    args = ap.parse_args()

    overall_t0 = time.time()

    _banner("AEGIS  ·  LOCAL PIPELINE RUNNER")
    print(f"  time (IST):    {_now_ist()}")
    print(f"  IST date:      {_today_ist()}")
    print(f"  repo:          {ROOT}")
    print(f"  pipeline YAML: {PIPELINE_YAML.relative_to(ROOT)}")

    with PIPELINE_YAML.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    stages = cfg["stages"]
    total = len(stages)

    print(f"  stages:        {total}")
    print(f"  flags:         skip_telegram={args.skip_telegram} · skip_mon001={args.skip_mon001} · force_send={args.force_send}")

    results: list[tuple[str, str, int, float]] = []
    telegram_refused = False

    for i, stage in enumerate(stages, 1):
        name = stage["name"]

        if args.skip_telegram and name in ("telegram_health_check", "telegram_notify"):
            print()
            print("-" * 70)
            print(f"  STEP {i}/{total}:  {name}   {_mark('SKIP')}   (--skip-telegram)")
            print("-" * 70)
            results.append((name, "SKIP", 0, 0.0))
            continue

        if args.skip_mon001 and name == "mon001_daily":
            print()
            print("-" * 70)
            print(f"  STEP {i}/{total}:  {name}   {_mark('SKIP')}   (--skip-mon001)")
            print("-" * 70)
            results.append((name, "SKIP", 0, 0.0))
            continue

        cmd = list(stage["command"])
        timeout_s = int(stage.get("timeout_s", 900))
        cof = bool(stage.get("continue_on_failure", False))

        status, rc, elapsed = run_stage(i, total, name, cmd, timeout_s, cof)
        results.append((name, status, rc, elapsed))

        if status == "STALE":
            telegram_refused = True

        # Hard-stop on freshness_gate failure — the pipeline's design contract.
        if status in ("FAIL", "TIMEOUT") and not cof and name == "freshness_gate":
            print()
            print("  Freshness gate failed. Pipeline halted per design.")
            print("  Remaining stages will not run.")
            break

    overall_elapsed = time.time() - overall_t0
    print_summary(results, overall_elapsed)

    # Bypass on request
    if telegram_refused and args.force_send:
        maybe_force_send()
    elif telegram_refused:
        print()
        print("  ℹ  Telegram refused because aegis_today.csv is not today's data.")
        print(f"     Data date: check `head -2 data/aegis_today.csv`")
        print(f"     Today IST: {_today_ist()}")
        print()
        print("  Two options to actually send a Telegram:")
        print("    1. Wait until after 16:00 IST (yfinance has today's close), rerun this script.")
        print("    2. Re-run with --force-send to bypass the freshcheck NOW.")

    # Return non-zero if any hard failure
    any_fail = any(s in ("FAIL", "TIMEOUT") for _, s, _, _ in results)
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
