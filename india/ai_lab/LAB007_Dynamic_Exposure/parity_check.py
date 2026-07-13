"""
LAB007 parity check — refactored (YAML-driven) vs historical (sealed) diagnostics.

Compares every numeric column of the refactored run's diagnostics CSV against the sealed
historical diagnostics `reports/lab007_diagnostics_2026-07-13.csv`. STOPS with a nonzero exit
code if any pair differs by more than 1e-10 in absolute value.

The historical CSV is NEVER overwritten by this check. The refactored run is written to a
scratch path.

Run: python india/ai_lab/LAB007_Dynamic_Exposure/parity_check.py
Exit codes: 0 = parity OK · 2 = mismatch found · 1 = setup error
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

    # Run refactored engine in-process (produces its own dated CSV)
    print(f"  Running refactored (YAML-driven) LAB007...")
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
    context = build_context()
    bundle = R.run_experiment(config, context, "exposure_cycle", reg_df)

    # Write refactored output to a SCRATCH path (never overwrite historical)
    scratch_dir = Path(__file__).parent / "reports" / "_parity_scratch"
    scratch_dir.mkdir(exist_ok=True)
    md_path, csv_path = write_report(bundle, out_dir=scratch_dir)
    print(f"  Refactored diagnostics written to: {csv_path}")

    ref = pd.read_csv(csv_path)

    # Verify shape
    if len(hist) != len(ref):
        print(f"  FAIL: PARITY FAIL: row count mismatch (hist={len(hist)} vs refactored={len(ref)})")
        sys.exit(2)
    print(f"  OK: row count matches ({len(hist)})")

    # Align on primary key (cash, cost, candidate)
    key = ["cash_annual", "cost_bps", "candidate"]
    hist = hist.sort_values(key).reset_index(drop=True)
    ref = ref.sort_values(key).reset_index(drop=True)
    for k in key:
        if not (hist[k].astype(str).values == ref[k].astype(str).values).all():
            print(f"  FAIL: PARITY FAIL: key column '{k}' mismatch after sort")
            sys.exit(2)
    print(f"  OK: primary key alignment OK")

    # Compare numeric columns
    numeric_cols = [c for c in hist.columns if c not in key and pd.api.types.is_numeric_dtype(hist[c])]
    mismatches = []
    for col in numeric_cols:
        if col not in ref.columns:
            mismatches.append((col, "column absent in refactored output", None, None))
            continue
        h_vals = hist[col].values
        r_vals = ref[col].values
        # Compare with NaN handling
        for i, (h, r) in enumerate(zip(h_vals, r_vals)):
            if pd.isna(h) and pd.isna(r):
                continue
            if pd.isna(h) or pd.isna(r):
                mismatches.append((col, i, h, r, "NaN alignment"))
                continue
            diff = abs(float(h) - float(r))
            if diff > TOLERANCE:
                mismatches.append((col, i, h, r, f"|diff|={diff:.3e} > {TOLERANCE}"))

    if mismatches:
        print(f"\n  FAIL: PARITY FAIL — {len(mismatches)} mismatches:")
        for m in mismatches[:20]:
            col, i = m[0], m[1]
            key_row = hist.iloc[i][key].to_dict() if isinstance(i, int) else "?"
            print(f"    col={col}  row={key_row}  hist={m[2]}  refactored={m[3]}  {m[-1]}")
        if len(mismatches) > 20:
            print(f"    ... {len(mismatches) - 20} more")
        print(f"\n  DO NOT overwrite historical evidence. Investigate refactoring before proceeding.")
        sys.exit(2)

    print(f"\n  OK: PARITY OK — all {len(numeric_cols)} numeric columns match within {TOLERANCE}")
    print(f"  {len(hist)} rows × {len(numeric_cols)} numeric columns verified")
    print(f"  LAB007 evidence unchanged. Framework refactor is safe.")
    sys.exit(0)


if __name__ == "__main__":
    main()
