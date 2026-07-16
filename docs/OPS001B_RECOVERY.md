# OPS001-B · Recovery Runbook

**Applies to:** OPS001-B daemon · **Version:** 0.1.0-ops001b

What to do when the daemon, the pipeline, or MON001 is in an unexpected state.

## Guiding principle

**Never delete or edit sealed files to make an error go away.** If the error
originates from sealed logic, the correct action is to diagnose it and (if
truly necessary) run the CHANGE_CONTROL_CHECKLIST ceremony — the last one
was `MON001-AMEND-2026-07-16-portability`.

## 1. Symptom → decision matrix

| Symptom | Most likely cause | First action |
|---|---|---|
| `pid_lock_held` on daemon start | Previous daemon didn't release. | `python scripts/nexaquant_daemon.py stop` then `start` |
| `slot_framework_error` on every fire | Import failure or env-var drift | Read `traceback` in log record |
| `slot_pipeline_failure` on every fire | A stage in the pipeline is failing | Read `reports/ops_alerts.jsonl` tail |
| Telegram alerts stop arriving | Bot token rotated / chat-id changed | `python scripts/telegram_health_check.py` |
| MON001 health reports HALT | Something changed in production or LAB files | Run `python -m india.monitoring.MON001_Forward_Validation.ops.health_check` |
| Daemon reports `daemon_running: true` but no slot has fired today | Fire window missed OR schedule state corrupted | Compare `next_run_utc` vs now |
| Log file stops growing but daemon is alive | Disk full or permissions issue | `df -h`, `ls -l reports/logs/` |

## 2. Interrupted pipeline (RunState phases)

The daemon writes `reports/ops_run_state.json` at each stage transition.
On next start the daemon inspects it and decides what to do:

| Previous phase | Decision | Emitted event |
|---|---|---|
| `idle` / `completed` | `NONE` | none |
| `starting` / `running` | `RESUME` | `WARN recovery_decision` |
| `aborted` | `RESUME` | `WARN recovery_decision` |
| `failed` | `ATTENTION` | `WARN recovery_decision` |

Recovery is always **re-fire on next due slot**, never in-place resume. The
AEGIS pipeline and MON001 stages are idempotent for a given `asof` — they
overwrite dated artefacts — so a fresh full pass is safe.

If you need to force a clean state:

```bash
mv reports/ops_run_state.json reports/ops_run_state.json.bak.$(date +%s)
```

## 3. Stale lock recovery

The `PidLock` breaks a lock when either condition holds:

- The recorded pid is not alive (`os.kill(pid, 0)` raises `ProcessLookupError`).
- The recorded `started_utc` is older than `stale_hours` (default 6h).

The daemon also refreshes its own lock every 15 min while running, so
long-running daemons never trip the age heuristic.

If the daemon crashes with `SIGKILL`, the lock stays behind but is broken
automatically at the next `start` or `stop` call.

Manual override (rarely needed):

```bash
python scripts/nexaquant_daemon.py stop      # cleans up broken lock if pid is dead
# or
rm reports/ops_daemon.lock                   # only if you're SURE no daemon is running
```

## 4. Schedule state corruption

`reports/ops_schedule_state.json` records the last successful fire per slot.
If it's corrupt (partial write, JSON error), the daemon treats every slot
as if it hasn't fired today.

**Impact:** slots whose fire window is still open MAY fire again — potentially
producing a second Telegram alert for the same asof. Acceptable but noisy.

**Fix:**

```bash
mv reports/ops_schedule_state.json reports/ops_schedule_state.json.bak.$(date +%s)
# Daemon regenerates it on the next fire.
```

## 5. MON001 HALT

**Do NOT restart the daemon and hope.**

1. Confirm HALT:
   ```bash
   python -m india.monitoring.MON001_Forward_Validation.ops.health_check
   ```

2. Read the specific failing check's `detail`. Common HALT causes:
   - `fingerprint_matches_seal` → production strategy file changed. Was there
     an unintended edit? Was a git checkout truncated? `git status` +
     `git diff india/recommendation_registry.py india/recommendation_generator.py`.
   - `envelope_byte_identical` → LAB009 diagnostics CSV changed (research
     integrity issue) OR envelope-building code drifted. Check
     `docs/MON001_CERTIFICATION.md §15` (portability amendment) if this appears
     on a new host.
   - `ledger_integrity` → the append-only forward ledger's hash chain broke.
     A row was mutated retroactively. This is a serious governance event —
     stop the daemon and investigate.

3. If HALT is real (not a portability quirk), do NOT try to "fix" MON001.
   Stop the daemon, then follow the CHANGE_CONTROL_CHECKLIST ceremony for the
   root cause.

## 6. Framework error inside daemon

If `slot_framework_error` fires:

1. Read the `traceback` field from the JSON log record:
   ```bash
   jq -c 'select(.event=="slot_framework_error") | .traceback' \
       reports/logs/nexaquant_ops.jsonl | tail -1
   ```

2. Cross-reference the module in the traceback:
   - If the error is in `nexaquant/ops/*` → OPS001 code bug. Roll back to
     previous known-good commit or file a fix under OPS001-B (never OPS001-A —
     that's shipped).
   - If the error is in `india/**` (except MON001 sealed) → a production
     module change. Investigate the diff.
   - If the error is in `india/monitoring/MON001_Forward_Validation/**` →
     STOP. Follow §5.

3. Re-run the failing pipeline manually via
   `python scripts/nexaquant_service.py` to reproduce with fresh output.

## 7. Log rotation gone wrong

If the daemon appears to be writing but no rotated files ever appear:

- Check `max_bytes` in `DaemonConfig.log_max_bytes` (default 5 MiB). Increase
  if your fire is producing >5 MiB per line, which is a bug in caller code.
- Check filesystem: `ls -l reports/logs/`. Confirm `nexaquant_ops.jsonl.1`
  etc. exist after enough logging.

If rotation is deleting files it shouldn't (i.e., you see `pruned` events
removing recent files):

- Verify `log_retention_days` — default 30.
- Confirm the active file (`nexaquant_ops.jsonl`, no numeric suffix) is
  never in the prune set. It's guarded in
  [nexaquant/ops/logging_setup.py::prune_old_logs](../nexaquant/ops/logging_setup.py).

## 8. Timeout handling

The daemon polls every `poll_interval_s` (default 30s). If a pipeline pass
takes hours (e.g., yfinance rate-limited), the daemon does NOT time it out —
it delegates timeout enforcement to OPS001-A's pipeline stage-level timeouts
(`timeout_s` in the YAML).

If you need the daemon itself to abort a stuck pass:

```bash
python scripts/nexaquant_daemon.py stop --timeout 60
```

The daemon receives SIGTERM, the currently-running stage's subprocess is
sent SIGTERM by the pipeline, and the daemon marks `RunState.phase =
ABORTED` before exiting.

## 9. Escalation path

If you have exhausted §§1-8 and the daemon is still in a bad state:

1. Stop the daemon: `python scripts/nexaquant_daemon.py stop`.
2. Snapshot the state directory for debugging:
   ```bash
   tar czf /tmp/nexaquant-state-$(date +%s).tar.gz reports/logs/ reports/ops_*.json
   ```
3. Roll back to the previous green commit:
   ```bash
   git log --oneline -10
   git checkout <last-green-sha>
   ```
4. Restart the daemon. If it now runs cleanly, bisect between the two commits.
5. Escalate: the last certification (`MON001-CERT-2026-07-15`) plus any
   amendments (currently just `MON001-AMEND-2026-07-16-portability`) is the
   contract. If they no longer hold, the failure is out of the daemon's
   scope — escalate to operator.

## 10. What recovery MUST NEVER involve

- Editing sealed files to bypass a check.
- Deleting `reports/logs/nexaquant_ops.jsonl` while the daemon is running.
- Deleting `india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json`.
- Deleting `india/monitoring/MON001_Forward_Validation/ledger/forward_ledger.jsonl`.
- Committing `--no-verify` to bypass a pre-commit hook.
- Force-pushing to `main`.

Each of the above will destroy audit evidence and invalidate the MON001
certification without producing an explanation of what was wrong. If any
of them looks tempting, stop and escalate instead.
