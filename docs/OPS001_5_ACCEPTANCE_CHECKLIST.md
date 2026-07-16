# OPS001.5 · Acceptance Checklist

Sign-off contract for declaring a NexaQuant deployment production-ready.
Every item below must be checked. If any item fails, the deployment is NOT
accepted. The role signing off holds accountability for the health of the
system for the acceptance window.

**Signer:** _____________________
**Date (IST):** _____________________
**Host / environment:** _____________________
**Commit SHA under test:** _____________________
**Verdict:** ☐ ACCEPTED   ☐ REJECTED

---

## 1. Repository state (pre-flight)

- [ ] `git status` is clean (no unstaged or uncommitted changes)
- [ ] `git rev-parse HEAD` matches the SHA above
- [ ] `git log --oneline -1` matches the intended release commit
- [ ] MON001 fingerprint on host equals `64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42`

## 2. Automated verification (must all exit 0)

- [ ] `python nexaquant/tests/test_regression.py` — all suites PASS, all invariance guards hold
- [ ] `python nexaquant/tests/test_ops_commissioning.py` — 23 / 23 PASS, verdict `ACCEPTED`
- [ ] `python nexaquant/tests/test_governance.py` — all governance checks PASS
- [ ] `python -m india.monitoring.MON001_Forward_Validation.ops.health_check` — 9 / 9 checks INFO, exit 0

## 3. Twenty operational subsystems (auto-verified inside §2)

Each has an explicit PASS criterion; the commissioning suite in §2 asserts
all of them. Record the result of the last commissioning run:

- [ ] SUB-01 Cold boot after machine restart — PASS
- [ ] SUB-02 Graceful shutdown (SIGTERM) — PASS
- [ ] SUB-03 Restart recovery — PASS
- [ ] SUB-04 PID lock recovery (dead pid) — PASS
- [ ] SUB-05 Stale lock cleanup (age) — PASS
- [ ] SUB-06 Interrupted pipeline recovery — PASS
- [ ] SUB-07 Scheduler correctness — PASS
- [ ] SUB-08 Time-zone correctness — PASS
- [ ] SUB-09 Log rotation — PASS
- [ ] SUB-10 Log retention — PASS
- [ ] SUB-11 Metrics persistence — PASS
- [ ] SUB-12 Dashboard refresh — PASS
- [ ] SUB-13 Telegram delivery — PASS
- [ ] SUB-14 Retry behaviour — PASS
- [ ] SUB-15 Failure escalation — PASS
- [ ] SUB-16 Status endpoint accuracy — PASS
- [ ] SUB-17 Health endpoint accuracy — PASS
- [ ] SUB-18 Recovery after pipeline exception — PASS
- [ ] SUB-19 Power loss simulation — PASS
- [ ] SUB-20 End-to-end daily pipeline wiring — PASS

## 4. Governance guards (auto-verified inside §2)

- [ ] GOV-21 No sealed / LAB artefacts touched by uncommitted diff
- [ ] GOV-22 MON001 fingerprint matches seal
- [ ] GOV-23 Production constants (HOLD=63, rebal=63, cumulative_strategy_search=38, sector_cap=2, name_cap=0.30) unchanged

## 5. Live deployment probes

- [ ] `python scripts/nexaquant_daemon.py status` → `daemon_running: true`
- [ ] `python scripts/nexaquant_daemon.py status` → `next_run_utc` is a future ISO timestamp
- [ ] `python scripts/telegram_health_check.py` → OK
- [ ] `reports/logs/nexaquant_ops.jsonl` contains a `daemon_started` event within the last hour
- [ ] Latest MON001 dashboard file matches today's IST date OR the most recent trading day
- [ ] `reports/ops_status.json` exists and has all schema-v1 fields
- [ ] Ops daemon supervisor (systemd/Task Scheduler/launchd) reports the process as running

## 6. GitHub state

- [ ] CI status on the release commit is **green** across all workflows
- [ ] No `--no-verify` commits on `main` since the last certification
- [ ] No sealed-file changes on `main` since `MON001-AMEND-2026-07-16-portability`

## 7. Documentation

- [ ] Operator on call has read [`docs/OPS001_5_OPERATOR_RUNBOOK.md`](OPS001_5_OPERATOR_RUNBOOK.md)
- [ ] Recovery playbook [`docs/OPS001B_RECOVERY.md`](OPS001B_RECOVERY.md) is accessible from the deployment host
- [ ] MON001 certification [`docs/MON001_CERTIFICATION.md`](MON001_CERTIFICATION.md) has been reviewed and is current

## 8. Explicit non-goals of this acceptance

The signer is NOT attesting to:

- Strategy edge (that's `MON001-CERT-2026-07-15`)
- Broker fills (system is PAPER_ONLY)
- Regulatory compliance beyond what the sealed baseline preserves
- Third-party data-provider SLA (yfinance, NSE, Telegram)

The signer IS attesting to:

- Every item in §§1–7 above is TRUE at the moment of signing
- The signer has verified each item personally, not by proxy
- No sealed file has been modified during the acceptance window

## 9. Signature block

**I attest that every checkbox above is TRUE for the commit SHA and host named at the top of this document. I understand that a false attestation invalidates the acceptance and requires a fresh commissioning ceremony.**

Signed: _____________________
Role:   _____________________
Date:   _____________________

## 10. Post-acceptance actions

Within 24h of acceptance:

- [ ] Archive this signed checklist under `docs/acceptance/OPS001.5-<sha>-<date>.md`
- [ ] Enable the weekly commissioning canary if not already scheduled
- [ ] Confirm on-call operator handoff for the acceptance window
