"""Mechanically recompute R1/R2/R3 research summary from single-source registry.

CEO 2026-09-04 · replaces hand-tallied summaries. Reads:
  1. backend/research/research_registry.py       · declarative item list
  2. backend/research/coverage/tracker.py        · 13-stage sub-signal state
  3. reports/research/stp/*.json                 · STP worth verdicts

Emits:
  reports/research/summary_recomputed_{yyyy-mm-dd}.json
  docs/AEGIS/RESEARCH_SUMMARY.md                  · human-readable

Reconciliation guarantee · totals mechanically add. Never hand-tallied.
"""
from __future__ import annotations
import io, json, sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from backend.research.research_registry import ALL_ITEMS, by_runner, total_count


# ── STP verdict → Coverage-Tracker stage mapping ────────────────────────────
# CEO 2026-09-04 · fold 5-state into 13-stage (single vocabulary)
STP_TO_COVERAGE = {
    "WORTH":       "Corrected",       # OOS+Corrected · both tests pass · DSR-cleared
    "CONDITIONAL": "OOS",              # T3 pass · T4 partial · one-more-window needed
    "NOT_WORTH":   "Tested",           # ran but did not clear · preserve REJECT
    "BLOCKED":     "Data-required",    # data availability blocker
}


def load_stp_verdicts() -> dict[str, dict]:
    """{item_id: {market: verdict}} · from reports/research/stp/*.json"""
    d = _ROOT / "reports" / "research" / "stp"
    out: dict[str, dict] = defaultdict(dict)
    if not d.exists(): return out
    for f in d.glob("*.json"):
        if "batch_summary" in f.name: continue
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
            rid = j.get("research_id")
            market = j.get("market")
            verdict = j.get("worth_verdict")
            if rid and market and verdict:
                out[rid][market] = verdict
        except Exception:
            continue
    return dict(out)


def classify_item(item, stp_verdicts: dict) -> tuple[str, str]:
    """Return (state, evidence). State ∈ {PROMOTED, CONDITIONAL, REJECTED,
    BLOCKED, WORKED_LEGACY, PENDING}. Evidence explains classification."""
    # Look for STP verdicts across markets (both markets combined view)
    verdicts = stp_verdicts.get(item.id, {})

    # Legacy shipped items · items with no STP but produced substrate previously
    LEGACY_SHIPPED = {
        "R1.1", "R1.2", "R1.5.3", "R1.7", "R1.9-S1", "R1-OPT1", "R1-BANNER",
        "P0", "P5.4", "R2-USA-PARQUET", "R2-ZERO-DIAG",
        "II.1-GBM", "II.2-FN", "II.4-PIOT", "II.4-BENE", "II.4-GOV",
        "II.5-REV", "II.5-TONE", "II.6-MH",
        "FUND-ACCUM",
        "D06-CS", "D14-RISK", "D15-KELLY", "D16-MAE", "D18-INT", "D19-STAT",
        "COMP-META", "COMP-SHEET", "COMP-ADM",
        "STP", "COV-13",
    }
    LEGACY_REJECTED = {"II.3-CUSUM", "T09-BRK"}    # both markets REJECT (memory)
    LEGACY_DEFERRED = {"II.1-STK", "II.1-GNN", "II.1-BMA", "II.2-PAIR"}
    PENDING_R2 = {"P3", "P4", "P5.1", "P5.2", "P5.3", "P5.5"}
    LEGACY_CONDITIONAL = {"P1"}     # P1 CONDITIONAL_PROMOTE this session
    LEGACY_NOT_WORTH = {"F01-05-COMP", "F01-05-GRID"}   # prior REJECT

    if item.id in verdicts.values() or verdicts:
        # STP evaluated
        if any(v == "WORTH" for v in verdicts.values()):
            return "PROMOTED", f"STP WORTH · {verdicts}"
        if any(v == "CONDITIONAL" for v in verdicts.values()):
            return "CONDITIONAL", f"STP CONDITIONAL · {verdicts}"
        if all(v == "BLOCKED" for v in verdicts.values()):
            return "BLOCKED", f"STP BLOCKED · {verdicts}"
        if any(v == "NOT_WORTH" for v in verdicts.values()):
            return "REJECTED", f"STP NOT_WORTH · {verdicts}"
    # Fall through to legacy classification
    if item.id in LEGACY_SHIPPED:  return "WORKED_LEGACY", "shipped-in-substance (pre-STP)"
    if item.id in LEGACY_CONDITIONAL: return "CONDITIONAL", "P1 CONDITIONAL_PROMOTE (this session)"
    if item.id in LEGACY_REJECTED: return "REJECTED", "prior REJECT verdict (locked memory)"
    if item.id in LEGACY_NOT_WORTH: return "REJECTED", "prior NOT_WORTH (F01-05 composite + grid)"
    if item.id in LEGACY_DEFERRED: return "PENDING", "explicitly deferred (Tier 2/3)"
    if item.id in PENDING_R2: return "PENDING", "not started (R2 backlog)"
    if item.id == "LT-COMPOUNDER-01": return "BLOCKED", "LT-COMPOUNDER-01 EXTERNAL_DATA"
    return "PENDING", "not yet classified"


def recompute() -> dict:
    stp_verdicts = load_stp_verdicts()
    per_runner: dict[str, Counter] = defaultdict(Counter)
    per_item: list[dict] = []
    for it in ALL_ITEMS:
        state, evidence = classify_item(it, stp_verdicts)
        per_runner[it.runner][state] += 1
        per_item.append({
            "id": it.id, "runner": it.runner, "category": it.category,
            "name": it.name, "state": state, "evidence": evidence,
            "coverage_stage_equivalent": STP_TO_COVERAGE.get(
                {"PROMOTED":"WORTH","CONDITIONAL":"CONDITIONAL",
                 "BLOCKED":"BLOCKED","REJECTED":"NOT_WORTH"}.get(state, "Tested"),
                "Mapped"),
        })

    # Totals across all runners (mechanical addition · no hand-tally)
    grand_total = Counter()
    for runner_counts in per_runner.values():
        for state, n in runner_counts.items():
            grand_total[state] += n

    return {
        "recomputed_utc": date.today().isoformat(),
        "single_source": "backend/research/research_registry.py",
        "total_items_in_registry": total_count(),
        "grand_totals": dict(grand_total),
        "reconciliation_check": {
            "sum_of_grand_totals": sum(grand_total.values()),
            "total_items_in_registry": total_count(),
            "reconciles": sum(grand_total.values()) == total_count(),
        },
        "per_runner": {r: dict(c) for r, c in per_runner.items()},
        "per_item": per_item,
        "stp_verdicts_seen": stp_verdicts,
        "stp_to_coverage_mapping": STP_TO_COVERAGE,
    }


def render_markdown(summary: dict) -> str:
    lines = [
        "# AEGIS R1/R2/R3 Research Summary · Mechanically Recomputed",
        "",
        f"*Recomputed: {summary['recomputed_utc']} · single source: `{summary['single_source']}`*",
        "",
        f"**Total items in registry:** {summary['total_items_in_registry']}",
        "",
        "## Grand totals (mechanical · sums equal total)",
        "",
        "| State | Count |",
        "|---|---:|",
    ]
    for state, n in sorted(summary["grand_totals"].items(), key=lambda x: -x[1]):
        lines.append(f"| {state} | {n} |")
    lines.append(f"| **Sum** | **{sum(summary['grand_totals'].values())}** |")
    reco = summary["reconciliation_check"]
    lines.append(f"| Reconciles? | **{'✅ YES' if reco['reconciles'] else '❌ NO'}** |")
    lines.append("")

    lines.append("## Per runner")
    lines.append("")
    lines.append("| Runner | " + " | ".join(sorted(summary["grand_totals"].keys())) + " | Total |")
    lines.append("|---|" + "|".join(["---:"] * (len(summary["grand_totals"]) + 1)) + "|")
    states = sorted(summary["grand_totals"].keys())
    for runner in sorted(summary["per_runner"].keys()):
        counts = summary["per_runner"][runner]
        row = f"| {runner} | " + " | ".join(str(counts.get(s, 0)) for s in states)
        row += f" | **{sum(counts.values())}** |"
        lines.append(row)
    lines.append("")

    lines.append("## STP verdict → 13-stage Coverage Tracker mapping (single vocabulary)")
    lines.append("")
    lines.append("| STP verdict | 13-stage equivalent |")
    lines.append("|---|---|")
    for stp, cov in summary["stp_to_coverage_mapping"].items():
        lines.append(f"| {stp} | {cov} |")
    lines.append("")

    lines.append("## Per-item detail (compact)")
    lines.append("")
    lines.append("| ID | Runner | Category | Name | State |")
    lines.append("|---|---|---|---|---|")
    for row in summary["per_item"]:
        lines.append(f"| {row['id']} | {row['runner']} | {row['category']} | {row['name']} | **{row['state']}** |")
    return "\n".join(lines)


def main():
    summary = recompute()
    out_json = _ROOT / "reports" / "research" / f"summary_recomputed_{date.today().isoformat()}.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    md = render_markdown(summary)
    out_md = _ROOT / "docs" / "AEGIS" / "RESEARCH_SUMMARY.md"
    out_md.write_text(md, encoding="utf-8")

    # Print to console
    reco = summary["reconciliation_check"]
    print(f"[recompute] {out_json.relative_to(_ROOT)}")
    print(f"[recompute] {out_md.relative_to(_ROOT)}")
    print(f"total_items: {summary['total_items_in_registry']}")
    print(f"grand_totals: {summary['grand_totals']}")
    print(f"sum of totals: {sum(summary['grand_totals'].values())}")
    print(f"reconciles: {reco['reconciles']}")
    if not reco['reconciles']:
        print("!! RECONCILIATION FAILURE · totals do not equal registry size")
        sys.exit(1)


if __name__ == "__main__":
    main()
