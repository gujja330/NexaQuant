"""AEGIS · lightweight performance profiler.

Profiles the daily orchestrator step-by-step (elapsed + memory delta)
and the dashboard's `loadState()`-equivalent JSON loading cost.
Emits `reports/aegis_performance.json` + a human summary.

No cProfile / py-spy dependency — uses `time.perf_counter()` and
optionally `psutil` if installed (for RSS memory).

Usage:
  python scripts/aegis_profile.py
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

_ROOT = Path(__file__).resolve().parents[1]

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


# Steps to profile
STEPS = [
    ("adaptive_rec_v2",  "research/adaptive_rec_v2/run.py"),
    ("validation_v2",    "research/validation_v2/run.py"),
    ("risk_capital_v2",  "research/risk_capital_v2/run.py"),
    ("dna_feedback",     "research/recommendation_dna/run_feedback.py"),
    ("knowledge_graph",  "research/knowledge_graph/run.py"),
    ("fusion",           "research/adaptive_rec_v2/run_fusion.py"),
    ("decision_center",  "research/decision_center/run.py"),
]


def _banner(msg: str) -> None:
    print(); print("=" * 72); print(f"  {msg}"); print("=" * 72)


def profile_step(name: str, script: str) -> dict:
    p = _ROOT / script
    if not p.exists():
        return {"name": name, "verdict": "MISSING", "elapsed_s": 0.0, "peak_rss_mb": None}

    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [sys.executable, str(p)],
        cwd=str(_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    peak_rss = 0.0
    if _HAS_PSUTIL:
        try:
            pp = psutil.Process(proc.pid)
            while proc.poll() is None:
                try:
                    rss = pp.memory_info().rss / 1024 / 1024
                    if rss > peak_rss:
                        peak_rss = rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break
                time.sleep(0.05)
        except psutil.NoSuchProcess:
            pass
    proc.wait(timeout=600)
    elapsed = time.perf_counter() - t0

    return {
        "name":         name,
        "script":       script,
        "verdict":      "OK" if proc.returncode == 0 else "FAILED",
        "returncode":   proc.returncode,
        "elapsed_s":    round(elapsed, 3),
        "peak_rss_mb":  round(peak_rss, 1) if peak_rss > 0 else None,
    }


def profile_dashboard_load() -> dict:
    """Simulate what the dashboard does on page load — read every consumed JSON."""
    reports = _ROOT / "reports"
    files = [
        "recommendations.json", "portfolio.json", "champion_strategy.json",
        "global_context.json", "confidence_calibration.json",
        "adaptive_rec_v2_signal.json", "validation_v2_latest.json",
        "risk_capital_v2_latest.json", "investment_intelligence.json",
        "intelligence_summary.json", "intelligence_conflicts.json",
        "intelligence_explanation.json", "graph_statistics.json",
        "community_clusters.json", "stress_scenarios.json",
        "recommendation_dna_feedback.json", "decision_center_today.json",
    ]
    total_bytes = 0
    per_file = []
    t0 = time.perf_counter()
    for f in files:
        p = reports / f
        if not p.exists():
            per_file.append({"file": f, "exists": False, "bytes": 0, "parse_ms": None})
            continue
        size = p.stat().st_size
        total_bytes += size
        pt0 = time.perf_counter()
        try:
            json.loads(p.read_text(encoding="utf-8"))
            parse_ms = round((time.perf_counter() - pt0) * 1000, 2)
        except Exception:
            parse_ms = None
        per_file.append({"file": f, "exists": True, "bytes": size, "parse_ms": parse_ms})
    total_elapsed = time.perf_counter() - t0

    return {
        "n_files":      len(files),
        "files_found":  sum(1 for f in per_file if f["exists"]),
        "total_bytes":  total_bytes,
        "total_mb":     round(total_bytes / 1024 / 1024, 3),
        "total_load_s": round(total_elapsed, 3),
        "per_file":     sorted(per_file, key=lambda x: -(x.get("bytes") or 0))[:8],
    }


def main() -> int:
    _banner("AEGIS · PERFORMANCE PROFILE")

    if _HAS_PSUTIL:
        print(f"  psutil available · will capture peak RSS per step")
    else:
        print(f"  psutil not installed · timing only")

    _banner("STEP-BY-STEP PROFILE")
    step_results = []
    total_elapsed = 0.0
    for name, script in STEPS:
        print(f"  profiling {name}...")
        r = profile_step(name, script)
        step_results.append(r)
        total_elapsed += r["elapsed_s"]
        rss = f" · peak {r['peak_rss_mb']} MB" if r["peak_rss_mb"] else ""
        print(f"    {r['verdict']:<8} {r['elapsed_s']:>6.2f}s{rss}")

    _banner("DASHBOARD LOAD PROFILE")
    dashboard = profile_dashboard_load()
    print(f"  files loaded: {dashboard['files_found']}/{dashboard['n_files']}")
    print(f"  total size:   {dashboard['total_mb']} MB")
    print(f"  total load:   {dashboard['total_load_s']*1000:.1f} ms")
    print(f"  top files by size:")
    for f in dashboard["per_file"][:6]:
        if not f["exists"]:
            continue
        print(f"    {f['file']:<40} {f['bytes']/1024:>7.1f} KB  parse {f['parse_ms']} ms")

    _banner("SUMMARY")
    print(f"  total pipeline wall-clock:  {total_elapsed:.2f}s")
    print(f"  target (per HOWTO):         < 30s")
    print(f"  target met:                 {'YES' if total_elapsed < 30 else 'NO'}")
    print()
    print(f"  dashboard initial load:     {dashboard['total_load_s']*1000:.1f} ms")
    print(f"  target (per HOWTO):         < 2000 ms")
    print(f"  target met:                 {'YES' if dashboard['total_load_s'] < 2 else 'NO'}")

    # Emit report
    out = {
        "run_utc":         datetime.now(timezone.utc).isoformat(),
        "psutil":          _HAS_PSUTIL,
        "steps":           step_results,
        "pipeline_wall_clock_s": round(total_elapsed, 2),
        "dashboard_load":  dashboard,
        "targets": {
            "pipeline_max_s":            30.0,
            "dashboard_max_ms":          2000,
            "pipeline_target_met":       total_elapsed < 30,
            "dashboard_target_met":      dashboard["total_load_s"] < 2,
        },
    }
    p = _ROOT / "reports" / "aegis_performance.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\n  written: reports/aegis_performance.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
