"""
LAB007 parity check — refactored (YAML-driven) vs historical (sealed) diagnostics.

Enhanced 2026-07-13:
- Explicitly enumerates every numeric column in the historical CSV.
- Fails loud if any historical numeric column is absent from the refactored output.
- Prints max absolute difference per column (surfacing any drift < TOLERANCE).
- Reports overall max diff across the entire matrix.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

TOLERANCE = 1e-10
HISTORICAL_CSV = Path(__file__).parent / "reports" / "lab007_diagnostics_2026-07-13.csv"


def main():
    if not HISTORICAL_CSV.exists():
        print(f"  ERROR: historical CSV not found at {HISTORICAL_CSV}")
        sys.exit(1)

    print(f"  Reading historical diagnostics: {HISTORICAL_CSV.name}")
    hist = pd.read_csv(HISTORICAL_CSV)

    print(f"  Running refactored (YAML-driven) LAB007 v2...")
    from india.ai_lab.lab_config import load_experiment_config
    from india.ai_lab import lab_runner as R
    from india.ai_lab.lab_reporting import write_report
    from india.ai_lab.LAB007_Dynamic_Exposure.exposure_policies import (
        build_context, build_multiplicative_gates_series, build_constant_series, simulate_cycle,
    )

    R.register_policy("multiplicative_gates", build_multiplicative_gates_series)
    R.register_policy("constant", build_constant_series)
    R.register_simulator("exposure_cycle", simulate_cycle)

    cfg_path = Path(__file__).parent / "lab007.yaml"
    config = load_experiment_config(cfg_path)
    reg_df = pd.read_csv(ROOT / config.simulation["registry_path"])
    context = build_context(rolling_min_periods=int(config.policy_parameters["rolling_min_periods"]))
    bundle = R.run_experiment(config, context, "exposure_cycle", reg_df)

    scratch_dir = Path(__file__).parent / "reports" / "_parity_scratch"
    scratch_dir.mkdir(exist_ok=True)
    md_path, csv_path = write_report(bundle, out_dir=scratch_dir)
    print(f"  Refactored diagnostics written to: {csv_path}")

    ref = pd.read_csv(csv_path)

    # Shape
    if len(hist) != len(ref):
        print(f"  FAIL: row count mismatch (hist={len(hist)} vs refactored={len(ref)})")
        sys.exit(2)
    print(f"  OK: row count matches ({len(hist)})")

    # Primary key alignment
    key = ["cash_annual", "cost_bps", "candidate"]
    hist = hist.sort_values(key).reset_index(drop=True)
    ref = ref.sort_values(key).reset_index(drop=True)
    for k in key:
        if not (hist[k].astype(str).values == ref[k].astype(str).values).all():
            print(f"  FAIL: key column '{k}' mismatch after sort")
            sys.exit(2)
    print(f"  OK: primary key alignment OK")

    # Enumerate all numeric columns explicitly
    hist_numeric = [c for c in hist.columns if c not in key and pd.api.types.is_numeric_dtype(hist[c])]
    ref_numeric = [c for c in ref.columns if c not in key and pd.api.types.is_numeric_dtype(ref[c])]

    print(f"\n  Historical numeric columns ({len(hist_numeric)}):")
    for c in hist_numeric:
        print(f"    - {c}")
    print(f"  Refactored numeric columns ({len(ref_numeric)}):")
    for c in ref_numeric:
        print(f"    - {c}")

    missing = [c for c in hist_numeric if c not in ref_numeric]
    if missing:
        print(f"\n  FAIL: {len(missing)} historical numeric columns MISSING from refactored:")
        for c in missing:
            print(f"    - {c}")
        print(f"\n  Refactored output must expose every historical numeric column.")
        sys.exit(2)

    # Compare every historical numeric column and track max diff per column
    max_diff_by_col = {}
    mismatches = []
    for col in hist_numeric:
        h_vals = hist[col].values
        r_vals = ref[col].values
        max_diff = 0.0
        for i, (h, r) in enumerate(zip(h_vals, r_vals)):
            if pd.isna(h) and pd.isna(r):
                continue
            if pd.isna(h) or pd.isna(r):
                mismatches.append((col, i, h, r, "NaN alignment"))
                continue
            diff = abs(float(h) - float(r))
            max_diff = max(max_diff, diff)
            if diff > TOLERANCE:
                mismatches.append((col, i, h, r, f"|diff|={diff:.3e} > {TOLERANCE}"))
        max_diff_by_col[col] = max_diff

    print(f"\n  Max absolute difference by column:")
    for col, md in sorted(max_diff_by_col.items(), key=lambda x: -x[1]):
        marker = " OK" if md <= TOLERANCE else " ** FAIL **"
        print(f"    {col:30s}  max |diff| = {md:.3e}{marker}")

    if mismatches:
        print(f"\n  FAIL: PARITY FAIL - {len(mismatches)} mismatches:")
        for m in mismatches[:20]:
            col, i = m[0], m[1]
            key_row = hist.iloc[i][key].to_dict() if isinstance(i, int) else "?"
            print(f"    col={col}  row={key_row}  hist={m[2]}  refactored={m[3]}  {m[-1]}")
        if len(mismatches) > 20:
            print(f"    ... {len(mismatches) - 20} more")
        print(f"\n  DO NOT overwrite historical evidence. Investigate before proceeding.")
        sys.exit(2)

    overall_max = max(max_diff_by_col.values()) if max_diff_by_col else 0.0
    print(f"\n  OK: PARITY OK - all {len(hist_numeric)} historical numeric columns compared;")
    print(f"     overall max |diff| across matrix = {overall_max:.3e} <= {TOLERANCE}")
    print(f"  {len(hist)} rows x {len(hist_numeric)} numeric columns verified.")
    print(f"  LAB007 evidence unchanged. Framework refactor is safe.")
    sys.exit(0)


if __name__ == "__main__":
    main()
