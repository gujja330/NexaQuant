"""CLI entrypoint for the NexaQuant operations service (OPS001-A).

Not a daemon (OPS001-B ships that). Invokes NexaQuantService.run_once() and
exits with the pipeline's status code. Intended callers:
- Windows Task Scheduler at 16:15 IST
- Linux/macOS cron at same time
- GitHub Actions manual dispatch (as a fallback / mirror of aegis-daily)

Exit codes:
  0  pipeline succeeded
  1  pipeline failed (at least one non-continue-on-failure stage failed)
  2  framework error (bad config, service crashed BEFORE pipeline could run)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexaquant.ops.service import NexaQuantService, default_config


def main() -> int:
    ap = argparse.ArgumentParser(description="NexaQuant operations service (run once).")
    ap.add_argument("--pipeline", type=str, default=None,
                     help="Path to pipeline YAML. Defaults to nexaquant/ops/pipelines/aegis_daily.yaml")
    ap.add_argument("--no-telegram", action="store_true",
                     help="Force disable Telegram channel (file-only notifications)")
    args = ap.parse_args()

    cfg = default_config(repo_root=ROOT,
                          pipeline_config=args.pipeline)
    if args.no_telegram:
        cfg.include_telegram = False
    svc = NexaQuantService(cfg)
    rc = svc.run_once()
    print(f"[ops] pipeline exit code: {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
