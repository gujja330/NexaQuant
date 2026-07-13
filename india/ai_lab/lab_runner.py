"""
india/ai_lab/lab_runner.py — generic experiment orchestrator.

Reads an ExperimentConfig (from lab_config.load_experiment_config), builds candidate policies
via a registered policy-builder registry, executes the sweep (cash × cost × candidate), and
returns structured results.

The RUNNER does not know anything experiment-specific. All specifics live in:
- YAML config (parameters)
- Registered policy builders (how to convert config → policy input, e.g. exp_series for LAB007)
- Registered simulator (how to run one policy through the registry cycles)

Register once, run for any Lab.

USAGE (LAB007 example, from run_lab007.py):
    from india.ai_lab import lab_runner as R
    from india.ai_lab.LAB007_Dynamic_Exposure import exposure_policies as P

    R.register_policy("multiplicative_gates", P.build_multiplicative_gates_series)
    R.register_policy("constant", P.build_constant_series)
    R.register_simulator("exposure_cycle", P.simulate_cycle)

    results = R.run_experiment(config)
"""
from __future__ import annotations
from typing import Callable
import pandas as pd

from india.ai_lab.lab_config import ExperimentConfig
from india.ai_lab.lab_metrics import (
    metric_suite, period_metrics, read_trial_manifest_count,
    pbo_across_configs, sharpe_rank_stability,
)


# ----------------------- Policy + Simulator plugin registry -----------------------

_POLICY_BUILDERS: dict[str, Callable] = {}
_SIMULATORS: dict[str, Callable] = {}


def register_policy(policy_type: str, builder: Callable) -> None:
    """Register a policy builder. builder(params, context) → policy input for the simulator.
    e.g. for LAB007 the "policy input" is a pd.Series of exp values."""
    _POLICY_BUILDERS[policy_type] = builder


def register_simulator(name: str, simulator: Callable) -> None:
    """Register a simulator. simulator(policy_input, reg_df, closes, cash_return, cost_bps,
    initial_capital) → (equity_series, cycles_meta_list)."""
    _SIMULATORS[name] = simulator


def get_policy_builder(policy_type: str) -> Callable:
    if policy_type not in _POLICY_BUILDERS:
        raise KeyError(f"Policy type '{policy_type}' not registered. Available: {list(_POLICY_BUILDERS)}")
    return _POLICY_BUILDERS[policy_type]


def get_simulator(name: str) -> Callable:
    if name not in _SIMULATORS:
        raise KeyError(f"Simulator '{name}' not registered. Available: {list(_SIMULATORS)}")
    return _SIMULATORS[name]


# ----------------------- Generic experiment executor -----------------------

def build_policies(config: ExperimentConfig, context: dict) -> dict:
    """Build all candidate policy inputs from config.
    context = shared data (closes panel, vix series, etc.) passed to each builder.
    Returns dict {candidate_id: policy_input}."""
    out = {}
    for cid, cand in config.candidates.items():
        builder = get_policy_builder(cand["type"])
        out[cid] = builder(cand, context)
    return out


def run_experiment(config: ExperimentConfig, context: dict, simulator_name: str,
                   registry_df: pd.DataFrame) -> dict:
    """Execute the full sweep for a config.

    Iterates: cash_return × cost_bps × candidate.
    For each combo, runs the registered simulator and computes metric suite + period splits.
    Returns nested dict: results[cash][cost][candidate] = {equity, meta, full, disc, conf, regime, dsr}.
    """
    sim = get_simulator(simulator_name)
    policies = build_policies(config, context)

    n_trials = _resolve_n_trials(config)

    disc_end = pd.Timestamp(config.periods["discovery_end"])
    conf_start = pd.Timestamp(config.periods["confirmation_start"])
    cash_grid = config.simulation["cash_returns_annual"]
    cost_grid = config.simulation["cost_grid_bps"]
    capital = float(config.simulation["initial_capital"])

    results = {}
    for cash in cash_grid:
        results[cash] = {}
        for cost in cost_grid:
            results[cash][cost] = {}
            for cid, policy_input in policies.items():
                eq, meta = sim(policy_input, registry_df, context["closes"],
                               initial_capital=capital, cash_return_annual=float(cash),
                               cost_bps=float(cost))
                full = metric_suite(eq, meta)
                disc_asofs = {pd.Timestamp(m["asof"]) for m in meta
                              if pd.Timestamp(m["asof"]) <= disc_end}
                conf_asofs = {pd.Timestamp(m["asof"]) for m in meta
                              if pd.Timestamp(m["asof"]) >= conf_start}
                disc = period_metrics(eq, meta, disc_asofs)
                conf = period_metrics(eq, meta, conf_asofs)
                # Regime attribution (if 'regime' key present in meta)
                reg_metrics = {}
                if meta and "regime" in meta[0]:
                    for reg_name in ("Strong", "Neutral", "Weak"):
                        reg_asofs = {pd.Timestamp(m["asof"]) for m in meta if m.get("regime") == reg_name}
                        reg_metrics[reg_name] = period_metrics(eq, meta, reg_asofs)
                dsr_d = _compute_dsr(eq, n_trials)
                results[cash][cost][cid] = {
                    "equity": eq, "meta": meta,
                    "full": full, "disc": disc, "conf": conf,
                    "regime": reg_metrics, "dsr": dsr_d,
                }
    # PBO at canonical (first cost) per cash — per config
    pbo_by_cash = {}
    stability_by_cash = {}
    canonical_cost = cost_grid[0]
    for cash in cash_grid:
        eq_by_name = {cid: results[cash][canonical_cost][cid]["equity"] for cid in policies}
        common = None
        for eq in eq_by_name.values():
            common = eq.index if common is None else common.intersection(eq.index)
        if common is not None and len(common) >= 30:
            R = pd.DataFrame({cid: eq.reindex(common).pct_change() for cid, eq in eq_by_name.items()}).dropna(how="any")
            pbo_by_cash[cash] = pbo_across_configs(R, S=config.pbo["folds"],
                                                    min_configs_for_interpretation=config.pbo["min_configs_for_interpretation"])
        else:
            pbo_by_cash[cash] = {"status": "N/A", "value": float("nan"),
                                 "note": "insufficient common index", "n_configs": 0, "s_folds": 0}
        stability_by_cash[cash] = sharpe_rank_stability(eq_by_name, n_folds=4)

    return {
        "config": config,
        "n_trials": n_trials,
        "results": results,
        "pbo_by_cash": pbo_by_cash,
        "stability_by_cash": stability_by_cash,
        "policies": policies,
    }


# ----------------------- Helpers -----------------------

def _resolve_n_trials(config: ExperimentConfig) -> int:
    src = config.dsr["n_trials_source"]
    if isinstance(src, int):
        return src
    if src == "manifest":
        return read_trial_manifest_count(config.trial_manifest_path)
    raise ValueError(f"Unknown dsr.n_trials_source: {src!r}. Use 'manifest' or an integer.")


def _compute_dsr(equity: pd.Series, n_trials: int) -> dict:
    from india.validation import deflated_sharpe
    return deflated_sharpe(equity.pct_change().dropna(), n_trials=n_trials)


# ----------------------- Gate evaluator (config-driven) -----------------------

def evaluate_gates(config: ExperimentConfig, cash: float, result: dict, control_result: dict,
                   cost_50bps_result: dict = None, control_50bps_result: dict = None) -> dict:
    """Evaluate each promotion gate for one candidate at one cash-return assumption.

    Each gate has an `expression` string that operates on:
      cand.full/disc/conf/regime.{cagr,sharpe,max_dd,ulcer,cvar5,dsr,...}
      n0.full/disc/conf/regime.{...}
      cand50.{...} (populated only if cost_50bps_result passed)
      n050.{...}
    Expression is Python; evaluated in a restricted namespace. Returns bool per gate + overall.
    """
    namespace = {
        "cand": _ns_from_result(result),
        "n0":   _ns_from_result(control_result),
    }
    if cost_50bps_result is not None:
        namespace["cand50"] = _ns_from_result(cost_50bps_result)
    if control_50bps_result is not None:
        namespace["n050"] = _ns_from_result(control_50bps_result)

    out = {"gates": {}, "all_pass": True}
    for g in config.gates:
        expr = g["expression"]
        try:
            val = bool(eval(expr, {"__builtins__": {}}, namespace))
        except Exception as e:
            val = False
            g_err = str(e)
        else:
            g_err = None
        out["gates"][g["id"]] = {"pass": val, "name": g["name"], "expression": expr, "error": g_err}
        if not val:
            out["all_pass"] = False
    return out


def _ns_from_result(result: dict):
    """Wrap the nested result dict in an object with attribute access for gate expressions."""
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
