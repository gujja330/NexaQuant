#!/usr/bin/env python3
"""AEGIS Layer 3 · Assembly · builds XLSX + runs delivery gate. Fast (<30s).

Wrapper around telegram_command_center_send.py in --build-only mode.
Skips heavy intelligence (Layer 2 already produced JSON on disk).
Config in configs/pipeline_layers.yaml::layers.assembly.
"""
from __future__ import annotations

import argparse
import io
import subprocess
import sys
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                                    encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=date.today().isoformat())
    args = ap.parse_args()

    print(f"[assembly:{args.market}] build-only XLSX + delivery gate")
    r = subprocess.run(
        [sys.executable, "scripts/telegram_command_center_send.py",
             "--market", args.market, "--build-only"],
        cwd=str(_ROOT), text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        print(f"[assembly:{args.market}] BLOCKED · exit={r.returncode}")
        return r.returncode
    print(f"[assembly:{args.market}] XLSX built + gate ALLOWed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
