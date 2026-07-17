"""UX030 · CLI. Produces 5 JSON configs + telegram_examples.md."""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

# Windows terminal (cp1252) cannot print emoji; force UTF-8 stdout.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from ux.telegram.publish import bundle                                                  # noqa: E402
from ux.telegram.lib import commands, renderer                                          # noqa: E402
from ux.telegram.lib.aggregator import load_context                                     # noqa: E402


def _banner(msg: str) -> None:
    print(); print("=" * 70); print(f"  {msg}"); print("=" * 70)


def main() -> int:
    t0 = time.time()
    _banner("UX030 - INSTITUTIONAL TELEGRAM INTELLIGENCE PLATFORM")

    _banner("STEP 1/2 - Publish configs + examples")
    result = bundle.build_and_publish()
    for name in result["written"]:
        print(f"  written: reports/{name}")
    print(f"  context_ok: {result['context_ok']}")

    _banner("STEP 2/2 - Render live executive summary")
    ctx = load_context()
    print()
    print(renderer.render_executive_summary(ctx))

    _banner("SAMPLE COMMANDS")
    print()
    for cmd in ["/help", "/champion", "/regime", "/confidence"]:
        print(f">>> {cmd}")
        print(commands.dispatch(ctx, cmd))
        print()

    _banner(f"UX030 - DONE ({time.time()-t0:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
