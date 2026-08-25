#!/usr/bin/env python3
"""AEGIS Layer 2 · Intelligence · runs guard chain (shadow / rotation / NEW / risk).

Wrapper around backend.recommendation.new_opp_guard.guarded_run().
Config in configs/pipeline_layers.yaml::layers.intelligence.
"""
from __future__ import annotations

import argparse
import io
import sys
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                                    encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=date.today().isoformat())
    args = ap.parse_args()

    from backend.recommendation.new_opp_guard import guarded_run, summary_line
    h = guarded_run(_ROOT, args.market, args.asof)
    print(f"[intelligence:{args.market}] {summary_line(h)}")
    for err in h.error_history[:5]:
        print(f"  · {err[:150]}")
    return 0 if h.verdict in ("GREEN", "YELLOW") else 1


if __name__ == "__main__":
    sys.exit(main())
