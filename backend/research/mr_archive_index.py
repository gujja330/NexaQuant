"""AEGIS · Sprint M-R · Archive Index Generator.

CEO handover 2026-08-27:
> "Create the 45-day research archive/index so every previous finding
>  has a status: successful / promising / failed / superseded / data-gap."

Walks reports/research/archive/ + reports/research/active/MR_V1/ +
reports/research/topology/ and emits ONE consolidated index:

   reports/research/ARCHIVE_INDEX.md

Every finding gets a row with:
   Title · ID · Status (5-way) · Hist n · Fwd N · Decision · Revisit

Nothing is deleted. Failed / superseded findings remain retained.

Under M-R sandbox rules. Zero production changes.
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

from backend.research.mr_runner import ALLOWED_WRITE_ROOT
from backend.research.mr_research_topology import STATUS_LABEL_5WAY

ENGINE_ID = "aegis.mr_archive_index.v0.1"

STATUS_ORDER = [
    "SUCCESSFUL_PROMOTION_CANDIDATE",
    "PROMISING_NEED_MORE_DATA",
    "FAILED_RETAIN_EVIDENCE",
    "SUPERSEDED_KEEP_HISTORY",
    "DATA_GAP_FIX_DATA",
]

# CEO 2026-08-27 · 8-field research_index contract
CEO_INDEX_FIELDS = (
    "research_id", "hypothesis", "evidence", "sample_size",
    "result", "status", "superseded_by", "next_action",
)


def _evidence_source(kind: str, experiment_id: str) -> str:
    if kind == "data_gap":
        return "reports/research/topology/archive/data_quality/"
    return f"reports/research/experiments/{experiment_id}/"


def _next_action(current_status: str, fwd_n: int, min_n: int) -> str:
    if current_status == "ACTIVE_SHADOW":
        if fwd_n >= min_n:
            return "RUN_ACCEPTANCE_EVALUATION"
        return f"ACCUMULATE_FORWARD_EVIDENCE ({fwd_n}/{min_n})"
    if current_status == "PASSED":
        return "PAPER_TRADE_30_SESSIONS · then CEO promotion decision"
    if current_status == "FAILED":
        return f"RECHECK_WHEN_N_GE_{min_n * 3} · or regime changes"
    if current_status == "SUPERSEDED_BY":
        return "REFER_TO_SUCCESSOR (see superseded_by)"
    if current_status in ("ARCHIVED_FOR_LATER","ARCHIVED_LOW_PRIORITY"):
        return "REVISIT_WHEN_CEO_UNARCHIVES"
    if current_status == "DATA_GAP":
        return "FIX_DATA_SOURCE_FIRST"
    return "NO_ACTION"


def _load_all_cards(root: Path) -> list:
    cards = []
    exp_dir = root / ALLOWED_WRITE_ROOT / "experiments"
    if exp_dir.exists():
        for p in sorted(exp_dir.glob("aegis_mr_experiment_*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception: continue
            cards.append({
                "kind":            "experiment",
                "title":           d.get("title","?"),
                "experiment_id":   d.get("experiment_id"),
                "market":          d.get("market","?"),
                "current_status":  d.get("current_status","?"),
                "hypothesis":      d.get("hypothesis",""),
                "hist_n":          d.get("min_sample_size", 0),
                "fwd_n":           d.get("days_of_evidence", 0),
                "min_sample_size": d.get("min_sample_size", 100),
                "acceptance":      d.get("acceptance_criteria", ""),
                "superseded_by":   d.get("superseded_by"),
            })
    # Data gaps · fixed 3 entries per CEO spec
    for gap in (
        {"title": "Momentum · Historical corpus empty",
         "experiment_id": "data_gap_momentum_historical",
         "market": "BOTH", "current_status": "DATA_GAP",
         "hist_n": 0, "fwd_n": 0,
         "hypothesis": "Momentum forward corpus started 2026-08-27 · need N>=20 to first-evaluate",
         "acceptance": "N forward >= 20 sessions",
         "superseded_by": None,
         "kind": "data_gap"},
        {"title": "USA · Fundamentals parquet empty",
         "experiment_id": "data_gap_usa_fundamentals",
         "market": "USA", "current_status": "DATA_GAP",
         "hist_n": 0, "fwd_n": 0,
         "hypothesis": "yfinance batch pull required for S&P 500 fundamentals",
         "acceptance": "coverage >= 95% of daily-pred tickers",
         "superseded_by": None,
         "kind": "data_gap"},
        {"title": "USA · Canonical portfolio JSON not locally available",
         "experiment_id": "data_gap_usa_canonical_local",
         "market": "USA", "current_status": "DATA_GAP",
         "hist_n": 0, "fwd_n": 0,
         "hypothesis": "CI generates USA canonical · commit step runs only on send success · diagnostic-upload step added",
         "acceptance": "next USA CI publishes canonical + XLSX artifact",
         "superseded_by": None,
         "kind": "data_gap"},
    ):
        cards.append(gap)
    # Apply 5-way label + decision + revisit
    for c in cards:
        c["status_5way"] = STATUS_LABEL_5WAY.get(c["current_status"],
                                                  "SUPERSEDED_KEEP_HISTORY")
        c["decision"] = _decision_from_status(c["current_status"], c.get("superseded_by"))
        c["revisit"] = (f"forward N reaches {c['min_sample_size']} observations"
                        if c["kind"] == "experiment"
                        else c.get("acceptance") or "manual")
    return cards


def _decision_from_status(status: str, superseded_by):
    if status == "ACTIVE_SHADOW": return "PENDING (accumulating)"
    if status == "SUPERSEDED_BY": return f"RETIRED (→ {superseded_by})"
    if status in ("ARCHIVED_FOR_LATER","ARCHIVED_LOW_PRIORITY"): return "ARCHIVED"
    if status == "PASSED": return "PROMOTED_CANDIDATE"
    if status == "FAILED": return "REJECTED"
    if status == "DATA_GAP": return "BLOCKED_ON_DATA"
    return status


def _group_by_status(cards: list) -> dict:
    g: dict = {s: [] for s in STATUS_ORDER}
    for c in cards:
        g.setdefault(c["status_5way"], []).append(c)
    return g


def render_markdown(cards: list) -> str:
    grouped = _group_by_status(cards)
    L = [f"# AEGIS · Research Archive Index\n"]
    L.append(f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n")
    L.append(f"**Total findings tracked:** {len(cards)}\n")
    counts = {k: len(v) for k, v in grouped.items()}
    L.append(f"**Status counts:** `{counts}`\n\n---\n")
    for status in STATUS_ORDER:
        items = grouped.get(status, [])
        L.append(f"\n## {status} ({len(items)})\n")
        if not items:
            L.append(f"_(none · this bucket earned by future forward evidence)_")
            continue
        L.append(f"| Title | Market | Hist n | Fwd N | Decision | Revisit |")
        L.append(f"|---|---|---:|---:|---|---|")
        for c in items:
            short = c["title"][:60]
            L.append(f"| {short} | {c['market']} | {c.get('hist_n',0)} | "
                     f"{c.get('fwd_n',0)}/{c.get('min_sample_size',100) if c['kind']=='experiment' else '—'} | "
                     f"{c['decision']} | {c['revisit']} |")
    L.append(f"\n---\n")
    L.append(f"## Rules\n")
    L.append(f"- **SUCCESSFUL_PROMOTION_CANDIDATE:** forward acceptance PASS · never populated by historical evidence alone.")
    L.append(f"- **PROMISING_NEED_MORE_DATA:** forward BORDERLINE or ACTIVE_SHADOW · N < 100.")
    L.append(f"- **FAILED_RETAIN_EVIDENCE:** forward FAIL · retained as negative finding.")
    L.append(f"- **SUPERSEDED_KEEP_HISTORY:** retired or replaced · shadow output continues for continuity.")
    L.append(f"- **DATA_GAP_FIX_DATA:** blocked by data availability · fix data source before evaluating.")
    L.append(f"\n## Compliance\n")
    L.append(f"- No historical/failed findings deleted.")
    L.append(f"- Zero production changes.")
    L.append(f"- 5-way label uniform across cards and this index.")
    return "\n".join(L)


def _ceo_index_row(c: dict) -> dict:
    """Return CEO's exact 8-field row per finding."""
    hist = c.get("hist_n", 0)
    fwd = c.get("fwd_n", 0)
    minn = c.get("min_sample_size", 100)
    return {
        "research_id":     c.get("experiment_id",""),
        "hypothesis":      c.get("hypothesis","")[:220],
        "evidence":        _evidence_source(c.get("kind","experiment"),
                                             c.get("experiment_id","")),
        "sample_size":     f"historical_n={hist}, forward_n={fwd}, target_n={minn}",
        "result":          c.get("decision",""),
        "status":          c.get("status_5way",""),
        "superseded_by":   c.get("superseded_by") or "—",
        "next_action":     _next_action(c.get("current_status","?"),
                                          fwd, minn),
    }


def emit(root: Path, cards: list, md: str) -> tuple:
    p_md = root / ALLOWED_WRITE_ROOT / "ARCHIVE_INDEX.md"
    p_json = root / ALLOWED_WRITE_ROOT / "mr_archive_index.json"
    p_md.write_text(md, encoding="utf-8")
    p_json.write_text(json.dumps({
        "engine":       ENGINE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_findings":   len(cards),
        "cards":        cards,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    # CEO 2026-08-27 · research_index.csv/json with the 8 exact fields
    p_csv = root / ALLOWED_WRITE_ROOT / "research_index.csv"
    p_idx_json = root / ALLOWED_WRITE_ROOT / "research_index.json"
    rows = [_ceo_index_row(c) for c in cards]
    with p_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(CEO_INDEX_FIELDS))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    p_idx_json.write_text(json.dumps({
        "engine":       ENGINE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_rows":       len(rows),
        "fields":       list(CEO_INDEX_FIELDS),
        "rows":         rows,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    # Also drop the index inside topology/archive/ + historical/45d/
    for sub in ("topology/archive", "topology/historical/45d"):
        d = root / ALLOWED_WRITE_ROOT / sub
        if d.exists():
            (d / "ARCHIVE_INDEX.md").write_text(md, encoding="utf-8")
    return (p_md, p_json)


if __name__ == "__main__":
    root = Path(".").resolve()
    cards = _load_all_cards(root)
    md = render_markdown(cards)
    p_md, p_json = emit(root, cards, md)
    from collections import Counter
    c = Counter(x["status_5way"] for x in cards)
    print(f"[archive_index] n={len(cards)} · dist={dict(c)}")
    print(f"[archive_index] wrote {p_md}")
