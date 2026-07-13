"""
LAB010 runner — H84 Robustness Validation harness.

DO NOT EXECUTE at seal time. This runner is preregistered together with lab010.yaml. Any
execution must be operator-approved. Sealed 2026-07-13.

Purpose: Validate LAB009's H84 promote-eligible verdict (commit 413a735) under chronological
block-level LOBO and cost stress. Same H84 hypothesis, same phase offsets, same simulator.
Does NOT introduce new candidates, horizons, or phase offsets. Does NOT increment
cumulative_strategy_search (validation of already-counted H84 hypothesis, not new search).

Scopes evaluated (all under cash in {0.0, 0.06}):
  - full,cost:canonical       : LAB009 full-window reproduction, canonical cost (=15bps)
  - full,cost:stress          : LAB009 full-window under stress cost (=50bps)
  - block:B1|B2|B3,cost:canonical  : per-block metrics
  - lobo:LOBO_dropB{1|2|3},cost:canonical : LOBO variants

Run:  python india/ai_lab/LAB010_H84_Robustness_Validation/run_lab010.py
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
)
from india.ai_lab.lab_expression import compile_gate_expression
from india.validation import deflated_sharpe
from india.ai_lab.LAB009_Horizon_Phase_Recalibration.horizon_phase_policies import (
    build_context, phase_offsets_for, build_registry_for_horizon_phase,
    simulate_horizon_phase, compute_common_window,
)


REPORTS = Path(__file__).parent / "reports"
REPORTS.mkdir(exist_ok=True)


# --------------------------- REGISTRY SLICING ---------------------------

def filter_registry_to_ranges(reg_df: pd.DataFrame, ranges: list[tuple]) -> pd.DataFrame:
    """Return the subset of reg_df whose (asof, mature_date) is FULLY contained in AT LEAST
    ONE of the provided (start, end) ranges.

    Mature-bounded rule: row belongs to range iff start <= asof AND mature_date <= end.
    """
    r = reg_df.copy()
    r["asof"] = pd.to_datetime(r["asof"]).dt.normalize()
    r["mature_date"] = pd.to_datetime(r["mature_date"]).dt.normalize()
    mask = pd.Series(False, index=r.index)
    for s, e in ranges:
        s = pd.Timestamp(s).normalize()
        e = pd.Timestamp(e).normalize()
        mask |= ((r["asof"] >= s) & (r["mature_date"] <= e))
    return r[mask].copy()


def scope_ranges(scope_id: str, blocks: dict, lobo_folds: dict) -> list[tuple]:
    """Return the list of (start, end) ranges the given scope covers.

    scope_id: 'full' | 'block:B<n>' | 'lobo:LOBO_dropB<n>'
    """
    if scope_id == "full":
        starts = [pd.Timestamp(b["start"]) for b in blocks.values()]
        ends = [pd.Timestamp(b["end"]) for b in blocks.values()]
        return [(min(starts), max(ends))]
    if scope_id.startswith("block:"):
        bid = scope_id.split(":", 1)[1]
        b = blocks[bid]
        return [(pd.Timestamp(b["start"]), pd.Timestamp(b["end"]))]
    if scope_id.startswith("lobo:"):
        lid = scope_id.split(":", 1)[1]
        excluded = lobo_folds[lid]["exclude"]
        return [(pd.Timestamp(b["start"]), pd.Timestamp(b["end"]))
                for bid, b in blocks.items() if bid != excluded]
    raise ValueError(f"Unknown scope: {scope_id}")


# --------------------------- AGGREGATION HELPERS ---------------------------

def _median(values: list) -> float:
    values = [v for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    return float(statistics.median(values)) if values else float("nan")


def _worst_by_direction(values: list, metric: str) -> float:
    values = [v for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not values:
        return float("nan")
    if metric in {"cagr", "sharpe", "sortino", "dsr", "total_ret"}:
        return min(values)
    if metric in {"max_dd", "cvar5"}:
        return min(values)
    if metric in {"ulcer", "recovery_days"}:
        return max(values)
    return float("nan")


def _aggregate_phases(phase_dicts: list[dict]) -> dict:
    keys = ["cagr", "sharpe", "sortino", "max_dd", "cvar5", "ulcer", "recovery_days",
            "avg_exp", "min_exp", "n_exp_changes", "total_ret", "years",
            "total_exits", "cycles_with_any_exit", "false_exit_rate", "opportunity_cost"]
    return {k: _median([pm.get(k) for pm in phase_dicts]) for k in keys}


def _aggregate_worst(phase_dicts: list[dict]) -> dict:
    out = {}
    for k in ("cagr", "sharpe", "sortino", "total_ret", "max_dd", "cvar5"):
        out[k] = _worst_by_direction([pm.get(k) for pm in phase_dicts], k)
    for k in ("ulcer", "recovery_days"):
        out[k] = _worst_by_direction([pm.get(k) for pm in phase_dicts], k)
    return out


# --------------------------- CORE PER-SCOPE SIMULATOR ---------------------------

def run_scope(scope_id: str, cash: float, cost: float, *, all_registries: dict,
              horizons_by_cid: dict, context: dict, config, blocks: dict, lobo_folds: dict,
              conf_start: pd.Timestamp, disc_end: pd.Timestamp, conf_end: pd.Timestamp,
              n_trials: int) -> dict:
    """Run all (candidate, phase) simulations restricted to the scope's cycle ranges.

    Returns a dict {cid: {"median": {...}, "worst": {...}, "phases": {...}, "phase_top2_sharpe": float,
                          "cost_drag": float placeholder}} for every candidate.
    """
    ranges = scope_ranges(scope_id, blocks, lobo_folds)
    span_start = min(r[0] for r in ranges).normalize()
    span_end = max(r[1] for r in ranges).normalize()

    phase_results: dict = {cid: {} for cid in horizons_by_cid}
    for (cid, h, p), reg in all_registries.items():
        reg_scoped = filter_registry_to_ranges(reg, ranges)
        if reg_scoped.empty:
            phase_results[cid][p] = {
                "equity": pd.Series(dtype=float), "meta": [],
                "full": {k: float("nan") for k in ["cagr", "sharpe", "sortino", "max_dd",
                        "cvar5", "ulcer", "recovery_days", "avg_exp", "min_exp",
                        "n_exp_changes", "total_ret", "years", "total_exits",
                        "cycles_with_any_exit", "false_exit_rate", "opportunity_cost"]},
                "disc": {k: float("nan") for k in ["cagr", "sharpe", "max_dd", "ulcer"]},
                "conf": {k: float("nan") for k in ["cagr", "sharpe", "max_dd", "ulcer"]},
                "dsr":  {"dsr": float("nan")},
            }
            continue
        eq, meta = simulate_horizon_phase(
            reg_scoped, context["closes"], context["exp_series"],
            span_start, span_end,
            initial_capital=float(config.simulation["initial_capital"]),
            cash_return_annual=float(cash), cost_bps=float(cost),
            trading_days_per_year=int(config.trading_days()),
        )
        full = metric_suite(eq, meta, trading_days=int(config.trading_days()))
        # discovery/confirmation slices — same mature-bounded rule as LAB009 sealed addendum
        disc_asofs = {pd.Timestamp(m["asof"]).normalize() for m in meta
                      if pd.Timestamp(m["asof"]).normalize() >= span_start
                      and pd.Timestamp(m["mature"]).normalize() <= disc_end}
        conf_asofs = {pd.Timestamp(m["asof"]).normalize() for m in meta
                      if pd.Timestamp(m["asof"]).normalize() >= conf_start
                      and pd.Timestamp(m["mature"]).normalize() <= conf_end}
        disc = period_metrics(eq, meta, disc_asofs, trading_days=int(config.trading_days()))
        conf = period_metrics(eq, meta, conf_asofs, trading_days=int(config.trading_days()))
        dsr_d = deflated_sharpe(eq.pct_change().dropna(), n_trials=n_trials)
        phase_results[cid][p] = {
            "equity": eq, "meta": meta,
            "full": full, "disc": disc, "conf": conf, "dsr": dsr_d,
        }

    # Aggregate per candidate across phases
    aggregated: dict = {}
    for cid, phases in phase_results.items():
        pds = list(phases.values())
        aggregated[cid] = {
            "median": {
                "full": _aggregate_phases([pd["full"] for pd in pds]),
                "disc": _aggregate_phases([pd["disc"] for pd in pds]),
                "conf": _aggregate_phases([pd["conf"] for pd in pds]),
                "dsr":  {"dsr": _median([pd["dsr"]["dsr"] for pd in pds])},
            },
            "worst": {
                "full": _aggregate_worst([pd["full"] for pd in pds]),
                "disc": _aggregate_worst([pd["disc"] for pd in pds]),
                "conf": _aggregate_worst([pd["conf"] for pd in pds]),
            },
            "phases": phase_results[cid],
            "horizon_days": horizons_by_cid[cid],
            "phase_top2_sharpe": None,     # filled below
            "cost_drag": None,             # filled after canonical+stress complete
        }

    # phase_top2_sharpe: preserved for V6 gate_5 (LAB009 reproduction sanity) — under LAB010's
    # 2-candidate universe (N0 + H84) this metric is degenerate (both always in top-2), so it
    # functions as a LIVENESS SENTINEL only, not a robustness check. See preregistration V3.
    for cid, h in horizons_by_cid.items():
        phases = phase_offsets_for(h)
        fractions = []
        for pi, p in enumerate(phases):
            my_sh = phase_results[cid][p]["full"]["sharpe"]
            others = []
            for other_cid, other_h in horizons_by_cid.items():
                if other_cid == cid:
                    continue
                other_p = phase_offsets_for(other_h)[pi]
                other_sh = phase_results[other_cid][other_p]["full"]["sharpe"]
                others.append(other_sh)
            if my_sh is None or (isinstance(my_sh, float) and np.isnan(my_sh)):
                fractions.append(0.0)
                continue
            all_sh = [my_sh] + [v for v in others if v is not None and not (isinstance(v, float) and np.isnan(v))]
            rank = sum(1 for v in all_sh if v > my_sh) + 1
            fractions.append(1.0 if rank <= 2 else 0.0)
        aggregated[cid]["phase_top2_sharpe"] = float(np.mean(fractions))

    # phase_win_rate: fraction of phase INDICES where THIS candidate's phase-Sharpe is >= the
    # OTHER candidate's phase-Sharpe at the same phase index. Non-degenerate under 2-candidate
    # universe. Threshold 0.50 reuses LAB009's "half of phases" semantics. Used by V3 and V6-g5.
    non_control_cids = [c for c in horizons_by_cid if c != "N0"]
    for cid in horizons_by_cid:
        h = horizons_by_cid[cid]
        phases_cid = phase_offsets_for(h)
        # Compare against N0 phase-index-wise (2-cand universe by preregistration)
        wins = []
        for pi, p in enumerate(phases_cid):
            my_sh = phase_results[cid][p]["full"]["sharpe"]
            n0_p = phase_offsets_for(horizons_by_cid["N0"])[pi]
            n0_sh = phase_results["N0"][n0_p]["full"]["sharpe"]
            if (my_sh is None or (isinstance(my_sh, float) and np.isnan(my_sh))
                    or n0_sh is None or (isinstance(n0_sh, float) and np.isnan(n0_sh))):
                wins.append(0.0)
            else:
                wins.append(1.0 if my_sh >= n0_sh else 0.0)
        aggregated[cid]["phase_win_rate"] = float(np.mean(wins)) if wins else float("nan")

    return aggregated


# --------------------------- COST_DRAG (canonical vs stress) ---------------------------

def apply_cost_drag(canonical_agg: dict, stress_agg: dict) -> None:
    """cost_drag = canonical CAGR - stress CAGR (median across phases), mutates in place."""
    for cid in canonical_agg:
        cc = canonical_agg[cid]["median"]["full"]["cagr"]
        sc = stress_agg[cid]["median"]["full"]["cagr"]
        canonical_agg[cid]["cost_drag"] = float(cc - sc)
        stress_agg[cid]["cost_drag"] = float(cc - sc)


# --------------------------- GATE EVALUATION ---------------------------

def build_namespace(cand: dict, n0: dict) -> dict:
    """Build the namespace consumed by AST evaluator for cand + n0 comparisons.

    Exposes cand.median.{full,conf,disc}.{sharpe,cagr,...} and cand.phase_top2_sharpe,
    cand.cost_drag; same for n0.
    """
    class Namespace:
        def __init__(self, d):
            for k, v in d.items():
                if isinstance(v, dict):
                    setattr(self, k, Namespace(v))
                else:
                    setattr(self, k, v)

    def _flatten(agg: dict) -> dict:
        return {
            "median": agg["median"],
            "worst": agg["worst"],
            "phase_top2_sharpe": agg["phase_top2_sharpe"],
            "phase_win_rate": agg.get("phase_win_rate", float("nan")),
            "cost_drag": agg["cost_drag"],
        }

    return {"cand": Namespace(_flatten(cand)), "n0": Namespace(_flatten(n0))}


def parse_gate_scope(scope_str: str, config) -> tuple[str, float]:
    """Return (scope_id, cost_bps) parsed from scope declaration in the YAML gate.

    scope_str examples:
      "full,cost:canonical"
      "full,cost:stress"
      "block:B1,cost:canonical"
      "lobo:LOBO_dropB1,cost:canonical"
    """
    scope_id = None
    kv = {}
    for seg in (s.strip() for s in scope_str.split(",")):
        if ":" in seg:
            k, v = seg.split(":", 1)
            kv[k.strip()] = v.strip()
        elif seg == "full":
            scope_id = "full"
        else:
            raise ValueError(f"Unrecognized scope segment: '{seg}' in '{scope_str}'")
    if scope_id is None:
        if "lobo" in kv:
            scope_id = f"lobo:{kv['lobo']}"
        elif "block" in kv:
            scope_id = f"block:{kv['block']}"
        else:
            raise ValueError(f"No scope root (full/block/lobo) in '{scope_str}'")
    cost_label = kv.get("cost", "canonical")
    if cost_label == "canonical":
        cost_bps = config.canonical_cost()
    elif cost_label == "stress":
        cost_bps = config.stress_cost()
    else:
        raise ValueError(f"Unknown cost label '{cost_label}' in '{scope_str}'")
    return scope_id, cost_bps


def evaluate_lab010_gates(config, scoped_results: dict, cash: float) -> dict:
    """Evaluate every LAB010 gate for a specific cash assumption.

    scoped_results: {scope_id: {cost: {cid: aggregated_dict}}}
    """
    verdicts = {}
    for g in config.gates:
        scope_str = g["scope"]
        scope_id, cost_bps = parse_gate_scope(scope_str, config)

        cand = scoped_results[scope_id][cost_bps]["H84"]
        n0 = scoped_results[scope_id][cost_bps]["N0"]
        ns = build_namespace(cand, n0)

        try:
            fn = compile_gate_expression(g["expression"], allowed_roots=("cand", "n0"))
            passed = bool(fn(ns))
            err = None
        except Exception as exc:
            passed = False
            err = f"{type(exc).__name__}: {exc}"
        verdicts[g["id"]] = {"pass": passed, "expression": g["expression"],
                             "scope": scope_str, "error": err}
    return verdicts


# --------------------------- MAIN ---------------------------

def main():
    print("=" * 70)
    print("  LAB010 EXECUTION — H84 Robustness Validation")
    print("  Sealed 2026-07-13 preregistration")
    print("=" * 70)

    cfg_path = Path(__file__).parent / "lab010.yaml"
    config = load_experiment_config(cfg_path)
    print(f"  Config: {cfg_path.name}  hash: {config.config_hash}")

    n_trials = read_trial_manifest_count(config.trial_manifest_path)
    print(f"  n_trials from central manifest: {n_trials}")
    if n_trials != 38:
        raise RuntimeError(f"Expected cumulative_strategy_search=38 at LAB010 seal, "
                           f"manifest returned {n_trials}. LAB010 does NOT increment trial count.")

    context = build_context(rolling_min_periods=int(config.policy_parameters["rolling_min_periods"]))
    print(f"  closes {context['closes'].shape}   exp_series {len(context['exp_series'])} bars")

    horizons_by_cid = {cid: int(cfg["horizon_days"]) for cid, cfg in config.candidates.items()}
    if set(horizons_by_cid.keys()) != {"N0", "H84"}:
        raise RuntimeError(f"LAB010 candidates must be exactly N0 and H84; got {horizons_by_cid.keys()}")
    if horizons_by_cid["N0"] != 63 or horizons_by_cid["H84"] != 84:
        raise RuntimeError("LAB010 horizons must be N0=63 and H84=84 (LAB009 seal).")

    # Build all registries — 2 candidates × 4 phases = 8
    all_registries = {}
    print("\n  Building per-(horizon, phase) registries...")
    for cid, h in horizons_by_cid.items():
        for p in phase_offsets_for(h):
            reg = build_registry_for_horizon_phase(h, p, context["closes"], context["rets"])
            all_registries[(cid, h, p)] = reg
            print(f"    {cid} H={h:>2}d phase={p:>2}: {reg['rec_id'].nunique()} cycles")

    # Common window — same as LAB009 (all-config bounded)
    common_start, common_end = compute_common_window(
        {(h, p): reg for (cid, h, p), reg in all_registries.items()})
    print(f"\n  COMMON WINDOW (all configs): {common_start.date()} -> {common_end.date()}")

    # Blocks (from YAML)
    blocks = {b["id"]: {"start": b["start"], "end": b["end"]} for b in config.raw["blocks"]}
    lobo_folds = {f["id"]: {"exclude": f["exclude"]} for f in config.raw["lobo_folds"]}
    for bid, b in blocks.items():
        print(f"    Block {bid}: {b['start']} -> {b['end']}")

    # Sealed period boundaries (from LAB009 addendum)
    disc_end = pd.Timestamp(config.periods["discovery_end"]).normalize()
    conf_start = pd.Timestamp(config.periods["confirmation_start"]).normalize()
    conf_end = pd.Timestamp("2026-01-27").normalize()

    # Scopes to compute
    scope_ids = ["full", "block:B1", "block:B2", "block:B3",
                 "lobo:LOBO_dropB1", "lobo:LOBO_dropB2", "lobo:LOBO_dropB3"]

    cash_grid = config.simulation["cash_returns_annual"]
    cost_grid = config.simulation["cost_grid_bps"]
    canon_cost = config.canonical_cost()
    stress_cost = config.stress_cost()

    # cash_scoped[cash][scope_id][cost][cid] = aggregated
    cash_scoped: dict = {c: {sid: {} for sid in scope_ids} for c in cash_grid}

    print("\n  Running scope × cash × cost simulations...")
    for cash in cash_grid:
        for scope_id in scope_ids:
            # Full at both canonical + stress. Others only at canonical.
            costs_needed = [canon_cost, stress_cost] if scope_id == "full" else [canon_cost]
            for cost in costs_needed:
                agg = run_scope(scope_id, cash, cost,
                                all_registries=all_registries,
                                horizons_by_cid=horizons_by_cid,
                                context=context, config=config,
                                blocks=blocks, lobo_folds=lobo_folds,
                                conf_start=conf_start, disc_end=disc_end, conf_end=conf_end,
                                n_trials=n_trials)
                cash_scoped[cash][scope_id][cost] = agg
                print(f"    cash={100*cash:.0f}%  scope={scope_id:<22}  cost={cost}bps  done")
        # cost_drag only meaningful for full (canonical minus stress)
        apply_cost_drag(cash_scoped[cash]["full"][canon_cost],
                        cash_scoped[cash]["full"][stress_cost])
        # Set cost_drag to nan on block/LOBO scopes (not defined there)
        for scope_id in scope_ids:
            if scope_id == "full":
                continue
            for cost in cash_scoped[cash][scope_id]:
                for cid in cash_scoped[cash][scope_id][cost]:
                    cash_scoped[cash][scope_id][cost][cid]["cost_drag"] = float("nan")

    # Evaluate gates per cash
    print("\n" + "=" * 70)
    print("  GATE VERDICTS — must PASS under BOTH cash assumptions")
    print("=" * 70)
    all_verdicts = {}
    for cash in cash_grid:
        v = evaluate_lab010_gates(config, cash_scoped[cash], cash)
        all_verdicts[cash] = v
        print(f"\n  cash={100*cash:.0f}%:")
        for gate_id, gv in v.items():
            icon = "PASS" if gv["pass"] else "FAIL"
            print(f"    {icon}  {gate_id:<28}  ({gv['scope']})")

    # Block-majority rule
    print("\n  Block-majority check (H84 wins Sharpe in >= 2 of 3 blocks per cash):")
    block_majority_pass = {}
    min_wins = int(config.raw["block_majority_min_wins"])
    for cash in cash_grid:
        wins = sum(1 for gid in ("v5_block_B1", "v5_block_B2", "v5_block_B3")
                   if all_verdicts[cash][gid]["pass"])
        block_majority_pass[cash] = (wins >= min_wins)
        print(f"    cash={100*cash:.0f}%: wins={wins}/3  min_required={min_wins}  "
              f"{'PASS' if block_majority_pass[cash] else 'FAIL'}")

    # PBO diagnostic on the full-window canonical case (matches LAB009 semantics)
    print("\n  PBO diagnostic (matches LAB009 across 8 configs = N0+H84, 4 phases each):")
    pbo_by_cash = {}
    for cash in cash_grid:
        eq_by_config = {}
        for cid, h in horizons_by_cid.items():
            for p in phase_offsets_for(h):
                phase = cash_scoped[cash]["full"][canon_cost][cid]["phases"][p]
                if len(phase["equity"]) > 0:
                    eq_by_config[f"{cid}_p{p}"] = phase["equity"]
        common_idx = None
        for eq in eq_by_config.values():
            common_idx = eq.index if common_idx is None else common_idx.intersection(eq.index)
        if common_idx is not None and len(common_idx) >= 30 and len(eq_by_config) >= 6:
            R = pd.DataFrame({name: eq.reindex(common_idx).pct_change() for name, eq in eq_by_config.items()}).dropna(how="any")
            pbo = pbo_across_configs(R, S=config.pbo["folds"],
                                     min_configs_for_interpretation=config.pbo["min_configs_for_interpretation"])
        else:
            pbo = {"status": "N/A", "value": float("nan"), "note": "insufficient common index",
                   "n_configs": len(eq_by_config), "s_folds": 0}
        pbo_by_cash[cash] = pbo
        print(f"    cash={100*cash:.0f}%: status={pbo['status']}, value={pbo.get('value')}, note='{pbo.get('note','')}'")

    # ----- Final LAB010 outcome -----
    print("\n" + "=" * 70)
    print("  LAB010 FINAL OUTCOME")
    print("=" * 70)

    all_gates_pass = all(all(gv["pass"] for gv in v.values()) for v in all_verdicts.values())
    block_majority = all(block_majority_pass.values())

    if all_gates_pass and block_majority:
        outcome = "VALIDATED"
    elif not all_gates_pass or not block_majority:
        outcome = "NOT_VALIDATED"
    else:
        outcome = "INCONCLUSIVE"

    print(f"  Outcome: {outcome}")
    print("  Production HOLD=63 remains unchanged (LAB010 does not modify production).")

    _write_report(config, cash_scoped, all_verdicts, block_majority_pass, pbo_by_cash,
                  n_trials, outcome, common_start, common_end, blocks, lobo_folds)


# --------------------------- REPORT ---------------------------

def _fmt(x, kind="num"):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    if kind == "pct":   return f"{x*100:+.1f}%"
    if kind == "raw":   return f"{x:.4f}"
    if kind == "int":   return f"{int(x)}"
    if kind == "num":   return f"{x:+.4f}"
    return str(x)


def _write_report(config, cash_scoped, all_verdicts, block_majority_pass, pbo_by_cash,
                  n_trials, outcome, common_start, common_end, blocks, lobo_folds):
    now = datetime.now().date().isoformat()
    md_name = config.reporting["report_name_template"].format(date=now)
    csv_name = config.reporting["diagnostics_name_template"].format(date=now)
    md = REPORTS / md_name
    csv = REPORTS / csv_name

    cash_grid = config.simulation["cash_returns_annual"]
    canon = config.canonical_cost()
    stress = config.stress_cost()

    lines = [
        f"# LAB010 · H84 Robustness Validation — Results {now}", "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_", "",
        f"- **Config**: `{config.config_path.name}` · hash `{config.config_hash}`",
        f"- **Preregistration**: `{config.preregistration_file.name}`",
        f"- **n_trials (cumulative, unchanged)**: **{n_trials}**",
        f"- **Common evaluation window (all configs)**: `{common_start.date()}` -> `{common_end.date()}`",
        f"- **Canonical cost**: {canon}bps · **stress**: {stress}bps",
        "",
        "## Blocks (sealed)",
        "",
    ]
    for bid, b in blocks.items():
        lines.append(f"- {bid}: {b['start']} -> {b['end']}")
    lines.append("")

    # Full-window medians per cash
    for cash in cash_grid:
        lines.append(f"## Full-window medians (cash={100*cash:.0f}%, canonical cost)")
        lines.append("")
        lines.append("| Cand | median full Sharpe | median full CAGR | median conf Sharpe | worst full MaxDD | phase top-2 | cost_drag |")
        lines.append("|---|---|---|---|---|---|---|")
        for cid in ("N0", "H84"):
            hr = cash_scoped[cash]["full"][canon][cid]
            lines.append(f"| {cid} | {_fmt(hr['median']['full']['sharpe'],'raw')} | "
                         f"{_fmt(hr['median']['full']['cagr'],'pct')} | "
                         f"{_fmt(hr['median']['conf']['sharpe'],'raw')} | "
                         f"{_fmt(hr['worst']['full']['max_dd'],'pct')} | "
                         f"{_fmt(hr['phase_top2_sharpe'],'raw')} | "
                         f"{_fmt(hr['cost_drag'],'raw')} |")
        lines.append("")

    # Block + LOBO tables
    for cash in cash_grid:
        lines.append(f"## Block-level medians (cash={100*cash:.0f}%, canonical cost)")
        lines.append("")
        lines.append("| Scope | N0 full Sharpe | H84 full Sharpe | H84 - N0 |")
        lines.append("|---|---|---|---|")
        for scope in ("block:B1", "block:B2", "block:B3", "lobo:LOBO_dropB1",
                      "lobo:LOBO_dropB2", "lobo:LOBO_dropB3"):
            n0 = cash_scoped[cash][scope][canon]["N0"]["median"]["full"]["sharpe"]
            h84 = cash_scoped[cash][scope][canon]["H84"]["median"]["full"]["sharpe"]
            delta = (h84 - n0) if (not np.isnan(n0) and not np.isnan(h84)) else float("nan")
            lines.append(f"| {scope} | {_fmt(n0,'raw')} | {_fmt(h84,'raw')} | {_fmt(delta,'raw')} |")
        lines.append("")

    # Gate table
    lines.append("## Gate verdicts (must PASS under BOTH cash assumptions)")
    lines.append("")
    for cash in cash_grid:
        lines.append(f"### cash={100*cash:.0f}%")
        for gate_id, gv in all_verdicts[cash].items():
            icon = "✅" if gv["pass"] else "❌"
            err = f" · ERROR: {gv['error']}" if gv.get("error") else ""
            lines.append(f"- {icon} `{gate_id}`  scope=`{gv['scope']}`  expr=`{gv['expression']}`{err}")
        lines.append(f"- Block majority: {'PASS' if block_majority_pass[cash] else 'FAIL'}")
        lines.append("")

    # PBO
    lines.append("## PBO diagnostic (NOT a gate)")
    lines.append("")
    for cash in cash_grid:
        p = pbo_by_cash[cash]
        vs = f"value={p['value']:.4f}" if p["status"] == "computed" else ""
        lines.append(f"- cash={100*cash:.0f}%: status={p['status']}  {vs}  note='{p.get('note','')}'")
    lines.append("")

    # Outcome
    lines.append("## LAB010 outcome")
    lines.append("")
    lines.append(f"**{outcome}**")
    lines.append("")
    lines.append("Production HOLD=63 remains unchanged. LAB010 does not modify production even under "
                 "VALIDATED. Operator approval separately required for any Core change.")

    md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  report -> {md}")

    # Diagnostics CSV
    rows = []
    for cash in cash_grid:
        for scope in cash_scoped[cash]:
            for cost, cids in cash_scoped[cash][scope].items():
                for cid, agg in cids.items():
                    rows.append({
                        "cash_annual": cash, "cost_bps": cost, "scope": scope, "candidate": cid,
                        "sharpe_full_median": agg["median"]["full"]["sharpe"],
                        "sharpe_full_worst":  agg["worst"]["full"]["sharpe"],
                        "cagr_full_median":   agg["median"]["full"]["cagr"],
                        "max_dd_full_worst":  agg["worst"]["full"]["max_dd"],
                        "sharpe_conf_median": agg["median"]["conf"]["sharpe"],
                        "phase_top2_sharpe":  agg["phase_top2_sharpe"],
                        "cost_drag":          agg["cost_drag"],
                    })
    pd.DataFrame(rows).to_csv(csv, index=False)
    print(f"  diagnostics -> {csv}")


if __name__ == "__main__":
    main()
