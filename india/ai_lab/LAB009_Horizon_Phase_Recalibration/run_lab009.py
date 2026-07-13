"""
LAB009 runner — YAML-driven, phase-aware, realistic-cost.

Orchestrates 16 (horizon × phase) simulations, aggregates per horizon (median + worst +
phase_top2_sharpe + cost_drag), evaluates 6 sealed gates via AST-safe evaluator, writes a
markdown report + diagnostics CSV.

Run:  python india/ai_lab/LAB009_Horizon_Phase_Recalibration/run_lab009.py
"""
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path
import statistics
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from india.ai_lab.lab_config import load_experiment_config
from india.ai_lab.lab_metrics import (
    metric_suite, period_metrics, read_trial_manifest_count, pbo_across_configs,
    sharpe_rank_stability,
)
from india.ai_lab.lab_runner import evaluate_gates
from india.validation import deflated_sharpe
from india.ai_lab.LAB009_Horizon_Phase_Recalibration.horizon_phase_policies import (
    build_context, phase_offsets_for, build_registry_for_horizon_phase,
    simulate_horizon_phase, compute_common_window,
)


REPORTS = Path(__file__).parent / "reports"
REPORTS.mkdir(exist_ok=True)


# --------------------------- AGGREGATION HELPERS ---------------------------

def _worst_by_direction(values: list, metric: str):
    """Return the WORST value across phases according to metric-specific direction."""
    values = [v for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not values:
        return float("nan")
    # Lower-is-worse metrics: CAGR, Sharpe, Sortino, DSR, total_ret
    if metric in {"cagr", "sharpe", "sortino", "dsr", "total_ret"}:
        return min(values)
    # More-negative-is-worse (MaxDD, CVaR5)
    if metric in {"max_dd", "cvar5"}:
        return min(values)
    # Higher-is-worse (Ulcer, recovery days)
    if metric in {"ulcer", "recovery_days"}:
        return max(values)
    return float("nan")


def _median(values: list):
    values = [v for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    return float(statistics.median(values)) if values else float("nan")


def _aggregate_phases(phase_period_metrics: list[dict]) -> dict:
    """Aggregate a list of per-phase metric_suite dicts into a single dict with the same keys.
    Median (each metric) + worst-by-direction (each metric)."""
    keys = ["cagr", "sharpe", "sortino", "max_dd", "cvar5", "ulcer", "recovery_days",
            "avg_exp", "min_exp", "n_exp_changes", "total_ret", "years",
            "total_exits", "cycles_with_any_exit", "false_exit_rate", "opportunity_cost"]
    median_out = {k: _median([pm.get(k) for pm in phase_period_metrics]) for k in keys}
    return median_out


def _aggregate_worst(phase_period_metrics: list[dict]) -> dict:
    keys_lower_is_worse = ("cagr", "sharpe", "sortino", "total_ret")
    keys_more_negative = ("max_dd", "cvar5")
    keys_higher_is_worse = ("ulcer", "recovery_days")
    out = {}
    for k in keys_lower_is_worse + keys_more_negative:
        out[k] = _worst_by_direction([pm.get(k) for pm in phase_period_metrics], k)
    for k in keys_higher_is_worse:
        out[k] = _worst_by_direction([pm.get(k) for pm in phase_period_metrics], k)
    return out


# --------------------------- MAIN ---------------------------

def main():
    print("=" * 70)
    print("  LAB009 EXECUTION — per sealed 2026-07-13 preregistration")
    print("=" * 70)

    cfg_path = Path(__file__).parent / "lab009.yaml"
    config = load_experiment_config(cfg_path)
    print(f"  Config: {cfg_path.name}  hash: {config.config_hash}")

    n_trials = read_trial_manifest_count(config.trial_manifest_path)
    print(f"  n_trials from central manifest: {n_trials}")
    if n_trials != 38:
        raise RuntimeError(f"Expected cumulative_strategy_search=38 after LAB009 seal, "
                           f"manifest returned {n_trials}. Update the manifest first.")

    trading_days = config.trading_days()
    canon_cost = config.canonical_cost()
    stress_cost = config.stress_cost()
    print(f"  trading_days_per_year={trading_days}  canonical={canon_cost}bps  stress={stress_cost}bps")

    context = build_context(rolling_min_periods=int(config.policy_parameters["rolling_min_periods"]))
    print(f"  closes {context['closes'].shape}   exp_series {len(context['exp_series'])} bars")

    # ----- Build all 16 registries (horizon × phase) -----
    horizons_by_cid = {cid: int(cfg["horizon_days"]) for cid, cfg in config.candidates.items()}
    all_registries = {}
    print("\n  Building per-(horizon, phase) registries...")
    for cid, h in horizons_by_cid.items():
        for p in phase_offsets_for(h):
            reg = build_registry_for_horizon_phase(h, p, context["closes"], context["rets"])
            all_registries[(cid, h, p)] = reg
            print(f"    {cid} H={h:>2}d phase={p:>2}: {reg['rec_id'].nunique()} cycles "
                  f"[{reg['asof'].min()} → {reg['asof'].max()}]")

    # ----- Common evaluation window -----
    common_start, common_end = compute_common_window(
        {(h, p): reg for (cid, h, p), reg in all_registries.items()})
    print(f"\n  COMMON WINDOW: {common_start.date()} → {common_end.date()}")

    # ----- Cycle counts inside common window (report) -----
    print("\n  Cycle counts INSIDE common window (H×P × period × regime):")
    disc_end = pd.Timestamp(config.periods["discovery_end"]).normalize()
    conf_start = pd.Timestamp(config.periods["confirmation_start"]).normalize()
    hp_counts = []
    for (cid, h, p), reg in all_registries.items():
        reg_iw = reg.copy()
        reg_iw["asof"] = pd.to_datetime(reg_iw["asof"]).dt.normalize()
        iw = reg_iw[(reg_iw["asof"] >= common_start) & (reg_iw["asof"] <= common_end)]
        n_full = iw["rec_id"].nunique()
        n_disc = iw[iw["asof"] <= disc_end]["rec_id"].nunique()
        n_conf = iw[iw["asof"] >= conf_start]["rec_id"].nunique()
        # Regime counts using exp_series at asof
        n_regime = {"Strong": 0, "Neutral": 0, "Weak": 0}
        for asof in iw["asof"].unique():
            e = float(context["exp_series"].reindex([pd.Timestamp(asof)], method="ffill").iloc[0])
            b = config.regime_bucket_for(e)
            if b in n_regime:
                n_regime[b] += 1
        hp_counts.append({
            "candidate": cid, "horizon": h, "phase": p,
            "n_full": n_full, "n_disc": n_disc, "n_conf": n_conf, **n_regime,
        })
    hp_counts_df = pd.DataFrame(hp_counts)
    print(hp_counts_df.to_string(index=False))

    # ----- Run all 16 configs at each cash × cost -----
    cash_grid = config.simulation["cash_returns_annual"]
    cost_grid = config.simulation["cost_grid_bps"]
    print(f"\n  Running {len(all_registries)} configs × {len(cash_grid)} cash × {len(cost_grid)} cost = "
          f"{len(all_registries) * len(cash_grid) * len(cost_grid)} sims...")

    # results[cash][cost][cid][phase] = {equity, meta, full, disc, conf, regime, dsr}
    results: dict = {c: {b: {cid: {} for cid in horizons_by_cid} for b in cost_grid} for c in cash_grid}
    for cash in cash_grid:
        for cost in cost_grid:
            for (cid, h, p), reg in all_registries.items():
                eq, meta = simulate_horizon_phase(
                    reg, context["closes"], context["exp_series"],
                    common_start, common_end,
                    initial_capital=float(config.simulation["initial_capital"]),
                    cash_return_annual=float(cash), cost_bps=float(cost),
                    trading_days_per_year=trading_days,
                )
                # Regime attribution: assign bucket per cycle from exp_series
                for m in meta:
                    e = float(context["exp_series"].reindex([m["asof"]], method="ffill").iloc[0])
                    m["regime"] = config.regime_bucket_for(e)
                full = metric_suite(eq, meta, trading_days=trading_days)
                disc_asofs = {pd.Timestamp(m["asof"]).normalize() for m in meta
                              if pd.Timestamp(m["asof"]).normalize() <= disc_end}
                conf_asofs = {pd.Timestamp(m["asof"]).normalize() for m in meta
                              if pd.Timestamp(m["asof"]).normalize() >= conf_start}
                disc = period_metrics(eq, meta, disc_asofs, trading_days=trading_days)
                conf = period_metrics(eq, meta, conf_asofs, trading_days=trading_days)
                # Regime attribution period-metrics
                reg_metrics = {}
                for reg_name in [b.name for b in config.regimes["buckets"]]:
                    reg_asofs = {pd.Timestamp(m["asof"]).normalize() for m in meta
                                 if m.get("regime") == reg_name}
                    reg_metrics[reg_name] = period_metrics(eq, meta, reg_asofs, trading_days=trading_days)
                dsr_d = deflated_sharpe(eq.pct_change().dropna(), n_trials=n_trials)
                results[cash][cost][cid][p] = {
                    "equity": eq, "meta": meta,
                    "full": full, "disc": disc, "conf": conf, "regime": reg_metrics,
                    "dsr": dsr_d,
                }
        print(f"    cash={100*cash:.0f}% done")

    # ----- Horizon-level aggregation -----
    # For each candidate horizon, aggregate metrics across its 4 phases.
    horizon_results: dict = {c: {b: {} for b in cost_grid} for c in cash_grid}
    for cash in cash_grid:
        for cost in cost_grid:
            for cid, h in horizons_by_cid.items():
                phases = phase_offsets_for(h)
                phase_dicts = [results[cash][cost][cid][p] for p in phases]

                # Median + worst across phases for full/disc/conf periods
                median_agg = {
                    "full": _aggregate_phases([pd["full"] for pd in phase_dicts]),
                    "disc": _aggregate_phases([pd["disc"] for pd in phase_dicts]),
                    "conf": _aggregate_phases([pd["conf"] for pd in phase_dicts]),
                    "dsr":  {"dsr": _median([pd["dsr"]["dsr"] for pd in phase_dicts])},
                    "regime": {
                        rn: _aggregate_phases([pd["regime"][rn] for pd in phase_dicts])
                        for rn in [b.name for b in config.regimes["buckets"]]
                    },
                }
                worst_agg = {
                    "full": _aggregate_worst([pd["full"] for pd in phase_dicts]),
                    "disc": _aggregate_worst([pd["disc"] for pd in phase_dicts]),
                    "conf": _aggregate_worst([pd["conf"] for pd in phase_dicts]),
                    "dsr":  {"dsr": min([pd["dsr"]["dsr"] for pd in phase_dicts
                                          if pd["dsr"]["dsr"] == pd["dsr"]["dsr"]] or [float("nan")])},
                }

                # phase_top2_sharpe computed at end (needs all candidates for the same cash+cost)
                horizon_results[cash][cost][cid] = {
                    "median": median_agg, "worst": worst_agg,
                    "phases": {p: results[cash][cost][cid][p] for p in phases},
                    "horizon_days": h,
                    # placeholders — filled below
                    "phase_top2_sharpe": None,
                    "cost_drag": None,
                    # Convenience: expose median.full etc at top level too so standard write_report works
                    "full": median_agg["full"], "disc": median_agg["disc"], "conf": median_agg["conf"],
                    "regime": median_agg["regime"], "dsr": median_agg["dsr"],
                    # Meta placeholder for write_report (aggregate — no per-cycle detail)
                    "meta": [],
                }

    # ----- phase_top2_sharpe: fraction of the 4 phases where THIS candidate ranks in top-2 by Sharpe -----
    for cash in cash_grid:
        for cost in cost_grid:
            for cid in horizons_by_cid:
                h = horizons_by_cid[cid]
                phases = phase_offsets_for(h)
                # For each of THIS candidate's phases p, compare its full.sharpe against the median-phase
                # Sharpe of every OTHER candidate. (Different candidates have different phase-offset sets,
                # so we compare phase-INDEX-wise: this candidate's phase-i Sharpe vs other candidates'
                # phase-i Sharpe by phase INDEX 0..3.)
                fractions = []
                for pi, p in enumerate(phases):
                    my_sharpe = horizon_results[cash][cost][cid]["phases"][p]["full"]["sharpe"]
                    others = []
                    for other_cid, other_h in horizons_by_cid.items():
                        if other_cid == cid:
                            continue
                        other_phases = phase_offsets_for(other_h)
                        other_p = other_phases[pi]        # same phase INDEX (not offset value)
                        other_sh = horizon_results[cash][cost][other_cid]["phases"][other_p]["full"]["sharpe"]
                        others.append(other_sh)
                    # Rank: my_sharpe among (my_sharpe + others), 1 = best
                    all_sh = [my_sharpe] + others
                    all_sh_clean = [v for v in all_sh if v is not None and not (isinstance(v, float) and np.isnan(v))]
                    if my_sharpe is None or (isinstance(my_sharpe, float) and np.isnan(my_sharpe)):
                        fractions.append(0.0)
                        continue
                    rank = sum(1 for v in all_sh_clean if v > my_sharpe) + 1
                    fractions.append(1.0 if rank <= 2 else 0.0)
                horizon_results[cash][cost][cid]["phase_top2_sharpe"] = float(np.mean(fractions))

    # ----- cost_drag: median-phase full CAGR at canonical minus median-phase full CAGR at stress -----
    for cash in cash_grid:
        for cid in horizons_by_cid:
            canon_cagr = horizon_results[cash][canon_cost][cid]["median"]["full"]["cagr"]
            stress_cagr = horizon_results[cash][stress_cost][cid]["median"]["full"]["cagr"]
            horizon_results[cash][canon_cost][cid]["cost_drag"] = float(canon_cagr - stress_cagr)
            horizon_results[cash][stress_cost][cid]["cost_drag"] = float(canon_cagr - stress_cagr)
            for cost in cost_grid:
                if cost not in (canon_cost, stress_cost):
                    horizon_results[cash][cost][cid]["cost_drag"] = float(canon_cagr - stress_cagr)

    # ----- Evaluate gates -----
    print("\n" + "=" * 70)
    print("  GATE VERDICTS (must PASS under BOTH cash assumptions at canonical cost)")
    print("=" * 70)
    verdicts = {}
    ctrl = config.control_id()
    for cid in horizons_by_cid:
        if cid == ctrl:
            continue
        verdicts[cid] = {}
        for cash in cash_grid:
            cand = horizon_results[cash][canon_cost][cid]
            n0 = horizon_results[cash][canon_cost][ctrl]
            v = evaluate_gates(config, cand, n0)
            verdicts[cid][cash] = v
            print(f"    {cid} cash={100*cash:.0f}%:  " +
                  " ".join(f"{g['id']}={'PASS' if v['gates'][g['id']]['pass'] else 'FAIL'}"
                           for g in config.gates))
        overall = all(verdicts[cid][c]["all_pass"] for c in cash_grid)
        print(f"  {cid}: {'PROMOTE-ELIGIBLE' if overall else 'REJECT'}")

    # ----- PBO (diagnostic — dependence caveat) -----
    print("\n  PBO across 16 horizon-phase configs (DIAGNOSTIC only — phase-dependence caveat):")
    pbo_by_cash = {}
    for cash in cash_grid:
        eq_by_config = {}
        for cid in horizons_by_cid:
            for p in phase_offsets_for(horizons_by_cid[cid]):
                eq_by_config[f"{cid}_p{p}"] = results[cash][canon_cost][cid][p]["equity"]
        common_idx = None
        for eq in eq_by_config.values():
            common_idx = eq.index if common_idx is None else common_idx.intersection(eq.index)
        if common_idx is not None and len(common_idx) >= 30:
            R = pd.DataFrame({name: eq.reindex(common_idx).pct_change() for name, eq in eq_by_config.items()}).dropna(how="any")
            pbo = pbo_across_configs(R, S=config.pbo["folds"],
                                     min_configs_for_interpretation=config.pbo["min_configs_for_interpretation"])
        else:
            pbo = {"status": "N/A", "value": float("nan"), "note": "insufficient common index",
                   "n_configs": 0, "s_folds": 0}
        pbo_by_cash[cash] = pbo
        print(f"    cash={100*cash:.0f}%: status={pbo['status']}, value={pbo['value']}, note='{pbo['note']}'")

    # ----- Write report + diagnostics -----
    _write_report(config, hp_counts_df, common_start, common_end, horizon_results, results,
                   verdicts, pbo_by_cash, n_trials)


# --------------------------- REPORT ---------------------------

def _fmt(x, kind="num"):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    if kind == "pct":   return f"{x*100:+.1f}%"
    if kind == "raw":   return f"{x:.3f}"
    if kind == "int":   return f"{int(x)}"
    if kind == "num":   return f"{x:+.3f}"
    return str(x)


def _write_report(config, hp_counts_df, common_start, common_end, horizon_results,
                   phase_results, verdicts, pbo_by_cash, n_trials):
    now = datetime.now().date().isoformat()
    md_name = config.reporting["report_name_template"].format(lab_id=config.lab_id, date=now)
    csv_name = config.reporting["diagnostics_name_template"].format(lab_id=config.lab_id, date=now)
    md = REPORTS / md_name
    csv = REPORTS / csv_name

    ctrl = config.control_id()
    non_ctrl = [c for c in config.candidates if c != ctrl]
    cash_grid = config.simulation["cash_returns_annual"]
    cost_grid = config.simulation["cost_grid_bps"]
    canon = config.canonical_cost()
    stress = config.stress_cost()

    lines = [
        f"# LAB009 · Horizon Recalibration (turnover + phase) — Results Report {now}", "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_", "",
        f"- **Config file**: `{config.config_path.name}` · hash `{config.config_hash}`",
        f"- **Preregistration**: `{config.preregistration_file.name}`",
        f"- **n_trials (cumulative Lab-wide)**: **{n_trials}**",
        f"- **Common evaluation window**: `{common_start.date()}` → `{common_end.date()}`",
        f"- **Cash returns**: {[f'{100*c:.0f}%' for c in cash_grid]}",
        f"- **Cost grid (bps)**: canonical={canon}, stress={stress}",
        f"- **Cost model**: Formulation B EXTENDED (effective portfolio weights incl. cash bucket, one-sided cost basis)",
        "",
        "## Horizon × Phase cycle counts (inside common window)",
        "",
        "| Candidate | Horizon | Phase | Full | Discovery | Confirmation | Strong | Neutral | Weak |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in hp_counts_df.itertuples(index=False):
        lines.append(f"| {row.candidate} | {row.horizon} | {row.phase} | {row.n_full} | "
                     f"{row.n_disc} | {row.n_conf} | {row.Strong} | {row.Neutral} | {row.Weak} |")
    lines.append("")

    # Aggregate metric table per horizon (at canonical cost, both cash assumptions)
    for cash in cash_grid:
        lines.append(f"## Horizon-aggregate metrics — cash={100*cash:.0f}% · cost={canon} bps (canonical)")
        lines.append("")
        lines.append("| Cand | median CAGR | worst CAGR | median Sharpe | worst Sharpe | worst MaxDD | median Ulcer | worst Ulcer | median DSR | worst DSR | phase top-2 | cost_drag (pp) |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for cid in [ctrl] + non_ctrl:
            hr = horizon_results[cash][canon][cid]
            lines.append(f"| {cid} | "
                         f"{_fmt(hr['median']['full']['cagr'],'pct')} | "
                         f"{_fmt(hr['worst']['full']['cagr'],'pct')} | "
                         f"{_fmt(hr['median']['full']['sharpe'],'raw')} | "
                         f"{_fmt(hr['worst']['full']['sharpe'],'raw')} | "
                         f"{_fmt(hr['worst']['full']['max_dd'],'pct')} | "
                         f"{_fmt(hr['median']['full']['ulcer'],'raw')} | "
                         f"{_fmt(hr['worst']['full']['ulcer'],'raw')} | "
                         f"{_fmt(hr['median']['dsr']['dsr'],'raw')} | "
                         f"{_fmt(hr['worst']['dsr']['dsr'],'raw')} | "
                         f"{_fmt(hr['phase_top2_sharpe'],'raw')} | "
                         f"{_fmt(hr['cost_drag']*100,'raw')}pp |")
        lines.append("")

        # Confirmation-period detail at canonical cost
        lines.append(f"### Confirmation-period medians — cash={100*cash:.0f}% · canonical cost")
        lines.append("| Cand | median CAGR | median Sharpe | median MaxDD | median Ulcer |")
        lines.append("|---|---|---|---|---|")
        for cid in [ctrl] + non_ctrl:
            hr = horizon_results[cash][canon][cid]
            lines.append(f"| {cid} | {_fmt(hr['median']['conf']['cagr'],'pct')} | "
                         f"{_fmt(hr['median']['conf']['sharpe'],'raw')} | "
                         f"{_fmt(hr['median']['conf']['max_dd'],'pct')} | "
                         f"{_fmt(hr['median']['conf']['ulcer'],'raw')} |")
        lines.append("")

    # Gate verdicts
    lines.append("## Gate verdicts (locked preregistration; must PASS under BOTH cash assumptions)")
    lines.append("")
    for cid in non_ctrl:
        lines.append(f"### {cid}")
        for cash in cash_grid:
            v = verdicts[cid][cash]
            lines.append(f"**Cash={100*cash:.0f}%**")
            for g in config.gates:
                gv = v["gates"][g["id"]]
                icon = "✅" if gv["pass"] else "❌"
                err = f" · ERROR: {gv['error']}" if gv.get("error") else ""
                lines.append(f"- {icon} **{g['id']}** — {g['name']}: `{gv['expression']}`{err}")
            lines.append(f"- **ALL 6**: {'✅ PASS' if v['all_pass'] else '❌ FAIL'}")
            lines.append("")

    # PBO diagnostic
    lines.append("## PBO across 16 horizon-phase configs (DIAGNOSTIC ONLY — phase-dependence caveat)")
    lines.append("")
    for cash in cash_grid:
        pbo = pbo_by_cash[cash]
        vs = f" value = {pbo['value']:.3f} ·" if pbo["status"] == "computed" else ""
        lines.append(f"- Cash={100*cash:.0f}%: status = **{pbo['status']}**{vs} {pbo['note']}")
    lines.append("")
    lines.append("**Interpretation:** Phase configurations within the same horizon share policy "
                 "definition; their per-fold Sharpes are correlated via shared underlying data. "
                 "Treating N=16 as independent strategy hypotheses in CSCV UNDER-adjusts for "
                 "dependence — PBO is diagnostic here, NOT a promotion gate. The effective "
                 f"strategy-hypothesis count is 3 (H21/H42/H84), reflected in n_trials={n_trials}.")
    lines.append("")

    # Final verdict
    lines.append("## Final LAB009 verdict")
    lines.append("")
    promoted = [cid for cid in non_ctrl if all(verdicts[cid][c]["all_pass"] for c in cash_grid)]
    if promoted:
        lines.append(f"**PROMOTE-ELIGIBLE (subject to operator approval)**: {', '.join(promoted)}")
    else:
        lines.append(f"**REJECT — no candidate clears all 6 gates under both cash assumptions.**")
        lines.append("")
        lines.append("Production HOLD=63 remains unchanged.")
    lines.append("")
    lines.append("_LAB009 does not modify production even if a candidate promotes; operator "
                 "approval is required for any Core change._")

    md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  report -> {md}")

    # Diagnostics CSV: one row per (cash, cost, cid, phase) plus aggregate marker row per (cash, cost, cid)
    rows = []
    for cash in cash_grid:
        for cost in cost_grid:
            for cid in [ctrl] + non_ctrl:
                h = int(config.candidates[cid]["horizon_days"])
                for p in phase_offsets_for(h):
                    r = phase_results[cash][cost][cid][p]
                    rows.append({
                        "cash_annual": cash, "cost_bps": cost, "candidate": cid,
                        "horizon_days": h, "phase_offset": p, "aggregate": "phase",
                        "cagr_full": r["full"]["cagr"], "sharpe_full": r["full"]["sharpe"],
                        "max_dd_full": r["full"]["max_dd"], "ulcer_full": r["full"]["ulcer"],
                        "cvar5_full": r["full"]["cvar5"], "dsr": r["dsr"]["dsr"],
                        "cagr_disc": r["disc"]["cagr"], "sharpe_disc": r["disc"]["sharpe"],
                        "cagr_conf": r["conf"]["cagr"], "sharpe_conf": r["conf"]["sharpe"],
                        "max_dd_conf": r["conf"]["max_dd"], "ulcer_conf": r["conf"]["ulcer"],
                    })
                # aggregate row
                hr = horizon_results[cash][cost][cid]
                rows.append({
                    "cash_annual": cash, "cost_bps": cost, "candidate": cid,
                    "horizon_days": h, "phase_offset": -1, "aggregate": "median",
                    "cagr_full": hr["median"]["full"]["cagr"], "sharpe_full": hr["median"]["full"]["sharpe"],
                    "max_dd_full": hr["median"]["full"]["max_dd"], "ulcer_full": hr["median"]["full"]["ulcer"],
                    "cvar5_full": hr["median"]["full"]["cvar5"], "dsr": hr["median"]["dsr"]["dsr"],
                    "cagr_disc": hr["median"]["disc"]["cagr"], "sharpe_disc": hr["median"]["disc"]["sharpe"],
                    "cagr_conf": hr["median"]["conf"]["cagr"], "sharpe_conf": hr["median"]["conf"]["sharpe"],
                    "max_dd_conf": hr["median"]["conf"]["max_dd"], "ulcer_conf": hr["median"]["conf"]["ulcer"],
                    "phase_top2_sharpe": hr["phase_top2_sharpe"], "cost_drag": hr["cost_drag"],
                })
                rows.append({
                    "cash_annual": cash, "cost_bps": cost, "candidate": cid,
                    "horizon_days": h, "phase_offset": -2, "aggregate": "worst",
                    "cagr_full": hr["worst"]["full"]["cagr"], "sharpe_full": hr["worst"]["full"]["sharpe"],
                    "max_dd_full": hr["worst"]["full"]["max_dd"], "ulcer_full": hr["worst"]["full"]["ulcer"],
                    "cvar5_full": hr["worst"]["full"]["cvar5"],
                    "cagr_conf": hr["worst"]["conf"]["cagr"], "sharpe_conf": hr["worst"]["conf"]["sharpe"],
                    "max_dd_conf": hr["worst"]["conf"]["max_dd"], "ulcer_conf": hr["worst"]["conf"]["ulcer"],
                })
    pd.DataFrame(rows).to_csv(csv, index=False)
    print(f"  diagnostics -> {csv}")


if __name__ == "__main__":
    main()
