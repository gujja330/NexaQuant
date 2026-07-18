"""Decision Center · CLI."""
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

from decision_center.compute import engine                                              # noqa: E402
from decision_center.publish import bundle as publish                                    # noqa: E402


def _banner(msg: str) -> None:
    print(); print("=" * 72); print(f"  {msg}"); print("=" * 72)


def main() -> int:
    t0 = time.time()
    _banner("DECISION CENTER · v1.0 · OVERNIGHT DIFF + EXIT CENTER + WATCHLIST")

    _banner("STEP 1/2 · Snapshot + diff")
    result = engine.run(verbose=True)

    _banner("STEP 2/2 · Publish")
    outcome = publish.build_and_publish(result)
    for name in outcome["written"]:
        print(f"  written: reports/{name}")

    _banner("OVERNIGHT SUMMARY")
    print(f"\n  {result['overnight_summary']}\n")

    _banner("TOP CHANGES (up to 10)")
    changes = (result["diff"] or {}).get("changes") or []
    for c in changes[:10]:
        print(f"  [{c['kind']:<18}] {c['ticker']:<12} · {c['reason']}")

    _banner("EXIT CENTER")
    exits = result["exit_center"]
    if not exits:
        print("  no exits required today")
    else:
        for x in exits[:10]:
            print(f"  [{x['severity']:<8}] {x['ticker']:<12} "
                    f"{'; '.join(x['reasons'])[:100]}")

    _banner("WATCHLIST · near-buy candidates")
    for w in result["watchlist"][:10]:
        trend = f"{w['intel_trend']:+.1f}" if w['intel_trend'] is not None else "n/a"
        print(f"  {w['ticker']:<12} intel {w['intelligence_score']:.1f} "
                f"(gap {w['gap_to_buy']:.1f} to Buy) · trend {trend}")

    _banner("NOTIFICATIONS · priority-tiered")
    for n in result["notifications"][:10]:
        print(f"  [{n['priority']:<8}] {n['kind']:<24} {n['ticker']:<12} {n['detail'][:100]}")

    _banner(f"DECISION CENTER · DONE ({time.time() - t0:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
