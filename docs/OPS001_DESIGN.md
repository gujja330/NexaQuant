# OPS001-A · Live Operations Foundation — Design

**Date:** 2026-07-15
**Author:** Principal Production Platform Architect
**Scope:** reusable operational framework — pipeline orchestrator, notification
             bus, service wrapper, metrics ledger, status endpoint
**Not in scope:** daemon mode (OPS001-B), extra notification channels
                 (OPS001-C), observability platform (OPS002+)

---

## 1. Executive summary

OPS001-A converts NexaQuant from a set of scripts into the substrate for a
continuously-running production platform. It introduces:

- A **NotificationChannel** abstraction with two initial implementations:
  `TelegramChannel` (operational alerts; distinct from the daily recommendation)
  and `FileChannel` (append-only JSONL fallback that cannot silently fail).
- A **NotificationManager** that fans out every notification to every attached
  channel, isolating per-channel failures.
- A **Pipeline** orchestrator that runs a config-driven sequence of stages with
  timeouts, retries, exponential backoff, `continue_on_failure`, and
  `depends_on` gating. Each stage runs as a subprocess so a crash never kills
  the ops process.
- A **NexaQuantService** wrapper that loads a pipeline YAML, executes it once,
  writes a **StatusSnapshot** to `reports/ops_status.json` (atomic write),
  appends per-stage rows to a **MetricsLedger** at `reports/ops_metrics.jsonl`,
  and broadcasts lifecycle events through the notification bus.
- A **CLI entrypoint** at `scripts/nexaquant_service.py` that a scheduler
  (Windows Task Scheduler, cron, or later a systemd unit built in OPS001-B) can
  invoke.
- **31 unit tests** covering every layer.

**Zero strategy behaviour changes. Zero MON001 fingerprint impact. Zero LAB
evidence modifications. `HOLD=63`, `rebal=63`, `cumulative_strategy_search=38`
all unchanged.**

---

## 2. Architecture diagram

```
                                    ┌──────────────────────────┐
                                    │  scripts/                │
                                    │  nexaquant_service.py    │
                                    │     (CLI entrypoint)     │
                                    └────────────┬─────────────┘
                                                 │ run_once()
                                                 ▼
              ┌────────────────────────────────────────────────────────┐
              │                 NexaQuantService                       │
              │  (loads config, orchestrates, writes status)           │
              └────────┬───────────────────┬────────────────┬──────────┘
                       │                   │                │
        load_pipeline  │                   │  build_notifier │  MetricsLedger
                       ▼                   ▼                ▼
           ┌───────────────────┐  ┌──────────────────┐  ┌──────────────────┐
           │  config.py        │  │  NotificationMgr │  │  metrics.py      │
           │  PipelineConfig   │  │  (fan-out bus)   │  │  append-only     │
           │  StageDefinition  │  │                  │  │  ops_metrics.jsonl│
           └────────┬──────────┘  │  channels:       │  └──────────────────┘
                    │             │   • FileChannel  │
                    ▼             │   • TelegramChan │
          ┌───────────────────┐   │   (OPS001-C:     │
          │  pipeline.py      │◄──┤    Email/Slack/  │
          │  Pipeline.run()   │   │    Discord/HTTP) │
          │  ├─ subprocess    │   └──────────────────┘
          │  │  per stage     │
          │  ├─ RetryPolicy   │
          │  ├─ Event bus     │
          │  └─ StageResult   │
          └────────┬──────────┘
                   │
                   ▼
          ┌───────────────────┐
          │  status.py        │
          │  StatusWriter     │
          │  ops_status.json  │
          │  (atomic write)   │
          └───────────────────┘
```

---

## 3. Component responsibilities

| Module | Responsibility | Never |
|---|---|---|
| `events.py` | `StageEvent`, `Severity`, `Event` dataclass — pure data | I/O, logging |
| `retry.py` | `RetryPolicy` — max attempts, backoff schedule, per-attempt timeout | Never executes anything |
| `notify/base.py` | `NotificationChannel` abstract + `Notification` dataclass | Filesystem, network |
| `notify/file.py` | `FileChannel` — append JSONL, never raises | Skip severity filter |
| `notify/telegram.py` | `TelegramChannel` — ops alerts via Bot API, never raises, honors min_severity | Send the daily recommendation (that's `india/telegram_notify.py`) |
| `notify/manager.py` | `NotificationManager` — fan-out to all channels, per-channel outcomes | Fail loudly (per-channel errors are collected, not raised) |
| `metrics.py` | `MetricsLedger` — append-only JSONL of per-stage + per-pipeline rows | Rewrite history |
| `status.py` | `StatusWriter` — atomic write of `ops_status.json` with schema v1 | Read across writes; single writer |
| `config.py` | `load_pipeline` — YAML → `PipelineConfig` + validation | Silent defaults; misconfiguration fails LOUDLY |
| `pipeline.py` | `Pipeline.run()` — execute stages with subprocess isolation + retries + events | Raise; catches every exception |
| `service.py` | `NexaQuantService.run_once()` — glue: load config, run pipeline, write status | Loop forever (that's OPS001-B) |

---

## 4. Failure flow

```
Stage attempt fails
        │
        ▼
  attempts < max_attempts?
        │
   ┌────┴────┐
   │         │
  YES        NO
   │         │
   ▼         ▼
 emit    emit FAILED
 RETRY   record metric
 sleep   ┌──────────────────┐
 backoff │ continue_on_failure ?│
   │     └─────┬────────┬─────┘
   │           │        │
   │          YES       NO
   │           │        │
   │           │        ▼
   │           │   mark remaining
   │           │   stages as SKIPPED
   │           │        │
   │           ▼        ▼
   │       next stage runs
   ▼
 loop back to attempt N+1
```

**Never** crashes the process. Every failure produces:
1. A metrics row (append-only)
2. A lifecycle event (routed through NotificationManager → every channel)
3. A `StageResult` in the returned `PipelineResult`
4. A row in the ops_alerts.jsonl (via FileChannel)
5. A Telegram alert IF severity ≥ WARN AND Telegram is configured

---

## 5. Retry flow

```
attempt 1:  runner(stage, timeout=T)
              │
              ├─ exit 0                        → SUCCESS, return
              ├─ TimeoutExpired               → record, next attempt
              ├─ non-zero exit                 → record, next attempt
              └─ any other exception           → record, next attempt

sleep backoff_s[0]

attempt 2:  runner(stage, timeout=T)
              │
              └─ ...

sleep backoff_s[min(i-2, len(backoff_s)-1)]  # extends last if too short

attempt N:  runner(stage, timeout=T)
              │
              └─ if still failing → FAILED (last exit/exception recorded)
```

- `RetryPolicy.sleep_before_attempt(1)` = 0 (no sleep before first attempt)
- Backoff schedule extends by repeating the last value if `max_attempts` is
  larger than `backoff_s + 1`.
- Sleep is injectable via `Pipeline(..., sleeper=fn)` for deterministic tests.

---

## 6. Notification flow

```
Pipeline emits Event (STARTED / RUNNING / RETRY / FAILED / SUCCESS / COMPLETE)
        │
        ▼
Pipeline wraps as Notification(severity, source, title, body, context)
        │
        ▼
NotificationManager.emit(notification)
        │
        ├─ for each channel:
        │   ├─ channel.accepts(severity)?
        │   │     NO  → mark accepted=False, ok=True (filtered ≠ failed)
        │   │     YES → channel.send(notification)
        │   │           ├─ True  → DeliveryResult(ok=True)
        │   │           └─ False → DeliveryResult(ok=False)
        │   │           any exception is caught → DeliveryResult(ok=False)
        │
        └─ return list[DeliveryResult] (never raises)
```

**Invariant**: `FileChannel` is always first in the list — it accepts INFO+
and appends unconditionally. So even if every other channel fails, the file
ledger records the notification.

---

## 7. Configuration schema

`nexaquant/ops/pipelines/aegis_daily.yaml` (reference pipeline shipped with
OPS001-A):

```yaml
name: aegis_daily
description: Daily AEGIS pipeline (refresh → engine → notify → monitor)
stages:
  - name: refresh_data
    command: [python, india/refresh_data.py]
    timeout_s: 900
    retries: 2
    backoff_s: [30, 90]
    continue_on_failure: true
  - name: freshness_gate
    command: [python, scripts/check_data_freshness.py]
    timeout_s: 60
    retries: 0
    depends_on: [refresh_data]
  # ... 7 more stages
```

**Validated at load time** — misconfiguration raises `ValueError` immediately,
never silently at runtime.

---

## 8. Status snapshot schema

`reports/ops_status.json` schema v1:

```json
{
  "schema_version": 1,
  "written_at_utc": "2026-07-15T16:20:00+00:00",
  "ops_version": "0.1.0-ops001a",
  "git_sha": "dcdec20",
  "pipeline_name": "aegis_daily",
  "last_pipeline_success": true,
  "last_pipeline_run_utc": "2026-07-15T16:19:45+00:00",
  "last_pipeline_duration_s": 82.3,
  "stages_ok": 9,
  "stages_total": 9,
  "next_run_scheduled_utc": "",
  "active_alerts": [],
  "mon001_state": "INSUFFICIENT_EVIDENCE",
  "mon001_halt": false,
  "mon001_fingerprint_hash": "64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42",
  "mon001_algorithm_version": 2,
  "broker_status": "PAPER_ONLY",
  "recommendation_last_asof": "2026-07-14",
  "ops_uptime_s": 0.34,
  "metadata": {}
}
```

Consumers read the file directly. Schema-versioned so future changes stay
backwards-compatible.

---

## 9. Metrics ledger schema

`reports/ops_metrics.jsonl` — JSONL, one row per stage or pipeline completion:

```json
{"timestamp_utc": "2026-07-15T16:19:45+00:00",
 "pipeline": "aegis_daily", "stage": "refresh_data",
 "kind": "stage", "success": true, "attempts": 1,
 "duration_s": 12.4, "retry_count": 0, "exit_code": 0,
 "exception_type": "", "memory_kib": 68320, "cpu_user_s": 8.1,
 "context": {"stdout_tail": ["...", "done"]}}
```

Append-only. Never rewritten. `MetricsLedger.rows()` reads everything;
`.recent(N)` returns the last N.

OPS001-B/C will consume this for trend analysis, MTTR, availability metrics.

---

## 10. Files created (16)

| File | LOC | Purpose |
|---|---:|---|
| `nexaquant/ops/__init__.py` | 6 | Package marker + version |
| `nexaquant/ops/events.py` | 76 | `StageEvent`, `Severity`, `Event` |
| `nexaquant/ops/retry.py` | 63 | `RetryPolicy`, `RetryOutcome` |
| `nexaquant/ops/notify/__init__.py` | 18 | Package re-exports |
| `nexaquant/ops/notify/base.py` | 69 | `NotificationChannel`, `Notification` |
| `nexaquant/ops/notify/file.py` | 40 | `FileChannel` (always-succeeds fallback) |
| `nexaquant/ops/notify/telegram.py` | 88 | `TelegramChannel` (ops alerts only) |
| `nexaquant/ops/notify/manager.py` | 46 | `NotificationManager` (fan-out bus) |
| `nexaquant/ops/metrics.py` | 121 | `MetricsLedger` |
| `nexaquant/ops/status.py` | 88 | `StatusWriter`, `StatusSnapshot` |
| `nexaquant/ops/config.py` | 88 | `load_pipeline`, `PipelineConfig` |
| `nexaquant/ops/pipeline.py` | 217 | `Pipeline.run()` orchestrator |
| `nexaquant/ops/service.py` | 152 | `NexaQuantService.run_once()` |
| `nexaquant/ops/pipelines/aegis_daily.yaml` | 62 | Reference pipeline |
| `scripts/nexaquant_service.py` | 36 | CLI entrypoint |
| `nexaquant/tests/test_ops_pipeline.py` | 385 | 31 tests |
| `docs/OPS001_DESIGN.md` | this | Design doc |

Total new code: ~1400 LOC + tests + docs.

## 11. Files modified (1)

- `nexaquant/tests/test_regression.py` — added `("OPS001-A pipeline", ...)` to
  the suite list (1 line added). No other logic change.

**No sealed file was modified. No LAB artefact modified. No workflow modified
(that comes with OPS001-B).**

---

## 12. Operational capabilities added

| Capability | Before OPS001-A | After OPS001-A |
|---|---|---|
| Multi-stage orchestration | Bash `\|\|` chain in `aegis-daily.yml` | Config-driven `Pipeline` with per-stage retry/timeout/backoff |
| Per-stage retry | Only Telegram (via `telegram_send_with_retry.py`) | Every stage (configurable) |
| Structured notification | Direct calls to Telegram | Abstract bus; multi-channel; per-channel outcomes |
| Fallback delivery | None (Telegram failures silent) | FileChannel always records |
| Metrics collection | None (only test-suite pass/fail) | Per-stage + per-pipeline JSONL |
| Status endpoint | None | `ops_status.json` with schema v1 |
| MON001 state visibility | Only inside MON001's own reports | Surfaced in `ops_status.json` |
| Process isolation | Bash: one bad script can leave orphans | subprocess.run with timeout + capture |
| Failure semantics | `\|\| echo` masks everywhere | Explicit `continue_on_failure` per stage |
| Test coverage of ops | 0 tests | 31 tests (100% on new modules) |

---

## 13. Regression results (post-OPS001-A)

Full regression harness (10 suites):

| Suite | Pass | Notes |
|---|:-:|---|
| MON001 core | 25/25 | unchanged |
| MON001 ops | 23/23 | unchanged (local) |
| LAB010 framework | 25/25 | unchanged |
| Core lab framework | 17/17 | unchanged |
| LAB009 maturity | 8/8 | unchanged |
| ENG001 lib | 33/33 | unchanged |
| ENG003 CI discipline | 5/5 | unchanged |
| ENG003 governance | 8/8 | unchanged |
| Telegram reliability | 13/13 | unchanged |
| **OPS001-A pipeline** | **31/31** | **new** |
| **TOTAL** | **188/188** | **10 suites** |

Invariance guards (5/5 HOLD):
- MON001 fingerprint `64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42` unchanged
- `HOLD=63`, `rebal=63`, `sector_cap=2`, `name_cap=0.30`, `method=hrp` unchanged
- `cumulative_strategy_search=38` unchanged
- `forward_boundary_asof=2026-03-28` unchanged
- Sealed + LAB files: empty diff vs HEAD

---

## 14. Future OPS roadmap

### OPS001-B · Daemon Mode (next)
- systemd unit + Windows Task Scheduler template + macOS launchd plist
- Long-running `run_forever.py` loop with configurable schedule
- Signal handling (SIGTERM → graceful shutdown)
- Log rotation
- Process supervision hooks
- Trigger: after ~2 weeks of successful `run_once()` invocations from cron

### OPS001-C · Multi-Channel Notification
- `EmailChannel` (SMTP; credentials-optional)
- `DiscordChannel` (webhook)
- `SlackChannel` (webhook)
- `WebhookChannel` (generic HTTP POST)
- `PushoverChannel` (mobile push)
- Trigger: when Telegram alone is insufficient (e.g., team distribution list)

### OPS002 · Observability Platform
- Metrics aggregation over `ops_metrics.jsonl`
- Rolling windows: 24h / 7d / 30d / 90d / 365d
- MTTR, availability, success rate, latency percentiles
- Trend detection (alert on 2× degradation vs 7-day baseline)
- Trigger: after 30 days of `ops_metrics.jsonl` accumulation

### OPS003 · Continuous Improvement Engine
- Upgrade recommendation detector:
  - stale parquets (age > N trading days)
  - missing NSE holidays for next year
  - `pip-audit` security advisories
  - MON001 fingerprint drift (with human-readable diff)
  - Model version drift (via LAB manifest)
- Trigger: after OPS002 provides trend baseline

### OPS004 · Self-Healing Automation
- Auto-restart failed stages beyond the pipeline retry policy
- Circuit breakers (halt cascading failures)
- Chaos injection (test fault tolerance in staging)
- Trigger: after OPS002 + OPS003 provide reliable failure detection

### OPS005 · Distributed Scheduler
- Move from single-node cron/systemd to a lightweight scheduler
  (options: Windmill, Prefect, Temporal, or a purpose-built Python one)
- Multi-region redundancy
- Trigger: only when operator is running multiple markets / geographies

---

## 15. Governance and reversibility

- Every OPS001-A file is **additive** — no existing sealed file changed
- **Trivial revert**: `git revert <ops001a-commit>` restores the pre-OPS state;
  no dependencies leak into sealed layers
- MON001 certification `MON001-CERT-2026-07-15` remains VALID
- No new `|| echo` / `|| true` masks introduced
- CI-discipline test unchanged (no new grandfathered masks)
- OPS001-A does not authorize modifications to any sealed file — the CHANGE_CONTROL_CHECKLIST discipline continues to apply

---

## 16. Explicit no-ops (guardrails held)

OPS001-A did NOT:

- Modify `HOLD`, `rebal`, `sector_cap`, `name_cap`, `method`, or any strategy input
- Modify `current_regime()`, `select_names()`, `weights_for()`, `NIFTY200`
- Modify any of the 5 MON001-sealed baseline files
- Modify any MON001 sealed core file (fingerprint, monitor, ledger, envelope, broker)
- Modify `india/telegram_notify.py` (the daily-recommendation sender)
- Modify any `india/ai_lab/**` artefact
- Introduce any new `|| echo` or `|| true` mask
- Modify `cumulative_strategy_search`
- Promote any LAB001–LAB010 candidate
- Launch OPS001-B, OPS001-C, OPS002, OPS003, OPS004, or OPS005
