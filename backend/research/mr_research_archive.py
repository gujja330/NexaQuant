"""AEGIS · Sprint M-R · Research Archive Structure.

CEO handover 2026-08-27:
> "45-day research archive · create a structured archive rather than
>  letting old experiments disappear:
>    research/archive/successful/promising/failed/superseded/data_gaps/retired/
>    research/active/MR_V1/E1|E2|E3/
>    research/evidence/india/usa/
>    research/reports/
>  Each research item metadata:
>    hypothesis → data → result → sample size → status → reason → revisit"
> "Failed ≠ deleted. A failed result with n=30 may become interesting at
>  n=300; a genuinely failed result with strong evidence should stay
>  archived as a negative finding."

Materializes the archive directory structure and writes a metadata
card per research item routed to the correct bucket by its current
status. Cards are markdown for humans + JSON for machines.

Under M-R sandbox rules. Zero production changes.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_research_archive.v0.1"


ARCHIVE_BUCKETS = ("successful", "promising", "failed",
                    "superseded", "data_gaps", "retired")
ACTIVE_ROOT = "MR_V1"
ACTIVE_EXPERIMENTS = ("E1", "E2", "E3")


def _route_status(current_status: str, superseded_by: Optional[str]) -> str:
    """Map a status → archive bucket."""
    if current_status == "ACTIVE_SHADOW": return "active"
    if current_status == "SUPERSEDED_BY": return "superseded"
    if current_status in ("ARCHIVED_FOR_LATER", "ARCHIVED_LOW_PRIORITY"): return "retired"
    if current_status == "FAILED": return "failed"
    if current_status == "PASSED": return "successful"
    if current_status == "PROMISING": return "promising"
    return "retired"


def _ensure_tree(root: Path):
    base = root / ALLOWED_WRITE_ROOT / "archive"
    for b in ARCHIVE_BUCKETS:
        (base / b).mkdir(parents=True, exist_ok=True)
    active = root / ALLOWED_WRITE_ROOT / "active" / ACTIVE_ROOT
    for e in ACTIVE_EXPERIMENTS:
        (active / e).mkdir(parents=True, exist_ok=True)
    (root / ALLOWED_WRITE_ROOT / "evidence" / "india").mkdir(parents=True, exist_ok=True)
    (root / ALLOWED_WRITE_ROOT / "evidence" / "usa").mkdir(parents=True, exist_ok=True)
    (root / ALLOWED_WRITE_ROOT / "reports").mkdir(parents=True, exist_ok=True)


def _card_md(item: dict) -> str:
    L = [f"# {item.get('title') or item['experiment_id']}\n"]
    L.append(f"**Experiment ID:** `{item['experiment_id']}`  ")
    L.append(f"**Status:** `{item.get('current_status','?')}`  ")
    L.append(f"**Route:** `{item.get('_route','?')}`  ")
    if item.get("superseded_by"):
        L.append(f"**Superseded by:** `{item['superseded_by']}`  ")
    L.append(f"**Market:** {item.get('market','?')}  ")
    L.append(f"**Card generated:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n")
    L.append(f"## Metadata\n")
    L.append(f"- **Hypothesis:** {item.get('hypothesis','—')}")
    L.append(f"- **Data source:** {item.get('source_evidence') or item.get('source_tickets') or item.get('source_ticket_id') or '—'}")
    L.append(f"- **Result (historical):** {item.get('title','—')}")
    L.append(f"- **Sample size (forward):** N = {item.get('days_of_evidence',0)} shadow days ({item.get('first_snapshot_date','?')} onwards)")
    L.append(f"- **Metric:** {item.get('metric','—')}")
    L.append(f"- **Reason for current status:** {item.get('current_status','—')} · "
             f"{'superseded by ' + item['superseded_by'] if item.get('superseded_by') else 'no successor'}")
    L.append(f"- **Revisit condition:** N reaches {item.get('min_sample_size','100')} forward observations")
    if item.get("acceptance_criteria"):
        L.append(f"- **Acceptance:** {item['acceptance_criteria']}")
    if item.get("rejection_criteria"):
        L.append(f"- **Rejection:** {item['rejection_criteria']}")
    if item.get("attempts"):
        L.append(f"\n## Recent attempts\n")
        for a in item["attempts"][-5:]:
            L.append(f"- `{a.get('iso')}` n_rows={a.get('n_rows')}")
    L.append(f"\n## Governance\n")
    L.append(f"- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)")
    L.append(f"- Zero auto-promotion")
    L.append(f"- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry")
    return "\n".join(L)


def _copy_or_link(root: Path, experiment_id: str, bucket: str) -> tuple:
    src = root / ALLOWED_WRITE_ROOT / "experiments" / f"{experiment_id}.json"
    dst_dir = root / ALLOWED_WRITE_ROOT / ("archive/" + bucket
                                            if bucket in ARCHIVE_BUCKETS
                                            else f"active/{ACTIVE_ROOT}/E?")
    if bucket == "active":
        # place under active/MR_V1/E1|E2|E3 based on ID
        for e in ACTIVE_EXPERIMENTS:
            slug = f"_{e.lower()}_"
            if slug in experiment_id:
                dst_dir = root / ALLOWED_WRITE_ROOT / "active" / ACTIVE_ROOT / e
                break
        else:
            dst_dir = root / ALLOWED_WRITE_ROOT / "active" / ACTIVE_ROOT / "other"
    dst_dir.mkdir(parents=True, exist_ok=True)
    if not src.exists(): return (None, None)
    payload = json.loads(src.read_text(encoding="utf-8"))
    payload["_route"] = bucket
    dst = dst_dir / f"{experiment_id}.card.json"
    dst.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    md = _card_md(payload)
    dst_md = dst_dir / f"{experiment_id}.card.md"
    dst_md.write_text(md, encoding="utf-8")
    return (dst, dst_md)


def build(root: Path) -> dict:
    _ensure_tree(root)
    exp_dir = root / ALLOWED_WRITE_ROOT / "experiments"
    if not exp_dir.exists():
        return {"engine": ENGINE_ID, "status": "NO_EXPERIMENTS"}
    routed = []
    for p in sorted(exp_dir.glob("aegis_mr_experiment_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        status = d.get("current_status","?")
        superseded_by = d.get("superseded_by")
        bucket = _route_status(status, superseded_by)
        j, md = _copy_or_link(root, d["experiment_id"], bucket)
        routed.append({
            "experiment_id":    d["experiment_id"],
            "current_status":   status,
            "route":            bucket,
            "card_json":        str(j.relative_to(root)) if j else None,
            "card_md":          str(md.relative_to(root)) if md else None,
        })
    # Also index data-gap items
    gap_dir = root / ALLOWED_WRITE_ROOT / "archive" / "data_gaps"
    # Momentum
    (gap_dir / "MOMENTUM_HISTORICAL_GAP.card.md").write_text(
        "# Momentum Historical Coverage Gap\n\n"
        "**Status:** data_gaps · **Route:** archive/data_gaps\n\n"
        "- **Hypothesis:** Momentum performance cannot be evaluated · "
        "n=0 historical snapshots.\n"
        "- **Data source:** `reports/research/short_term_momentum_*.json` · "
        "walk-forward daemon captures daily from 2026-08-27 onward.\n"
        "- **Result:** UNKNOWN · not measurable until corpus >= 20 sessions.\n"
        "- **Sample size:** 0 historical + growing forward.\n"
        "- **Status reason:** insufficient historical evidence · not a "
        "failure · resume research when N >= 100 forward.\n"
        "- **Revisit condition:** N forward Momentum captures >= 20 sessions.\n",
        encoding="utf-8")
    (gap_dir / "USA_FUNDAMENTALS_GAP.card.md").write_text(
        "# USA Fundamentals Coverage Gap\n\n"
        "**Status:** data_gaps · **Route:** archive/data_gaps\n\n"
        "- **Hypothesis:** USA fundamentals studies cannot be measured "
        "because parquet is empty (0/908 universe · 0/498 daily-preds).\n"
        "- **Data source:** `usa/data/raw/us/fundamentals.parquet`\n"
        "- **Result:** BLOCKED · zero coverage.\n"
        "- **Sample size:** 0.\n"
        "- **Status reason:** requires yfinance batch pull for S&P 500.\n"
        "- **Revisit condition:** USA fundamentals coverage >= 95% of "
        "daily-pred set.\n"
        "- **Plan:** see FUNDAMENTALS_GAP_PLAN.md.\n",
        encoding="utf-8")

    tree = _tree_index(root)
    idx_p = root / ALLOWED_WRITE_ROOT / "archive" / "INDEX.json"
    idx_p.write_text(json.dumps({
        "engine":        ENGINE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_routed":      len(routed),
        "tree":          tree,
        "routed":        routed,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "engine":        ENGINE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_routed":      len(routed),
        "routed":        routed,
        "tree":          tree,
    }


def _tree_index(root: Path) -> dict:
    """Snapshot of what lives under archive/ + active/ + evidence/ + reports/."""
    base = root / ALLOWED_WRITE_ROOT
    def _list(d: Path) -> list:
        if not d.exists(): return []
        return sorted([p.name for p in d.iterdir()])
    return {
        "archive/": {b: _list(base / "archive" / b) for b in ARCHIVE_BUCKETS},
        "active/MR_V1/": {e: _list(base / "active" / ACTIVE_ROOT / e)
                          for e in ACTIVE_EXPERIMENTS},
        "evidence/": {m: _list(base / "evidence" / m) for m in ("india","usa")},
        "reports/": _list(base / "reports"),
    }


def render_console(res: dict):
    print(f"\n======== RESEARCH ARCHIVE · n_routed={res['n_routed']} ========")
    by_route: dict = {}
    for r in res["routed"]:
        by_route.setdefault(r["route"], []).append(r["experiment_id"])
    for route, ids in sorted(by_route.items()):
        print(f"\n  [{route}] ({len(ids)}):")
        for i in ids:
            short = i.replace("aegis_mr_experiment_20260827_","")
            print(f"    · {short}")
    print(f"\n  Tree:")
    for k, v in res["tree"].items():
        if isinstance(v, dict):
            print(f"    {k}")
            for kk, vv in v.items():
                print(f"      {kk}: {len(vv)} entries")
        else:
            print(f"    {k}: {len(v)} entries")


if __name__ == "__main__":
    root = Path(".").resolve()
    res = build(root)
    render_console(res)
    print(f"\n[research_archive] Failed ≠ deleted · negative findings retained")
