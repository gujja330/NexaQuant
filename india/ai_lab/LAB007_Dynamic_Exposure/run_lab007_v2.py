"""
LAB007 v2 — thin YAML-driven runner using the shared AI Lab framework.

Registers LAB007-specific policy builders + simulator, then hands off to lab_runner. No
experiment-specific values in this file — everything comes from lab007.yaml.

Post-parity-verification, this replaces run_lab007.py as the canonical LAB007 driver.
Historical evidence in reports/lab007_2026-07-13.md is NOT rewritten by this file.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import pandas as pd

from india.ai_lab.lab_config import load_experiment_config
from india.ai_lab import lab_runner as R
from india.ai_lab.lab_reporting import write_report
from india.ai_lab.LAB007_Dynamic_Exposure.exposure_policies import (
    build_context, build_multiplicative_gates_series, build_constant_series, simulate_cycle,
)


def main():
    cfg_path = Path(__file__).parent / "lab007.yaml"
    print(f"  Loading experiment config: {cfg_path}")
    config = load_experiment_config(cfg_path)
    print(f"  Config hash: {config.config_hash}")
    print(f"  n_trials source: {config.dsr['n_trials_source']}")

    # Register LAB007 plugins
    R.register_policy("multiplicative_gates", build_multiplicative_gates_series)
    R.register_policy("constant", build_constant_series)
    R.register_simulator("exposure_cycle", simulate_cycle)

    # Load registry + build shared context (rolling_min_periods MUST come from config)
    reg_df = pd.read_csv(ROOT / config.simulation["registry_path"])
    context = build_context(rolling_min_periods=int(config.policy_parameters["rolling_min_periods"]))
    print(f"  Registry: {len(reg_df)} rows · price panel: {context['closes'].shape}")

    # Execute
    bundle = R.run_experiment(config, context, "exposure_cycle", reg_df)
    print(f"  n_trials resolved: {bundle['n_trials']}")

    # Print quick verdict summary (ASCII-safe for Windows console)
    ctrl = config.control_id()
    canon = config.canonical_cost()
    stress = config.stress_cost()
    for cid in config.candidate_ids(exclude_control=True):
        cash_grid = config.simulation["cash_returns_annual"]
        overalls = []
        for cash in cash_grid:
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
