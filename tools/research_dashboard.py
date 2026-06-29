# tools/research_dashboard.py
"""
AEGIS Research Dashboard — the executive summary. NOT framework code (core/ is locked); this is research
OPS reporting. Reads the single source of truth (markets/research/LEADERBOARD.csv) and rolls it up per
Research Program into markets/research/RESEARCH_DASHBOARD.md.

Status buckets: promoted (✅ kept) · investigate (🟡 live lead) · closed (🔴/⚪/❌ rejected/weak/neutral).
Run after appending any leaderboard row:  python tools/research_dashboard.py
"""
import csv
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
LB = ROOT / "markets" / "research" / "LEADERBOARD.csv"
OUT = ROOT / "markets" / "research" / "RESEARCH_DASHBOARD.md"

PROMOTED = {"kept", "promoted"}
INVESTIGATE = {"investigate"}


def main():
    rows = list(csv.DictReader(LB.open()))
    prog = defaultdict(lambda: {"n": 0, "promoted": 0, "investigate": 0, "closed": 0, "market": ""})
    for r in rows:
        p = prog[r["program"]]
        p["n"] += 1
        p["market"] = r["market"]
        s = r["status"].strip().lower()
        if s in PROMOTED:
            p["promoted"] += 1
        elif s in INVESTIGATE:
            p["investigate"] += 1
        else:
            p["closed"] += 1

    tot = {"n": sum(p["n"] for p in prog.values()),
           "promoted": sum(p["promoted"] for p in prog.values()),
           "investigate": sum(p["investigate"] for p in prog.values()),
           "closed": sum(p["closed"] for p in prog.values())}

    L = []
    L.append("# AEGIS Research Dashboard (executive summary)")
    L.append("")
    L.append("Auto-generated from `LEADERBOARD.csv` (single source of truth) — "
             "regenerate with `python tools/research_dashboard.py`. Do not edit by hand.")
    L.append("")
    L.append("| Market | Program | Experiments | ✅ Promoted | 🟡 Investigate | Closed |")
    L.append("|---|---|---:|---:|---:|---:|")
    for name in sorted(prog):
        p = prog[name]
        L.append(f"| {p['market']} | {name} | {p['n']} | {p['promoted']} | {p['investigate']} | {p['closed']} |")
    L.append(f"| **All** | **{len(prog)} programs** | **{tot['n']}** | "
             f"**{tot['promoted']}** | **{tot['investigate']}** | **{tot['closed']}** |")
    L.append("")
    L.append(f"_Total: {tot['n']} experiments logged · {tot['promoted']} promoted · "
             f"{tot['investigate']} live leads · {tot['closed']} closed._")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  wrote {OUT.relative_to(ROOT)} · {tot['n']} experiments across {len(prog)} programs")


if __name__ == "__main__":
    main()
