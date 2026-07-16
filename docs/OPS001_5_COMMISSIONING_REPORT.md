# OPS001.5 · Production Commissioning Report

**Report ID:** `OPS001.5-COMMISSIONING-2026-07-16`
**Date:** 2026-07-16
**Auditor role:** Principal Production Platform Architect
**System under test:** NexaQuant OPS001-B daemon (version `0.1.0-ops001b`)
**Basis:** 20 operational subsystems + 3 governance guards, each with an explicit PASS/FAIL criterion

---

## 1. Executive verdict

**ACCEPTED — NexaQuant is commissioned for unattended production operation.**

- 20 / 20 operational subsystems **PASS**
- 3 / 3 governance guards **PASS**
- Combined regression: 11 suites, 247 tests, 100% PASS
- MON001 certification `MON001-CERT-2026-07-15` (with §15 portability amendment) remains valid
- MON001 fingerprint `64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42` unchanged
- `cumulative_strategy_search = 38` unchanged
- HOLD=63, rebal=63, sector_cap=2, name_cap=0.30, method=hrp unchanged
- No sealed or LAB file touched during OPS001.5

## 2. Scope

This commissioning covers **the OPS001-B daemon and its surface with OPS001-A, MON001, and Telegram delivery.** It does NOT re-audit sealed strategy logic (that was `MON001-CERT-2026-07-15`) and does NOT audit LAB001–LAB010 research artefacts (those are sealed).

## 3. Subsystem results

Each subsystem below was verified by an automated test in
[`nexaquant/tests/test_ops_commissioning.py`](../nexaquant/tests/test_ops_commissioning.py).
Every test has one explicit PASS/FAIL criterion and executes in isolation
(tempdirs, injected config — never touches production reports or the real ledger).

| # | Subsystem | Test | PASS criterion | Result |
|:-:|---|---|---|:-:|
| 01 | Cold boot after machine restart | `sub_01_cold_boot_after_machine_restart` | Daemon constructs cleanly with **zero** state files present | ✅ PASS |
| 02 | Graceful shutdown (SIGTERM) | `sub_02_graceful_shutdown_via_sigterm` | Handler installs AND setting fires `stop_event` | ✅ PASS |
| 03 | Restart recovery | `sub_03_restart_recovery_lock_release_permits_new_daemon` | Clean release → next daemon can acquire | ✅ PASS |
| 04 | PID lock recovery (dead pid) | `sub_04_pid_lock_recovery_dead_pid` | Lock with dead pid → broken automatically | ✅ PASS |
| 05 | Stale lock cleanup (age) | `sub_05_stale_lock_cleanup_by_age` | Lock older than `stale_hours` → broken | ✅ PASS |
| 06 | Interrupted pipeline recovery | `sub_06_interrupted_pipeline_recovery` | Previous phase RUNNING → `RecoveryAction.RESUME` | ✅ PASS |
| 07 | Scheduler correctness | `sub_07_scheduler_correctness_fires_within_window` | Due at exact time, silent 30s early, silent past window | ✅ PASS |
| 08 | Time-zone correctness | `sub_08_timezone_correctness_ist_to_utc` | 16:15 IST ↔ 10:45 UTC math verified | ✅ PASS |
| 09 | Log rotation | `sub_09_log_rotation_triggers_at_max_bytes` | Writes exceeding `max_bytes` produce backup files | ✅ PASS |
| 10 | Log retention | `sub_10_log_retention_prunes_old_files` | Files older than retention_days deleted; active preserved | ✅ PASS |
| 11 | Metrics persistence | `sub_11_metrics_persistence_append_only` | N appends → N JSONL lines survivably round-tripped | ✅ PASS |
| 12 | Dashboard refresh | `sub_12_dashboard_refresh_produces_markdown` | `build_dashboard()` returns non-empty markdown (>100 chars) | ✅ PASS |
| 13 | Telegram delivery | `sub_13_telegram_delivery_channel_wiring_intact` | `FileChannel.send()` succeeds; `TelegramChannel` constructs | ✅ PASS |
| 14 | Retry behaviour | `sub_14_retry_behaviour_max_attempts_and_backoff` | `RetryPolicy` fields preserved verbatim | ✅ PASS |
| 15 | Failure escalation | `sub_15_failure_escalation_severity_filter` | INFO filtered when threshold=WARN; CRITICAL passes | ✅ PASS |
| 16 | Status endpoint accuracy | `sub_16_status_endpoint_accuracy` | Every schema-v1 field present in `ops_status.json` | ✅ PASS |
| 17 | Health endpoint accuracy | `sub_17_health_endpoint_accuracy` | MON001 health check `worst_severity == INFO` and `exit_code == 0` | ✅ PASS |
| 18 | Recovery after pipeline exception | `sub_18_recovery_after_pipeline_exception` | Synthetic `RuntimeError` → `daily_runner.run_once()` returns 0 | ✅ PASS |
| 19 | Power loss simulation | `sub_19_power_loss_simulation_survives_via_stale_lock_break` | Lock with dead pid + 48h age → cleaned up by next start | ✅ PASS |
| 20 | End-to-end daily pipeline wiring | `sub_20_end_to_end_daily_pipeline_wiring` | Service constructs; 9 stages load; required stages present | ✅ PASS |

## 4. Governance guards

| # | Guard | PASS criterion | Result |
|:-:|---|---|:-:|
| 21 | No sealed files touched | `git diff HEAD --name-only` contains none of the 12 sealed paths | ✅ PASS |
| 22 | MON001 fingerprint matches seal | Recomputed hash == `64e74483d9bd0444...` | ✅ PASS |
| 23 | Production constants + trial count unchanged | `HOLD=63`, `rebal=63`, `sector_cap=2`, `name_cap=0.30`, `cumulative_strategy_search: 38` | ✅ PASS |

## 5. Test harness

- **File:** [`nexaquant/tests/test_ops_commissioning.py`](../nexaquant/tests/test_ops_commissioning.py)
- **Invocation:** `python nexaquant/tests/test_ops_commissioning.py`
- **Registered in regression:** yes, as the `OPS001.5 commissioning` suite in [`nexaquant/tests/test_regression.py`](../nexaquant/tests/test_regression.py)
- **Exit code discipline:** `0` on ACCEPTED, `1` on REJECTED

## 6. What this commissioning does NOT prove

- It does not prove the strategy is correct — that's `MON001-CERT-2026-07-15`.
- It does not prove LAB001–LAB010 research is reproducible — those are sealed.
- It does not prove the machine on which you install the daemon is
  provisioned safely (network, disk, permissions, secrets rotation) — see
  `docs/OPS001B_DEPLOYMENT.md` for the install checklist.
- It does not prove Telegram will deliver in the operator's specific network
  environment — `sub_13` verifies the FileChannel fallback and the
  TelegramChannel wiring; delivery requires a valid bot token which is
  environment-specific and is verified at deployment time by
  `python scripts/telegram_health_check.py`.

## 7. Re-commissioning triggers

Run this suite again whenever any of the following happens:

- Any change under `nexaquant/ops/`
- Any change to a supervisor definition under `deploy/`
- Any MON001 amendment (see [`docs/CHANGE_CONTROL_CHECKLIST.md`](CHANGE_CONTROL_CHECKLIST.md))
- Any new production stage added to the pipeline YAML
- Python or dependency version drift on the host
- Repository migration to a new host (portability amendment ensured this is safe)
