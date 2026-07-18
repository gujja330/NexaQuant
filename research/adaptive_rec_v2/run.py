"""Adaptive Rec v2.0 · CLI."""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from adaptive_rec_v2.compute import engine                                              # noqa: E402
from adaptive_rec_v2.publish import bundle as publish                                    # noqa: E402


def _banner(msg: str) -> None:
    print(); print("=" * 72); print(f"  {msg}"); print("=" * 72)


def main() -> int:
    t0 = time.time()
    _banner("ADAPTIVE RECOMMENDATION ENGINE · v2.0 · CONFIDENCE SIGNAL REBUILD")

    _banner("STEP 1/2 · Fit + evaluate candidate signal models")
    result = engine.run(verbose=True)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    _banner("STEP 2/2 · Publish 6 outputs")
    outcome = publish.build_and_publish(result)
    for name in ["adaptive_rec_v2_signal.json",
                   "adaptive_rec_v2_scoreboard.json",
                   "adaptive_rec_v2_feature_importance.json",
                   "adaptive_rec_v2_reliability.json",
                   "adaptive_rec_v2_signal.parquet",
                   "adaptive_rec_v2_migration.md"]:
        print(f"  written: reports/{name}")

    _banner("SCOREBOARD")
    print(f"\n  {'model':<38} {'brier':>8} {'auc':>8} {'P@5':>8} {'P@10':>8} {'P@20':>8}")
    print(f"  {'-' * 78}")
    for name, entry in result["scoreboard"].items():
        m = entry["metrics"]
        marker = "* " if name == result["best_model"] else "  "
        print(f"  {marker}{name:<36} {m['brier']:>8.4f} {m['auc']:>8.4f} "
                f"{m['precision_at_5']:>8.3f} {m['precision_at_10']:>8.3f} "
                f"{m['precision_at_20']:>8.3f}")

    _banner("TIER DISCRIMINATION · v2.0 best model")
    best = result["scoreboard"][result["best_model"]]
    tier_check = best["tier_check"]
    print(f"  verdict: {tier_check['verdict']}")
    print(f"  monotone: {tier_check['monotone_decreasing']}")
    print(f"  top-vs-bottom spread: {tier_check['top_bottom_spread']}")
    print()
    print(f"  {'tier':<14} {'n':>6} {'win rate':>10} {'predicted':>10} {'expectancy':>10}")
    for tier, row in best["tier_discrimination"].items():
        print(f"  {tier:<14} {row['n']:>6} {row['win_rate']:>10.3f} "
                f"{row['predicted_mean']:>10.3f} "
                f"{row.get('expectancy', 0):>10.3f}")

    _banner("FEATURE IMPORTANCE · top 8")
    sorted_fi = sorted(result["feature_importance"].items(), key=lambda kv: -kv[1])
    for name, imp in sorted_fi[:8]:
        print(f"  {name:<32} {imp:.4f}")

    _banner("MIGRATION SUMMARY")
    print(f"  delta Precision@10 (best vs baseline): {outcome['delta_precision_10']:+.4f}")
    print(f"  tier discrimination verdict:            {outcome['tier_verdict']}")

    _banner(f"ADAPTIVE REC v2.0 · DONE ({time.time() - t0:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
