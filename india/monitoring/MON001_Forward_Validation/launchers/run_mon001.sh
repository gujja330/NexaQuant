#!/usr/bin/env bash
# MON001 · Linux/macOS cron launcher
#
# Install as a cron entry (weekdays only, 06:15 IST):
#   15 6 * * 1-5 /path/to/prism/india/monitoring/MON001_Forward_Validation/launchers/run_mon001.sh >> /var/log/mon001.log 2>&1
#
# Or for macOS launchd, wrap in a LaunchDaemon .plist referencing this script.
#
# Environment overrides:
#   PYTHON=/usr/local/bin/python3.12  (default: python3)
#   REPO_ROOT=/custom/path            (default: script's grand-grand-grand-parent)

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
PYTHON="${PYTHON:-python3}"

cd "$REPO_ROOT"

LOG_DIR="$REPO_ROOT/logs/mon001"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/mon001_$(date -u +%Y-%m-%d).log"

{
    echo ""
    echo "============================================================"
    echo "MON001 daily runner starting $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "cwd: $REPO_ROOT"
    echo "python: $PYTHON"
    echo "============================================================"
} >> "$LOG"

"$PYTHON" -m india.monitoring.MON001_Forward_Validation.ops.daily_runner "$@" >> "$LOG" 2>&1
EXIT=$?

echo "MON001 daily runner exit=$EXIT at $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
exit "$EXIT"
