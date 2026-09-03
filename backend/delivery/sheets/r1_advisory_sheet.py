"""05_R1_Advisory sheet builder · CEO 2026-09-03 pasted-plan §5.

R1 is retired from production P&L but its engine is alive. This sheet
surfaces the daily R1 picks WITH an explicit banner that R1 positions
carry NO dynamic-exit protection. Operator can act on the advisory but
does so with eyes open.
"""
from __future__ import annotations

from datetime import datetime


ADVISORY_BANNER = (
    "R1 ADVISORY · runner is retired from AEGIS production P&L. "
    "Positions listed here carry NO dynamic-exit protection · "
    "operator must monitor manually if acting on any advisory pick."
)


R1_ADVISORY_COLUMNS = [
    "Ticker", "Sector", "R1 Signal", "Rank",
    "Suggested Entry Zone", "R1 Reason",
    "KG Community", "Group Composite Score",
    "Advisory Warning",
]


def build_r1_advisory_rows(root, market: str, asof: str,
                           r1_picks: list[dict],
                           kg_filter_result: dict) -> list[list]:
    """Return list of row-tuples for the 05_R1_Advisory sheet.

    r1_picks · list of R1 recommendation dicts
    kg_filter_result · output of backend.research.r1_kg_filter.build_r1_kg_filter
    """
    # Build ticker → community_id + group_composite_score map
    comm_map = {}
    if kg_filter_result and "communities" in kg_filter_result:
        for c in kg_filter_result["communities"]:
            cid = c["community_id"]
            for t in c.get("members_preview", []):
                comm_map[t] = (cid, c.get("group_composite_score"))
    rows = []
    for i, p in enumerate(r1_picks, start=1):
        ticker = str(p.get("ticker", "")).upper()
        cid, gcs = comm_map.get(ticker, (None, None))
        rows.append([
            ticker,
            p.get("sector") or "",
            p.get("recommendation") or p.get("action") or "",
            i,
            p.get("entry_zone") or "",
            (p.get("bull_case") or p.get("reason") or "")[:200],
            cid or "unknown",
            round(float(gcs), 4) if gcs is not None else "",
            "no dynamic-exit protection",
        ])
    return rows


def sheet_meta() -> dict:
    return {
        "sheet_name": "05_R1_Advisory",
        "banner": ADVISORY_BANNER,
        "columns": R1_ADVISORY_COLUMNS,
        "notes": [
            "R1 is RETIRED_ADVISORY per configs/aegis_runner_registry.yaml",
            "Contribution to AEGIS P&L: NONE",
            "Every pick shown here bears the 'no dynamic-exit protection' warning",
        ],
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
