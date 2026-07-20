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
    {
        "name":     "recommendations",
        "desc":     "USA Adaptive Recommendation Engine (technicals-based)",
        "script":   "usa/research/recommendations/run.py",
        "produces": ["usa/reports/recommendations.json"],
        "requires": ["usa/reports/market_data_freshness.json"],
    },
    {
        "name":     "validation",
        "desc":     "USA Validation Engine (paper harness + drift)",
        "script":   "usa/research/validation/run.py",
        "produces": ["usa/reports/validation_latest.json", "usa/reports/stock_validation.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "risk",
        "desc":     "USA Risk & Capital Engine (sizing + sector caps + verdict)",
        "script":   "usa/research/risk/run.py",
        "produces": ["usa/reports/risk_latest.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "fusion",
        "desc":     "USA Intelligence Fusion (10-dim aggregate + conflicts)",
        "script":   "usa/research/fusion/run.py",
        "produces": ["usa/reports/investment_intelligence.json",
                       "usa/reports/intelligence_summary.json",
                       "usa/reports/intelligence_conflicts.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "price_context",
        "desc":     "USA Price Context (CMP + 52W bounds per ticker)",
        "script":   "usa/research/price_context/run.py",
        "produces": ["usa/reports/price_context.json"],
        "requires": ["usa/reports/universe.json"],
    },
    {
        "name":     "institutional_memory",
        "desc":     "USA Institutional Memory (archive + lifecycle + missed-opps + history)",
        "script":   "usa/research/institutional_memory/run.py",
        "produces": ["usa/reports/recommendation_lifecycle.json",
                       "usa/reports/missed_opportunities.json",
                       "usa/reports/recommendation_history.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "winner_genome",
        "desc":     "USA Winner Genome (Alpha Signatures)",
        "script":   "usa/research/winner_genome/run.py",
        "produces": ["usa/reports/winner_genome.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "decision_attribution",
        "desc":     "USA Decision Attribution (per-rec + subsystem accuracy)",
        "script":   "usa/research/decision_attribution/run.py",
        "produces": ["usa/reports/decision_attribution.json"],
        "requires": ["usa/reports/recommendations.json",
                       "usa/reports/investment_intelligence.json"],
    },
    {
        "name":     "benchmark",
        "desc":     "USA Continuous Benchmark (vs S&P 500)",
        "script":   "usa/research/benchmark/run.py",
        "produces": ["usa/reports/benchmark.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "morning_report",
        "desc":     "USA Morning Research Report (MD + HTML, USD)",
        "script":   "usa/research/morning_report/run.py",
        "produces": ["usa/reports/morning_latest.md", "usa/reports/morning_latest.html"],
        "requires": ["usa/reports/recommendations.json", "usa/reports/benchmark.json"],
    },
    {
        "name":     "ops_check",
        "desc":     "USA Operational Hardening (artifacts + schemas + verdict)",
        "script":   "usa/scripts/usa_ops_check.py",
        "produces": ["usa/reports/ops_check.json"],
        "requires": [],
    },
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
