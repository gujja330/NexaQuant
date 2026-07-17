# How to run the AEGIS pipeline locally with a single command

**Audience:** operator debugging or force-running today's recommendations
without waiting for GitHub Actions cron.
**Prerequisite:** repo cloned, Python 3.12 installed, deps installed.

---

## TL;DR — the two single-file runners

### 🟢 Recommended — verbose runner (prints every step)

```bash
python scripts/run_pipeline_local.py
```

Prints big banners for every stage. Shows timing, exit codes, and a summary table.
Same 9-stage pipeline as GitHub Actions.

**Common flags:**

| Flag | Purpose |
|---|---|
| (none) | Full pipeline + Telegram (freshcheck may refuse stale) |
| `--force-send` | If Telegram refuses as stale, bypass the check and send yesterday's data anyway |
| `--skip-telegram` | Everything except Telegram health check + notify |
| `--skip-mon001` | Everything except MON001 daily runner |

### 🔵 Alternative — quiet runner (OPS001-A framework)

```bash
python scripts/nexaquant_service.py
```

Same pipeline, quieter output (JSON events + metrics ledger). Faster to read
programmatically; harder to read as a human. Prefer `run_pipeline_local.py`
during manual invocation.

---

### What you'll see with `run_pipeline_local.py`

```
======================================================================
  AEGIS  ·  LOCAL PIPELINE RUNNER
======================================================================
  time (IST):    11:47:12 IST
  IST date:      2026-07-17
  repo:          /path/to/prism
  pipeline YAML: nexaquant/ops/pipelines/aegis_daily.yaml
  stages:        9

----------------------------------------------------------------------
  STEP 1/9:  refresh_data
----------------------------------------------------------------------
  command:  python india/refresh_data.py
  started:  11:47:12 IST
  timeout:  900s   ·   continue_on_failure: True
  ...
  [OK]     finished  11:48:03 IST   (51.2s)

----------------------------------------------------------------------
  STEP 2/9:  freshness_gate
----------------------------------------------------------------------
  ...

======================================================================
  PIPELINE SUMMARY
======================================================================
  [OK]     refresh_data                   (51.2s)  exit=0
  [OK]     freshness_gate                 (1.1s)   exit=0
  [OK]     recommendation_generator       (48.3s)  exit=0
  ...
  [STALE]  telegram_notify                (0.4s)   exit=2
  [OK]     mon001_daily                   (18.7s)  exit=0

  Totals:  OK=8   FAILED=0   STALE=1   SKIPPED=0
  Wall clock: 129.2s (2.2min)
```

### Exit codes

- `0` — every stage succeeded (or was skipped by flag)
- `1` — at least one non-continue-on-failure stage failed
- `2` — framework error (bad YAML, missing dep, etc.)

### Freshness gate (`REFUSED_STALE`)

The Telegram sender (OPS001-F) refuses to send if the recommendation's
`Generated` date is not today's IST date. If you run the pipeline while
the market is still open (before ~16:00 IST), yfinance won't have today's
close yet, generator stamps yesterday's date, and Telegram refuses. That
shows as `[STALE]` on the `telegram_notify` line — everything else still
completes. Use `--force-send` to bypass (sends yesterday's data), or wait
until after 16:00 IST to run without the flag.

---

## What the 9 stages do

Defined in [`nexaquant/ops/pipelines/aegis_daily.yaml`](../nexaquant/ops/pipelines/aegis_daily.yaml):

| # | Stage | Command | Effect |
|:-:|---|---|---|
| 1 | `refresh_data` | `python india/refresh_data.py` | yfinance → appends today's close to every parquet in `data/raw/india/*_D1.parquet` |
| 2 | `freshness_gate` | `python scripts/check_data_freshness.py` | Exits non-zero if data gap ≥ 1 trading day |
| 3 | `recommendation_generator` | `python india/recommendation_generator.py --capital 100000` | Writes `data/aegis_today.csv`, appends to `data/aegis_registry.csv`, writes `reports/AEGIS_LATEST.xlsx` |
| 4 | `recommendation_db` | `python india/recommendation_db.py` | Updates `data/aegis_recommendation_db.csv` (append-only DB) |
| 5 | `scorecard` | `python india/scorecard.py` | Writes `data/aegis_scorecard.csv` + `india/reports/scorecard_*.md` |
| 6 | `ops_check` | `python india/ops_check.py` | Prints AEGIS OPERATIONS HEALTH board (informational) |
| 7 | `telegram_health_check` | `python scripts/telegram_health_check.py` | Verifies bot token + chat via getMe + getChat |
| 8 | `telegram_notify` | `python scripts/telegram_send_with_retry.py --attempts 4` | Sends the daily message (OPS001-F freshness gate refuses stale) |
| 9 | `mon001_daily` | `python -m india.monitoring.MON001_Forward_Validation.ops.daily_runner` | Appends to forward_ledger, writes dashboard + diagnostics |

Any stage with `continue_on_failure: true` in the YAML is treated as
non-blocking — it can fail without aborting the whole pipeline.

---

## Setup — one-time prerequisites

### 1. Secrets in a local `.env` file (git-ignored)

Create `/.env` at the repo root. **NEVER commit this file.**

```dotenv
# Required for Telegram send
TELEGRAM_BOT_TOKEN=123456789:AA...your bot token
TELEGRAM_CHAT_ID=123456789

# Optional — enables Google Sheets sync (skip if you don't use Sheets)
AEGIS_SPREADSHEET_ID=1abc...
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
```

Verify `.env` is git-ignored:

```bash
git check-ignore .env
# should print: .env
```

### 2. Python dependencies

```bash
pip install pyyaml pandas numpy pyarrow scipy scikit-learn yfinance
# optional:
pip install gspread google-auth       # Google Sheets sync
pip install psutil                    # OPS001-B daemon monitoring
```

Same list as `.github/workflows/aegis-daily.yml` installs.

---

## Common invocations

### A. Full pipeline with Telegram send (default)

```bash
python scripts/nexaquant_service.py
```

Runs all 9 stages. Sends Telegram. Modifies committed files.

### B. Full pipeline WITHOUT Telegram (safest for testing)

```bash
python scripts/nexaquant_service.py --no-telegram
```

Everything runs except stages 7-8. Great for:
- Testing generator output without spamming your phone
- Regenerating `aegis_today.csv` with today's date
- Verifying MON001 stays green

### C. Just the recommendation engine (skip MON001 + Telegram)

Three commands in order:

```bash
python india/refresh_data.py
python scripts/check_data_freshness.py
python india/recommendation_generator.py
```

Fastest path if you only want today's picks in `data/aegis_today.csv`.

### D. Just MON001 daily runner

```bash
python -m india.monitoring.MON001_Forward_Validation.ops.daily_runner
```

Independent of the AEGIS pipeline. Writes ledger row + dashboard.

### E. Only the Telegram send (uses whatever's in aegis_today.csv)

```bash
python scripts/telegram_send_with_retry.py --attempts 4
```

Uses OPS001-F's freshness gate — refuses to send if `Generated` field
doesn't match today's IST date. Exits with code 2 (`REFUSED_STALE`) if
stale.

### F. Alternate pipeline YAML

```bash
python scripts/nexaquant_service.py --pipeline path/to/custom.yaml
```

Advanced. Only useful if you have a customized pipeline definition.

---

## Files that get modified

### Committed files rewritten by a full run

```
data/aegis_today.csv                                                   ← Generated becomes today
data/aegis_recommendation_db.csv                                       ← new row appended
data/aegis_registry.csv                                                ← new REC-YYYYMMDD-NNNN rows
data/aegis_candidates.csv                                              ← full candidate scores
data/raw/india/*_D1.parquet                                            ← ~228 files, yfinance appends
reports/AEGIS_LATEST.xlsx                                              ← workbook rewritten
data/aegis_scorecard.csv                                               ← scorecard rewritten
india/reports/scorecard_*.md                                           ← scorecard reports
india/monitoring/MON001_Forward_Validation/reports/dashboard_*.md      ← MON001 dashboard
india/monitoring/MON001_Forward_Validation/reports/mon001_report_*.md
india/monitoring/MON001_Forward_Validation/reports/mon001_diagnostics_*.json
india/monitoring/MON001_Forward_Validation/reports/.mon001_published
india/monitoring/MON001_Forward_Validation/ledger/forward_ledger.jsonl ← APPEND-ONLY (never rewritten)
india/monitoring/MON001_Forward_Validation/reports/mon001_alerts.jsonl ← APPEND-ONLY
data/.published                                                        ← IST-date marker
```

### Runtime state files (OPS001-A/B/C, not usually committed)

```
reports/ops_status.json                     ← current status snapshot
reports/ops_metrics.jsonl                   ← metrics ledger
reports/ops_alerts.jsonl                    ← file-channel notification log
reports/telegram_delivery_YYYY-MM-DD.jsonl  ← attempt log per day
```

---

## Verifying a successful run

Four quick checks:

```bash
# 1. Generated field of aegis_today.csv must be today's IST date
head -2 data/aegis_today.csv | tail -1 | cut -d, -f1

# 2. Registry has new REC-YYYYMMDD-* rows for today
tail -3 data/aegis_registry.csv

# 3. Forward ledger appended (150 → 151+ or more)
wc -l india/monitoring/MON001_Forward_Validation/ledger/forward_ledger.jsonl

# 4. MON001 health check green
python -m india.monitoring.MON001_Forward_Validation.ops.health_check
```

Expected all four to show today's evidence + green MON001.

---

## Warnings

### ⚠ 1. Local runs modify committed files

Every local run leaves a dirty working tree. Options after running:

**Best — commit your run** (only if you WANT to overwrite what aegis-bot would do):

```bash
git add data/aegis_today.csv data/aegis_recommendation_db.csv data/aegis_registry.csv \
        data/raw/india/*_D1.parquet reports/AEGIS_LATEST.xlsx \
        india/monitoring/MON001_Forward_Validation/reports/ \
        india/monitoring/MON001_Forward_Validation/ledger/forward_ledger.jsonl
git commit -m "Manual local run 2026-07-17: refresh + regenerate"
git push
```

But note: **if you push a manual commit today, the next scheduled cron
at 16:15 IST may race with you**. The workflow's guard step reads
`data/.published` — if you committed with today's IST date in that file,
the cron will skip (once-per-day guard). If you committed WITHOUT
updating `.published`, the cron will overwrite your work.

**Recommended safer flow if just testing:**

```bash
git stash push -u -m "before-local-pipeline-run"
python scripts/nexaquant_service.py
# inspect outputs, verify what you wanted
git stash pop   # restore working tree if you don't want to commit
```

**Nuclear option — discard everything (destructive):**

```bash
git checkout .  # reverts every uncommitted file — ONLY use if run failed
```

### ⚠ 2. Do not `git push` local pipeline output casually

The workflow has an `aegis-bot` identity for audit trail cleanliness.
If you push local output under `praveen330`, git-blame shows the daily
rows attributed to you instead of the bot. Distinguishable but noisy.

If the cron is broken (like the OPS001-E defect was), a manual push is
justified. Under steady state, prefer to let the cron run.

### ⚠ 3. yfinance ingestion latency

- NSE market closes at 15:30 IST
- yfinance typically has today's close available ~15-60 min later (16:00-16:30 IST)
- If you run BEFORE market close: yfinance has yesterday's close only → generator stamps `asof=yesterday`
- If you run AFTER market close but BEFORE yfinance settles: same result
- **Practical rule: run at 16:30 IST or later to reliably get today's asof**

If today's asof isn't what you expected, that's not a bug — that's a data-provider timing issue.

### ⚠ 4. OPS001-F sender-side freshness gate

`scripts/telegram_send_with_retry.py` REFUSES to send if
`aegis_today.csv` `Generated` field is not today's IST date. It exits
with code 2 (`REFUSED_STALE`).

This is intentional — it's the guard from OPS001-F that prevents the
17-day silent-stale-Telegram defect from recurring.

If you want to force-send anyway (rarely justified), bypass the wrapper:

```bash
python india/telegram_notify.py           # NO freshness gate
```

Only do this if you understand you may be sending stale content.

### ⚠ 5. MON001 fingerprint invariance

Every run computes the fingerprint against sealed baseline files. If it
mismatches, MON001 reports HALT.

If you see HALT after a local run:

- Check if you accidentally modified any of the 12 sealed files
- Check if a dependency upgrade changed pandas/numpy behaviour
- Run `python nexaquant/tests/test_regression.py` — the invariance guards will tell you exactly what drifted

---

## Right-now cookbook — Friday 2026-07-17 example

Current IST time when this doc was written: **~11:13 IST**. Market is
open (09:15-15:30 IST). yfinance definitely does NOT have today's close
yet.

**If you run the pipeline NOW (11:13 IST):**

```bash
python scripts/nexaquant_service.py --no-telegram
```

Result:
- `refresh_data`: yfinance appends 2026-07-16 close (yesterday). No 2026-07-17 bar yet.
- `freshness_gate`: expected=07-16, latest=07-16, gap=0 → FRESH → PASS.
- `recommendation_generator`: `asof = closes.index[-1] = 2026-07-16`. Writes `aegis_today.csv` with `Generated=2026-07-16`.
- `recommendation_db`, `scorecard`, `ops_check`: run against 07-16 data.
- `telegram_health_check`: skipped due to `--no-telegram`.
- `telegram_notify`: skipped due to `--no-telegram`.
- `mon001_daily`: runs against 07-16 data. Ledger appends. Dashboard updated.

**Then if you re-run WITHOUT `--no-telegram`**:

```bash
python scripts/nexaquant_service.py
```

The sender-side freshcheck will see `Generated=2026-07-16` vs
`today_IST=2026-07-17` → **REFUSED_STALE, no Telegram sent**. This is
correct: 2026-07-16 recommendations aren't today's data.

**To force a real 2026-07-17 pipeline run:** wait until **after 15:35
IST** (market close + a small buffer for yfinance ingestion), then run.
By 16:00-16:15 IST the data will be available.

---

## Troubleshooting

### Pipeline stops at freshness_gate with exit 2

`check_data_freshness.py` decided data is stale. Read its output — it
tells you `latest_bar` vs `expected_session`. Usually means yfinance
hasn't ingested the expected close yet.

Fix: wait 15-30 minutes and rerun.

### recommendation_generator raises an exception

Very unlikely post-OPS001-F (pandas-QE fix). If it happens, the exact
traceback goes to stdout. Common causes:

- Missing dependency (`pip install pyarrow scipy scikit-learn`)
- Corrupted parquet file (`rm data/raw/india/BAD_D1.parquet && python india/refresh_data.py`)
- Data-schema drift from yfinance (very rare)

### Telegram not sent (REFUSED_STALE)

Sender-side freshcheck refused. Read the message — it tells you
`Generated=... != today IST=...`. Two options:

1. Fix the input: rerun the pipeline when yfinance has today's data (post-close + 30-45 min)
2. Bypass the gate: `python india/telegram_notify.py` directly (only for genuine emergencies)

### MON001 daily runner fails

The runner catches every internal exception and exits 0 (this is by
design — see MON001 preregistration §6). It emits an alert to
`mon001_alerts.jsonl` instead.

Check `india/monitoring/MON001_Forward_Validation/reports/mon001_alerts.jsonl`
tail for the last alert.

### Git working tree dirty after run

Expected. See "Warnings §1" above.

### GitHub Actions cron and local run conflict

If you commit + push a local run, and then the scheduled cron fires
later the same day:

- If you updated `data/.published` to today's IST date, the cron's guard
  skips the whole workflow. Safe.
- If you did NOT update `data/.published`, the cron overwrites your work.

Best practice: don't manually push aegis-bot-style commits on days when
the cron will fire cleanly.

---

## Reference links

- Pipeline definition: [`nexaquant/ops/pipelines/aegis_daily.yaml`](../nexaquant/ops/pipelines/aegis_daily.yaml)
- Service wrapper source: [`scripts/nexaquant_service.py`](../scripts/nexaquant_service.py)
- OPS001-A pipeline runner: [`nexaquant/ops/pipeline.py`](../nexaquant/ops/pipeline.py)
- Telegram sender: [`scripts/telegram_send_with_retry.py`](../scripts/telegram_send_with_retry.py)
- MON001 runbook: [`docs/MON001_OPERATIONS.md`](MON001_OPERATIONS.md)
- OPS001-B operator runbook: [`docs/OPS001B_OPERATIONS.md`](OPS001B_OPERATIONS.md)
- OPS001-E root cause (why the 17-day stale defect happened): [`docs/OPS001E_ROOT_CAUSE_REPORT.md`](OPS001E_ROOT_CAUSE_REPORT.md)
- OPS001-F fix (pandas-QE + freshcheck): [`docs/OPS001F_IMPLEMENTATION.md`](OPS001F_IMPLEMENTATION.md)
- OPS001-J diagnosis (why cron may show yesterday's date): [`docs/OPS001-J_ROOT_CAUSE.md`](OPS001-J_ROOT_CAUSE.md)

---

**Saved 2026-07-17 by operator request. Presentation-only doc — no code changes.**
