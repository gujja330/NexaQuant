"""Decision Attribution v1.0 · CLI.

Emits reports/decision_attribution.json.
"""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from decision_attribution.lib import attribution                                       # noqa: E402


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  DECISION ATTRIBUTION v1.0 · per-rec + subsystem accuracy")
    print("=" * 70)

    result = attribution.run_attribution()
    result["run_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"

    print(f"  recommendations attributed: {result['n_recommendations']}")
    acc = result.get("subsystem_accuracy") or {}
    if acc.get("available"):
        print(f"  historical baseline win-rate: {acc['baseline_wr']}  "
              f"({acc['n_trades']} trades)")
        print()
        print("  Subsystem accuracy (from historical closed trades):")
        for sub, info in sorted(acc.get("subsystems", {}).items(),
                                    key=lambda kv: -kv[1]["alpha_created"]):
            print(f"    {sub:14s}  lift={info['lift']:.2f}  "
                  f"wr_high={info['wr_high'] * 100:>4.1f}%  wr_low={info['wr_low'] * 100:>4.1f}%  "
                  f"α_created={info['alpha_created']:+.3f}  → {info['verdict']}")
    else:
        print(f"  subsystem accuracy: unavailable ({acc.get('reason')})")

    # Print top-3 alpha creators + destroyers
    if result.get("top_alpha_creators"):
        print("\n  Top alpha creators:")
        for c in result["top_alpha_creators"][:3]:
            print(f"    {c['subsystem']:14s}  α={c['alpha_created']:+.3f}  ({c['verdict']})")
    if result.get("top_alpha_destroyers"):
        print("  Top alpha destroyers:")
        for c in result["top_alpha_destroyers"][:3]:
            print(f"    {c['subsystem']:14s}  α={c['alpha_created']:+.3f}  ({c['verdict']})")

    p = HERE.parents[1] / "reports" / "decision_attribution.json"
    p.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n  written: reports/decision_attribution.json ({p.stat().st_size / 1024:.1f} KB)")
    print(f"  elapsed: {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
