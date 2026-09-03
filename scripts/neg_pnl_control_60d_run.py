"""NEG-PNL-CONTROL-60D · orchestrator · Sprint A · Batch B8
CEO 2026-09-03 · additive research family runner.

Runs the full 18-test diagnostic (implemented core: T1, T2, T3, T5, T6,
T12, T13, T14, T15, T16 · deferred to enrichers: T4, T7, T8, T9, T10, T11
where substrate is not yet wired).

Emits:
    reports/research/neg_pnl_control_60d/dataset_{market}.json
    reports/research/neg_pnl_control_60d/panel_{market}.json
    reports/research/neg_pnl_control_60d/summary.md
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
        f"# NEG-PNL-CONTROL-60D · {market.upper()} · asof {panel.get('asof_today')}",
        f"_generated {panel.get('built_utc')}_\n",
        "**Governance:** additive research family · NOT a P0 replacement · NOT a stop-tightening prescription.\n",
        "## Recent 60-day protection metrics",
        f"- N positions in window: {panel['protection_recent_60d']['n']}",
        f"- Loss count: {panel['protection_recent_60d']['loss_count']}",
        f"- Loss rate: {round(100*panel['protection_recent_60d']['loss_rate'],1)}%",
        f"- Mean loss (negative pos only): {panel['protection_recent_60d']['mean_loss']}",
        f"- Max loss: {panel['protection_recent_60d']['max_loss']}",
        "\n## Historical baseline (full dataset)",
    ]
    hist = panel.get("historical_baseline_full_dataset") or {}
    lines.append(f"- N: {hist.get('n', 0)} · Mean: {hist.get('mean')} · Loss rate: {round(100*(hist.get('loss_rate') or 0),1)}%")
    lines.append("\n## Trajectory classification")
    for k, v in (panel.get("trajectory_classification") or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("\n## MFE/MAE buckets")
    for k, v in (panel.get("mfe_mae_buckets") or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("\n## Counterfactual variants · protection vs damage")
    lines.append("| Variant | n_exit | Δ mean P&L | 95% CI | p_two | winners_sacrificed | winner_rate |")
    lines.append("|---|---:|---:|---|---:|---:|---:|")
    for v in (panel.get("counterfactual_variants") or []):
        name = (f"static_pct@{v['threshold_pct']}"
                if v.get("doctrine") == "static_pct"
                else f"static_time@{v['timing_days']}d")
        ci = v["paired_bootstrap"]
        lines.append(
            f"| {name} | {v['n_exited_early']} | "
            f"{round(v['protection']['delta']*100,3)}% | "
            f"[{round((ci.get('ci_low') or 0)*100,3)}%, {round((ci.get('ci_high') or 0)*100,3)}%] | "
            f"{round(ci.get('p_two') or 0,3)} | "
            f"{v['damage']['n_winners_sacrificed']} | "
            f"{round(100*v['damage']['winner_sacrifice_rate'],1)}% |"
        )
    lines.append(f"\n**Trial family count:** {panel.get('trial_count_family')} · any 'best' selection deflates by this.")
    lines.append("\n## False-negative analysis (deep losers still missed)")
    for row in (panel.get("false_negative_table") or []):
        an = row.get("false_negative_analysis")
        if an:
            lines.append(f"- {row['variant']} · deep losers={an['n_deep']} · missed by variant={an['n_missed_by_variant']}")
    lines.append("")
    lines.append(f"## Governance\n\n{panel.get('governance_reminder')}\n")
    p = root / "reports" / "research" / "neg_pnl_control_60d" / f"summary_{market}.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    from backend.research.neg_pnl_control_60d import (
        build_60d_dataset, analyze_trajectories,
        run_counterfactual_controls, build_panel,
    )
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        ds = build_60d_dataset(root, m, args.asof)
        if ds.get("status") in ("OUTCOME_DATASET_MISSING","OUTCOME_DATASET_EMPTY",
                                 "NO_POSITIONS_IN_WINDOW"):
            print(json.dumps(ds, indent=2, default=str)); continue
        traj = analyze_trajectories(ds)
        cf = run_counterfactual_controls(ds)
        panel = build_panel(root, m, ds, traj, cf)
        md = render_md(root, m, panel)
        print(f"[neg-pnl-60d] {m} · positions={ds.get('n_positions')} · md={md.relative_to(root)}")
        print(json.dumps(panel, indent=2, default=str)[:1500])


if __name__ == "__main__":
    main()
