"""AEGIS USA · Daily Orchestrator (Phase 1 skeleton).

Sequential runner for the USA pipeline. Mirrors India's
scripts/aegis_daily_v2.py shape so future phases can plug in
engines in the same style.

Phase 1 steps:
  1. build_universe        — read configs/universe.yaml → reports/universe.json
  2. refresh_market_data   — yfinance → data/raw/us/*.parquet

Later phases will add:
  3. recommendation engine    (Phase 2)
  4. validation, risk         (Phase 2)
  5. fusion, DNA, graph       (Phase 3)
  6. IM, winner genome, DA    (Phase 4)
  7. benchmark vs S&P 500     (Phase 4)
  8. morning report           (Phase 5)
  9. dashboard, telegram      (Phase 5)
 10. ops_check                (Phase 6)

This file is scaffolded so Phase-2 engineers add ONE dict to STEPS.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


_ROOT = Path(__file__).resolve().parents[2]
_USA  = Path(__file__).resolve().parents[1]
LEDGER = _USA / "reports" / "usa_daily_history.jsonl"


# ─── Pipeline definition ────────────────────────────────────────
STEPS = [
    {
        "name":     "build_universe",
        "desc":     "Resolve active universe → usa/reports/universe.json",
        "script":   "usa/scripts/build_universe.py",
        "produces": ["usa/reports/universe.json"],
        "requires": ["usa/configs/universe.yaml"],
    },
    {
        "name":     "refresh_market_data",
        "desc":     "Fetch OHLCV from yfinance → usa/data/raw/us/*.parquet",
        "script":   "usa/scripts/refresh_market_data.py",
        "produces": ["usa/reports/market_data_freshness.json"],
        "requires": ["usa/reports/universe.json"],
    },
    # Phase 2+ steps get added here.
]


def _banner(msg: str) -> None:
    print(); print("=" * 78); print(f"  {msg}"); print("=" * 78)


def _run_step(step: dict) -> dict:
    script = _ROOT / step["script"]
    if not script.exists():
        return {"name": step["name"], "verdict": "MISSING_SCRIPT", "elapsed_s": 0.0}

    # Verify required inputs exist
    for req in step.get("requires", []):
        if not (_ROOT / req).exists():
            return {
                "name": step["name"],
                "verdict": "MISSING_INPUT",
                "elapsed_s": 0.0,
                "missing": req,
            }

    t0 = time.time()
    r = subprocess.run(
        [sys.executable, step["script"]],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=600,
    )
    elapsed = time.time() - t0

    # Stream stdout live to operator
    if r.stdout:
        print(r.stdout.rstrip())
    if r.returncode != 0 and r.stderr:
        print(r.stderr[:1200])

    verdict = "SUCCESS" if r.returncode == 0 else "FAILED"
    return {
        "name":       step["name"],
        "verdict":    verdict,
        "elapsed_s":  round(elapsed, 2),
        "returncode": r.returncode,
    }


def main() -> int:
    _banner("AEGIS USA · Daily Orchestrator (Phase 1)")
    print(f"  UTC now:  {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"  steps:    {len(STEPS)}")
    print(f"  currency: USD ($)")

    results: list[dict] = []
    t_total = time.time()

    for i, step in enumerate(STEPS, 1):
        _banner(f"[{i}/{len(STEPS)}] {step['name']} · {step['desc']}")
        res = _run_step(step)
        results.append(res)
        print(f"\n  verdict: {res['verdict']}  ·  elapsed: {res['elapsed_s']}s")
        if res["verdict"] == "FAILED":
            print(f"  aborting pipeline — {step['name']} failed.")
            break

    total_elapsed = round(time.time() - t_total, 2)
    n_ok  = sum(1 for r in results if r["verdict"] == "SUCCESS")

    _banner("SUMMARY")
    print(f"  steps:    {n_ok}/{len(STEPS)} ok")
    print(f"  elapsed:  {total_elapsed}s")

    # Append to ledger
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "run_utc":         datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "phase":           1,
        "n_steps":         len(STEPS),
        "n_success":       n_ok,
        "n_failure":       len(results) - n_ok,
        "total_elapsed_s": total_elapsed,
        "results":         results,
    }
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    print(f"  ledger:   {LEDGER.relative_to(_ROOT)}")

    return 0 if n_ok == len(STEPS) else 1


if __name__ == "__main__":
    sys.exit(main())
