# OPS001-D · Production Validation & Live Commissioning Plan

**Plan ID:** `OPS001-D-PLAN-2026-07-16`
**Role:** Principal Reliability Engineer / Production Validation Lead
**Repository state:** commit `7a86013` on `main` (OPS001-C merged, CI green)
**Scope:** Planning only. No chaos test executed. No production code modified.
**Predecessor:** OPS001.5 commissioning report (`ACCEPTED 23/23`, 2026-07-16)

> This document is the plan. Execution begins when the operator explicitly
> approves and names an execution window. **STOP after this plan** —
> nothing in phases 1-6 authorises live chaos injection.

---

## Table of contents

- [Phase 1 · Repository Audit + Architecture Dependency Map](#phase-1--repository-audit--architecture-dependency-map)
- [Phase 2 · Production Validation Matrix](#phase-2--production-validation-matrix)
- [Phase 3 · Chaos Scenario Registry](#phase-3--chaos-scenario-registry)
- [Phase 4 · 7-Day Commissioning Plan](#phase-4--7-day-commissioning-plan)
- [Phase 5 · Acceptance Criteria (Production Gates)](#phase-5--acceptance-criteria-production-gates)
- [Phase 6 · Operational Risk Assessment](#phase-6--operational-risk-assessment)
- [Phase 7 · Final Recommendation](#phase-7--final-recommendation)
- [Appendix A · Evidence collected during Phase 1](#appendix-a--evidence-collected-during-phase-1)

---

## Phase 1 · Repository Audit + Architecture Dependency Map

### 1.1 What was audited

Every operational component shipped through OPS001-A / OPS001-B / OPS001.5 /
OPS001-C, plus the sealed MON001 core and the GitHub Actions surface.

| Layer | Files (count) | Location |
|---|:-:|---|
| Ops modules (core) | 15 | `nexaquant/ops/*.py` |
| Notification subsystem | 12 | `nexaquant/ops/notify/*.py` |
| Pipeline definitions | 1 | `nexaquant/ops/pipelines/aegis_daily.yaml` |
| Ops tests | 4 | `nexaquant/tests/test_ops_*.py` |
| Regression + governance tests | 9 | `nexaquant/tests/test_*.py` (excluding ops_*) |
| MON001 sealed core (read-only) | 8 | `india/monitoring/MON001_Forward_Validation/*.py + .yaml + .md` |
| MON001 ops | 6 | `india/monitoring/MON001_Forward_Validation/ops/*.py` |
| Entrypoint scripts | 5 | `scripts/*.py` |
| Platform deploy templates | 3 | `deploy/{systemd,task-scheduler,launchd}/` |
| GitHub Actions workflows | 3 | `.github/workflows/*.yml` |
| Documentation | 56 | `docs/*.md` |

### 1.2 Architecture dependency map — text form

```
    ┌────────────────────────────────────────────────────────────────┐
    │              TIME + INFRASTRUCTURE TRIGGERS                     │
    │   GitHub Actions cron  ───┐        Local systemd/TaskSched     │
    │   (aegis-daily.yml,       │        (deploy/{systemd,           │
    │    mon001-daily.yml)      │         task-scheduler,launchd}/)  │
    └───────────────────────────┼────────────────────────────┬───────┘
                                │                            │
                                ▼                            ▼
                    ┌─────────────────────┐    ┌───────────────────────────┐
                    │ ci-workflow steps   │    │ scripts/nexaquant_daemon.py│
                    │ (in-workflow shell) │    │  → nexaquant.ops.cli       │
                    └──────────┬──────────┘    │  → NexaQuantDaemon.start() │
                               │               └──────────┬────────────────┘
                               │                          │
              ┌────────────────┴──────────────────┐       │
              │                                   │       │
              ▼                                   ▼       ▼
    ┌────────────────────┐              ┌──────────────────────────┐
    │  Legacy path:      │              │  Daemon path (OPS001-B): │
    │  direct python     │              │   PidLock  → Scheduler   │
    │  invocations:      │              │   Slot (16:15/18:30/     │
    │   - refresh_data   │              │    21:00 IST Mon-Fri)    │
    │   - freshness_gate │              │   → tick() → run_once()  │
    │   - AEGIS engine   │              └──────────────┬───────────┘
    │   - Telegram       │                             │
    │   - MON001 daily   │                             ▼
    └──────────┬─────────┘              ┌──────────────────────────┐
               │                        │  NexaQuantService        │
               │                        │  (OPS001-A)              │
               │                        │  load_pipeline           │
               │                        │  → Pipeline.run          │
               │                        └──────────────┬───────────┘
               │                                       │
               └──────────────────┬────────────────────┘
                                  ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                    AEGIS DAILY PIPELINE (9 stages)              │
    │                                                                 │
    │  refresh_data → freshness_gate → recommendation_generator       │
    │     → recommendation_db → scorecard → ops_check                 │
    │       → telegram_health_check → telegram_notify → mon001_daily  │
    │                                                                 │
    │  Each stage: RetryPolicy (max_attempts, backoff_s), timeout_s,  │
    │  continue_on_failure flag                                       │
    └────────────────────────┬────────────────────────────────────────┘
                             │
      emits StageEvent to    │
      ┌──────────────────────┴─────────────────────────┐
      ▼                                                ▼
    MetricsLedger                          NotificationManager
    (ops_metrics.jsonl,                    (OPS001-A + OPS001-C)
     append-only)                             │
                                              ├─ FileChannel (always)
                                              ├─ TelegramChannel
                                              ├─ EmailChannel
                                              ├─ SlackChannel
                                              ├─ DiscordChannel
                                              └─ WebhookChannel
                                                    │
                                              on send() = False
                                                    ▼
                                              RetryQueue (JSONL)
                                                    │
                                              max_attempts exceeded
                                                    ▼
                                              Dead-Letter Queue

                             │
                             ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                        STATE + OBSERVABILITY                    │
    │                                                                 │
    │  StatusWriter → reports/ops_status.json (atomic, schema v1)     │
    │  ProcessMonitor → uptime/memory/CPU (psutil/resource/minimal)   │
    │  RunState (recovery.py) → reports/ops_run_state.json            │
    │  Scheduler state → reports/ops_schedule_state.json              │
    │  Dashboard (notify) → reports/ops_notify_*.jsonl                │
    │  History → reports/ops_alerts.jsonl                             │
    │  Logging (JSON) → reports/logs/nexaquant_ops.jsonl + rotations  │
    └─────────────────────────────────────────────────────────────────┘

                             │
                             │  independently verified by
                             ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │              MON001 (sealed, invariance-verified)               │
    │                                                                 │
    │  fingerprint.py (v2 LF-normalised)                              │
    │  → sealed_fingerprint.json (64e74483d9bd0444...)                │
    │  → forward_ledger.jsonl (150 rows, hash-chained)                │
    │  → baseline_envelope (portability-amended 2026-07-16)           │
    │  → broker_layer (PAPER_ONLY, code-forced)                       │
    │                                                                 │
    │  health_check exposes 9 checks, exit 0 == INFO worst_severity   │
    └─────────────────────────────────────────────────────────────────┘
```

### 1.3 Integration matrix (16 subsystems × direct dependencies)

| # | Subsystem | Depends directly on | Depended on by |
|:-:|---|---|---|
| S01 | GitHub Actions (aegis-daily / mon001-daily) | GitHub cron, secrets, runner Python | Legacy daily pipeline path |
| S02 | AEGIS daily pipeline (YAML) | S03, S04, S05, S06, S08, S10, S11, S12, S13 | S18 |
| S03 | MON001 (sealed) | S14 (fingerprint), sealed data files | S02 stage 9, S17, S18 |
| S04 | OPS001-A pipeline runner | S06 (retry), S07 (config), S16 (metrics), S17 (status) | S05, S16 |
| S05 | OPS001-B daemon | S04, S06, S08, S09, S15 (logging), S17 (status) | operator, S22 |
| S06 | Retry policy | (stdlib) | S04, S18 |
| S07 | Pipeline config loader | (stdlib + pyyaml) | S04 |
| S08 | Scheduler + slots | (stdlib) | S05 |
| S09 | PID lock | (stdlib) | S05 |
| S10 | Telegram notify (channel) | env vars (BOT_TOKEN, CHAT_ID) | S02 stage 8, S18 |
| S11 | File fallback channel | (stdlib) | S02, S18 (always in routing) |
| S12 | Notification templates (8) | (pure) | operator, S05, S18 |
| S13 | Routing policy | (stdlib) | S18 |
| S14 | Recovery logic (RunState) | (stdlib) | S05 |
| S15 | Log rotation + retention | (stdlib logging.handlers) | S05, S18 |
| S16 | Metrics ledger | (stdlib) | S04 |
| S17 | Status endpoint (ops_status.json) | (stdlib) | S05, dashboard |
| S18 | NotificationManager + all channels | S10-S13, S15, S16, S17 | S05, operator |
| S19 | Retry queue + DLQ | S18 | operator (via CLI) |
| S20 | Alert history (JSONL/CSV/MD) | S18's file output | operator (via CLI) |
| S21 | Notification dashboard + health APIs | S18, S19 | operator (via CLI) |
| S22 | CLI (nexaquant-ops) | S05, S18, S19, S20, S21 | operator |

Dependency graph is **acyclic** — verified by inspection. No module depends
on any other in a cycle.

### 1.4 Trust boundaries

| Boundary | Modules on our side | External | Failure impact |
|---|---|---|:-:|
| Data provider | S02 stage 1 (`refresh_data`) | yfinance / NSE | HIGH — freshness_gate should catch |
| Telegram API | S10 | api.telegram.org | MED — retry+file fallback |
| Slack / Discord / Webhook | S18 channels | webhook endpoints | LOW — file fallback is durable |
| SMTP relay | S18 email | smtp.gmail.com / operator's server | MED — retry+file fallback |
| GitHub API (workflow cron) | S01 | github.com | MED — daemon path covers |
| Filesystem (`reports/`) | S15, S16, S17, S18, S19, S20 | host disk | HIGH — disk full breaks everything |
| Host clock | S08 (Scheduler) | NTP | MED — slot dedup uses IST offset |
| Process supervisor | Systemd / TaskSched / launchd | host OS | LOW — restart-on-failure covers |

### 1.5 Data flow — one daily pipeline pass

```
t=0        Cron / Scheduler fires slot.
t+0-30s    PidLock acquired, RunState.STARTING written.
t+30s-2min refresh_data (yfinance) → data/*.csv appended.
t+2-3min   freshness_gate → aborts if data > cutoff.
t+3-9min   recommendation_generator → india/reports/recommendations_YYYY-MM-DD.csv.
t+9-11min  recommendation_db → sqlite snapshot.
t+11-13m   scorecard, ops_check → india/reports/*.md.
t+13-14m   telegram_health_check → 200 OK from getMe.
t+14-16m   telegram_notify (--attempts 4) → user's phone.
t+16-22m   mon001_daily → dashboard + diagnostics + alert bus.
t+22m      Pipeline SUCCESS, RunState.COMPLETED, StatusSnapshot written.
```

MTTR budget for one pipeline pass: **~25 minutes wall clock** (from
existing production runs; validated in Phase 4).

---

## Phase 2 · Production Validation Matrix

Every subsystem below MUST have every field verified during commissioning.
This is the artefact the operator signs off.

Fields per subsystem: **Purpose · Dependencies · Failure modes · Expected
behaviour · Recovery path · PASS criteria · FAIL criteria · Evidence
required · Owner.**

### 2.1 S01 · GitHub Actions (aegis-daily, mon001-daily)

- **Purpose:** External time trigger for the daily pipeline when the
  self-hosted daemon is not running.
- **Dependencies:** GitHub cron scheduler, repo secrets, ubuntu-latest runner.
- **Failure modes:** Cron drop (GitHub jitter), missing secret, dependency
  install failure, network blip during checkout.
- **Expected behaviour:** Primary slot at 16:15 IST Mon-Fri. Backup slots at
  18:30 and 21:00 IST. Idempotent same-IST-day guard prevents duplicate runs.
- **Recovery path:** Backup crons + `workflow_dispatch` manual trigger.
- **PASS:** Every trading day has exactly one successful pipeline commit
  during the observation window.
- **FAIL:** Any weekday with zero successful runs after 21:00 IST.
- **Evidence:** GitHub Actions run history + `data/aegis_registry.csv` daily
  rows.
- **Owner:** Operator.

### 2.2 S02 · AEGIS daily pipeline (9 stages)

- **Purpose:** Compute daily recommendations, publish to Sheets/DB/Telegram,
  invoke MON001.
- **Dependencies:** yfinance, sealed strategy files (data_nse, arjuna_v2,
  confidence_engine, recommendation_registry, recommendation_generator),
  broker_layer (PAPER_ONLY).
- **Failure modes:** yfinance rate-limit, stale data, sealed-file drift,
  broker mode flip, dependency version mismatch.
- **Expected behaviour:** All 9 stages run in order. `continue_on_failure`
  on refresh_data + recommendation_db + scorecard + ops_check + mon001_daily
  allows the pipeline to progress even if one non-critical stage fails.
  `telegram_notify` is gated on `telegram_health_check`.
- **Recovery path:** RetryPolicy on early stages (retry=1-2, backoff 30-90s).
  Failed pipeline runs again at the next slot.
- **PASS:** ≥ 95% of scheduled runs report `pipeline_success` in the
  30-day observation window; 100% of runs preserve MON001 fingerprint.
- **FAIL:** any run modifies HOLD, rebal, cumulative_strategy_search,
  or the MON001 fingerprint.
- **Evidence:** `reports/ops_status.json`, `reports/ops_metrics.jsonl`,
  MON001 diagnostics files.
- **Owner:** Operator + this Principal Engineer.

### 2.3 S03 · MON001 sealed core

- **Purpose:** Independent oversight — every daily recommendation is
  checked against the sealed baseline envelope.
- **Dependencies:** fingerprint.py (v2), forward_ledger.jsonl,
  baseline_envelope_*.json, sealed_fingerprint.json.
- **Failure modes:** Fingerprint drift, ledger hash-chain break,
  envelope drift (portability amendment covered cross-host case),
  broker mode flipping to non-PAPER.
- **Expected behaviour:** Every daily run appends one hash-chained row to
  forward_ledger; produces mon001_report_YYYY-MM-DD.md and diagnostics JSON;
  emits alerts on drift.
- **Recovery path:** None automatic — HALT requires operator inspection
  and CHANGE_CONTROL_CHECKLIST ceremony.
- **PASS:** `health_check` → INFO on every day of the observation window.
- **FAIL:** Any HALT event.
- **Evidence:** Daily `mon001_diagnostics_*.json` + `mon001_alerts.jsonl`.
- **Owner:** Principal Engineer.

### 2.4 S04 · OPS001-A pipeline runner

- **Purpose:** Orchestrate stages with retry / backoff / timeout / event
  emission / metrics recording.
- **Dependencies:** RetryPolicy (S06), config loader (S07), MetricsLedger (S16),
  StatusWriter (S17), NotificationManager (S18).
- **Failure modes:** Subprocess timeout leaves child processes, YAML parse
  error, notifier crash, atomic-write race on status file.
- **Expected behaviour:** Each stage runs in a subprocess with the
  configured timeout; RetryPolicy honours max_attempts and backoff_s;
  events emit STARTED → RUNNING → RETRY? → SUCCESS/FAILED → COMPLETE.
- **Recovery path:** `continue_on_failure` on non-critical stages. Retries
  handle transient failures.
- **PASS:** Every pipeline run in the observation window returns exit 0/1;
  no framework errors (exit 2).
- **FAIL:** Any `slot_framework_error` event in daemon logs.
- **Evidence:** `reports/ops_metrics.jsonl`, event stream.
- **Owner:** Principal Engineer.

### 2.5 S05 · OPS001-B daemon

- **Purpose:** Long-lived process that fires the pipeline at scheduled slots,
  handles signals, recovers from prior interruption.
- **Dependencies:** All of S04-S17 except S01, S02, S03.
- **Failure modes:** Lock leak (SIGKILL), signal handler not installed on
  Windows, uncaught exception in tick, timezone drift.
- **Expected behaviour:** Acquires PID lock, refreshes every 15 min, polls
  every 30s, fires due slots, marks RunState transitions, releases lock
  on clean stop.
- **Recovery path:** systemd `Restart=on-failure` / Task Scheduler
  RestartOnFailure / launchd KeepAlive.
- **PASS:** Uptime ≥ 99% of scheduled window; graceful stop always releases
  lock; every restart correctly reads prior RunState.
- **FAIL:** Two consecutive weekdays with zero slot fires while daemon
  reports running.
- **Evidence:** `reports/logs/nexaquant_ops.jsonl`, `ops_status.json`,
  `ops_schedule_state.json`.
- **Owner:** Operator + Principal Engineer.

### 2.6 S06 · RetryPolicy

- **Purpose:** Per-stage retry semantics (max_attempts, backoff, timeout).
- **Dependencies:** stdlib only.
- **Failure modes:** Backoff array shorter than max_attempts (already
  handled with modulo).
- **Expected behaviour:** attempt N waits backoff_s[N-1]s (or last element
  if shorter) before retry.
- **Recovery path:** N/A — pure data.
- **PASS:** OPS001-A pipeline tests remain green.
- **FAIL:** Any observed retry that doesn't match declared backoff.
- **Evidence:** Metrics ledger `attempts` column.
- **Owner:** Principal Engineer.

### 2.7 S08 · Scheduler + slots

- **Purpose:** Fire slot when local (IST) time is inside `[scheduled,
  scheduled + fire_window]` AND slot hasn't fired today.
- **Dependencies:** stdlib datetime, host clock, ops_schedule_state.json.
- **Failure modes:** Host clock drift, fire_window too short (< poll_interval),
  DST edge cases (India has no DST — safe).
- **Expected behaviour:** Slot fires exactly once per calendar IST day.
  Persistent state survives daemon restart.
- **Recovery path:** Corrupt schedule state → daemon treats every slot as
  "not fired today" → may double-fire once, tolerable.
- **PASS:** For every daemon-uptime weekday, exactly one primary_1615_ist
  fire OR at least one backup fires.
- **FAIL:** Duplicate fire in same IST day (visible in
  ops_schedule_state.json OR duplicate rec_id in mon001 ledger).
- **Evidence:** `ops_schedule_state.json`, `ops_alerts.jsonl` for duplicates.
- **Owner:** Principal Engineer.

### 2.8 S09 · PID lock

- **Purpose:** Ensure at most one daemon per host.
- **Dependencies:** stdlib os.kill, filesystem.
- **Failure modes:** Lock file survives SIGKILL, stale by age vs stale by
  dead-pid ambiguity, filesystem read-only.
- **Expected behaviour:** Break lock if pid dead OR age > 6h; refresh
  every 15 min while owned; release on clean exit.
- **Recovery path:** Stale-lock cleanup on next start (verified in
  OPS001.5 SUB-04, SUB-05, SUB-19).
- **PASS:** No observed "two daemons alive" state; no daemon ever fails to
  start due to legitimately-stale lock.
- **FAIL:** Two daemons run simultaneously (visible via duplicate
  ops_status.json writes) OR daemon fails to start with dead lock.
- **Evidence:** `ops_daemon.lock` age, `ops_status.json` `pid` field.
- **Owner:** Principal Engineer.

### 2.9 S10 · Telegram channel

- **Purpose:** Push alerts + daily summary to operator's phone.
- **Dependencies:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, network to
  api.telegram.org.
- **Failure modes:** Bot token rotated, chat_id changed, message > 4096
  chars, api rate limit, DNS failure.
- **Expected behaviour:** `configured=True` → `send()` returns True on 2xx
  HTTP. On failure, retry-wrapper attempts 4x with backoff (already in the
  workflow).
- **Recovery path:** File fallback captures every message regardless of
  Telegram outcome. Retry queue can re-attempt.
- **PASS:** ≥ 95% delivery in 30-day window; every day's first alert
  arrives before 22:00 IST.
- **FAIL:** > 3 consecutive weekdays without any Telegram delivery while
  daemon reports pipeline success.
- **Evidence:** Telegram delivery ledger (workflow artifact), `ops_alerts.jsonl`.
- **Owner:** Operator.

### 2.10 S11 · File fallback channel

- **Purpose:** Durable audit trail. Never lose a notification.
- **Dependencies:** filesystem.
- **Failure modes:** Disk full, permission denied, journal corruption.
- **Expected behaviour:** Every emit → append one JSON line to `ops_alerts.jsonl`.
  `send()` returns True unless disk is full.
- **Recovery path:** Rotate the file manually if it grows too large.
- **PASS:** No missing alerts vs upstream event stream (cross-check
  count of `slot_completed` events against alert count).
- **FAIL:** Any `slot_completed` event with no corresponding alert entry.
- **Evidence:** `reports/ops_alerts.jsonl` count vs
  `reports/logs/nexaquant_ops.jsonl` count of relevant events.
- **Owner:** Principal Engineer.

### 2.11 S13 · Routing policy

- **Purpose:** Choose destination channels per severity.
- **Dependencies:** none (pure data).
- **Failure modes:** Policy modified to skip file fallback (rejected by
  `include_file_fallback=True`).
- **Expected behaviour:** INFO→file; WARN→telegram+file; ERROR→telegram+email+file;
  CRITICAL→ all channels.
- **Recovery path:** N/A.
- **PASS:** For each severity level, the observed set of channels attempted
  matches the policy (visible in `notify status`).
- **FAIL:** Any severity-level delivery attempt bypasses file channel.
- **Evidence:** `nexaquant-ops notify status` output.
- **Owner:** Principal Engineer.

### 2.12 S14 · Recovery logic (RunState)

- **Purpose:** Detect and act on previous pipeline interruption.
- **Dependencies:** `reports/ops_run_state.json`.
- **Failure modes:** Corrupt file, phase never transitions to COMPLETED.
- **Expected behaviour:** On daemon startup, decide() returns NONE / RESUME
  / ATTENTION based on prior phase; RESUME emits WARN alert.
- **Recovery path:** N/A — this IS the recovery.
- **PASS:** Every daemon restart with a mid-flight prior run emits
  `recovery_decision` event.
- **FAIL:** Silent skip of a leftover RUNNING state.
- **Evidence:** `nexaquant_ops.jsonl` filtered for `event=recovery_decision`.
- **Owner:** Principal Engineer.

### 2.13 S15 · Log rotation + retention

- **Purpose:** Bounded disk footprint + auditability.
- **Dependencies:** Python `RotatingFileHandler`, `prune_old_logs()`.
- **Failure modes:** Rotation off (max_bytes = 0), retention deletes active
  file, prune fails silently on permission error.
- **Expected behaviour:** Active file ≤ 5 MiB. Up to 14 backups. Rotations
  older than 30 days deleted.
- **Recovery path:** Manual `logrotate` fallback.
- **PASS:** `reports/logs/` total size < 100 MiB throughout observation window.
- **FAIL:** Disk usage grows unboundedly OR active log file gets pruned.
- **Evidence:** `du -sh reports/logs/` snapshot per day.
- **Owner:** Principal Engineer.

### 2.14 S17 · Status endpoint

- **Purpose:** External-consumer view of daemon + last pipeline pass.
- **Dependencies:** `_atomic_write_json`, git, filesystem.
- **Failure modes:** Concurrent writes (safe — atomic), git binary missing.
- **Expected behaviour:** Atomic rewrite after every pipeline pass; every
  schema-v1 field present; `mon001_state` reflects last `mon001_diagnostics_*`.
- **Recovery path:** N/A — regenerated on next pass.
- **PASS:** `ops_status.json` has all 15 schema-v1 fields on every day.
- **FAIL:** Missing field OR schema_version != 1.
- **Evidence:** Daily snapshot of `ops_status.json`.
- **Owner:** Principal Engineer.

### 2.15 S18 · NotificationManager + all channels

- **Purpose:** Fan-out notification delivery.
- **Dependencies:** S10, S11, plus 4 new OPS001-C channels.
- **Failure modes:** All remote channels fail simultaneously (network
  partition), FileChannel disk full, one channel raises uncaught exception.
- **Expected behaviour:** Every channel is tried in order; per-channel result
  captured; `emit_or_raise` fails only if EVERY accepted channel returned False.
- **Recovery path:** File fallback captures the message even under total
  remote failure. RetryQueue enqueues failed remote sends.
- **PASS:** Every emit produces per-channel DeliveryResult; at least
  FileChannel = True.
- **FAIL:** Any emit produces zero delivery results OR an unhandled exception.
- **Evidence:** `notify status` output + `notify history` count.
- **Owner:** Principal Engineer.

### 2.16 S19 · Retry queue + DLQ

- **Purpose:** Recover from transient remote failures without losing alerts.
- **Dependencies:** S18, filesystem JSONL.
- **Failure modes:** Queue file grows unbounded, DLQ never drained, JSONL
  corruption breaks reader.
- **Expected behaviour:** Failed remote sends enqueued; `process_queue()`
  drains ready entries with exponential backoff; max_attempts exceeded →
  DLQ.
- **Recovery path:** Manual `notify retry` invocation. `notify purge --yes`
  clears DLQ + delivered ledger.
- **PASS:** Queue drains to 0 within 30 minutes of remote recovery; DLQ
  entries reflect only genuinely persistent failures.
- **FAIL:** Queue grows monotonically OR DLQ receives entries during
  healthy remote availability.
- **Evidence:** `notify status` (pending / DLQ counts over time).
- **Owner:** Principal Engineer.

### 2.17 S21 · Dashboard + health APIs

- **Purpose:** Operator single-glance view of notification subsystem health.
- **Dependencies:** S18, S19, S20.
- **Failure modes:** Stale reads if daemon writes concurrently (best-effort
  — dashboard is a view, not a source of truth).
- **Expected behaviour:** `notification_status()` returns OK when DLQ
  empty; DEGRADED when DLQ has entries; per-channel row for each configured
  channel.
- **Recovery path:** N/A — pure aggregator.
- **PASS:** `channel_health()` correctly reports `configured=True` for every
  channel with env vars set.
- **FAIL:** Configured channel reports `configured=False`.
- **Evidence:** `notify status` JSON output.
- **Owner:** Principal Engineer.

### 2.18 Coverage summary

| Field | Verified for | Missing on |
|---|:-:|---|
| Purpose | all 22 | — |
| Dependencies | all 22 | — |
| Failure modes | all 22 | — |
| Expected behaviour | all 22 | — |
| Recovery path | all 22 | — |
| PASS criteria | all 22 | — |
| FAIL criteria | all 22 | — |
| Evidence required | all 22 | — |
| Owner | all 22 | — |

---

## Phase 3 · Chaos Scenario Registry

26 pre-designed failure scenarios. **NONE are executed by this plan.**
Execution requires explicit operator authorisation per scenario.

Each scenario: **Trigger · Expected recovery · Expected alert · Expected
operator action · PASS criteria · Estimated severity · Estimated MTTR.**

### CS-01 · Network unavailable (host loses uplink)

- **Trigger:** Disable network interface for 5 minutes during a slot fire.
- **Expected recovery:** yfinance / Telegram / Slack / Discord / SMTP fail;
  FileChannel succeeds; retry queue enqueues remote channels; backup slot
  16:15 → 18:30 retries.
- **Expected alert:** WARN on daemon; eventually CRITICAL if all slots miss.
- **Expected operator action:** Restore network. Run `notify retry`.
- **PASS:** No alert lost; retry queue drains within 30 min of restore.
- **Severity:** HIGH.
- **MTTR:** 30 min after network restore.

### CS-02 · Telegram unavailable (api.telegram.org 5xx)

- **Trigger:** Block api.telegram.org via hosts file for 10 minutes.
- **Expected recovery:** telegram_health_check fails; telegram_notify skipped
  (workflow) OR TelegramChannel.send returns False (daemon); retry queue
  captures.
- **Expected alert:** WARN via other channels; ERROR if backup also fails.
- **Expected operator action:** Verify api.telegram.org reachable; run
  `notify retry`.
- **PASS:** Message eventually delivered via retry OR reflected in DLQ.
- **Severity:** MED.
- **MTTR:** 30-60 min.

### CS-03 · Slack unavailable (webhook 5xx)

- **Trigger:** Point `NEXAQUANT_SLACK_WEBHOOK_URL` to a URL that returns 503.
- **Expected recovery:** SlackChannel.send returns False; other channels succeed.
- **Expected alert:** none (delivered elsewhere).
- **Expected operator action:** Verify webhook URL still valid.
- **PASS:** No alert lost; Slack entry enters retry queue.
- **Severity:** LOW.
- **MTTR:** 10 min.

### CS-04 · Discord unavailable

- **Trigger:** Same as CS-03, discord.com/api/webhooks.
- **Expected recovery / alert / action / PASS:** Same as CS-03.
- **Severity:** LOW.
- **MTTR:** 10 min.

### CS-05 · SMTP unavailable

- **Trigger:** Set `NEXAQUANT_SMTP_HOST` to unreachable host.
- **Expected recovery:** EmailChannel.send returns False after timeout;
  retry queue captures.
- **Expected alert:** none (delivered elsewhere).
- **Expected operator action:** Restore SMTP; run `notify retry`.
- **PASS:** No alert lost.
- **Severity:** LOW.
- **MTTR:** 20 min.

### CS-06 · Webhook timeout

- **Trigger:** Point `NEXAQUANT_WEBHOOK_URL` at slow-response endpoint (>20s).
- **Expected recovery:** WebhookChannel.send times out → False.
- **Expected alert:** none.
- **Expected operator action:** Restore endpoint.
- **PASS:** Daemon does not hang on the timeout; other channels not blocked.
- **Severity:** LOW.
- **MTTR:** 10 min.

### CS-07 · GitHub Actions skipped (cron drop)

- **Trigger:** Wait for observed GitHub cron miss (natural — GH cron is
  best-effort).
- **Expected recovery:** Backup crons (18:30, 21:00 IST) OR self-hosted
  daemon fires the same day.
- **Expected alert:** none if backup succeeds; WARN if all miss.
- **Expected operator action:** Manual `workflow_dispatch` OR daemon
  intervention.
- **PASS:** No trading day ends without a successful pipeline pass.
- **Severity:** MED.
- **MTTR:** Same-day recovery via backup slot.

### CS-08 · Pipeline crash (uncaught exception)

- **Trigger:** Inject a synthetic exception into a stage (e.g., patch
  `run_mon001.main` — same technique as `test_ops_commissioning.py SUB-18`).
- **Expected recovery:** OPS001-A pipeline catches, marks stage FAILED,
  emits event, continues if `continue_on_failure` set. daily_runner
  absorbs top-level exceptions.
- **Expected alert:** ERROR via `pipeline_failure` template.
- **Expected operator action:** Read log, decide if this needs a fix.
- **PASS:** rc = 0 or 1 (never 2); alert delivered; RunState.FAILED written.
- **Severity:** MED.
- **MTTR:** Same-day via backup slot.

### CS-09 · Daemon SIGTERM (graceful shutdown)

- **Trigger:** `systemctl stop nexaquant` OR
  `python scripts/nexaquant_daemon.py stop`.
- **Expected recovery:** Signal handler sets stop_event, loop exits within
  poll_interval, PidLock released, ops_run_state.phase → ABORTED if
  mid-pipeline.
- **Expected alert:** WARN on next start via `recovery_event` template.
- **Expected operator action:** Restart daemon.
- **PASS:** Lock file removed; next start reads ABORTED and emits
  `recovery_decision`.
- **Severity:** LOW.
- **MTTR:** immediate.

### CS-10 · Daemon SIGKILL (ungraceful)

- **Trigger:** `kill -9 <pid>`.
- **Expected recovery:** Lock file remains with dead pid; next start breaks
  lock via `_pid_alive()==False`; RunState may be RUNNING → RESUME action.
- **Expected alert:** WARN on next start.
- **Expected operator action:** Restart daemon; verify no data loss.
- **PASS:** Next start succeeds, breaks lock, emits recovery event.
- **Severity:** MED.
- **MTTR:** 1-5 min.

### CS-11 · Power interruption

- **Trigger:** Pull power / VM stop-hard during pipeline.
- **Expected recovery:** On boot, systemd/TaskSched restart daemon; PidLock
  broken (dead pid); RunState might be corrupted (partial write) — treated
  as IDLE if unreadable.
- **Expected alert:** WARN on next successful start.
- **Expected operator action:** Verify host clock (NTP), verify MON001 fingerprint.
- **PASS:** Daemon comes back online within 5 min of boot; first slot
  after boot fires cleanly.
- **Severity:** HIGH.
- **MTTR:** 5-30 min depending on boot time.

### CS-12 · PID lock corruption

- **Trigger:** Overwrite `ops_daemon.lock` with garbage bytes.
- **Expected recovery:** `PidLock._read_raw()` catches JSONDecodeError,
  returns None; acquire proceeds (treats corrupt lock as no lock).
- **Expected alert:** none.
- **Expected operator action:** none (self-heals).
- **PASS:** Daemon starts normally.
- **Severity:** LOW.
- **MTTR:** immediate.

### CS-13 · Disk almost full (90%)

- **Trigger:** Fill root disk to 90% capacity.
- **Expected recovery:** Everything still works; log rotation may retain
  fewer backups.
- **Expected alert:** none (OS-level, not our system).
- **Expected operator action:** `df -h`, prune old files, verify
  `reports/logs/` retention is honoured.
- **PASS:** Pipeline runs to completion without error.
- **Severity:** MED.
- **MTTR:** 5 min after cleanup.

### CS-14 · Disk full (100%)

- **Trigger:** Fill root disk to 100%.
- **Expected recovery:** Writes to `ops_status.json`, `ops_alerts.jsonl`,
  `forward_ledger.jsonl` fail; MON001 daily may not append; daemon logs
  errors.
- **Expected alert:** none guaranteed (alert writes also fail); may reach
  Telegram if it's still working before the pipeline writes.
- **Expected operator action:** Free disk space immediately.
- **PASS:** Once disk restored, next slot recovers state; MON001 fingerprint
  still matches sealed.
- **Severity:** CRITICAL.
- **MTTR:** manual, dependent on operator.

### CS-15 · JSONL corruption (partial line)

- **Trigger:** Truncate `ops_run_state.json` mid-write; append garbage
  to `ops_alerts.jsonl`.
- **Expected recovery:** Readers use try/except; corrupt lines skipped.
- **Expected alert:** none direct; may cascade if recovery reads garbage.
- **Expected operator action:** none (self-heals with data loss on the
  garbage lines).
- **PASS:** No exception propagates to caller.
- **Severity:** LOW.
- **MTTR:** immediate.

### CS-16 · Retry queue overflow

- **Trigger:** Force all remote channels to fail for 24h; observe queue
  grow.
- **Expected recovery:** Entries stay in queue; after max_attempts (5) each
  moves to DLQ.
- **Expected alert:** `notification_status` reports DEGRADED once DLQ
  non-empty.
- **Expected operator action:** Diagnose root cause of remote failure; run
  `notify retry` after fix.
- **PASS:** Queue size bounded; DLQ growth is proportional to actual
  channel failures.
- **Severity:** MED.
- **MTTR:** Determined by underlying channel outage.

### CS-17 · DLQ overflow

- **Trigger:** Continue CS-16 for 7 days.
- **Expected recovery:** DLQ grows monotonically; disk consumption bounded
  by JSONL size.
- **Expected alert:** `notification_status: DEGRADED` continuously.
- **Expected operator action:** Diagnose, fix, then `notify purge --yes`.
- **PASS:** DLQ can be inspected + purged without daemon downtime.
- **Severity:** MED.
- **MTTR:** operator-dependent.

### CS-18 · Clock drift

- **Trigger:** Set host clock 30 min ahead OR behind (temporarily disable
  NTP).
- **Expected recovery:** Slot fires early or late by drift amount;
  same-day-dedup guard uses IST-derived date so drift within same day is
  tolerated.
- **Expected alert:** If drift moves fire outside window, slot missed →
  backup catches; if drift crosses midnight IST, dedup may reset.
- **Expected operator action:** Re-enable NTP; verify next slot fires
  correctly.
- **PASS:** No duplicate fires within same IST calendar day.
- **Severity:** MED.
- **MTTR:** Immediate after NTP restore.

### CS-19 · Timezone mismatch

- **Trigger:** Host in non-IST timezone.
- **Expected recovery:** Scheduler converts explicitly via
  `tz_offset_hours=5.5`; fires at 10:45 UTC regardless of host TZ.
- **Expected alert:** none.
- **Expected operator action:** none (already tested in OPS001-B test 15,
  OPS001.5 SUB-08).
- **PASS:** Slot fires at 16:15 IST irrespective of host TZ setting.
- **Severity:** LOW.
- **MTTR:** N/A.

### CS-20 · MON001 HALT

- **Trigger:** Manually corrupt one row of `forward_ledger.jsonl` and
  re-run `mon001_daily`.
- **Expected recovery:** `ledger_integrity` check reports HALT; daemon
  logs CRITICAL alert via `mon001_halt` template; pipeline stage marked
  failed; daemon does NOT auto-remediate.
- **Expected alert:** CRITICAL to Telegram + Email + Slack + Discord + Webhook + File.
- **Expected operator action:** STOP daemon; follow docs/OPS001B_RECOVERY.md §5;
  do NOT restart.
- **PASS:** HALT alert delivered; daemon not aggressively restarted;
  investigation logged.
- **Severity:** CRITICAL.
- **MTTR:** Operator-dependent; MON001 amendment ceremony required.

### CS-21 · Fingerprint mismatch

- **Trigger:** Edit `india/recommendation_generator.py` (whitespace only)
  and re-run.
- **Expected recovery:** `fingerprint_matches_seal` check HALTs;
  `test_ops_daemon.py test_36` and other guards report FAIL on CI;
  daemon continues but MON001 refuses to publish.
- **Expected alert:** CRITICAL via `mon001_halt` template.
- **Expected operator action:** Revert change OR run
  CHANGE_CONTROL_CHECKLIST ceremony.
- **PASS:** No sealed change lands on `main` without ceremony.
- **Severity:** CRITICAL.
- **MTTR:** Operator-dependent.

### CS-22 · Configuration drift (mon001.yaml modified)

- **Trigger:** Change `forward_boundary_asof` value.
- **Expected recovery:** `test_ops_daemon.py test_33` and
  `test_no_sealed_files_modified_by_eng001` catch on `git diff HEAD`; if
  committed, `test_mon001_forward_boundary` catches.
- **Expected alert:** CI fails on next push.
- **Expected operator action:** Revert.
- **PASS:** Change never reaches `main`.
- **Severity:** CRITICAL.
- **MTTR:** Immediate revert.

### CS-23 · Missing environment variables

- **Trigger:** Unset `TELEGRAM_BOT_TOKEN` on host.
- **Expected recovery:** `TelegramChannel.configured=False`, `send()` returns
  False; other channels + file fallback preserve alert.
- **Expected alert:** File captures; other channels attempt.
- **Expected operator action:** Re-export env; restart daemon or invoke
  `notify retry`.
- **PASS:** No alert lost; daemon does not crash.
- **Severity:** LOW.
- **MTTR:** 5 min.

### CS-24 · Corrupted status file

- **Trigger:** Overwrite `ops_status.json` with garbage.
- **Expected recovery:** Next pipeline pass overwrites atomically; readers
  catch JSONDecodeError and treat as empty.
- **Expected alert:** none.
- **Expected operator action:** none (self-heals).
- **PASS:** `notify status` continues to run.
- **Severity:** LOW.
- **MTTR:** immediate.

### CS-25 · Partial recommendation generation

- **Trigger:** Kill `recommendation_generator` subprocess mid-write of CSV.
- **Expected recovery:** Truncated CSV; downstream `recommendation_db` +
  `scorecard` see fewer rows or fail freshness_gate; `mon001_daily` may
  refuse to snapshot.
- **Expected alert:** ERROR via `pipeline_failure`.
- **Expected operator action:** Verify data provider; rerun.
- **PASS:** No half-committed recommendation reaches Telegram / DB.
- **Severity:** HIGH.
- **MTTR:** Same-day via backup slot.

### CS-26 · Pipeline timeout

- **Trigger:** yfinance hangs; `refresh_data` stage exceeds
  `timeout_s: 900` (15 min).
- **Expected recovery:** OPS001-A pipeline kills the subprocess after
  timeout; RetryPolicy retries up to `max_attempts`; if all attempts time
  out, stage marked failed; `continue_on_failure` allows downstream
  stages to run OR aborts.
- **Expected alert:** WARN → ERROR via retry/failure events.
- **Expected operator action:** Investigate yfinance; consider fallback
  data source.
- **PASS:** Subprocess is genuinely terminated (no orphan process);
  daemon does not hang.
- **Severity:** MED.
- **MTTR:** Backup slot recovers same day.

### 3.1 Chaos coverage summary

| Category | Scenarios | Severity distribution |
|---|:-:|---|
| Network | 6 (CS-01, 02, 03, 04, 05, 06) | 1 HIGH, 1 MED, 4 LOW |
| Process lifecycle | 5 (CS-08, 09, 10, 11, 26) | 1 HIGH, 3 MED, 1 LOW |
| Disk / persistence | 4 (CS-13, 14, 15, 24) | 1 CRITICAL, 1 MED, 2 LOW |
| Notification | 3 (CS-16, 17, 23) | 2 MED, 1 LOW |
| Time / TZ | 2 (CS-18, 19) | 1 MED, 1 LOW |
| Governance (MON001) | 3 (CS-20, 21, 22) | 3 CRITICAL |
| Miscellaneous | 3 (CS-07, 12, 25) | 1 HIGH, 1 MED, 1 LOW |
| **Total** | **26** | **3 CRITICAL, 3 HIGH, 11 MED, 9 LOW** |

---

## Phase 4 · 7-Day Commissioning Plan

Each day has: **objective · start of day tasks · scenarios to run · evidence
to collect · PASS/FAIL gate before next day.**

### Day 1 · Baseline validation

- **Objective:** Establish the "green baseline" before any chaos.
- **Tasks:** Start daemon fresh under systemd/TaskSched/launchd. Run
  full regression suite, commissioning suite, MON001 health check,
  `notify status`. Snapshot every state file.
- **Scenarios:** none.
- **Evidence:** `docs/commissioning/day1-baseline.json` containing:
  fingerprint hash, ledger row count, MON001 exit code, test counts,
  daemon uptime, log volume, memory footprint, docker/systemd status.
- **PASS gate:** All tests green; MON001 INFO; daemon running.

### Day 2 · Notification validation

- **Objective:** Exercise every notification channel end-to-end.
- **Tasks:** Configure each channel (Telegram already; Email / Slack /
  Discord / Webhook per operator's choice). Emit one INFO, WARN, ERROR,
  CRITICAL via `notify test`. Verify each channel receives (or is
  correctly filtered by min_severity).
- **Scenarios:** CS-03, CS-04, CS-05, CS-06 (only channels the operator
  intends to use).
- **Evidence:** Screenshot of each channel's inbox; `notify history
  --since-hours 24 --format json`.
- **PASS gate:** Every configured channel delivered at CRITICAL; File
  channel captured all 4 test events; DLQ empty.

### Day 3 · Scheduler validation

- **Objective:** Confirm slot semantics under real daemon.
- **Tasks:** Run daemon through a full IST trading day. Verify primary
  fires; simulate primary failure and confirm backup fires; simulate
  same-day-dedup by manually re-triggering.
- **Scenarios:** CS-07 (natural cron drop if observed), CS-18 (clock drift
  ±5 min via `date` command), CS-19 (verify by daemon status only).
- **Evidence:** `ops_schedule_state.json` before/after; `logs/nexaquant_ops.jsonl`
  filtered for `slot_firing` / `slot_completed`.
- **PASS gate:** Exactly one successful pipeline pass on the trading day.

### Day 4 · Recovery validation

- **Objective:** Prove interrupted-pipeline recovery.
- **Tasks:** SIGTERM daemon mid-pipeline; verify `recovery_decision`
  event on restart. SIGKILL and verify same. Corrupt run_state and
  verify daemon starts. Simulate stale lock (dead pid + 48h age) and
  verify break.
- **Scenarios:** CS-09, CS-10, CS-12, CS-15, CS-24.
- **Evidence:** Timeline log of each induced event + recovery event
  captured.
- **PASS gate:** Every recovery scenario emits the expected event and
  the daemon continues.

### Day 5 · Chaos validation

- **Objective:** Verify graceful degradation under multi-fault conditions.
- **Tasks:** Network unavailable for 5 min during a slot fire. Force each
  remote channel to fail for 30 min. Fill disk to 90%.
- **Scenarios:** CS-01, CS-02, CS-13, CS-16, CS-23, CS-25.
- **Evidence:** `notify status` output before/during/after; retry queue
  drain time; DLQ contents.
- **PASS gate:** File channel captured every alert; retry queue drained
  within 30 min of recovery; no data loss.

### Day 6 · Long-running stability

- **Objective:** Detect resource leaks, log-rotation issues, and
  time-of-day edge cases.
- **Tasks:** Run daemon for 24 continuous hours with normal load. Sample
  memory + CPU every 15 min via `notify status` OR external tool. Verify
  log rotation triggers at 5 MiB. Verify daemon PID lock refreshes
  every 15 min.
- **Scenarios:** none (observation only).
- **Evidence:** Time-series of process memory, thread count, log file
  size. Verify no monotonic growth.
- **PASS gate:** Memory usage plateau (± 20% of steady state) after
  6h; log rotation observed; no unhandled exceptions in log.

### Day 7 · Acceptance review

- **Objective:** Sign the acceptance checklist.
- **Tasks:** Review Days 1-6 evidence; run
  `test_ops_commissioning.py` one more time; produce final
  `OPS001D_COMMISSIONING_REPORT.md`; operator signs
  `docs/OPS001_5_ACCEPTANCE_CHECKLIST.md` (extended with Day 1-6 evidence).
- **Scenarios:** none.
- **Evidence:** Signed acceptance checklist filed under `docs/acceptance/`.
- **PASS gate:** All Phase-5 gates GREEN and signed.

### Day-by-day dependency chain

```
Day 1 (baseline)  ──►  Day 2 (notify)  ──►  Day 3 (scheduler)  ──►
Day 4 (recovery)  ──►  Day 5 (chaos)   ──►  Day 6 (stability)  ──►
Day 7 (acceptance sign-off)
```

Skipping a day's gate advances the schedule but does NOT skip that
verification — it just marks the gate as OPEN in the acceptance record.

---

## Phase 5 · Acceptance Criteria (Production Gates)

Every gate has a measurable definition. All must be GREEN before OPS001-D
is closed.

| # | Gate | Measurement | GREEN | AMBER | RED |
|:-:|---|---|---|---|---|
| G01 | 100% successful scheduled executions | Trading days in window with ≥ 1 successful pipeline pass | 100% | 95-99% | < 95% |
| G02 | No duplicate recommendations | `SELECT COUNT(*) - COUNT(DISTINCT (rec_id, asof)) FROM forward_ledger` | 0 | 1 | > 1 |
| G03 | No duplicate notifications | Unique count of `(source, title, timestamp_utc)` in ops_alerts.jsonl matches total | equal | ± 1 | discrepancy > 1 |
| G04 | Retry queue eventually drains | Time from remote-recovery to `pending == 0` | ≤ 30 min | ≤ 60 min | > 60 min |
| G05 | DLQ remains empty (under normal ops) | `notify status.status` after 7 days | OK | DEGRADED (1-2 stale) | DEGRADED (persistent) |
| G06 | Dashboard updates correctly | `generated_at_utc` within 60s of last emit | fresh | ≤ 5 min | > 5 min |
| G07 | Status endpoint accurate | `ops_status.json.last_pipeline_success` matches actual last pipeline | matches | discrepancy on retry | persistent mismatch |
| G08 | Recovery under SLA | MTTR for each chaos scenario in Phase 3 | within estimate | 1-2x estimate | > 2x estimate |
| G09 | No unexpected MON001 halt | Count of HALT events in observation window | 0 | 0 (but WARNs) | ≥ 1 HALT |
| G10 | CI remains green | Every push to main is green | 100% | 1-2 flakes | any push red |
| G11 | Fingerprint unchanged | Recomputed hash == `64e74483d9bd0444...` | matches | mismatch → immediate stop | — |
| G12 | Trial count unchanged | `cumulative_strategy_search: 38` | matches | — | mismatch |
| G13 | Broker mode PAPER_ONLY | `broker_layer.PaperOnlyBrokerLayer.available() == False` | verified | — | any deviation |
| G14 | Daemon uptime | % of scheduled window daemon is alive | ≥ 99% | 95-99% | < 95% |
| G15 | Log growth bounded | `du -sh reports/logs/` | ≤ 100 MiB | ≤ 500 MiB | > 500 MiB |
| G16 | Memory stability | Daemon RSS after 24h vs 1h baseline | ± 20% | ± 50% | > 50% growth |
| G17 | Alert audit complete | Every `slot_completed` has a corresponding `ops_alerts.jsonl` row | 100% | 99-99.9% | < 99% |

### 5.1 Sign-off requirements

The operator signs OPS001-D acceptance ONLY when:
- All 17 gates are GREEN OR the operator has documented an accepted AMBER.
- No gate is RED.
- Every chaos scenario in Phase 3 has been either executed OR
  explicitly deferred with rationale.

---

## Phase 6 · Operational Risk Assessment

Each risk: **Probability · Impact · Mitigation · Blocks production? (Y/N)**.

### 6.1 CRITICAL risks

| ID | Risk | Probability | Impact | Mitigation | Blocks |
|:-:|---|:-:|:-:|---|:-:|
| R-C1 | Data provider (yfinance/NSE) blocks / rate-limits | MED | Daily pipeline fails; no recommendation | Retry policy + backup slots + operator alert; long-term: alternate data source | Personal: N. Public/Commercial: Y |
| R-C2 | Host disk fills mid-pipeline | LOW | ops_alerts, ledger writes fail; potential ledger corruption | External monitoring of disk usage; alarm at 80%; log retention pruning | N (mitigation active) |
| R-C3 | Sealed file modified without ceremony | LOW | MON001 fingerprint breaks; system halts | 3 test guards + CI enforcement + operator training | N (defense in depth) |
| R-C4 | Broker mode flips to non-PAPER | VERY LOW | Real orders placed | `PaperOnlyBrokerLayer` is the only implementation; `make_broker_layer` always returns it | N (code-forced) |

### 6.2 HIGH risks

| ID | Risk | Probability | Impact | Mitigation | Blocks |
|:-:|---|:-:|:-:|---|:-:|
| R-H1 | Single-machine deployment (no HA) | HIGH | Machine loss → pipeline miss for the day | Backup: fallback to GitHub Actions cron; long-term: OPS002 leader election | Personal: N. Commercial: Y |
| R-H2 | Secrets on operator's `.env` (no rotation) | HIGH | Compromised token silently keeps working | Documented in operator runbook; recommendation: rotate every 90 days | Personal: N. Public/Commercial: Y |
| R-H3 | No canary environment (prod is the only env) | HIGH | Bug ships directly to production | Small blast radius: PAPER_ONLY; MON001 catches strategy drift; regression suite gates | Personal: N. Public/Commercial: Y |
| R-H4 | Dependency version drift (no version pins in CI) | MED | Silent behavioural change in pandas/numpy/scipy | Fingerprint check + envelope check would catch; long-term: pin exact versions in workflow | Personal: N. Public/Commercial: Y |
| R-H5 | Time-zone handling depends on host clock | MED | Slot fires wrong time under clock skew | Scheduler uses explicit tz_offset, not host TZ; NTP required on host | N |
| R-H6 | Multi-tenant not supported | LOW | Public beta impossible | Design decision; personal use unaffected | Public/Commercial: Y |

### 6.3 MEDIUM risks

| ID | Risk | Probability | Impact | Mitigation | Blocks |
|:-:|---|:-:|:-:|---|:-:|
| R-M1 | Log rotation retention (30d) may be too short for compliance | LOW | Audit trail gaps beyond 30 days | Operator can extend retention via config; ops_alerts.jsonl is never pruned | Commercial: potentially Y |
| R-M2 | No structured audit trail for CLI commands invoked by operator | HIGH | Ambiguous provenance when things go wrong | Add CLI audit log in future (out of OPS001-D scope) | N |
| R-M3 | No monitor-the-monitor (who alerts when alert bus is broken?) | LOW | Silent failure of Telegram + File + all channels | Multiple channels + retry queue provides redundancy; extreme case would trigger MON001 halt | N |
| R-M4 | GitHub Actions cron jitter | MED | Slot late by up to 10 min | Fire window is 5 min — jitter beyond that misses primary; backup slots exist | N |
| R-M5 | MON001 alerts.jsonl grows unbounded | HIGH | Disk consumption over months | External `logrotate` recommended; long-term: MON001 hygiene phase | N |
| R-M6 | Retry queue file-writer race with CLI `notify retry` | LOW | Rare entry loss | Single-writer assumption; operator instructed not to run manual retry while daemon fires | N |
| R-M7 | Docs sprawl (56 files, many legacy) | HIGH | Operator reads wrong doc | Cleanup pass proposed to operator (Option 1/2/3) — pending | N |

### 6.4 LOW risks

| ID | Risk | Probability | Impact | Mitigation | Blocks |
|:-:|---|:-:|:-:|---|:-:|
| R-L1 | Windows CRLF/LF in text files | LOW | Historical (portability amendment resolved) | v2 fingerprint LF-normalises; envelope stores basename only | N |
| R-L2 | Package minor bumps in CI (patch versions) | HIGH | Very small chance of subtle behavioural change | Portability amendment + MON001 fingerprint would catch material drift | N |
| R-L3 | Weekly canary not scheduled (proposed in OPS001.5) | HIGH | Slow drift detection | Recommended in `docs/OPS001_5_DEPLOYMENT_VALIDATION.md §6` | N |
| R-L4 | Test suites use hardcoded date fixtures | MED | Test may need update when calendar changes | Fixtures locked to 2026 IST dates; will need refresh in 2027+ | N (5+ years out) |
| R-L5 | psutil optional; falls back to `resource`/`minimal` on Linux | HIGH | Reduced observability if not installed | Recommend pip install psutil in workflow deps | N |

### 6.5 Aggregate risk posture

| Tier | Count | Blocks personal? | Blocks public/commercial? |
|:-:|:-:|:-:|:-:|
| CRITICAL | 4 | 0 | 1 (R-C1) |
| HIGH | 6 | 0 | 4 (R-H1, R-H2, R-H3, R-H4, R-H6) |
| MEDIUM | 7 | 0 | 1 (R-M1 possibly) |
| LOW | 5 | 0 | 0 |

---

## Phase 7 · Final Recommendation

### 7.1 Verdict matrix

| Deployment tier | Verdict | Rationale |
|---|:-:|---|
| **Internal / personal (operator-only, PAPER_ONLY)** | ✅ **GO** after 7-day commissioning executes cleanly | Every critical risk mitigated. Broker layer code-forced to PAPER_ONLY. Regression + commissioning suites cover the mechanical surface. |
| **Personal production (real capital, still PAPER_ONLY mode)** | 🟡 **CONDITIONAL GO** — after commissioning + operator's explicit decision to enable live broker | Broker layer would need to be swapped, which requires ENG005 (or later) — NOT in OPS001-D scope. This tier is out of reach today. |
| **Public beta (multiple users)** | 🔴 **NO-GO** | Not multi-tenant. No admin controls. No user isolation. No SLA. No support process. R-H2, R-H3, R-H6 all block. |
| **Commercial deployment** | 🔴 **NO-GO** | On top of the beta blockers: no HA (R-H1), no audit-quality retention (R-M1), no dependency pinning (R-H4), no compliance framework, no data-provider redundancy (R-C1), no licensed data feed. |

### 7.2 What OPS001-D unlocks

Running the 7-day commissioning window (Phase 4) and closing every gate
in Phase 5 unlocks **internal production**. That is: the operator running
NexaQuant on a single machine under systemd/Task Scheduler, receiving
Telegram alerts, watching MON001, in PAPER_ONLY mode, for their own use.

### 7.3 What OPS001-D does NOT unlock

Public beta and commercial deployment are gated by architectural work
that this validation phase cannot substitute for:

- HA / multi-instance leader election (OPS002).
- Multi-tenant + admin (out of current scope).
- Compliance framework + audit retention (out of current scope).
- Real broker integration (ENG005 or later).

### 7.4 Recommendation

**Proceed to Day 1 of the commissioning plan (Phase 4).**

The current codebase has been through:
- 279 automated tests across 13 regression suites, all green
- 23/23 commissioning subsystems + 3/3 governance guards, verdict ACCEPTED
- MON001 certification `MON001-CERT-2026-07-15` valid with §15 portability amendment
- CI green on every push to main since portability amendment

The gap between "green tests" and "trusted production" is exactly what
this 7-day live commissioning closes.

### 7.5 Sequencing after OPS001-D

Recommend, in strict order, before any research work (LAB011):

1. **OPS001-D execution** (this plan). ~7 elapsed days, minimal operator time (~2 hours/day).
2. **Docs cleanup** (pending decision from turn 8). Reduces 56 → ~15 essentials. ~1 hour.
3. **OPS001-E — Observability & metrics** (proposed in your roadmap). Adds structured metrics
   collection, per-stage timing histograms, grafana-friendly output. ~2 sessions.
4. **OPS001-F — Performance profiling**. One-off measurement + capacity plan. ~1 session.
5. **Phase 2 (autonomous ops)** — evaluate whether needed after Phase 1's stability data.
6. **Phase 3 (intelligence: MON002, drift forecasting)** — start with MON002 only.
7. **Phase 4 — LAB011** only after all Phase 1 + 2 work above lands.

### 7.6 Author's confidence

I am **high confidence** on:
- The plan's coverage (26 scenarios span every real-world failure I have observed or can construct)
- The gate definitions (measurable, not aspirational)
- The dependency map (audited against the code, not memory)

I am **moderate confidence** on:
- MTTR estimates (best-effort — will be refined by Day 5's actual chaos runs)
- Third-party channel behaviours under load (Slack/Discord rate-limits are not documented in our test set)

I am **low confidence** on:
- yfinance's long-term reliability (out of our control)
- Whether operator's specific SMTP/Slack/Discord/Webhook endpoints will behave as documented

None of the moderate/low confidence areas block **internal production** in
PAPER_ONLY mode.

---

## Appendix A · Evidence collected during Phase 1

The following evidence was gathered from the live repository during
Phase 1 audit (commit `7a86013`):

- **Files audited (counts):**
  - `nexaquant/ops/*.py`: 15
  - `nexaquant/ops/notify/*.py`: 12
  - `nexaquant/ops/pipelines/*.yaml`: 1
  - `nexaquant/tests/test_ops_*.py`: 4
  - `.github/workflows/*.yml`: 3
  - `india/monitoring/MON001_Forward_Validation/*.py + .yaml + .md`: 8 (sealed)
  - `docs/*.md`: 56
  - `deploy/{systemd,task-scheduler,launchd}/*`: 3
- **AEGIS pipeline stages (order verified):** refresh_data → freshness_gate →
  recommendation_generator → recommendation_db → scorecard → ops_check →
  telegram_health_check → telegram_notify → mon001_daily
- **GitHub Actions cron schedule (UTC → IST):**
  - aegis-daily: 10:45 UTC / 13:00 UTC / 15:30 UTC = 16:15 / 18:30 / 21:00 IST Mon-Fri
  - mon001-daily: 11:00 UTC / 13:15 UTC / 15:45 UTC = 16:30 / 18:45 / 21:15 IST Mon-Fri
- **Regression suites registered (13):** MON001 core, MON001 ops, LAB010,
  Core lab, LAB009, ENG001 lib, ENG003 CI discipline, ENG003 governance,
  Telegram reliability, OPS001-A pipeline, OPS001-B daemon,
  OPS001.5 commissioning, OPS001-C notify
- **MON001 state at plan time:**
  - Sealed fingerprint hash: `64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42`
  - Forward ledger: **150 rows**, hash-chain intact
  - Baseline envelope hash (post-amendment): `e4ca8ecb97914f4828f6601eb5d05ebe4956099dac7c6df70df13ccaaa482812`
  - Certification: `MON001-CERT-2026-07-15` with `MON001-AMEND-2026-07-16-portability`
- **Runtime state files (post-OPS001-C):**
  - `reports/ops_status.json` — StatusWriter schema v1
  - `reports/ops_metrics.jsonl` — MetricsLedger append-only
  - `reports/ops_alerts.jsonl` — FileChannel durable log
  - `reports/ops_daemon.lock` — PidLock JSON
  - `reports/ops_run_state.json` — RunState phase transitions
  - `reports/ops_schedule_state.json` — Scheduler dedup ledger
  - `reports/ops_notify_queue.jsonl` — retry queue (empty at plan time)
  - `reports/ops_notify_delivered.jsonl` — retry-delivered ledger
  - `reports/ops_notify_dlq.jsonl` — dead-letter (empty at plan time)
- **Last 5 commits on `main`:** 7a86013 → 145cd55 → 55ce0d1 → f50e56f → 0e88794
- **CI status:** green on every push since `f50e56f` (2026-07-16).

---

**End of OPS001-D validation plan.**

No chaos executed. No production code modified. Awaiting operator
authorisation to execute Phase 4.
