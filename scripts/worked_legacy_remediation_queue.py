"""WORKED_LEGACY remediation queue · CEO 2026-09-04.

Uses the SAME 13-stage Coverage Tracker as source of truth · this queue only
adds SCHEDULING METADATA (priority, dependency, next STP action). It is NOT
a second state machine · it is a work-ordering view.

Output · reports/research/worked_legacy_queue.md · sorted by remediation_priority
ascending (lower = do first). Items blocked by substrate rule are visible at
priority ≥90 · never scheduled until F01-F05 clears.
"""
from __future__ import annotations
import io, sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from backend.research.research_registry import ALL_ITEMS


def render_queue() -> str:
    # Filter to items with remediation_priority < 90 (schedulable) and
    # items 90-98 (blocked-by-substrate · shown separately)
    schedulable = sorted(
        [x for x in ALL_ITEMS if x.remediation_priority < 90],
        key=lambda x: x.remediation_priority,
    )
    blocked_by_rule = [x for x in ALL_ITEMS if 90 <= x.remediation_priority <= 98]
    not_scheduled = [x for x in ALL_ITEMS if x.remediation_priority == 99]

    lines = [
        "# WORKED_LEGACY Remediation Queue · Scheduling View",
        "",
        "*Sole source of truth for state: 13-stage Coverage Tracker + STP verdicts.*",
        "*This file only adds work-ordering metadata · never a second state machine.*",
        "",
        "**Rule:** Substrate Before Sophistication (locked 2026-09-04). Items with",
        "priority 90-98 are blocked by that rule · will not be scheduled until",
        "their upstream substrate reaches `Tested` stage.",
        "",
        "## Schedulable · lowest-effort/highest-information first",
        "",
        "| Priority | ID | Runner | Category | Name | Upstream substrate | Next STP action |",
        "|---:|---|---|---|---|---|---|",
    ]
    for x in schedulable:
        sub = ", ".join(x.upstream_substrate) or "—"
        lines.append(f"| {x.remediation_priority} | `{x.id}` | {x.runner} | {x.category} | {x.name} | {sub} | {x.next_stp_action} |")

    lines += [
        "",
        "## Blocked by substrate-before-sophistication rule (priority 90-98)",
        "",
        "| Priority | ID | Runner | Waiting on | Reason |",
        "|---:|---|---|---|---|",
    ]
    for x in blocked_by_rule:
        sub = ", ".join(x.upstream_substrate) or "—"
        lines.append(f"| {x.remediation_priority} | `{x.id}` | {x.runner} | {sub} | {x.next_stp_action} |")

    lines += [
        "",
        "## Not scheduled (governance / delivery / permanent-reject / diagnostic)",
        "",
        "| ID | Runner | Reason |",
        "|---|---|---|",
    ]
    for x in not_scheduled:
        lines.append(f"| `{x.id}` | {x.runner} | {x.next_stp_action} |")

    lines += [
        "",
        "---",
        "",
        "**How the queue shrinks:** as each schedulable item runs through STP,",
        "it acquires a real WORTH verdict (WORTH / CONDITIONAL / NOT_WORTH / BLOCKED)",
        "and moves from WORKED_LEGACY into its evidence-based state in the",
        "recomputed summary. The queue itself is not a state · it is a schedule.",
    ]
    return "\n".join(lines)


def main():
    out = _ROOT / "reports" / "research" / "worked_legacy_queue.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_queue(), encoding="utf-8")
    print(f"[queue] wrote {out.relative_to(_ROOT)}")
    schedulable = [x for x in ALL_ITEMS if x.remediation_priority < 90]
    blocked = [x for x in ALL_ITEMS if 90 <= x.remediation_priority <= 98]
    print(f"schedulable: {len(schedulable)} · blocked-by-rule: {len(blocked)} · "
          f"not-scheduled: {len([x for x in ALL_ITEMS if x.remediation_priority == 99])}")
    print(f"top 5 schedulable:")
    for x in sorted(schedulable, key=lambda x: x.remediation_priority)[:5]:
        print(f"  p={x.remediation_priority} · {x.id} · {x.name[:60]}")


if __name__ == "__main__":
    main()
