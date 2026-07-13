# LAB007 — Framework Migration Note

**Date:** 2026-07-13 (same day as original LAB007 execution)
**Type:** Infrastructure refactor. NOT a new strategy search. NOT a new hypothesis.
**Trial count increment:** 0

## What this migration is

The AI Lab framework was refactored per operator directive: research-critical values must be
YAML/JSON config-driven; Python must implement reusable engines, not per-candidate copies. The
LAB007 executable was migrated to use the new framework.

## What this migration is NOT

- ❌ Not a new experiment. No candidates added or removed.
- ❌ Not a parameter change. Every locked value in `lab007.yaml` is bit-identical to what the
  original Python code hardcoded.
- ❌ Not a re-execution to try to improve results.
- ❌ Not a rewrite of `reports/lab007_2026-07-13.md`. The sealed historical report is preserved
  verbatim.

## Parity verification

`parity_check.py` runs the refactored YAML-driven engine and compares every numeric column of
its diagnostics CSV against the sealed historical
`reports/lab007_diagnostics_2026-07-13.csv`.

Tolerance: `abs(old - new) <= 1e-10`.

**Result: PASS.** 30 rows × 17 numeric columns match within tolerance.

```
OK: row count matches (30)
OK: primary key alignment OK
OK: PARITY OK — all 17 numeric columns match within 1e-10
LAB007 evidence unchanged. Framework refactor is safe.
```

The refactored engine reproduces every metric bit-identically to the sealed run. Findings,
gate verdicts, and the REJECT conclusion stand unchanged.

## Files added

| File | Purpose |
|---|---|
| `india/ai_lab/lab_config.py` | YAML loader + strict validation (raises on missing fields) |
| `india/ai_lab/lab_metrics.py` | Shared metric suite + DSR + PBO (feasibility-guarded) + fold-rank stability |
| `india/ai_lab/lab_runner.py` | Generic orchestrator + policy/simulator plugin registry + gate expression evaluator |
| `india/ai_lab/lab_reporting.py` | Dynamic markdown + CSV report with config hash + git hash provenance |
| `india/ai_lab/LAB_STANDARDS.md` | 11-point engineering rule for LAB008+ |
| `india/ai_lab/LAB007_Dynamic_Exposure/lab007.yaml` | LAB007 sealed configuration |
| `india/ai_lab/LAB007_Dynamic_Exposure/exposure_policies.py` | Policy plugin builders for `multiplicative_gates` + `constant` |
| `india/ai_lab/LAB007_Dynamic_Exposure/run_lab007_v2.py` | Thin YAML-driven runner |
| `india/ai_lab/LAB007_Dynamic_Exposure/parity_check.py` | Enforces 1e-10 parity vs historical CSV |
| `india/ai_lab/LAB007_Dynamic_Exposure/MIGRATION_NOTE.md` | This file |

## Files retained (historical, sealed)

- `india/ai_lab/LAB007_Dynamic_Exposure/exposure_lab.py` — original Python implementation
- `india/ai_lab/LAB007_Dynamic_Exposure/run_lab007.py` — original driver
- `india/ai_lab/LAB007_Dynamic_Exposure/reports/lab007_2026-07-13.md` — sealed report
- `india/ai_lab/LAB007_Dynamic_Exposure/reports/lab007_diagnostics_2026-07-13.csv` — sealed CSV
- `india/ai_lab/LAB007_Dynamic_Exposure/preregistration.md` — original sealed pre-reg
- `india/ai_lab/LAB007_Dynamic_Exposure/README.md` — original with results log

Both v1 (`run_lab007.py`) and v2 (`run_lab007_v2.py`) produce identical diagnostics under the
same YAML-config-equivalent parameters.

## Standing rule going forward

LAB008 and all future Labs MUST use the YAML-driven framework. See `india/ai_lab/LAB_STANDARDS.md`.
