"""Decision Center · orchestration.

Each daily run:
  1. Capture today's snapshot from live reports/*.json.
  2. Persist to data/market_intelligence/derived/decisions/<date>.json.
  3. Load the most recent prior snapshot.
  4. Compute the diff.
  5. Compute watchlist + exit-center + notifications.
  6. Build overnight summary paragraph.
  7. Emit reports/decision_center_*.json for the dashboard."""
from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from decision_center.lib import snapshot, diff, summary, watchlist, exit_center  # noqa: E402


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def run(day: str | None = None, verbose: bool = True) -> dict:
    day = day or date.today().isoformat()

    if verbose:
        print(f"  capturing today's snapshot ({day})")
    today = snapshot.capture_today(day)
    snap_path = snapshot.persist(today)
    if verbose:
        print(f"  wrote snapshot: {snap_path.relative_to(_ROOT)} "
                f"({today['n_recs']} recs)")

    yesterday = snapshot.load_latest_previous(day)
    if verbose:
        if yesterday:
            print(f"  loaded yesterday: {yesterday.get('date')} "
                    f"({yesterday.get('n_recs')} recs)")
        else:
            print(f"  no prior snapshot found — first day of tracking")

    d = diff.compute_diff(today, yesterday)
    if verbose:
        print(f"  computed diff: {d.get('n_changes', 0)} material changes")
        for kind, n in (d.get("counts_by_kind") or {}).items():
            print(f"    {kind:<24} {n}")

    watch = watchlist.watchlist_candidates(today, yesterday, n=15)
    exits = exit_center.exit_candidates(today, d)
    notifications = exit_center.notifications(today, d, exits, watch)

    if verbose:
        print(f"  watchlist candidates: {len(watch)}")
        print(f"  exit-center rows: {len(exits)}")
        n_crit = sum(1 for n in notifications if n["priority"] == "CRITICAL")
        n_high = sum(1 for n in notifications if n["priority"] == "HIGH")
        print(f"  notifications: {n_crit} CRITICAL · {n_high} HIGH · {len(notifications)} total")

    paragraph = summary.build_paragraph(d)

    return {
        "run_utc":        datetime.now(timezone.utc).isoformat() + "Z",
        "code_sha":       _git_sha(),
        "engine":         "Decision Center",
        "version":        "v1.0",
        "date":           day,
        "yesterday_date": yesterday.get("date") if yesterday else None,
        "snapshot":       today,
        "diff":           d,
        "watchlist":      watch,
        "exit_center":    exits,
        "notifications":  notifications,
        "overnight_summary": paragraph,
        "governance":     ("Advisory only. Diff is computed deterministically "
                            "from persisted snapshots; exit-center reasons name "
                            "the specific rule that fired."),
    }
