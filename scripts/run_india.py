#!/usr/bin/env python3
"""AEGIS · India-only pipeline wrapper.

Operator directive 2026-08-21: "seperate run method by country".

This is a dead-simple wrapper that ONLY runs India. It cannot accidentally
touch USA data · no --market flag · no cross-country leakage.

Usage:
    python scripts/run_india.py                    # full India pipeline
    python scripts/run_india.py --skip-refresh     # skip stage 1
    python scripts/run_india.py --skip-xlsx        # skip stage 4
    python scripts/run_india.py --dry-run          # preview, no Telegram send

All flags forwarded to scripts/aegis_run_all.py --market india.
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

# Windows cp1252 can't render 🇮🇳 · reconfigure stdout to UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                                    encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
_PYTHON = sys.executable


def main() -> int:
    # Strip any stray --market / --usa / -both from the args (defense in depth).
    filtered = []
    skip_next = False
    for a in sys.argv[1:]:
        if skip_next:
            skip_next = False; continue
        if a == "--market":
            skip_next = True    # drop --market <value>
            continue
        if a.startswith("--market="):
            continue
        if a in ("--usa", "--both"):
            continue
        filtered.append(a)

    print("=" * 66)
    print("🇮🇳  AEGIS · INDIA PIPELINE (dedicated · USA cannot run from here)")
    print("=" * 66)

    cmd = [_PYTHON, str(_ROOT / "scripts" / "aegis_run_all.py"),
              "--market", "india"] + filtered
    print(f"  cmd: {' '.join(cmd)}")
    print("-" * 66)
    return subprocess.call(cmd, cwd=str(_ROOT))


if __name__ == "__main__":
    sys.exit(main())
