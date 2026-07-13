"""
india/ai_lab/lab_reporting.py — dynamic Markdown + CSV report generation.

Consumes a run bundle from lab_runner.run_experiment() and a gate-verdict dict from
lab_runner.evaluate_gates(), then emits:
- reports/<lab_id>_<date>.md      — human-facing narrative + tables
- reports/<lab_id>_diagnostics_<date>.csv — machine-parseable per-(cash, cost, candidate) rows

Report layout is config-driven: the candidate ordering, gate list, period labels, and metric
column set all come from the YAML config or the results themselves. No experiment-specific
strings are hardcoded here.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import subprocess
import pandas as pd
import numpy as np

from india.ai_lab.lab_config import ExperimentConfig
from india.ai_lab.lab_runner import evaluate_gates


# ------------------------------ FORMATTING ------------------------------

def _fmt(x, kind="num"):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    if kind == "pct":   return f"{x*100:+.1f}%"
    if kind == "pctabs":return f"{x*100:.1f}%"
    if kind == "num":   return f"{x:+.2f}"
    if kind == "raw":   return f"{x:.2f}"
    if kind == "int":   return f"{int(x)}"
    return str(x)


def _git_commit_hash() -> str:
    """Best-effort git commit hash for provenance. Returns 'not-a-git-repo' on failure."""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                           timeout=5)
        return r.stdout.strip() if r.returncode == 0 else "not-a-git-repo"
    except Exception:
        return "not-a-git-repo"


# ------------------------------ REPORT ------------------------------

def write_report(bundle: dict, out_dir: Path = None) -> tuple[Path, Path]:
    """Write markdown + CSV. Returns (md_path, csv_path)."""
    config: ExperimentConfig = bundle["config"]
    results = bundle["results"]
    n_trials = bundle["n_trials"]
    pbo_by_cash = bundle["pbo_by_cash"]
    stability_by_cash = bundle["stability_by_cash"]

    cash_grid = config.simulation["cash_returns_annual"]
    cost_grid = config.simulation["cost_grid_bps"]
    canonical_cost = cost_grid[0]
    ctrl_id = config.control_id()
    non_ctrl = config.candidate_ids(exclude_control=True)

    out_dir = out_dir or (config.config_path.parent / config.reporting["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now().date().isoformat()
    md_name = config.reporting["report_name_template"].format(lab_id=config.lab_id, date=date)
    csv_name = config.reporting["diagnostics_name_template"].format(lab_id=config.lab_id, date=date)
    md_path = out_dir / md_name
    csv_path = out_dir / csv_name

    # ----- Gate verdicts across all candidates × cash assumptions -----
    verdicts = {}
    for cid in non_ctrl:
        verdicts[cid] = {}
        for cash in cash_grid:
            cand = results[cash][canonical_cost][cid]
            n0 = results[cash][canonical_cost][ctrl_id]
            cand50 = results[cash][cost_grid[-1]][cid]
            n050 = results[cash][cost_grid[-1]][ctrl_id]
            verdicts[cid][cash] = evaluate_gates(config, cash, cand, n0,
                                                  cost_50bps_result=cand50,
                                                  control_50bps_result=n050)

    lines = [
        f"# {config.lab_id} — {config.lab_name} · Results Report {date}", "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_", "",
        f"- **Config file**: `{config.config_path.name}`",
        f"- **Config hash**: `{config.config_hash}`",
        f"- **Git commit**: `{_git_commit_hash()}`",
        f"- **Pre-registration**: `{config.preregistration_file.name}`",
        f"- **Trial manifest**: `{config.trial_manifest_path.name}`",
        f"- **n_trials (cumulative Lab-wide)**: **{n_trials}**",
        f"- **Cash returns tested**: {[f'{100*c:.0f}%' for c in cash_grid]}",
        f"- **Cost grid (bps)**: {list(cost_grid)}",
        f"- **Control (N0)**: `{ctrl_id}` — {config.candidates[ctrl_id].get('description', '')}", "",
    ]

    # ----- Executive summary -----
    lines.append("## Executive summary")
    lines.append("")
    header = ["Candidate", "Overall verdict"] + [f"gates (cash={100*c:.0f}%)" for c in cash_grid]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    n_gates = len(config.gates)
    for cid in non_ctrl:
        v = verdicts[cid]
        overall = "✅ PROMOTE-ELIGIBLE" if all(v[c]["all_pass"] for c in cash_grid) else "❌ REJECT"
        cells = [cid, overall]
        for cash in cash_grid:
            gate_str = "".join(
                ("1" if v[cash]["gates"][g["id"]]["pass"] else "0") for g in config.gates)
            cells.append(gate_str)
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(f"(Gate strings read G1..G{n_gates} left→right; 1=pass, 0=fail. "
                 f"Candidate promotes only if ALL {n_gates} gates pass under EVERY cash-return assumption.)")
    lines.append("")

    # ----- Per-candidate detail -----
    for cid in [ctrl_id] + non_ctrl:
        title = config.candidates[cid].get("description", cid)
        lines.append(f"## {cid} — {title}")
        lines.append("")
        for cash in cash_grid:
            lines.append(f"### Cash return = {100*cash:.0f}% annualized")
            r = results[cash][canonical_cost][cid]
            lines.append(f"**{canonical_cost} bps** · Full: "
                         f"CAGR {_fmt(r['full']['cagr'],'pct')} · "
                         f"Sharpe {_fmt(r['full']['sharpe'],'raw')} · "
                         f"MaxDD {_fmt(r['full']['max_dd'],'pct')} · "
                         f"Ulcer {_fmt(r['full']['ulcer'],'raw')} · "
                         f"DSR {_fmt(r['dsr']['dsr'],'raw')}")
            lines.append("")
            lines.append("| Period | CAGR | Sharpe | Sortino | MaxDD | CVaR(5%) | Ulcer | avg exp | min exp |")
            lines.append("|---|---|---|---|---|---|---|---|---|")
            for pname, pd_ in (("Discovery", r["disc"]), ("Confirmation", r["conf"]), ("Full", r["full"])):
                lines.append(f"| {pname} | "
                             f"{_fmt(pd_['cagr'],'pct')} | {_fmt(pd_['sharpe'],'raw')} | "
                             f"{_fmt(pd_['sortino'],'raw')} | {_fmt(pd_['max_dd'],'pct')} | "
                             f"{_fmt(pd_['cvar5'],'pct')} | {_fmt(pd_['ulcer'],'raw')} | "
                             f"{_fmt(pd_.get('avg_exp'),'raw')} | {_fmt(pd_.get('min_exp'),'raw')} |")
            lines.append("")
            if r["regime"]:
                lines.append("Regime attribution (full period):")
                lines.append("| Regime | # cycles | CAGR | MaxDD | Ulcer |")
                lines.append("|---|---|---|---|---|")
                for reg_name in ("Strong", "Neutral", "Weak"):
                    rm = r["regime"].get(reg_name)
                    if rm is None:
                        continue
                    n = sum(1 for m in r["meta"] if m.get("regime") == reg_name)
                    lines.append(f"| {reg_name} | {n} | {_fmt(rm['cagr'],'pct')} | "
                                 f"{_fmt(rm['max_dd'],'pct')} | {_fmt(rm['ulcer'],'raw')} |")
                lines.append("")
            lines.append("Cost sensitivity (same policy, different friction — NOT a PBO input):")
            lines.append("| Cost | CAGR | Sharpe | MaxDD | Ulcer | avg exp |")
            lines.append("|---|---|---|---|---|---|")
            for cost in cost_grid:
                r2 = results[cash][cost][cid]
                lines.append(f"| {cost} bps | {_fmt(r2['full']['cagr'],'pct')} | "
                             f"{_fmt(r2['full']['sharpe'],'raw')} | {_fmt(r2['full']['max_dd'],'pct')} | "
                             f"{_fmt(r2['full']['ulcer'],'raw')} | {_fmt(r2['full']['avg_exp'],'raw')} |")
            lines.append("")

    # ----- Gate verdicts -----
    lines.append("## Gate verdicts (locked pre-registration)")
    lines.append("")
    for cid in non_ctrl:
        lines.append(f"### {cid}")
        for cash in cash_grid:
            lines.append(f"**Cash={100*cash:.0f}%**")
            v = verdicts[cid][cash]
            for g in config.gates:
                gv = v["gates"][g["id"]]
                icon = "✅" if gv["pass"] else "❌"
                err = f" · ERROR: {gv['error']}" if gv["error"] else ""
                lines.append(f"- {icon} **{g['id']}** — {g['name']}: `{gv['expression']}`{err}")
            lines.append(f"- **ALL {n_gates}**: {'✅ PASS' if v['all_pass'] else '❌ FAIL'}")
            lines.append("")

    # ----- PBO + Fold stability -----
    lines.append("## PBO + Fold Sharpe rank stability")
    lines.append("")
    for cash in cash_grid:
        pbo = pbo_by_cash[cash]
        val_str = f" value = {pbo['value']:.3f} ·" if pbo["status"] == "computed" else ""
        lines.append(f"**Cash={100*cash:.0f}%** · PBO status: **{pbo['status']}** ·{val_str} {pbo['note']}")
        lines.append("")
        ranks_df, top2 = stability_by_cash[cash]
        if not ranks_df.empty:
            lines.append("Per-fold Sharpe rank (1 = best):")
            lines.append("| Fold | " + " | ".join(ranks_df.columns) + " |")
            lines.append("|" + "|".join(["---"] * (1 + len(ranks_df.columns))) + "|")
            for fold, row in ranks_df.iterrows():
                lines.append(f"| {fold} | " + " | ".join(str(int(v)) for v in row) + " |")
            lines.append("")
            lines.append("Fraction of folds ranked in top-2:")
            lines.append("| " + " | ".join(top2.keys()) + " |")
            lines.append("|" + "|".join(["---"] * len(top2)) + "|")
            lines.append("| " + " | ".join(f"{100*v:.0f}%" for v in top2.values()) + " |")
            lines.append("")

    # ----- Final verdict -----
    lines.append("## Final verdict")
    lines.append("")
    promoted = [cid for cid in non_ctrl if all(verdicts[cid][c]["all_pass"] for c in cash_grid)]
    if promoted:
        lines.append(f"**PROMOTE-ELIGIBLE (subject to operator approval)**: {', '.join(promoted)}")
    else:
        lines.append(f"**REJECT — no candidate clears all {n_gates} gates under every cash-return assumption.**")
        lines.append("")
        lines.append(f"Control (`{ctrl_id}`) remains frozen. No Core or Telegram changes.")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    # ----- Diagnostics CSV -----
    diag_rows = []
    for cash in cash_grid:
        for cost in cost_grid:
            for cid in [ctrl_id] + non_ctrl:
                r = results[cash][cost][cid]
                row = {
                    "cash_annual": cash, "cost_bps": cost, "candidate": cid,
                    "cagr_full": r["full"]["cagr"], "sharpe_full": r["full"]["sharpe"],
                    "max_dd_full": r["full"]["max_dd"], "ulcer_full": r["full"]["ulcer"],
                    "cvar5_full": r["full"]["cvar5"], "avg_exp": r["full"]["avg_exp"],
                    "cagr_disc": r["disc"]["cagr"], "max_dd_disc": r["disc"]["max_dd"],
                    "ulcer_disc": r["disc"]["ulcer"],
                    "cagr_conf": r["conf"]["cagr"], "max_dd_conf": r["conf"]["max_dd"],
                    "ulcer_conf": r["conf"]["ulcer"], "cvar5_conf": r["conf"]["cvar5"],
                    "dsr": r["dsr"]["dsr"],
                }
                if r["regime"]:
                    w = r["regime"].get("Weak", {})
                    row.update({
                        "weak_cagr": w.get("cagr", np.nan),
                        "weak_dd": w.get("max_dd", np.nan),
                        "weak_ulcer": w.get("ulcer", np.nan),
                    })
                diag_rows.append(row)
    pd.DataFrame(diag_rows).to_csv(csv_path, index=False)

    return md_path, csv_path
