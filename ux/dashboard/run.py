"""UX031 · Executive Dashboard CLI. Emits 5 JSON configs."""
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
sys.path.insert(0, str(HERE.parents[1]))

from ux.dashboard.publish import bundle                                                 # noqa: E402
from ux.dashboard.lib import widgets, routes                                            # noqa: E402


def _banner(msg: str) -> None:
    print(); print("=" * 70); print(f"  {msg}"); print("=" * 70)


def main() -> int:
    t0 = time.time()
    _banner("UX031 - EXECUTIVE DASHBOARD")

    _banner("STEP 1/2 - Publish 5 configs")
    result = bundle.build_and_publish()
    for name in result["written"]:
        print(f"  written: reports/{name}")
    print()
    print(f"  widgets:  {result['n_widgets']}")
    print(f"  routes:   {result['n_routes']}")
    print(f"  layouts:  {result['n_layouts']}")
    print(f"  filters:  {result['n_filters']}")

    _banner("STEP 2/2 - Route map")
    for r in routes.routes():
        print(f"  {r['path']:<18} {r['name']:<26}  widgets: {len(r['widgets'])}")

    _banner("WIDGET INVENTORY (by refresh cadence)")
    by_cadence = {}
    for w in widgets.all_widgets():
        by_cadence.setdefault(w["refresh"], []).append(w["id"])
    for cad, ids in by_cadence.items():
        print(f"  {cad:<12} {len(ids)}")

    _banner(f"UX031 - DONE ({time.time() - t0:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
