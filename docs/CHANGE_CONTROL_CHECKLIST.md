# NexaQuant · Change Control Checklist

**Purpose:** governs changes to files or values that trigger MON001
`CONFIG_DRIFT` or invalidate research seals. Applies when — and ONLY when — the
operator has authorized modification of one of the following:

- The 5 MON001-sealed baseline files (`recommendation_registry.py`,
  `recommendation_generator.py`, `confidence_engine.py`, `arjuna_v2.py`,
  `data_nse.py`)
- `HOLD` value in `india/recommendation_registry.py`
- `rebal` / `sector_cap` / `name_cap` / `method` in `india/recommendation_generator.py`
- `current_regime()` in `india/confidence_engine.py`
- HRP kernel in `india/arjuna_v2.py`
- `NIFTY200` universe in `india/data_nse.py`
- `cumulative_strategy_search` in `india/ai_lab/trial_manifest.md`
- MON001 sealed core files (any of the 7 in `docs/MON001_CERTIFICATION.md` §13)
- `forward_boundary_asof` in `mon001.yaml`

**Any change to the above without following this checklist is a governance
breach** and MUST be reverted.

---

## 1. Pre-authorization

- [ ] Operator has written authorization (email / documented Slack message /
      recorded decision) linking to the specific change proposed
- [ ] The change is preregistered — a sealed document exists in `docs/` or
      `india/ai_lab/` that specifies:
  - what will change (file + field + old value + new value)
  - why (the evidence that motivates the change)
  - what will NOT change (explicit no-op list)
  - what tests will verify the change is safe
  - what conditions would trigger a rollback

## 2. Evidence requirements

Depending on the change:

| Change type | Required evidence |
|---|---|
| `HOLD` value | Lab-level PROMOTE-ELIGIBLE + LOBO validation + ≥ 3 months forward-paper divergence < envelope + operator-approved risk write-up |
| `rebal` / `sector_cap` / `name_cap` / `method` | ENG005-style portfolio-construction lab + byte-identity failure documented |
| `current_regime()` | Lab-level PROMOTE-ELIGIBLE + regime robustness under LOBO |
| HRP kernel | Portfolio-construction lab + adversarial audit |
| `NIFTY200` | Universe stability + survivorship analysis + operator sign-off |
| `cumulative_strategy_search` increment | New preregistered lab active; documented per `docs/FUTURE_RESEARCH_ROADMAP.md` §15 rules |
| MON001 sealed core | ENG-style refactor + byte-identity proof + MON001 re-seal ceremony |
| `forward_boundary_asof` | Never — would invalidate MON001 evidence retroactively. Change only if wiping the ledger and restarting from a new seal is explicitly authorized |

## 3. Execution

- [ ] Change is made in a separate branch, NOT on `main`
- [ ] Pre-change fingerprint captured (`python -m india.monitoring.MON001_Forward_Validation.ops.health_check`)
- [ ] Change committed with a message referencing:
  - the authorization document
  - the specific preregistration
  - the expected fingerprint delta (which files change, and by what)
- [ ] Post-change fingerprint captured
- [ ] MON001 re-seal ceremony:
      ```
      rm india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json
      python -m india.monitoring.MON001_Forward_Validation.ops.daily_runner --seal-init
      ```

## 4. Verification

- [ ] `python nexaquant/tests/test_regression.py` — all suites still pass
      (the invariance guards WILL flag the new fingerprint; document this
      explicitly)
- [ ] MON001 `daily_runner` continues to produce diagnostics + reports
- [ ] Forward-paper divergence envelope reset appropriately (or explicitly
      accepted with rationale)
- [ ] Every dependent doc (`MON001_CERTIFICATION.md`, `FUTURE_RESEARCH_ROADMAP.md`,
      relevant ENG reports) updated with the new fingerprint hash

## 5. Merge criteria

- [ ] Second operator has independently reviewed the change (four-eyes principle)
- [ ] Rollback plan documented and executable within 5 minutes
- [ ] Alerting is temporarily heightened for the first 4 weeks post-change

## 6. Immediate post-merge

- [ ] Watch MON001 D1 CONFIG_DRIFT alert — should NOT trigger (new fingerprint
      is now the sealed baseline)
- [ ] Watch daily pipeline for 5 consecutive days — no regressions
- [ ] Document `docs/MON001_CERTIFICATION.md` history section with the change
      and new certification ID
- [ ] If any drift dimension goes DIVERGED for 4 consecutive weeks post-change,
      HALT_REVIEW_REQUIRED fires and the change must be re-audited

## 7. Never

- **Never** modify a sealed file to silence a monitoring alert.
- **Never** re-seal MON001 to make a CONFIG_DRIFT alert go away without a
  documented authorized change.
- **Never** revert LAB evidence without a documented forensic reason.
- **Never** touch `cumulative_strategy_search` outside of an active preregistered
  lab.

**Change control failures are governance incidents. Log them, investigate root
cause, and update this checklist to prevent recurrence.**
