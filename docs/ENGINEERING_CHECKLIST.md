# NexaQuant · Engineering Checklist

**Purpose:** every ENG-phase (`ENGxxx`) PR must satisfy this checklist before merge.
Rejection of any single item blocks the merge — no exceptions without operator
authorization documented in the PR body.

---

## 0. Scope classification (fill in the PR body)

- [ ] This change is a **software engineering** change (infrastructure, tests, CI,
      docs, refactor, dependencies).
- [ ] This change is **NOT** a research change (no alpha search, no new
      hypothesis, no parameter tuning, no feature engineering, no model change).
- [ ] This change does **NOT** modify any of the 5 MON001-sealed baseline files:
  - `india/recommendation_registry.py`
  - `india/recommendation_generator.py`
  - `india/confidence_engine.py`
  - `india/arjuna_v2.py`
  - `india/data_nse.py`
- [ ] This change does **NOT** modify any file under `india/ai_lab/**`.
- [ ] This change does **NOT** modify any sealed MON001 core file (`monitor.py`,
      `forward_ledger.py`, `fingerprint.py`, `baseline_envelope.py`,
      `broker_layer.py`, `preregistration.md`, `mon001.yaml`).
- [ ] This change does **NOT** increment `cumulative_strategy_search` in
      `india/ai_lab/trial_manifest.md`.

## 1. Regression must be green

- [ ] `python nexaquant/tests/test_lib.py` — all pass
- [ ] `python nexaquant/tests/test_regression.py` — all suites pass, 5 invariance guards HOLD
- [ ] `python nexaquant/tests/test_ci_discipline.py` — pass
- [ ] `python nexaquant/tests/test_governance.py` — pass
- [ ] `python -m india.monitoring.MON001_Forward_Validation.ops.health_check` — exit 0

## 2. Invariance verification

- [ ] MON001 fingerprint byte-identical to sealed hash
      `064d8b04eb85b8194e02b07a07ead207770d598be72c46e4ec7698add912d52f`
- [ ] `HOLD = 63` still in `india/recommendation_registry.py`
- [ ] `rebal=63` still in `india/recommendation_generator.py`
- [ ] `cumulative_strategy_search: 38` still in `india/ai_lab/trial_manifest.md`
- [ ] `forward_boundary_asof: "2026-03-28"` still in
      `india/monitoring/MON001_Forward_Validation/mon001.yaml`
- [ ] `git diff HEAD -- india/ai_lab/` returns empty
- [ ] `git diff HEAD -- <5 sealed baseline files>` returns empty

## 3. Code quality

- [ ] Every new public function has type hints on parameters + return
- [ ] Every new public function has a docstring
- [ ] No new bare `except:` or `except Exception: pass` — narrow the exception
      type and either log the failure or re-raise
- [ ] No new `print()` in production code — use `nexaquant.lib.logging_setup.get_logger`
- [ ] No new `sys.path.insert(...)` — use `nexaquant.lib.paths` imports
- [ ] No new hardcoded absolute paths — derive from `pathlib.Path(__file__)`

## 4. Tests

- [ ] New behaviour is covered by a test in `nexaquant/tests/` or a lab-adjacent
      test file
- [ ] If migrating a helper, a byte-identity test proves output equality on
      synthetic data (see `test_lib.py` tests 26-31 for reference pattern)
- [ ] If touching a workflow, `test_ci_discipline.py` still passes
- [ ] If adding a new checklist / doc / report, `test_governance.py` still passes

## 5. Documentation

- [ ] If adding a new file: docstring at top explaining purpose
- [ ] If modifying a documented behaviour: relevant `docs/*.md` updated in the same PR
- [ ] If adding a new dependency: `requirements.txt` updated + rationale in PR body
- [ ] Cross-reference intact: this PR's ENG report (if any) references the
      correct commit hashes and does not contradict prior ENG reports

## 6. CI

- [ ] `.github/workflows/eng001-regression.yml` continues to have **zero** `||
      echo` / `|| true` masks
- [ ] Any new workflow parses via `test_workflow_yaml_parses`
- [ ] Every workflow that runs tests installs a parquet engine (`pyarrow` or
      `fastparquet`)
- [ ] Every `uses:` line pins to a version tag or SHA

## 7. Commit hygiene

- [ ] Commit message states the ENG phase, the invariants held, the tests added
- [ ] No secrets in commit content — `.env*` files are gitignored; no hardcoded
      tokens; no PAT in commit body
- [ ] Co-authored trailer if pair-produced with AI

## 8. Post-merge

- [ ] Watch `.github/workflows/eng001-regression.yml` on the merge commit — must
      go green within 20 minutes
- [ ] Watch `.github/workflows/aegis-daily.yml` next scheduled run — must succeed
- [ ] Watch `.github/workflows/mon001-daily.yml` next scheduled run — must
      succeed, MON001 state stable
