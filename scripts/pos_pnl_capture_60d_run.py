"""POS-PNL-CAPTURE-60D · orchestrator · Sprint A · C1
CEO 2026-09-03 · additive research family runner.

Emits:
    reports/research/pos_pnl_capture_60d/dataset_{market}.summary.json
    reports/research/pos_pnl_capture_60d/panel_{market}.json
    reports/research/pos_pnl_capture_60d/summary_{market}.md
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def render_md(root: Path, market: str, panel: dict) -> Path:
    lines = [
        f"# POS-PNL-CAPTURE-60D · {market.upper()} · asof {panel.get('asof_today')}",
        f"_generated {panel.get('built_utc')}_\n",
        "**Governance:** additive research family · NOT a P0 replacement · "
        "NOT a NEG-PNL replacement · winner thresholds predeclared.\n",
        f"## Substrate",
        f"- N candidate x date rows: **{panel.get('n_candidates_total', 0)}**",
        f"- Data available: {panel.get('n_data_available', 0)}",
        f"- Data missing: {panel.get('n_data_missing', 0)}",
        f"- Winner trial family: {panel.get('winner_definition_trial_count')} (4 horizons × 4 thresholds)",
        "",
        "## Selection quality per winner definition",
        "| Definition | TP | FP | FN | TN | Precision | Recall | F1 | Missed cost sum |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for defn, m in (panel.get("per_winner_definition") or {}).items():
        lines.append(
            f"| {defn} | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} | "
            f"{round(m['precision'],3)} | {round(m['recall'],3)} | {round(m['f1'],3)} | "
            f"{round(m['missed_winner_cost_sum_pct']*100,2)}% |"
        )
    lines.append("")
    lines.append("## Aggregate missed-winner cost (sum forward-return of missed winners)")
    for h, v in (panel.get("aggregate_missed_cost_pct_by_horizon") or {}).items():
        lines.append(f"- {h}: {round(v*100, 2)}%")
    lines.append("")
    lines.append("## Miss classification (sample · first winner definition)")
    first_def = next(iter((panel.get("per_winner_definition") or {}).values()), None)
    if first_def:
        for cat, n in (first_def.get("miss_category_distribution") or {}).items():
            lines.append(f"- {cat}: {n}")
    lines.append("")
    lines.append(f"## Governance\n\n{panel.get('governance_note')}")
    p = root / "reports" / "research" / "pos_pnl_capture_60d" / f"summary_{market}.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    from backend.research.pos_pnl_capture_60d import (
        build_pos_capture_dataset, build_capture_panel,
    )
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        ds = build_pos_capture_dataset(root, m, args.asof)
        if ds.get("status") in ("PIT_UNIVERSE_MISSING","NO_PIT_DATES_IN_WINDOW"):
            print(json.dumps(ds, indent=2, default=str)); continue
        panel = build_capture_panel(root, m, ds)
        md = render_md(root, m, panel)
        print(f"[pos-pnl-capture] {m} · candidates={ds.get('n_candidates_total')} · md={md.relative_to(root)}")


if __name__ == "__main__":
    main()
