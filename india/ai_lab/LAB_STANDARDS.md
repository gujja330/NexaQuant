# AI Lab Engineering Standards

**Mandatory for every LAB008 and later experiment.**
**Not retroactive — LAB001..LAB007 evidence is preserved as-is.**

The standards below reflect audit findings from LAB006 (silent-fallback bug, PIT leakage in P3
re-entry, degenerate N=2 PBO) and LAB007 (hardcoded candidate matrix, 4 duplicate candidate
functions, hardcoded gate thresholds). Every rule addresses a real bug caught in prior labs.

## 1. Pre-register the hypothesis
Every experiment starts with a `preregistration.md` in the Lab folder. State:
- The hypothesis in plain English
- The null (control) — traced to actual production code, PIT-safe
- The candidate matrix (bounded, small, economically motivated)
- The evaluation split (discovery / confirmation / full-period — no "training" unless a model is fit)
- The promotion gates with exact numeric thresholds

Any deviation post-run invalidates the pre-registration and requires a NEW experiment ID
with its own trial count.

## 2. Define the experiment matrix in YAML/JSON
Every experiment-specific value goes in `<lab_id>.yaml`. Python knows nothing about the
experiment. Config drives everything: candidates, gates, periods, cash assumptions, costs,
report paths, DSR/PBO settings.

## 3. No silent Python defaults on research-critical values
`lab_config.load_experiment_config()` raises `LookupError` / `TypeError` on missing or wrong-typed
fields. Never write `.get(key, default)` for a research parameter. If it's missing, the
experiment must fail to start.

## 4. Reusable engines, not per-candidate Python copies
If four candidates differ only in a multiplier, write ONE policy builder that reads the multiplier
from config, not four functions. `lab_runner` provides `register_policy(name, builder)` for the
plugin registry.

## 5. Config is sealed before execution
- The YAML is committed to git BEFORE `run_lab*.py` is executed.
- The commit hash of the pre-registration commit is recorded in the results report.
- The YAML's content hash (`config_hash` from `load_experiment_config`) is stamped in the
  markdown report.

## 6. Config hash + git hash in every report
`lab_reporting.write_report` automatically stamps:
- Config file name
- Config content hash (SHA-256 truncated to 16 hex chars)
- Git commit hash at report time
- Preregistration file path
- Central trial manifest path
- Cumulative `n_trials`

## 7. Trial manifest is updated BEFORE outcome viewing
- Central manifest lives at `india/ai_lab/trial_manifest.md`.
- Every new experiment appends its row to the ledger BEFORE any results are computed.
- `cumulative_strategy_search:` field is the source of truth for DSR `n_trials`.
- Cost-sensitivity variants do NOT increment the count. Same-config reruns (bug fixes) do NOT increment.
- Never revise past counts to fit a new hypothesis.

## 8. Execute once
Per pre-registered configuration. No re-running with tweaked parameters to see if a rejected
candidate can be rescued. If a bug is found, fix the scaffold, re-run under the SAME pre-reg,
and REQUIRE numerical parity vs the previous run (except where the bug fix intentionally changes
results, in which case the pre-registration must be re-sealed with an amendment log).

## 9. Audit diagnostics before promoting anything
Every experiment produces a machine-readable diagnostics CSV. Every claim in the markdown report
must be verifiable from the CSV. If a metric is displayed, its column must exist.

## 10. Commit and push findings
Two commits per experiment:
- **Pre-registration commit** (before execution): YAML + preregistration.md + code
- **Results commit** (after execution): reports/*.md + reports/*.csv + trial manifest update + README status

Never squash the pre-reg into the results — the sealed pre-reg must exist in git history at a
distinct hash before any outcomes are visible.

## 11. No Core/Telegram modification without gate pass + operator approval
- Promotion gates in the YAML are LOCKED. All must pass under EVERY sensitivity variant
  (cash-return / cost-bps / regime-attribution).
- Even after all gates pass, operator gives explicit approval before Core is touched.
- No advisory tier. No "promising enough" partial promotion. No bypass because "PBO is N/A".

## Framework files at a glance

| File | Responsibility |
|---|---|
| `india/ai_lab/lab_config.py` | YAML loader + strict validation (fails loud on missing fields) |
| `india/ai_lab/lab_metrics.py` | Shared metric suite, DSR, PBO with feasibility guard, fold-rank stability |
| `india/ai_lab/lab_runner.py` | Generic experiment orchestrator + policy/simulator plugin registry + gate expression evaluator |
| `india/ai_lab/lab_reporting.py` | Dynamic markdown + CSV report generation with provenance stamps |
| `india/ai_lab/trial_manifest.md` | Central Lab-wide cumulative trial ledger |
| `india/ai_lab/experiments.yaml` | Lab registry (status, question, decision, pointers) |
| `india/ai_lab/LAB_STANDARDS.md` | This document |
| `india/ai_lab/<LAB_ID>/<lab_id>.yaml` | Per-experiment sealed config |
| `india/ai_lab/<LAB_ID>/<experiment_policies>.py` | Per-experiment policy plugin builders |
| `india/ai_lab/<LAB_ID>/run_<lab_id>.py` | Thin runner (loads YAML, registers plugins, calls generic engine) |
| `india/ai_lab/<LAB_ID>/parity_check.py` | Only when refactoring an existing lab; enforces `abs(old - new) <= 1e-10` |
| `india/ai_lab/<LAB_ID>/preregistration.md` | Sealed hypothesis + methodology |
| `india/ai_lab/<LAB_ID>/reports/*.md`, `*.csv` | Executed results |

## Anti-patterns forbidden

- ❌ Silent defaults for research-critical values (`return 30` if manifest missing)
- ❌ Per-candidate Python functions when candidates differ only in parameters
- ❌ Hardcoded gate thresholds in Python (only in YAML)
- ❌ Adding candidates to a running experiment
- ❌ Tuning thresholds after seeing partial results
- ❌ Advisory tier / bypass promotion / "operator will filter"
- ❌ PBO across the wrong axis (e.g., cost variants of one strategy)
- ❌ Confusing discovery period with training data (there is no model to fit)
- ❌ Overwriting historical evidence reports (parity checks must use a scratch path)
