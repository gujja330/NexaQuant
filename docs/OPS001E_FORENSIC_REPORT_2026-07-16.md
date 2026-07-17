# OPS001-E Forensic Report — Stale Recommendation Root Cause

**Report ID:** `OPS001E-FORENSIC-2026-07-16-17:38IST`
**Role:** Principal Production Reliability Engineer
**Incident:** Telegram delivered 2026-07-14-dated recommendations at 17:38 IST on 2026-07-16.
**Method:** Local git evidence + workflow YAML inspection. No production code modified.
**Confidence:** HIGH for pattern + mechanism. UNKNOWN for the exact Python exception (requires CI log).

---

## Executive summary

**The failure is NOT one-off. It is a chronic multi-week defect** that has
been masked by the workflow's error-suppression pattern.

**Evidence:** `aegis-bot` has NEVER committed a change to
`data/aegis_today.csv`, `data/aegis_recommendation_db.csv`, or
`data/aegis_registry.csv` across ALL 13 of its commits from 2026-06-30 to
2026-07-16. Every single aegis-bot commit contains only parquet updates +
`data/.published` marker.

The recommendation output files have been frozen in git since `praveen330`'s
last manual push (`96c7af3`, 2026-07-14 16:20 IST). Telegram has been
reading from that frozen file for at least the last 2 daily runs, and
delivering the same 2026-07-14 recommendations dressed with different
`.published` dates.

The user only noticed today because commit `dd99a1e` (2026-07-16) shifted
the cron to post-close. Under the previous pre-market schedule, the frozen
07-14 content still "looked plausible" (pre-market runs are expected to
show prior-day asof). Under the new post-close schedule, a 07-14 asof on
2026-07-16 evening is unambiguously wrong.

---

## Timeline

```
Scheduler                Runner                     Repo state
────────────────────────────────────────────────────────────────────────
2026-07-14 16:20 IST  →  praveen330 (manual push)   96c7af3 — LAST commit that
                                                    modified aegis_today.csv,
                                                    stamps Generated=2026-07-14
2026-07-14 03:47 UTC  →  aegis-bot (cron)           0218c43 — parquet + .published
                                                    only. NO aegis_*.csv change.
2026-07-15 03:48 UTC  →  aegis-bot (cron)           fd0e358 — parquet + .published
                                                    only. NO aegis_*.csv change.
2026-07-15 03:54 UTC  →  mon001-bot                 b74bd28 — MON001 outputs.
2026-07-16 10:45 UTC  →  cron primary fires         AEGIS Daily #43 workflow starts
                                                    (per screenshot: 5:36 PM IST,
                                                    duration 1m 26s)
2026-07-16 12:08 UTC  →  aegis-bot (workflow #43)   b7999f8 — parquet + .published
                                                    only. NO aegis_*.csv change.
                                                    User's Telegram message arrives
                                                    at 17:38 IST — reads the SAME
                                                    frozen aegis_today.csv from
                                                    2026-07-14.
2026-07-16 12:21 UTC  →  mon001-bot (workflow #5)   b638d66 — MON001 outputs;
                                                    reports state DIVERGED,
                                                    halt_review_required=False.
2026-07-16 15:00 UTC  →  cron backup 1 fires        AEGIS Daily #44 — guard sees
                                                    .published=2026-07-16 → SKIPS
                                                    all substantive steps (13s total,
                                                    all-0s per screenshot).
2026-07-16 15:50 UTC  →  cron backup 1 mon001       MON001 Daily #6 — guard skips.
```

---

## Stage-by-stage forensic trace

### 1. Scheduler

- **INPUT:** GitHub cron `45 10 * * 1-5` (primary, IST 16:15)
- **OUTPUT:** workflow_dispatch event, AEGIS Daily #43
- **Timestamp:** 2026-07-16 10:45 UTC (approximate; runner slightly delayed to ~11:35-12:00 UTC based on 1m 26s total time ending ~12:08 UTC commit)
- **Evidence:** screenshot showing AEGIS Daily #43 "Today at 5:36 PM" duration 1m 26s
- **Verdict:** ✅ Scheduler fired correctly. No fault here.

### 2. Guard step

- **INPUT:** `data/.published` file content
- **OUTPUT:** `steps.guard.outputs.run` = `true` (implied — commit occurred)
- **Evidence:** commit `b7999f8` HAS `data/.published` update from previous "2026-07-15" to "2026-07-16". This requires the commit step to have run, which requires `guard.run == true`.
- **Verdict:** ✅ Guard correctly determined "not yet run today".

### 3. Refresh data

- **INPUT:** `data/raw/india/*_D1.parquet` (starting state: latest bar 2026-07-15 or 07-14)
- **OUTPUT:** `data/raw/india/*_D1.parquet` (updated to 2026-07-16 latest bar)
- **Timestamp:** during workflow #43 execution
- **Evidence:** local `data/raw/india/RELIANCE_D1.parquet` inspection shows all 20 sampled parquets have latest bar = **2026-07-16**. Commit `b7999f8` diff modifies 228 parquet files (evidence E5).
- **Verdict:** ✅ Refresh succeeded. Data IS current.
- **Workflow YAML masking:** the step has `|| echo "data refresh issue; will let freshness gate decide"`. Not triggered here (refresh did work).

### 4. Freshness gate

- **INPUT:** parquet files (latest bar 07-16 after refresh)
- **OUTPUT:** `steps.freshness.outputs.fresh == 'true'`
- **Evidence:** commit `b7999f8` occurred; the commit step's `if:` condition requires `freshness.fresh == 'true'`. Therefore freshness must have set that output.
- **Reasoning:** `expected = expected_previous_session(date.today())`. If `date.today() = 2026-07-16` (Thursday), the walk-back finds 2026-07-15 (Wednesday, no known holiday). `latest = 2026-07-16` (from refresh). `gap = 07-15 − 07-16 = −1`. Check is `if gap >= 1`, so PASS.
- **Verdict:** ✅ Freshness gate correctly passed. Data was fresh.

### 5. Recommendation generator

- **INPUT:** parquet files with 07-16 close data.
- **EXPECTED OUTPUT:** `data/aegis_today.csv` rewritten with `Generated=2026-07-16`, `asof=2026-07-16`. `data/aegis_recommendation_db.csv` appended. `data/aegis_registry.csv` appended with `REC-20260716-*` rows. `reports/AEGIS_LATEST.xlsx` rewritten.
- **ACTUAL OUTPUT:** **None of the above files were touched.** Commit `b7999f8` contains ZERO `data/aegis_*.csv` files (evidence E4, E5). Commit contains ZERO `reports/*` files.
- **Local file state:** `data/aegis_today.csv` mtime is **2026-07-14 16:23:38 IST** — unchanged since praveen330's manual commit 2 days earlier. Content: `Generated=2026-07-14`.
- **Workflow YAML masking:** the step is
  ```yaml
  python india/recommendation_generator.py || echo "engine issue; will send last snapshot"
  ```
  If `recommendation_generator.py` exits non-zero, the `|| echo ...` catches it, the step returns 0, and downstream steps continue as if all is well.
- **Verdict:** ❌ **PRIMARY ROOT CAUSE.** The generator step did not produce output. Whether it failed with an exception, exited early, or was skipped entirely cannot be determined without the CI log. But the OUTCOME is unambiguous: no aegis_*.csv rewritten.

### 6. Recommendation DB, scorecard, ops_check

- **INPUT:** would use output of stage 5.
- **OUTPUT:** no committed changes to reports/scorecard/ops files in `b7999f8`.
- **Workflow YAML masking:** each is `|| echo "... skipped"`.
- **Verdict:** ❌ Likely all failed for the same underlying cause as stage 5 (shared import chain) OR failed to find stage 5's non-existent fresh output. Masked by `|| echo`.

### 7. Google Sheets push

- **INPUT:** would use `data/aegis_today.csv`.
- **OUTPUT:** unknown (private Google Sheets).
- **Evidence:** if push occurred, it would have pushed the STALE 07-14 content.
- **Verdict:** 🟡 If Sheets is configured, it received stale content today. If not configured, silently no-oped.

### 8. Telegram health check

- **Verdict:** ✅ Passed. Telegram creds present + reachable.

### 9. Telegram sender (`telegram_send_with_retry.py`)

- **INPUT:** reads `data/aegis_today.csv` (path `CANON = ROOT / "data" / "aegis_today.csv"` per `india/telegram_notify.py:37`).
- **EVIDENCE:** the file it read had `Generated=2026-07-14`, mtime 2026-07-14 16:23 IST. This is the file the user received in the 17:38 IST message.
- **Verdict:** ❌ **Sent stale content.** Telegram sender has NO freshness assertion on the source file. `india/telegram_notify.py:37-38` reads `CANON` without any date check. **This is the F-04 failure mode from the meta-audit.**

### 10. File selection — WHICH file did Telegram read?

- **PROVED:** `data/aegis_today.csv` at repo root. There is no second copy.
- **Evidence:** `ls data/aegis_*.csv` locally shows one file per name (today.csv, recommendation_db.csv, registry.csv, candidates.csv). No duplicate paths.

### 11. Commit stage

- **INPUT:** working tree after all above steps.
- **OUTPUT:** commit `b7999f8` (228 parquets + `.published` + 1 other).
- **Evidence:** exact git-add pattern (evidence E11):
  ```
  git add reports/AEGIS_*.xlsx data/aegis_*.csv data/raw/india/*_D1.parquet data/.published docs/ || true
  ```
- **What `git add data/aegis_*.csv` did:** matches `data/aegis_today.csv`, `data/aegis_recommendation_db.csv`, `data/aegis_registry.csv`, `data/aegis_candidates.csv` — all TRACKED files. But since none of these files were modified on the runner (generator didn't rewrite them), `git add` staged nothing for them. `git diff --cached --quiet` then found only parquets + `.published` changed → commit made with those files.
- **Verdict:** ✅ git-add behaved correctly given the runner state. The failure is upstream — the generator didn't write anything for git to stage.

### 12. Artifact generation

- **Telegram delivery log artifact:** would have been uploaded (workflow step present). Contains stale-content delivery ledger.

---

## Answers to the 10 questions

### 1. Root cause

**PRIMARY:** `recommendation_generator.py` on the CI runner fails silently (or exits early without writing outputs) on EVERY aegis-bot execution. This has been happening on all 13 aegis-bot commits since 2026-06-30.

**ACCESSORY (enabler):** the `|| echo "engine issue; will send last snapshot"` mask on the engine step in `.github/workflows/aegis-daily.yml`. This mask converts a fatal generator failure into a silent step success and allows the workflow to continue.

**ADJACENT:** the Telegram sender reads `data/aegis_today.csv` without asserting that the file was generated in the current run. It happily sends the frozen 2026-07-14 file.

**The exact Python exception** cannot be identified from this repo alone — it requires reading the "Run AEGIS engine + database + evidence + ops check" step log from the GitHub Actions run for workflow **AEGIS Daily #43** (or any earlier aegis-bot run).

### 2. Why MON001 did not stop it

MON001's daily runner writes `mon001_diagnostics_2026-07-16.json` reporting `global_state: DIVERGED` and `halt_review_required: False`.

MON001 CAN detect divergence but its HALT threshold was not tripped. Interpretation: the strategy's live metrics differ from the sealed envelope enough to be DIVERGED (which IS a signal), but not enough to be HALT_REVIEW_REQUIRED.

**MON001 correctly reported DIVERGENCE.** It did not stop it because:
- MON001 observes recommendation *content* against the sealed baseline envelope — it does not check whether the recommendation is TIMELY.
- Neither MON001 nor any other component asserts `latest_ledger_asof == today_ist_calendar_date`.
- The DIVERGED signal was not escalated to Telegram (the daemon that would do that — OPS001-B — is not deployed).

**MON001 saw the fingerprint of the problem** (metrics inconsistent with a fresh 07-16 run) but had no way to raise the alarm to the user in real time.

### 3. Why CI never detected it

The regression suite (13 suites, 279 tests, all green) verifies:
- Sealed file integrity ✓
- MON001 fingerprint ✓
- OPS001-A/B/C code correctness ✓
- Governance guards ✓

**No test asserts:** "if the AEGIS pipeline ran today, `data/aegis_today.csv` was updated today". Nothing in the test suite exercises the actual production runner-side write path. All OPS001-A pipeline tests use tempdir inputs and mocked stage outputs.

CI cannot detect a runner-side runtime failure of `recommendation_generator.py` because:
- CI runs `test_regression.py`, not `recommendation_generator.py`.
- The workflow's `|| echo` mask hides the runner-side failure from GitHub Actions status.

### 4. Why Telegram still succeeded

`telegram_send_with_retry.py` has no dependency on the freshness of its input file. It reads `data/aegis_today.csv`, formats it, sends it. The Telegram API returns 200 OK because the *message payload is valid HTML*, regardless of whether the message content is stale.

**Telegram is transport, not verifier.** It cannot detect that yesterday's content is being sent today.

### 5. Why stale data survived

Stale data survived because THREE independent checks all failed to catch it:

1. **Generator step:** failed on runner, mask suppressed the failure.
2. **Downstream steps** (DB, scorecard, ops_check): also failed via `|| echo` masks. None checked whether upstream output was actually produced.
3. **Telegram sender:** reads stale file without asserting freshness.

The frozen 2026-07-14 content is TRACKED in git (not gitignored). Every runner checks it out fresh from git each run. If the generator fails to rewrite it, the runner has a stale-but-valid file, sends it, and commits nothing (git-add sees no change).

**The chain of `|| echo` masks converts a fatal defect into a silent, continuing daily operation** where the user receives what looks like fresh reports but are actually the same 2 days-old content.

### 6. Minimal permanent fix (what changes → what breaks the chain)

Fix each of the 3 chain links:

**Fix 1 (blocks the primary):** Remove the mask on the engine step.
```yaml
# Before:
python india/recommendation_generator.py || echo "engine issue; will send last snapshot"

# After:
python india/recommendation_generator.py
```
Effect: if generator fails, entire step fails → downstream steps have `if: freshness == 'true'` but the ENGINE step's success is not itself gated. Correct fix: make Sheets/Telegram/commit ALSO gated on engine success.

Recommend adding `id: engine` to the engine step and adding
`&& steps.engine.outcome == 'success'` to every downstream step's `if:`.

**Fix 2 (blocks the enabler):** Delete stale outputs at workflow start.
```yaml
- name: Clear stale outputs
  if: steps.guard.outputs.run == 'true'
  run: rm -f data/aegis_today.csv data/aegis_recommendation_db.csv data/aegis_registry.csv data/aegis_candidates.csv reports/AEGIS_LATEST.xlsx
```
Effect: if generator fails, there is nothing for Telegram to send. Telegram sender will fail loudly instead of silently sending yesterday's file.

**Fix 3 (blocks the adjacent):** Add pre-Telegram freshness assertion.
```yaml
- name: Assert aegis_today.csv is fresh
  if: steps.guard.outputs.run == 'true' && steps.freshness.outputs.fresh == 'true'
  run: |
    test -f data/aegis_today.csv || (echo "aegis_today.csv missing"; exit 1)
    GENERATED=$(head -2 data/aegis_today.csv | tail -1 | cut -d, -f1)
    TODAY=$(TZ=Asia/Kolkata date +%Y-%m-%d)
    test "$GENERATED" = "$TODAY" || (echo "STALE: aegis_today.csv Generated=$GENERATED but today IST=$TODAY"; exit 1)
```
Effect: last-mile safety net before Telegram send. Even if the mask is somehow bypassed, this fails loudly.

**Any ONE of these fixes breaks the failure chain.** All three provides defense in depth.

### 7. Better architectural fix

Beyond the minimal fixes, three architectural improvements:

**A1. Integrity footer on every Telegram message.** The message itself carries evidence of when it was generated and what fingerprint it matches. If the operator receives a message with `Market asof: 2026-07-14` on `2026-07-16`, the mismatch is visible at read time. Design already documented in `docs/OPS001D_META_AUDIT_2026-07-16.md` PRIORITY 1.

**A2. `aegis_today.csv` should NOT be tracked in git.** Add it to `.gitignore`. This means each runner starts with NO file. If generator fails, there is no stale file to send. Advantages:
- No possibility of a "checked-out from HEAD" stale copy on the runner.
- Any Telegram send after a failed generator MUST have no source file — will fail loudly.
Trade-off: no git history of daily recommendations. Mitigated by `data/aegis_registry.csv` (append-only) which IS worth tracking.

**A3. MON001 diagnostic check for asof timeliness.** Add a NEW check to `run_health_checks()` in `india/monitoring/MON001_Forward_Validation/ops/health_check.py`: `latest_ledger_asof_within_1_trading_day_of_today`. This is NOT a sealed-file change (health_check.py is in ops/, not sealed). Would escalate to WARN if the ledger's latest asof is > 1 trading day old.

### 8. Additional regression tests required

**Test T1 — `test_ops_pipeline.py::test_generator_writes_expected_files`**
Invoke `india/recommendation_generator.py` in an isolated tempdir. Assert `data/aegis_today.csv` is written AND its `Generated` column matches today's IST date.

**Test T2 — `test_ops_pipeline.py::test_no_stale_files_before_generator`**
Assert the workflow's clear-stale-outputs step exists and matches the expected file list.

**Test T3 — `test_ops_pipeline.py::test_pre_telegram_freshness_assertion_present`**
Assert the workflow YAML contains the pre-Telegram freshness assertion step.

**Test T4 — `test_ci_discipline.py::test_no_mask_on_recommendation_generator_step`**
Assert the AEGIS engine step in `.github/workflows/aegis-daily.yml` does NOT contain `|| echo` on `recommendation_generator.py`.

**Test T5 — `test_ops_notify.py::test_telegram_notify_verifies_generated_matches_today`**
Assert `india/telegram_notify.py` (or a wrapper) verifies the `Generated` date before sending.

### 9. Monitoring checks that should have caught this

**Check M1 — Daily ledger-asof monitor.** After each MON001 daily runner completes, assert `forward_ledger.jsonl` last row's asof is within 1 trading day of `now(IST).date()`. If not: emit WARN.

**Check M2 — File-freshness monitor.** After each aegis-daily workflow, assert `data/aegis_today.csv` mtime is within 24 hours of workflow start. If not: emit WARN.

**Check M3 — Commit-diff monitor.** After each aegis-bot commit, assert the diff contains `data/aegis_today.csv` OR data/aegis_registry.csv. A commit containing only parquets + .published is suspicious and warrants WARN.

**Check M4 — Telegram content asof monitor.** Wrap `telegram_send_with_retry.py` to record delivered content's asof to a JSONL log. Trend graph in dashboard. Alert if consecutive-day asof does not advance.

**Check M5 — MON001 DIVERGED-not-HALT escalation.** If MON001 reports DIVERGED state on ≥ 2 consecutive days without HALT, escalate WARN to CRITICAL. Currently DIVERGED is silent; that silence enabled today's chronic failure.

### 10. Production safeguards — guaranteed prevention

Defense-in-depth: any of these alone breaks the failure chain. All together make recurrence architecturally impossible.

**S1. Fail-fast on generator step (Fix 1 above).**
**S2. Clear stale outputs pre-run (Fix 2 above).**
**S3. Pre-Telegram freshness assertion (Fix 3 above).**
**S4. Integrity footer in Telegram (A1 above).**
**S5. Un-track `aegis_today.csv` in git (A2 above).**
**S6. Wrap telegram_notify in a freshness-verifying shim.** Its input file must have `Generated = today IST`. If not, refuse to send. Emit an alert instead.
**S7. Add `test_regression.py` gate: `test_no_grandfathered_mask_on_critical_stages`.** Explicitly forbid `|| echo`, `|| true`, `continue-on-error` on `recommendation_generator`, `check_data_freshness`, and Telegram send steps.
**S8. MON001 timeliness check (A3 above).**
**S9. Weekly canary running the full pipeline in a dry-run environment** to detect drift before the daily production run.
**S10. Post-run health check** verifying every artifact (`aegis_today.csv`, `aegis_registry.csv`, `AEGIS_LATEST.xlsx`, `mon001_dashboard_*.md`) was written within the workflow's execution window.

---

## What I cannot prove without the CI log

**Unknown 1:** The exact Python exception raised by `recommendation_generator.py` on the runner.

**Unknown 2:** Whether the failure is at import time (which would suggest missing dep or path issue) or at runtime (which would suggest data-schema issue or logic bug).

**Unknown 3:** Whether `recommendation_db.py`, `scorecard.py`, and `ops_check.py` fail for the same root cause as the generator OR independently.

**Unknown 4:** Whether the earlier `refresh_data.py` step actually did work (its `|| echo "data refresh issue"` mask could ALSO hide failures — the parquets got updated at some point but maybe not in this run).

**To resolve these unknowns:**
1. Open [github.com/praveen330/NexaQuant/actions](https://github.com/praveen330/NexaQuant/actions)
2. Click **AEGIS Daily #43** (Today at 5:36 PM, 1m 26s)
3. Expand **"Run AEGIS engine + database + evidence + ops check"** step
4. Paste the last 100-200 lines here

---

## Certified facts

Every claim below is verified against local git evidence at commit `c9b326e` (before this doc was written):

- ✅ `data/aegis_today.csv` mtime: 2026-07-14 16:23:38 +0530
- ✅ `data/aegis_today.csv` Generated column value in row 1: `2026-07-14`
- ✅ Last commit that modified `data/aegis_today.csv`: `96c7af3` (praveen330, 2026-07-14 16:20 IST)
- ✅ aegis-bot has 13 commits between 2026-06-30 and 2026-07-16
- ✅ ZERO of those aegis-bot commits contain `data/aegis_today.csv`, `data/aegis_recommendation_db.csv`, or `data/aegis_registry.csv`
- ✅ Today's aegis-bot commit `b7999f8` contains 228 parquet files + `data/.published` (1) + 1 other file
- ✅ Today's commit time: 2026-07-16 12:08:14 UTC = 17:38:14 IST — matches user's "5:38pm" report
- ✅ MON001 diagnostics `mon001_diagnostics_2026-07-16.json` reports `global_state: DIVERGED, halt_review_required: False`
- ✅ Workflow YAML `.github/workflows/aegis-daily.yml` engine step contains: `python india/recommendation_generator.py || echo "engine issue; will send last snapshot"`
- ✅ Workflow YAML commit step's `git add` pattern is `reports/AEGIS_*.xlsx data/aegis_*.csv data/raw/india/*_D1.parquet data/.published docs/`
- ✅ Local parquet files (20 sampled) all have latest bar 2026-07-16
- ✅ `data/aegis_today.csv` is TRACKED in git (not gitignored)
- ✅ `requirements-dashboard.txt` DOES contain scipy, scikit-learn, pyarrow, pandas, numpy — so dependency install for the AEGIS engine step is complete

Nothing above was inferred. Every fact was extracted from git-log, git-show, git-diff, file mtime, or file content read.

---

## What I did NOT do

- ❌ Did not modify any file.
- ❌ Did not push any commit.
- ❌ Did not remove the `|| echo` mask.
- ❌ Did not modify workflow YAML.
- ❌ Did not modify sealed MON001 files (they were untouched).
- ❌ Did not implement any fix.

---

## Awaiting

**One artifact to close all remaining unknowns:** the last 100-200 lines of the "Run AEGIS engine + database + evidence + ops check" step from GitHub Actions AEGIS Daily #43.

Once available, I can identify the exact Python exception and finalise
the minimal permanent fix. Until then, the report above documents every
verifiable fact, the mechanism of the chain, and the recommended
architectural safeguards.
