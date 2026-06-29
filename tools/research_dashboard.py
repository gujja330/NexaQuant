# tools/research_dashboard.py
"""
AEGIS Research Dashboard — the executive summary. NOT framework code (core/ is locked); this is research
OPS reporting. Reads the single source of truth (markets/research/LEADERBOARD.csv) plus the registries, and
rolls them up into markets/research/RESEARCH_DASHBOARD.md.

Per program: experiment count, promoted / investigate / closed, avg IC, avg IC-IR, last updated.
Status buckets: promoted (✅ kept) · investigate (🟡 live lead) · closed (🔴/⚪/❌ rejected/weak/neutral).
Run after appending any leaderboard row:  python tools/research_dashboard.py
"""
import csv
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "markets" / "research"
LB = RES / "LEADERBOARD.csv"
REG = RES / "registry"
OUT = RES / "RESEARCH_DASHBOARD.md"

PROMOTED = {"kept", "promoted"}
INVESTIGATE = {"investigate"}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return f"{sum(xs) / len(xs):+.3f}" if xs else "-"


def _count(path, status_field, statuses):
    if not path.exists():
        return 0
    return sum(1 for r in csv.DictReader(path.open()) if r.get(status_field, "").strip().lower() in statuses)


def main():
    rows = list(csv.DictReader(LB.open()))
    prog = defaultdict(lambda: {"n": 0, "promoted": 0, "investigate": 0, "closed": 0,
                                "market": "", "ic": [], "ir": [], "last": ""})
    conf = defaultdict(int)
    for r in rows:
        p = prog[r["program"]]
        p["n"] += 1
        p["market"] = r["market"]
        p["ic"].append(_f(r.get("IC")))
        p["ir"].append(_f(r.get("IC_IR")))
        p["last"] = max(p["last"], r.get("date", ""))
        cv = r.get("confidence", "")
        conf[cv.split("(")[-1].rstrip(")").strip() if "(" in cv else (cv.strip() or "—")] += 1
        s = r["status"].strip().lower()
        p["promoted"] += s in PROMOTED
        p["investigate"] += s in INVESTIGATE
        p["closed"] += not (s in PROMOTED or s in INVESTIGATE)

    tot = {k: sum(p[k] for p in prog.values()) for k in ("n", "promoted", "investigate", "closed")}
    last_all = max((p["last"] for p in prog.values()), default="")

    # registry rollups
    ds_ready = _count(REG / "DATASET_REGISTRY.csv", "status", {"ready"})
    ds_total = sum(1 for _ in csv.DictReader((REG / "DATASET_REGISTRY.csv").open())) if (REG / "DATASET_REGISTRY.csv").exists() else 0
    feat_prod = _count(REG / "FEATURE_CATALOG.csv", "status", {"production"})
    feat_inv = _count(REG / "FEATURE_CATALOG.csv", "status", {"investigate"})
    feat_total = sum(1 for _ in csv.DictReader((REG / "FEATURE_CATALOG.csv").open())) if (REG / "FEATURE_CATALOG.csv").exists() else 0
    exp_open = _count(REG / "EXPERIMENT_REGISTRY.csv", "status", {"designed", "running"})
    exp_total = sum(1 for _ in csv.DictReader((REG / "EXPERIMENT_REGISTRY.csv").open())) if (REG / "EXPERIMENT_REGISTRY.csv").exists() else 0

    L = ["# AEGIS Research Dashboard (executive summary)", "",
         "Auto-generated from `LEADERBOARD.csv` + `registry/` — regenerate with "
         "`python tools/research_dashboard.py`. Do not edit by hand.", "",
         f"_Last experiment: {last_all or 'n/a'}_", "",
         "## Programs",
         "| Market | Program | Exp | ✅ Prom | 🟡 Inv | Closed | Avg IC | Avg IC-IR | Last |",
         "|---|---|--:|--:|--:|--:|--:|--:|--|"]
    for name in sorted(prog):
        p = prog[name]
        L.append(f"| {p['market']} | {name} | {p['n']} | {p['promoted']} | {p['investigate']} | "
                 f"{p['closed']} | {_avg(p['ic'])} | {_avg(p['ir'])} | {p['last']} |")
    L.append(f"| **All** | **{len(prog)} programs** | **{tot['n']}** | **{tot['promoted']}** | "
             f"**{tot['investigate']}** | **{tot['closed']}** | | | {last_all} |")
    L += ["",
          "## Assets",
          "| Registry | Counts |",
          "|---|---|",
          f"| Datasets | {ds_ready}/{ds_total} ready |",
          f"| Features | {feat_total} catalogued · {feat_prod} production · {feat_inv} investigating |",
          f"| Experiments | {exp_total} registered · {exp_open} active/designed · {tot['n']} results logged |",
          f"| Confidence | " + " · ".join(f"{k} {conf[k]}" for k in ('High', 'Medium', 'Low') if conf.get(k)) + " |",
          "",
          f"_Totals: {tot['n']} experiments · {tot['promoted']} promoted · {tot['investigate']} live leads · "
          f"{tot['closed']} closed._"]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  wrote {OUT.relative_to(ROOT)} · {tot['n']} experiments across {len(prog)} programs")


if __name__ == "__main__":
    main()
