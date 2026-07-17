"""DEV029 — Confidence Calibration Engine · CLI."""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from confidence_calibration.compute import engine                                       # noqa: E402
from confidence_calibration.publish import bundle as publish                              # noqa: E402


ROOT = HERE.parents[1]


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _banner(msg: str) -> None:
    print(); print("=" * 70); print(f"  {msg}"); print("=" * 70)


def _now_ist() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")


def main() -> int:
    t0 = time.time()
    _banner("DEV029 - CONFIDENCE CALIBRATION & PROBABILITY ENGINE")
    print(f"  time (IST): {_now_ist()}")
    print(f"  code_sha:   {_git_sha()}")

    _banner("STEP 1/2 · Fit 5 calibrators, select best on held-out data")
    result = engine.run(verbose=True)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    _banner("STEP 2/2 · Publish 6 outputs")
    published = publish.build_and_publish(result)
    for name in ["confidence_calibration.json", "calibration_metrics.json",
                   "reliability_diagram.json", "confidence_bias.json",
                   "calibration_history.json", "confidence_calibration.parquet"]:
        print(f"  written: reports/{name}")

    _banner("SCOREBOARD (all 5 calibration methods on held-out test)")
    print(f"\n  {'method':<24} {'brier':>8} {'log_loss':>10} {'ECE':>8} {'MCE':>8} {'reliability':>12}")
    print(f"  {'-' * 72}")
    for name, m in sorted(result["scoreboard"].items(), key=lambda kv: kv[1]["brier_score"]):
        marker = "* " if name == result["best_method"] else "  "
        print(f"  {marker}{name:<22} {m['brier_score']:8.4f} {m['log_loss']:10.4f} "
                f"{m['ece']:8.4f} {m['mce']:8.4f} {m['reliability_score']:12.4f}")

    _banner("BEFORE / AFTER CALIBRATION (full corpus)")
    print(f"                              raw       calibrated    delta")
    r = result["raw_metrics_all"]
    c = result["calibrated_metrics_all"]
    for k, label in [("brier_score", "Brier score"),
                       ("ece", "ECE"),
                       ("mce", "MCE"),
                       ("log_loss", "Log loss"),
                       ("confidence_bias", "Confidence bias"),
                       ("sharpness", "Sharpness")]:
        delta = c[k] - r[k]
        print(f"  {label:<26}  {r[k]:8.4f}      {c[k]:8.4f}   {delta:+.4f}")

    _banner("RAW RELIABILITY CURVE (calibration gaps)")
    print(f"\n  {'bin':<22} {'n':>6} {'predicted':>10} {'observed':>10} {'gap':>8}")
    for row in result["raw_reliability"]:
        if row["n"] == 0:
            continue
        gap_str = f"{row['gap']:+.3f}" if row["gap"] is not None else "n/a"
        print(f"  [{row['bin_lo']:.2f}, {row['bin_hi']:.2f}]     {row['n']:>6} "
                f"{row['predicted']:>10.3f} {row['observed']:>10.3f} {gap_str:>8}")

    _banner("CALIBRATED RELIABILITY CURVE (after fix)")
    print(f"\n  {'bin':<22} {'n':>6} {'predicted':>10} {'observed':>10} {'gap':>8}")
    for row in result["calibrated_reliability"]:
        if row["n"] == 0:
            continue
        gap_str = f"{row['gap']:+.3f}" if row["gap"] is not None else "n/a"
        print(f"  [{row['bin_lo']:.2f}, {row['bin_hi']:.2f}]     {row['n']:>6} "
                f"{row['predicted']:>10.3f} {row['observed']:>10.3f} {gap_str:>8}")

    if result["warnings"]:
        _banner(f"WARNINGS ({len(result['warnings'])})")
        for w in result["warnings"][:8]:
            print(f"  [{w['type']}] {w['message']}")

    _banner("DEV029 · DONE")
    print(f"  elapsed: {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
