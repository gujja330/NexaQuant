# MON001 · Operations Handbook

**Audience:** operator responsible for running the frozen NexaQuant production
system and observing its forward behaviour via MON001.

**Never modifies production strategy.** MON001 is a read-only observation layer.

---

## 1. What MON001 does

Runs once per trading day. In one pass it:

1. Verifies the production baseline fingerprint hasn't drifted since the MON001 seal.
2. Ingests any new forward-eligible recommendations (asof ≥ `2026-03-28`) from
   `data/aegis_registry.csv` into an append-only, hash-chained ledger.
3. Reconstructs a paper equity curve from the ingested picks.
4. Compares forward metrics against the sealed LAB009 State C envelope (N0=63,
   canonical 15 bps).
5. Emits drift alerts (D1–D10) into `reports/mon001_alerts.jsonl`.
6. Writes a dated diagnostics JSON, human-readable report, and operator dashboard.

MON001 does **not**:
- modify `HOLD`, `CONFIG`, `current_regime()`, HRP, `sector_cap`, `name_cap`, or any
  strategy input
- place, modify, or cancel broker orders (order-placement methods raise `RuntimeError`)
- increment `cumulative_strategy_search`
- promote any research candidate
- rewrite historical registry rows or LAB001–LAB010 evidence

---

## 2. Installation

### 2.1 Windows (Task Scheduler)

Register once from an elevated PowerShell:

```powershell
$repo = "C:\Users\GPraveenKumar\Downloads\prism"
$launcher = "$repo\india\monitoring\MON001_Forward_Validation\launchers\run_mon001_windows.ps1"

$act = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`""
$trg = New-ScheduledTaskTrigger -Daily -At 06:15am
$set = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName "MON001-daily" -Action $act -Trigger $trg `
    -Settings $set -RunLevel Highest
```

`StartWhenAvailable` catches missed runs (laptop was asleep). `AllowStartIfOnBatteries`
keeps it running when the laptop is unplugged.

### 2.2 Linux / macOS (cron)

Weekdays at 06:15 IST:

```
15 6 * * 1-5 /path/to/prism/india/monitoring/MON001_Forward_Validation/launchers/run_mon001.sh
```

The launcher writes its own log under `logs/mon001/mon001_<date>.log`.

### 2.3 GitHub Actions (unattended)

`.github/workflows/mon001-daily.yml` already schedules the runner on 3 slots (IST
06:30 / 09:30 / 12:30). Once-per-IST-day guard prevents duplicate runs. Manual
dispatch is available at
`https://github.com/praveen330/NexaQuant/actions/workflows/mon001-daily.yml`.

CI commits the fresh ledger + diagnostics + dashboard so the operator has a paper
trail even if their laptop hasn't run in weeks.

### 2.4 Manual (troubleshooting)

```
python -m india.monitoring.MON001_Forward_Validation.ops.daily_runner
```

Or the raw MON001 pass (no recovery wrapper):

```
python india/monitoring/MON001_Forward_Validation/run_mon001.py
```

Add `--dry-run` to skip ledger append and alert emission.

---

## 3. Daily execution flow

```
06:15 IST (Windows) / 06:30 IST (CI)
     │
     ▼
┌──────────────────────────────────────────────────┐
│  daily_runner.run_once()                          │
│  1. acquire single-instance lock                  │
│  2. is_trading_day(today)?                        │
│       └── no  → OPS_MARKET_CLOSED INFO alert,     │
│                 minimal report, exit 0            │
│       └── yes → continue                          │
│  3. check parquet freshness                       │
│       └── stale → OPS_DATA_STALE WARN alert       │
│                    (MON001 still runs)            │
│  4. run_mon001.main() (fingerprint + envelope +   │
│     ledger ingest + drift + report)               │
│  5. dashboard.main()                              │
│  6. release lock; exit 0 (always)                 │
└──────────────────────────────────────────────────┘
     │
     ▼
Produces:
  reports/mon001_diagnostics_<date>.json   (machine)
  reports/mon001_report_<date>.md          (human)
  reports/dashboard_<date>.md              (operator TL;DR)
  reports/mon001_alerts.jsonl              (append-only)
  ops.log                                  (runner audit trail)
```

**Failure isolation:** the daily runner **always returns exit 0** on operational
failures. Errors surface via alerts (`OPS_RUN_FAILED`), never via non-zero exit.
This prevents a supervising process from misinterpreting a MON001 hiccup as a
recommendation-pipeline failure.

---

## 4. Manual rerun

```
python -m india.monitoring.MON001_Forward_Validation.ops.daily_runner
```

Safe to run at any time. Idempotent: rows already in the ledger are not re-appended.

To force a re-seal (only after an authorized production change):

```
rm india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json
python -m india.monitoring.MON001_Forward_Validation.ops.daily_runner --seal-init
```

This is a **change management event**. Do NOT re-seal to silence a `D1_CONFIG_DRIFT`
alert unless the production change was approved in writing.

---

## 5. Backup and restore

### 5.1 What to back up

| Path | Frequency | Reason |
|---|---|---|
| `india/monitoring/MON001_Forward_Validation/ledger/forward_ledger.jsonl` | Daily | Forward evidence — cannot be regenerated from scratch |
| `india/monitoring/MON001_Forward_Validation/ledger/corrections.jsonl` | Daily | Audit trail |
| `india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json` | Once at seal | Reseal reference — irreplaceable |
| `reports/baseline_envelope_2026-07-13.json` | Once at seal | Byte-identity check target |
| `india/monitoring/MON001_Forward_Validation/reports/mon001_alerts.jsonl` | Daily | Alert history for consecutive-window escalation |
| `india/monitoring/MON001_Forward_Validation/reports/mon001_diagnostics_*.json` | Daily | Time-series of MON001 state |

The GitHub Actions workflow commits all of these to `origin/main` after each run,
so a git backup is sufficient in most cases.

### 5.2 Restore procedure

If the working tree is corrupted:

```
git fetch origin main
git reset --hard origin/main
python -m india.monitoring.MON001_Forward_Validation.ops.health_check
```

Health check exit codes:
- 0 → healthy, run daily_runner as normal
- 1 → warning; review report but MON001 can still run
- 2 → HALT; do NOT run MON001 until root cause understood

If `verify_chain` reports `ledger_integrity` FALSE with a hash mismatch that
git reset cannot fix (mid-file corruption on disk), restore
`forward_ledger.jsonl` from the last known-good git blob:

```
git log --oneline --pretty=format:"%h %ci %s" -- india/monitoring/MON001_Forward_Validation/ledger/forward_ledger.jsonl | head -5
git checkout <good-commit-hash> -- india/monitoring/MON001_Forward_Validation/ledger/forward_ledger.jsonl
python -m india.monitoring.MON001_Forward_Validation.ops.health_check
```

---

## 6. Alert meanings

| Dimension | Meaning | Level | Operator action |
|---|---|---|---|
| `D1_CONFIG_DRIFT` | production baseline changed | HALT_REVIEW_REQUIRED | Check for authorized promotion; if unauthorized, revert; if authorized, re-seal |
| `D2_PERFORMANCE_DRIFT` | forward Sharpe outside envelope | WATCH → DIVERGED | Review report; do NOT tune strategy |
| `D3_RISK_DRIFT` | forward MaxDD deeper than envelope × buffer | WATCH → DIVERGED | Confirm no data glitch; check regime |
| `D4_TURNOVER_DRIFT` | realized turnover > backtest × threshold | WATCH → DIVERGED | Check rebalance cadence |
| `D5_COST_DRIFT` | realized cost > envelope | WATCH → DIVERGED | Verify turnover measurement |
| `D6_REGIME_BEHAVIOUR_DRIFT` | exposure distribution diverges from backtest | WATCH → DIVERGED | Verify `current_regime()` unchanged |
| `D7_CONCENTRATION_DRIFT` | name_cap or sector_cap breached | DIVERGED | Investigate the batch that produced it — hard constraint |
| `D8_DATA_DRIFT` | too many missing prices or stale recs | WATCH → DIVERGED | Check refresh pipeline |
| `D9_EXECUTION_DRIFT` | broker slippage exceeds threshold | DIVERGED | Only meaningful once broker fills are ingested (currently PAPER_ONLY) |
| `D10_DATA_INTEGRITY_FAILURE` | ledger corrupted / retroactively mutated | HALT_REVIEW_REQUIRED | Preserve current ledger; restore from backup; investigate |
| `OPS_RUN_FAILED` | daily runner exception | WARN | Read `ops.log`; investigate stack trace |
| `OPS_MARKET_CLOSED` | weekend or NSE holiday | INFO | No action |
| `OPS_DATA_STALE` | market data older than previous session | WARN | Wait for next data refresh; MON001 still runs |

**Escalation to HALT_REVIEW_REQUIRED:** any DIVERGED-level alert on the SAME
dimension for ≥ 4 consecutive weekly reports escalates automatically. HALT
does NOT stop production or MON001 — it produces a highly-visible alert
requiring operator decision.

---

## 7. `HALT_REVIEW_REQUIRED` procedure

1. **Do not modify production strategy in response.** Tuning is out-of-scope for
   MON001; it is post-hoc search on live evidence.
2. Read `docs/POST_LAB010_RESEARCH_AUDIT.md` and `docs/FUTURE_RESEARCH_ROADMAP.md`
   §14 (research STOP conditions).
3. Inspect the specific dimension that triggered HALT via
   `reports/mon001_alerts.jsonl` (filter by `severity=HALT_REVIEW_REQUIRED`).
4. Classify:
   - `D1_CONFIG_DRIFT` → change management incident.
   - `D10_DATA_INTEGRITY_FAILURE` → forensics + restore.
   - Any D2-D9 4-week-persistent divergence → operator judgment call whether to
     (a) accept and continue, (b) suspend live paper-trading, or (c) initiate a
     validation lab (e.g., ENG003) with fresh preregistration.
5. Document the decision in `docs/POST_LAB010_RESEARCH_AUDIT.md` history section.
6. If a valid production change is authorized, re-seal MON001
   (`daily_runner --seal-init`) with the new fingerprint.

---

## 8. Expected evidence timeline

At seal (`2026-07-13`) MON001 held 75 forward observations (after the ingest fix),
0 completed cycles, and state `INSUFFICIENT_EVIDENCE`.

| Milestone | Threshold | Earliest calendar date |
|---|:-:|:-:|
| Initial Sharpe reading (T30) | 30 forward trading days | ~2026-08-10 |
| First cycle completion | 63 forward trading days after asof 2026-06-25 | ~2026-09-24 |
| Reliable MaxDD reading (T126) | 126 forward trading days | ~2026-11-25 |
| Annualized Sharpe vs backtest (T252) | 252 forward trading days | ~2027-04-15 |

Do NOT interpret metrics before their minimum-evidence threshold — MON001 reports
`INSUFFICIENT_EVIDENCE` in that state and no PASS / WATCH / DIVERGED verdict is
computed for that metric.

---

## 9. Scalability

Stress test at 30/90/180/365-day scales confirms:

| Scale | Ledger rows | Disk (KiB) | verify_chain (s) |
|---|:-:|:-:|:-:|
| 30 days | 15 | 21 | 0.02 |
| 90 days | 15 | 21 | 0.02 |
| 180 days | 30 | 42 | 0.02 |
| 365 days | 75 | 106 | 0.02 |

Projected 5-year footprint: ~500 KiB. verify_chain remains sub-second at any
reasonable scale. No archival / rotation needed for years.

---

## 10. Files reference

| Path | Purpose |
|---|---|
| `india/monitoring/MON001_Forward_Validation/preregistration.md` | Sealed hypothesis + thresholds |
| `india/monitoring/MON001_Forward_Validation/mon001.yaml` | Sealed configuration |
| `india/monitoring/MON001_Forward_Validation/run_mon001.py` | Raw MON001 pass (no recovery wrapper) |
| `india/monitoring/MON001_Forward_Validation/ops/daily_runner.py` | Resilient wrapper (Windows/cron/CI entrypoint) |
| `india/monitoring/MON001_Forward_Validation/ops/health_check.py` | Pre-run state verifier |
| `india/monitoring/MON001_Forward_Validation/ops/alerts.py` | Alert bus + consecutive tracking + playbook |
| `india/monitoring/MON001_Forward_Validation/ops/dashboard.py` | Operator dashboard renderer |
| `india/monitoring/MON001_Forward_Validation/ops/stress_test.py` | Long-run simulation harness |
| `india/monitoring/MON001_Forward_Validation/ops/holiday_calendar.py` | NSE holiday calendar |
| `india/monitoring/MON001_Forward_Validation/launchers/run_mon001_windows.ps1` | Task Scheduler entry |
| `india/monitoring/MON001_Forward_Validation/launchers/run_mon001.sh` | cron entry |
| `.github/workflows/mon001-daily.yml` | GitHub Actions schedule |
| `docs/MON001_OPERATIONS.md` | This document |

---

## 11. Governance reminders

- MON001 does NOT modify production strategy — ever.
- MON001 is not authorized to place broker orders.
- MON001 alerts do NOT authorize starting a new alpha lab.
- `cumulative_strategy_search` must remain 38 until an authorized lab increments it.
- `HOLD = 63`, `rebal = 63`, `method = hrp`, `sector_cap = 2`, `name_cap = 0.30`
  are the sealed production constants.
- Roadmap ordering (see `docs/FUTURE_RESEARCH_ROADMAP.md`) is NOT modified by this
  operationalization — MON001 was already the recommended first phase; this
  handbook only expands its operational surface.
