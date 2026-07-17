# OPS001-M · First Successful Production Run Audit

**Audit ID:** `OPS001M-AUDIT-2026-07-17`
**Role:** Principal Production Engineer · Release Auditor · QA Lead · Site Reliability Engineer
**Method:** Read-only. Zero code changes. Zero workflow changes. Zero commits beyond this doc.
**Target of audit:** The first successful AEGIS Daily production run after OPS001-F (2026-07-17 09:33 IST) and OPS001-I (2026-07-17 10:49 IST).

---

## 0. Executive summary

# ⏳ AUDIT SUSPENDED — the target run does not exist yet

I cannot audit a production run that has not happened. As of the moment
this audit was conducted:

- **Current time:** 2026-07-17 11:13 IST (05:43 UTC), Friday
- **Primary AEGIS Daily cron:** scheduled 16:15 IST — **fires in 5h 2m**
- **Backup 1:** 18:30 IST — fires in 7h 17m
- **Backup 2:** 21:00 IST — fires in 9h 47m
- **Bot commits for 2026-07-17:** ZERO (both aegis-bot and mon001-bot)
- **Latest aegis-bot commit anywhere:** `b7999f8` at 2026-07-16 12:08 UTC (17:38 IST YESTERDAY) — pre-OPS001-F, part of the stale-content run OPS001-J identified

**There is no first successful post-OPS001-F/-I run to audit** because
the cron schedule has not fired since the fixes landed at 09:33 IST and
10:49 IST today.

Certification result: **DEFERRED.** This document remains a pre-populated
checklist ready to be re-executed and stamped when the first post-fix run
completes (expected within 6 hours from the timestamp of this doc).

---

## 1. Timeline

| Event | Time (IST) | Time (UTC) | Status |
|---|:-:|:-:|:-:|
| OPS001-F (pandas-QE fix) landed on `main` | 2026-07-17 09:33 | 2026-07-17 04:03 | ✅ complete |
| OPS001-I (Telegram redesign) landed on `main` | 2026-07-17 10:49 | 2026-07-17 05:19 | ✅ complete |
| Audit executed | 2026-07-17 11:13 | 2026-07-17 05:43 | 📋 this doc |
| **Primary AEGIS Daily cron** | **2026-07-17 16:15** | **2026-07-17 10:45** | ⏳ pending |
| Backup 1 AEGIS Daily cron | 2026-07-17 18:30 | 2026-07-17 13:00 | ⏳ pending |
| Backup 2 AEGIS Daily cron | 2026-07-17 21:00 | 2026-07-17 15:30 | ⏳ pending |
| MON001 Daily primary | 2026-07-17 16:30 | 2026-07-17 11:00 | ⏳ pending |
| **First candidate window for audit target** | **~16:20 IST today** | **~10:50 UTC today** | ⏳ pending |

**Gap: 5 hours 2 minutes** between audit execution and the earliest
possible target run. The audit is inherently un-completable at this
moment.

---

## 2. Pipeline diagram — current state

```
                                          ▲
                                          │
             pre-fix world:  b7999f8 aegis-bot 2026-07-16 12:08 UTC
                             (produced stale 07-14 Telegram — OPS001-E defect)
                                          │
─────────────────────────────────  code fix boundary  ─────────────
                                          │
             d8f6dba  praveen330  2026-07-17 04:03 UTC  OPS001-F
             dac4eaf  praveen330  2026-07-17 05:19 UTC  OPS001-I
                                          │
                                          │
                                     ✂ AUDIT NEEDED HERE
                                          │
                                          ▼
             ⏳ awaited: aegis-bot  2026-07-17 ~10:50 UTC  daily
```

The audit is anchored at the point marked ✂ — but no commit exists there
yet.

---

## 3. Stage-by-stage pre-populated audit template

Each stage has:
- **Status:** ⏳ pending (target run doesn't exist)
- **PASS criterion:** what would need to be observed
- **How to observe:** where to look when the run lands

### 3.1 GitHub Actions

| Field | PASS criterion | Where to observe |
|---|---|---|
| Workflow started | `AEGIS Daily #45+` appears with status `in_progress` on the Actions tab | github.com/praveen330/NexaQuant/actions/workflows/aegis-daily.yml |
| Workflow completed | Status transitions to `success` (green ✓) | Same page |
| Runtime | Duration displayed on run page. Historical median = 3-8 min. | Run page |
| Logs | Each step shows expandable log. Especially: `Refresh market data`, `Freshness gate`, `Run AEGIS engine (fail-fast)`, `Verify aegis_today.csv is fresh`, `Telegram daily notification` | Run page |
| Exit status | All step exit codes = 0 | Individual step summaries |
| Artifacts | `telegram-delivery-log` artifact uploaded | Artifacts section of run page |

**Status: ⏳ PENDING**

### 3.2 Data Refresh

| Field | PASS criterion | Where to observe |
|---|---|---|
| Parquet files updated | On CI runner: mtimes of `data/raw/india/*_D1.parquet` should be within the workflow's runtime window | `Refresh market data` step log |
| Latest trading session | `newest date now: 2026-07-17` in step log (or 2026-07-16 acceptable if yfinance slow) | `Refresh market data` step log tail |
| refresh_data completed | Exit code 0 | Step status |

**Status: ⏳ PENDING**

### 3.3 Recommendation Engine

| Field | PASS criterion | Where to observe |
|---|---|---|
| `recommendation_generator.py` executed | Log shows generator output including `PUBLISHED -> data/aegis_today.csv` | `Run AEGIS engine (fail-fast)` step log |
| No exceptions | No `Traceback` in step log | Same step |
| `aegis_today.csv` regenerated | Commit diff includes this file OR runner-side mtime is fresh | Commit diff `git show <sha> --name-only` |
| `recommendation_db.csv` regenerated | Commit diff includes this file | Commit diff |
| `registry.csv` regenerated | Commit diff includes new `REC-20260717-*` rows | Commit diff + `tail data/aegis_registry.csv` |

**Status: ⏳ PENDING**

### 3.4 Commit Verification

| Field | PASS criterion | Where to observe |
|---|---|---|
| aegis-bot commit created | `git log origin/main --author=aegis-bot --since="2026-07-17 00:00"` returns ≥ 1 commit | Local git after `git fetch` |
| Files changed | Commit diff must include ALL of: `data/aegis_today.csv`, `data/aegis_recommendation_db.csv`, `data/aegis_registry.csv`, `data/.published`, and 100+ `data/raw/india/*_D1.parquet` files | `git show <sha> --name-only` |
| No sealed file modified | `git show <sha> --name-only` must not intersect the forbidden set | Compare against `test_no_sealed_files_modified_by_eng001` |

**Status: ⏳ PENDING**

Expected list of modified files on a successful run:
```
data/.published
data/aegis_today.csv               ← must appear
data/aegis_recommendation_db.csv   ← must appear
data/aegis_registry.csv            ← must appear
data/aegis_candidates.csv          ← optional
data/raw/india/AARTIIND_D1.parquet
data/raw/india/ABBOTINDIA_D1.parquet
... (228 parquet files)
india/reports/AEGIS_LATEST.xlsx    ← may appear
india/reports/mon001_report_2026-07-17.md   ← from mon001-bot's follow-on commit
india/reports/dashboard_2026-07-17.md
```

### 3.5 Telegram

| Field | PASS criterion | Where to observe |
|---|---|---|
| Message delivered | Operator receives push on their phone/desktop between 16:20-16:35 IST (primary slot) OR 18:35 IST (backup slot) | Operator's Telegram client |
| Market asof | Header line 2 shows `Market asof YYYY-MM-DD` where date == today (best) or == last trading day (acceptable Friday-latency) | Telegram message body |
| Integrity footer | Footer contains: `Run <UTC>Z (<HH:MM> IST)`, `Market asof <YYYY-MM-DD>`, `MON001 fp e4c07067…`, `Cert MON001-CERT-2026-07-17`, `Cycle AEGIS_v2.2 · Trials 38`, `Report SHA <8-hex>`, disclaimer line | Telegram message tail |
| Report SHA | 8-hex string, changes daily (deterministic given content) | Telegram message tail |
| No stale data | Message asof matches today OR yesterday's trading close (nothing older) | Header vs today's date |
| First-screen actionability | ACTIONS TODAY block visible within first 25 lines (BUY/HOLD/EXIT/WATCH counts) | Scroll test |

**Status: ⏳ PENDING**

### 3.6 Google Sheets

| Field | PASS criterion | Where to observe |
|---|---|---|
| Upload executed | `Push to Google Sheets` step status = `success` | GH Actions run page |
| Upload succeeded | Sheet last-modified timestamp within workflow's runtime window | Google Sheets UI |
| Row counts | Sheets row count matches `aegis_today.csv` row count (typically 12 recommendations) | Compare Sheets tab vs CSV |
| Secrets present | `GOOGLE_SERVICE_ACCOUNT_JSON` + `AEGIS_SPREADSHEET_ID` in repo secrets (unverifiable from repo) | github.com/praveen330/NexaQuant/settings/secrets/actions |

**Status: ⏳ PENDING** (Sheets is optional per current design — a no-op if secrets absent)

### 3.7 Monitoring

| Field | PASS criterion | Where to observe |
|---|---|---|
| MON001 health check post-run | `worst_severity: INFO`, `exit_code: 0`, `global_state: OK` (not DIVERGED) | `india/monitoring/MON001_Forward_Validation/reports/mon001_diagnostics_2026-07-17.json` |
| Fingerprint | matches sealed `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf` | health check output |
| Governance | All ENG001 invariance guards HOLD | `python nexaquant/tests/test_regression.py` |
| Freshness gate | Exited 0 in workflow | `Freshness gate` step log |
| Notification wrapper | Sender exited 0 (successful send) OR exited 2 (REFUSED_STALE) — anything else is a defect | `Telegram daily notification` step + delivery ledger artifact |

**Status: ⏳ PENDING**

Note: current MON001 state is INFO (see attached live health check in §5),
but that check would need to be re-run AFTER the workflow to confirm no
drift was introduced.

---

## 4. Pass / fail matrix

| # | Stage | Result | Notes |
|:-:|---|:-:|---|
| 1 | GitHub Actions | ⏳ **PENDING** | No workflow run for 2026-07-17 yet |
| 2 | Data Refresh | ⏳ **PENDING** | Refresh only runs inside the workflow |
| 3 | Recommendation Engine | ⏳ **PENDING** | Generator only runs inside the workflow |
| 4 | Commit Verification | ⏳ **PENDING** | No aegis-bot commit today |
| 5 | Telegram | ⏳ **PENDING** | No send today; sender freshcheck correctly refuses stale |
| 6 | Google Sheets | ⏳ **PENDING** | Sheets sync only runs inside the workflow |
| 7 | Monitoring | 🟢 **PRE-RUN GREEN** | Live checks pass; would need re-check post-run |
| 8 | Final Certification | ⏳ **DEFERRED** | See §7 |

**None of stages 1-6 can be evaluated until the workflow fires. Stage 7 is verified only for the pre-run state.**

---

## 5. Live evidence at audit time

### 5.1 Fetch confirmation

```
git fetch origin main → From https://github.com/praveen330/NexaQuant
                        b638d66..b638d66  main → FETCH_HEAD  (no change)
```

Latest 8 commits on `origin/main`:

```
dac4eaf  praveen330  2026-07-17 05:19 UTC  OPS001-I: institutional Telegram redesign
dbf5448  praveen330  2026-07-17 04:35 UTC  Design docs: OPS001-G + OPS001-H + LAB011
d8f6dba  praveen330  2026-07-17 04:03 UTC  OPS001-F: pandas-QE compatibility
37aa266  praveen330  2026-07-16 15:23 UTC  OPS001-D meta-audit
b638d66  mon001-bot  2026-07-16 12:21 UTC  MON001 daily
b7999f8  aegis-bot   2026-07-16 12:08 UTC  AEGIS daily
c9b326e  praveen330  2026-07-16 11:17 UTC  OPS001-D audit
5f915c5  praveen330  2026-07-16 10:03 UTC  OPS001-D plan
```

**No 2026-07-17 bot commit.**

### 5.2 Time state

```
UTC:  2026-07-17T05:43:20+00:00
IST:  2026-07-17T11:13:20+05:30
Today IST date: 2026-07-17 (Friday)

Cron slot status:
  primary  16:15 IST: PENDING (fires in 5h 2m)
  backup 1 18:30 IST: PENDING (fires in 7h 17m)
  backup 2 21:00 IST: PENDING (fires in 9h 47m)
```

### 5.3 Local pre-run state (would be sent if invoked NOW)

`build_message()` output header:

```
NEXAQUANT · AEGIS Daily
Market asof 2026-07-14 (Tue) · Regime Weak
Shield · Deploy 60% · Cash 40%
```

Sender-side freshcheck (OPS001-F wrapper):

```
ok:     False
reason: aegis_today.csv Generated='2026-07-14' != today IST='2026-07-17'
        — refusing to send stale recommendations
```

**Verified:** even if the sender were invoked NOW, the OPS001-F guard
would refuse to deliver. No stale message can escape this system under
current code.

### 5.4 Pre-run monitoring — 🟢 GREEN

```
[ OK ] config_loads                      mon001.yaml loaded (20 top-level keys)
[ OK ] sealed_fingerprint_exists         sealed hash = e4c070673568c52d...
[ OK ] fingerprint_matches_seal          production baseline unchanged
[ OK ] envelope_byte_identical           envelope hash = e4ca8ecb97914f48...
[ OK ] ledger_integrity                  chain intact, 150 rows
[ OK ] no_duplicate_recs                 no duplicate rec_id
[ OK ] broker_paper_only                 PAPER_ONLY (read-only enforcement holds)
[ OK ] cumulative_strategy_search_38     trial count unchanged at 38
[ OK ] production_constants              HOLD=63 and rebal=63 unchanged
worst severity: INFO  exit code: 0
```

Fingerprint verification:

```
sealed:  e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf
current: e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf
MATCH:   True
```

Governance regression:

```
14 suites, 296 tests, 100% PASS
All ENG001 invariance guards HOLD.
```

### 5.5 Files not modified (audit scope)

```
git status → no uncommitted changes to production or sealed files
             (only untracked runtime artefacts in reports/)
```

---

## 6. Files that WOULD be modified on the target run (predicted)

Once the first successful post-fix run lands, the aegis-bot commit will
touch (per current workflow YAML `git add` pattern):

| File | Cadence | Purpose |
|---|:-:|---|
| `data/.published` | Every run | IST-date marker |
| `data/aegis_today.csv` | Every run | **The canonical file — MUST appear on success** |
| `data/aegis_recommendation_db.csv` | Every run | **DB append — MUST appear** |
| `data/aegis_registry.csv` | Every run | **New REC-* rows — MUST appear** |
| `data/aegis_candidates.csv` | Every run | Full candidate scores (optional) |
| `data/raw/india/*_D1.parquet` | Every run | ~228 parquet updates |
| `india/reports/AEGIS_LATEST.xlsx` | Every run | Workbook (may appear) |

Follow-on mon001-bot commit (~10-15 min later) touches:

| File | Purpose |
|---|---|
| `india/monitoring/MON001_Forward_Validation/reports/dashboard_2026-07-17.md` | Daily dashboard |
| `india/monitoring/MON001_Forward_Validation/reports/mon001_diagnostics_2026-07-17.json` | Diagnostics |
| `india/monitoring/MON001_Forward_Validation/reports/mon001_report_2026-07-17.md` | Report |
| `india/monitoring/MON001_Forward_Validation/ledger/forward_ledger.jsonl` | 1-2 new rows |
| `india/monitoring/MON001_Forward_Validation/reports/.mon001_published` | IST-date marker |
| `india/monitoring/MON001_Forward_Validation/reports/mon001_alerts.jsonl` | Alert record (if any) |

---

## 7. Final certification

### Did today's production run complete successfully?

# ⏳ NOT APPLICABLE — target run has not occurred

**Exact failed stage:** N/A — no stage has executed.

**Root cause:** the cron slot at 16:15 IST has not fired yet. Time of
audit was 11:13 IST, 5 hours 2 minutes before the primary slot.

**This is not a defect in OPS001-F or OPS001-I.** Both code fixes are
in place and locally verified. The audit target simply lies in the
future at the time of audit execution.

### Certification decision

**AEGIS Production Pipeline status: 🟡 CODE-READY, AWAITING FIRST LIVE PROOF**

- Code-level readiness: ✅ verified (296/296 tests, MON001 health green, freshcheck live-blocks stale)
- Production run: ⏳ not yet executed
- Certification: **DEFERRED until first successful post-fix aegis-bot commit**

### Auto-upgrade criteria (all 7 must hold on the target run)

The audit will re-execute against the target run when it lands. Certification
upgrades to **✅ OPERATIONAL** when ALL of the following are verified:

1. ⏳ Aegis-bot commit exists on `origin/main` dated 2026-07-17
2. ⏳ That commit's diff INCLUDES `data/aegis_today.csv`, `data/aegis_recommendation_db.csv`, `data/aegis_registry.csv`
3. ⏳ `data/aegis_today.csv` first-row `Generated` field ∈ {2026-07-17, 2026-07-16}
4. ⏳ Telegram delivered with header `Market asof YYYY-MM-DD` matching #3
5. ⏳ Integrity footer complete (run UTC/IST + market asof + MON001 fp + cert + trials + report SHA)
6. ⏳ MON001 fingerprint `e4c070673568c52d…` unchanged post-run
7. ⏳ No sealed / LAB file modified in the aegis-bot commit

### Auto-downgrade criteria

If the target run fires but ANY of the following:
- Freshcheck fails (workflow aborts before Telegram) — could be Friday yfinance latency; wait for backup
- Generator raises a NEW exception (not `resample("Q")` — already fixed) — escalate to OPS001-N diagnostics
- Telegram sends but message asof does not match today or yesterday — escalate to OPS001-P
- MON001 reports HALT — STOP DAEMON immediately, do not restart

---

## 8. Recommended next actions

### For the operator RIGHT NOW (in decreasing order of preference)

**A) WAIT. Let the 16:15 IST cron fire naturally.**
Zero effort. Highest confidence. Certification result available by 18:30 IST at latest.

**B) Trigger `workflow_dispatch` immediately.**
Go to [github.com/praveen330/NexaQuant/actions/workflows/aegis-daily.yml](https://github.com/praveen330/NexaQuant/actions/workflows/aegis-daily.yml) → "Run workflow" → main → click.
Result in 4-8 minutes.
**Risk:** If yfinance doesn't yet have 07-17 close (~50/50 at 11:13 IST), freshcheck aborts. That's diagnostic, not damaging.

**C) Do nothing and pick this up on Monday.**
If today is a heavy day and you want to defer. Weekend brings NO new cron activity. Monday 16:15 IST fires against 2026-07-20 data.

### Once the target run lands

Re-run this audit template. Populate every ⏳ row with observed evidence.
Emit either ✅ CERTIFIED or ❌ FAILED with the specific failing stage
identified.

### DO NOT

- ❌ Modify any code today. The fixes are already in.
- ❌ Trigger any workflow that isn't `aegis-daily.yml` or `mon001-daily.yml`.
- ❌ Start OPS002, LAB011, MON002 until the target run certifies.
- ❌ Interpret the sender freshcheck refusing today's local preview as a bug — that is exactly the OPS001-F guard doing its job.

---

## 9. Audit sign-off

**Audit conclusion:** Deferred — no target run exists yet. Documentation
of the READINESS state (code-ready, monitoring green, guards holding)
is complete. Documentation of the RUN state is pending its occurrence.

**No code modified. No workflow modified. No fix implemented. No
optimization. No research.**

MON001 fingerprint at audit time: `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf`
`cumulative_strategy_search`: 38
HOLD = 63, rebal = 63, sector_cap = 2, name_cap = 0.30, method = hrp

Signed:
- Principal Production Engineer
- Release Auditor
- QA Lead
- Site Reliability Engineer

*Awaiting the first aegis-bot commit of 2026-07-17 to re-execute stages 1-7.*
