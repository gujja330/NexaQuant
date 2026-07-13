"""
india/ai_lab/lab_runner.py — generic experiment orchestrator (hardened 2026-07-13).

Reads an ExperimentConfig, builds policies via a plugin registry, executes the sweep (cash ×
cost × candidate), computes metrics + regime attribution + gate verdicts via an AST-safe
expression evaluator. All research-critical values are read from config — no silent defaults.

The runner does NOT know experiment-specific values (regime names, canonical/stress costs,
trading days). Those come from config.
"""
from __future__ import annotations
from typing import Callable
import pandas as pd

from india.ai_lab.lab_config import ExperimentConfig
from india.ai_lab.lab_metrics import (
    metric_suite, period_metrics, read_trial_manifest_count,
    pbo_across_configs, sharpe_rank_stability,
)
from india.ai_lab.lab_expression import compile_gate_expression


# ----------------------- Plugin registry -----------------------

_POLICY_BUILDERS: dict[str, Callable] = {}
_SIMULATORS: dict[str, Callable] = {}


def register_policy(policy_type: str, builder: Callable) -> None:
    _POLICY_BUILDERS[policy_type] = builder


def register_simulator(name: str, simulator: Callable) -> None:
    _SIMULATORS[name] = simulator


def get_policy_builder(policy_type: str) -> Callable:
    if policy_type not in _POLICY_BUILDERS:
        raise KeyError(f"Policy type '{policy_type}' not registered. "
                       f"Available: {list(_POLICY_BUILDERS)}")
    return _POLICY_BUILDERS[policy_type]


def get_simulator(name: str) -> Callable:
    if name not in _SIMULATORS:
        raise KeyError(f"Simulator '{name}' not registered. "
                       f"Available: {list(_SIMULATORS)}")
    return _SIMULATORS[name]


# ----------------------- Executor -----------------------

def build_policies(config: ExperimentConfig, context: dict) -> dict:
    return {cid: get_policy_builder(c["type"])(c, context) for cid, c in config.candidates.items()}


def run_experiment(config: ExperimentConfig, context: dict, simulator_name: str,
                   registry_df: pd.DataFrame) -> dict:
    """Execute the full sweep. All parameters flow from config — no hardcoded values."""
    sim = get_simulator(simulator_name)
    policies = build_policies(config, context)
    n_trials = _resolve_n_trials(config)

    trading_days = config.trading_days()
    disc_end = pd.Timestamp(config.periods["discovery_end"])
    conf_start = pd.Timestamp(config.periods["confirmation_start"])
    cash_grid = config.simulation["cash_returns_annual"]
    cost_grid = config.simulation["cost_grid_bps"]
    capital = float(config.simulation["initial_capital"])
    regime_metric_key = config.regimes["metric_key"]
    regime_names = [b.name for b in config.regimes["buckets"]]

    results = {}
    for cash in cash_grid:
        results[cash] = {}
        for cost in cost_grid:
            results[cash][cost] = {}
            for cid, policy_input in policies.items():
                eq, meta = sim(
                    policy_input, registry_df, context["closes"],
                    initial_capital=capital,
                    cash_return_annual=float(cash),
                    cost_bps=float(cost),
                    trading_days_per_year=trading_days,
                )
                # Regime attribution — bucket assignment from config (not hardcoded strings)
                for m in meta:
                    if regime_metric_key in m:
                        m["regime"] = config.regime_bucket_for(m[regime_metric_key])
                full = metric_suite(eq, meta, trading_days=trading_days)
                disc_asofs = {pd.Timestamp(m["asof"]) for m in meta
                              if pd.Timestamp(m["asof"]) <= disc_end}
                conf_asofs = {pd.Timestamp(m["asof"]) for m in meta
                              if pd.Timestamp(m["asof"]) >= conf_start}
                disc = period_metrics(eq, meta, disc_asofs, trading_days=trading_days)
                conf = period_metrics(eq, meta, conf_asofs, trading_days=trading_days)
                reg_metrics = {}
                for reg_name in regime_names:
                    reg_asofs = {pd.Timestamp(m["asof"]) for m in meta if m.get("regime") == reg_name}
                    reg_metrics[reg_name] = period_metrics(eq, meta, reg_asofs, trading_days=trading_days)
                dsr_d = _compute_dsr(eq, n_trials)
                results[cash][cost][cid] = {
                    "equity": eq, "meta": meta,
                    "full": full, "disc": disc, "conf": conf,
                    "regime": reg_metrics, "dsr": dsr_d,
                }

    # PBO at CANONICAL cost — explicit from config, not cost_grid[0]
    canonical_cost = config.canonical_cost()
    pbo_by_cash = {}
    stability_by_cash = {}
    stab_folds = config.stability_folds()
    for cash in cash_grid:
        eq_by_name = {cid: results[cash][canonical_cost][cid]["equity"] for cid in policies}
        common = None
        for eq in eq_by_name.values():
            common = eq.index if common is None else common.intersection(eq.index)
        if common is not None and len(common) >= 30:
            R = pd.DataFrame({cid: eq.reindex(common).pct_change()
                              for cid, eq in eq_by_name.items()}).dropna(how="any")
            pbo_by_cash[cash] = pbo_across_configs(R, S=config.pbo["folds"],
                                                   min_configs_for_interpretation=config.pbo["min_configs_for_interpretation"])
        else:
            pbo_by_cash[cash] = {"status": "N/A", "value": float("nan"),
                                 "note": "insufficient common index", "n_configs": 0, "s_folds": 0}
        stability_by_cash[cash] = sharpe_rank_stability(eq_by_name, n_folds=stab_folds,
                                                        trading_days=trading_days)

    return {
        "config": config, "n_trials": n_trials, "results": results,
        "pbo_by_cash": pbo_by_cash, "stability_by_cash": stability_by_cash,
        "policies": policies,
    }


# ----------------------- Helpers -----------------------

def _resolve_n_trials(config: ExperimentConfig) -> int:
    src = config.dsr["n_trials_source"]
    if isinstance(src, int):
        return src
    if src == "manifest":
        return read_trial_manifest_count(config.trial_manifest_path)
    raise ValueError(f"Unknown dsr.n_trials_source: {src!r}")


def _compute_dsr(equity: pd.Series, n_trials: int) -> dict:
    from india.validation import deflated_sharpe
    return deflated_sharpe(equity.pct_change().dropna(), n_trials=n_trials)


# ----------------------- Gate evaluator (AST-safe) -----------------------

_ALLOWED_GATE_ROOTS = ("cand", "n0", "cand_stress", "n0_stress")


def evaluate_gates(config: ExperimentConfig, cand_result: dict, ctrl_result: dict,
                   cand_stress_result: dict = None, ctrl_stress_result: dict = None) -> dict:
    """Evaluate every gate via AST-safe evaluator. Namespace roots limited to:
    cand, n0, cand_stress, n0_stress. Attributes accessed downstream MUST come from result dicts."""
    ns = {
        "cand": _wrap_ns(cand_result),
        "n0":   _wrap_ns(ctrl_result),
    }
    if cand_stress_result is not None:
        ns["cand_stress"] = _wrap_ns(cand_stress_result)
    if ctrl_stress_result is not None:
        ns["n0_stress"] = _wrap_ns(ctrl_stress_result)

    out = {"gates": {}, "all_pass": True}
    for g in config.gates:
        try:
            checker = compile_gate_expression(g["expression"], allowed_roots=_ALLOWED_GATE_ROOTS)
            passed = bool(checker(ns))
            err = None
        except Exception as e:
            passed = False
            err = f"{type(e).__name__}: {e}"
        out["gates"][g["id"]] = {"pass": passed, "name": g["name"],
                                  "expression": g["expression"], "error": err}
        if not passed:
            out["all_pass"] = False
    return out


def _wrap_ns(result: dict):
    """Wrap {full/disc/conf/regime/dsr: {metric: val}} for attribute access."""
    class NS:
        pass
    root = NS()
    for period_key in ("full", "disc", "conf", "dsr"):
        if period_key in result:
            leaf = NS()
            for k, v in result[period_key].items():
                setattr(leaf, k, v)
            setattr(root, period_key, leaf)
    if "regime" in result:
        r = NS()
        for reg_name, reg_metrics in result["regime"].items():
            leaf = NS()
            for k, v in reg_metrics.items():
                setattr(leaf, k, v)
            setattr(r, reg_name, leaf)
        setattr(root, "regime", r)
    return root
