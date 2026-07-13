"""
LAB008 runner — thin YAML-driven executor.

Registers LAB008-specific plugin (horizon policy builder + simulator) and hands off to the
hardened generic AI Lab framework. No experiment-specific values in this file — everything
comes from lab008.yaml.

Run:  python india/ai_lab/LAB008_Horizon_Calibration/run_lab008.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import pandas as pd

from india.ai_lab.lab_config import load_experiment_config
from india.ai_lab import lab_runner as R
from india.ai_lab.lab_reporting import write_report
from india.ai_lab.LAB008_Horizon_Calibration.horizon_policies import (
    build_context, build_horizon_policy, simulate_horizon_cycle,
)


def main():
    cfg_path = Path(__file__).parent / "lab008.yaml"
    print(f"  Loading experiment config: {cfg_path}")
    config = load_experiment_config(cfg_path)
    print(f"  Config hash: {config.config_hash}")
    print(f"  Trial manifest source: {config.dsr['n_trials_source']}")

    R.register_policy("horizon", build_horizon_policy)
    R.register_simulator("horizon_cycle", simulate_horizon_cycle)

    # The framework expects a registry_df; LAB008's simulator ignores it and uses per-horizon
    # in-memory registries from policy_input. We still load the production registry as a valid
    # (but unused) placeholder to satisfy the framework's contract.
    reg_df = pd.read_csv(ROOT / config.simulation["registry_path"])
    context = build_context(rolling_min_periods=int(config.policy_parameters["rolling_min_periods"]))
    print(f"  Context loaded: closes {context['closes'].shape} · exp_series {len(context['exp_series'])}")

    bundle = R.run_experiment(config, context, "horizon_cycle", reg_df)
    print(f"  n_trials resolved from manifest: {bundle['n_trials']}")

    ctrl = config.control_id()
    canon = config.canonical_cost()
    stress = config.stress_cost()
    for cid in config.candidate_ids(exclude_control=True):
        overalls = []
        for cash in config.simulation["cash_returns_annual"]:
            cand = bundle["results"][cash][canon][cid]
            n0 = bundle["results"][cash][canon][ctrl]
            cand_str = bundle["results"][cash][stress][cid]
            n0_str = bundle["results"][cash][stress][ctrl]
            v = R.evaluate_gates(config, cand, n0, cand_str, n0_str)
            overalls.append(v["all_pass"])
            print(f"    {cid} cash={100*cash:.0f}%: " +
                  " ".join(f"{g['id']}={'PASS' if v['gates'][g['id']]['pass'] else 'FAIL'}"
                           for g in config.gates))
        print(f"  {cid}: {'PROMOTE-ELIGIBLE' if all(overalls) else 'REJECT'}")

    md_path, csv_path = write_report(bundle)
    print(f"\n  report -> {md_path}")
    print(f"  diagnostics -> {csv_path}")


if __name__ == "__main__":
    main()
