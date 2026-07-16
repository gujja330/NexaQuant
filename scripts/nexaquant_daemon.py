"""CLI entrypoint for the OPS001-B daemon.

Thin wrapper around nexaquant.ops.cli.main() so systemd / Task Scheduler /
launchd can invoke a stable path.

Examples:
  python scripts/nexaquant_daemon.py start
  python scripts/nexaquant_daemon.py status
  python scripts/nexaquant_daemon.py stop --timeout 60
  python scripts/nexaquant_daemon.py restart
  python scripts/nexaquant_daemon.py health
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexaquant.ops.cli import main


if __name__ == "__main__":
    sys.exit(main())
