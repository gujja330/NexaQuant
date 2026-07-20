# AEGIS AI Lab Discovery · LAB001–010
**Stage 0.5 deliverable · Runtime status of each lab**

---

## Classification key

- **README_ONLY** — only README.md exists, no code
- **HAS_CODE** — `.py` files that could run
- **HAS_ARTIFACTS** — output files present (evidence of past runs)
- **SCHEDULED** — invoked by any orchestrator
- **DORMANT** — has code + artifacts but never invoked from any scheduler

---

## Per-lab audit (findings from runtime agent)

### `india/ai_lab/LAB001_Earnings`
- **Contents:** `README.md` only
- **Status:** README_ONLY
- **Runtime:** None
- **Intended scope (per README):** Earnings Intelligence — pre/post PEAD drift, next-results date, earnings surprise
- **Reality:** No implementation

### `india/ai_lab/LAB002_Fundamentals`
- **Contents:** `README.md` only
- **Status:** README_ONLY
- **Runtime:** None
- **Intended scope (per README):** Point-in-Time Fundamentals
- **Reality:** No implementation. Note: this is separate from `india/fundamentals_nse.py` at the india/ root (which DOES exist but is unwired).

### `india/ai_lab/LAB003_Events`
- **Contents:** `README.md` only
- **Status:** README_ONLY
- **Runtime:** None
- **Intended scope:** Corporate Actions / Events

### `india/ai_lab/LAB004_Flows`
- **Contents:** `README.md` only
- **Status:** README_ONLY
- **Runtime:** None
- **Intended scope:** Institutional Money — note this is architecturally similar to `india/fii_dii.py` (which IS coded but unscheduled)

### `india/ai_lab/LAB005_Ranking`
- **Contents:** `README.md` only
- **Status:** README_ONLY
- **Runtime:** None
- **Intended scope:** Learning-to-Rank

### `india/ai_lab/LAB006_Exit_Strategy`
- **Contents:** `exit_lab.py`, `rule_B_vol_spike.py`, `rule_C1_regime_gated.py`, `rule_C_trailing_stop.py`, `score_path_collector.py`, `trial_manifest.md`, `rule_C1_preregistration.md`, plus `reports/` with 9 dated MD/CSV outputs (all `2026-07-13`)
- **Status:** HAS_CODE + HAS_ARTIFACTS
- **Runtime:** Not scheduled. One-time experiment run 2026-07-13.
- **Related production:** `research/RISK001-A/` sealed exit-policy study (which I saw earlier)

### `india/ai_lab/LAB007_Dynamic_Exposure`
- **Contents:** `exposure_lab.py`, `exposure_policies.py`, `run_lab007.py`, `run_lab007_v2.py`, `parity_check.py`, `lab007.yaml`, `MIGRATION_NOTE.md`, plus `reports/lab007_2026-07-13.md` + diagnostics CSV
- **Status:** HAS_CODE + HAS_ARTIFACTS
- **Runtime:** Not scheduled. Artifacts dated 2026-07-13.

### `india/ai_lab/LAB008_Horizon_Calibration`
- **Contents:** `horizon_policies.py`, `run_lab008.py`, `lab008.yaml`, `LAB008_EVIDENCE_AUDIT.md`, plus `reports/lab008_2026-07-13.md` + diagnostics CSV
- **Status:** HAS_CODE + HAS_ARTIFACTS
- **Runtime:** Not scheduled. Artifacts 2026-07-13.

### `india/ai_lab/LAB009_Horizon_Phase_Recalibration`
- **Contents:** `horizon_phase_policies.py`, `run_lab009.py`, `test_maturity_correction.py`, `test_period_boundary_correction.py`, `lab009.yaml`, 4 audit MDs, plus 6 dated report/diagnostic files (`2026-07-13`)
- **Status:** HAS_CODE + HAS_ARTIFACTS + HAS_TESTS
- **Runtime:** Not scheduled. Artifacts 2026-07-13.

### `india/ai_lab/LAB010_H84_Robustness_Validation`
- **Contents:** `run_lab010.py`, `test_lab010_framework.py`, `lab010.yaml`, `LAB010_EVIDENCE_REVIEW.md`, plus `reports/lab010_h84_robustness_2026-07-13.md` + diagnostics CSV
- **Status:** HAS_CODE + HAS_ARTIFACTS + HAS_TESTS
- **Runtime:** Not scheduled. Artifacts 2026-07-13.

## Governance files

| Path | Role |
|---|---|
| `india/ai_lab/LAB_STANDARDS.md` | Lab governance policy |
| `india/ai_lab/experiments.yaml` | Lab registry — only YAML in the whole repo containing "lab" references, and NOT invoked by any scheduler |

---

## Aggregate

| Status | Count |
|---|---|
| README_ONLY | 5 (LAB001-005) |
| HAS_CODE + HAS_ARTIFACTS (2026-07-13 batch) | 5 (LAB006-010) |
| SCHEDULED | **0** |
| ACTIVELY CONSUMED BY PRODUCTION | **0** — no v2 orchestrator step reads any LAB output |

**Every lab is off the critical path.** LAB006-010 were built as a batch on 2026-07-13 (7 days before this audit), ran once, produced artifacts, and have not been re-run since.

## Relationship to production

Some labs conceptually align with existing production modules:

| Lab (concept) | Production twin | Runtime status of production twin |
|---|---|---|
| LAB001 Earnings | `india/fundamentals_nse.py` (has earnings calendar functionality) | Never invoked |
| LAB002 Fundamentals | `india/fundamentals_nse.py`, `usa/research/fundamentals/run.py` | Both never invoked |
| LAB003 Events | None yet | — |
| LAB004 Flows | `india/fii_dii.py` | Manual-only |
| LAB005 Ranking | None (matches "learning-to-rank" concept in `AI_ML_REFINEMENT_PLAN.md`) | — |
| LAB006 Exit Strategy | `research/RISK001-A/` (sealed) + `india/exit_reasons.py` | RISK001-A is sealed, exit_reasons is a library |
| LAB007 Dynamic Exposure | `research/risk_capital_v2/` | LIVE DAILY |
| LAB008/009 Horizon Calibration | `india/horizon_matrix.py` | Library |
| LAB010 H84 Robustness | Validation framework | LAB-specific, not in main pipeline |

**None of the LAB→production connections are wired end-to-end.** Labs are experiment sandboxes; graduation to production would require explicit engineering work (which the labs' `MIGRATION_NOTE.md` files acknowledge).
