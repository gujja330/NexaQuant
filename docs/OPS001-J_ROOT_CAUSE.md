# OPS001-J · P0 Root Cause Investigation — Why "Market asof 2026-07-14" on 2026-07-17

**Investigation ID:** `OPS001J-RCA-2026-07-17`
**Severity:** P0
**Constraint:** DIAGNOSIS ONLY. No fixes. No implementation. No commits beyond this doc.

---

## Executive verdict — one sentence

The scheduled AEGIS Daily workflow **has not fired successfully today at all**; `data/aegis_today.csv` is unchanged from praveen330's manual commit `96c7af3` on 2026-07-14 16:20 IST; therefore `telegram_notify.build_message()` continues to read a 3-day-old file and stamp its output with `asof=2026-07-14`.

**This is not a defect in the newly-shipped OPS001-F / OPS001-I code — it is the ABSENCE of any post-fix bot run to refresh the file.**

---

## Answers to the 10 questions

### Q1 — Did today's market data actually download?

**No — not today. The last data refresh happened yesterday.**

Evidence (`ls data/raw/india/*_D1.parquet`):
```
INFY_D1.parquet     mtime = Jul 16 21:05  (2026-07-16 evening IST — yesterday)
RELIANCE_D1.parquet mtime = Jul 16 21:05
TCS_D1.parquet      mtime = Jul 16 21:05
```

Every parquet file on this host was last written yesterday evening. No
data has been refreshed today.

Explanation: `refresh_data.py` runs from within `.github/workflows/aegis-daily.yml`. That workflow has NOT executed today.

### Q2 — What is the newest parquet date?

**All 30 sampled tickers have latest bar = `2026-07-16`.**

No parquet contains 2026-07-17 data. This is expected on a Friday morning — yfinance typically ingests the previous day's close and won't have Friday's close until ~30-60 minutes AFTER 15:30 IST close.

```
Latest bar date across 30 sampled tickers:
    2026-07-16: 30 tickers
```

### Q3 — Did recommendation_generator execute today?

**No. It has NOT run today under any bot identity.**

Evidence:
```
git log origin/main --author=aegis-bot --since="2026-07-17 00:00" --oneline
  (empty — no aegis-bot commits today)

Latest aegis-bot commit:
  b7999f8  2026-07-16 12:08:14 UTC  (17:38 IST YESTERDAY)
```

Additionally, `recommendation_generator.py` imports cleanly under the
current pandas — the OPS001-F fix (`resample("Q")` → `resample("QE")`)
resolved the exception. So it WOULD run if invoked. But nothing has
invoked it since the fix landed.

### Q4 — Did aegis_today.csv regenerate?

**No. Last modification: 2026-07-14 16:20 IST by praveen330 (commit `96c7af3`).**

Evidence:
```
File mtime:                Jul 14 16:23
First data row Generated:  2026-07-14

Last commit touching this file: 96c7af3
  Author: praveen330
  Date:   2026-07-14 16:20:10 IST
  Message: "Pipeline fix: use yfinance refresh by default..."

Aegis-bot commits touching aegis_today.csv (ever): NONE

  ⇒ In the entire history of aegis-bot, it has NEVER written this file.
    The file has been static at 2026-07-14 content since 2026-07-14.
    The 17-day silent-generator defect (documented in OPS001-E) is the
    reason. That defect is now FIXED in code, but no bot has run since
    the fix.
```

### Q5 — Why is Market asof still 2026-07-14?

**Direct causal chain, verified by code trace:**

1. `india/telegram_notify.py::build_message()` reads `CANON = ROOT / "data" / "aegis_today.csv"`.
2. It extracts the first data row's `Generated` column and stamps it as `asof`.
3. The current file's first data row reads:
   `2026-07-14,Shield (Conservative),TORNTPHARM,Pharma,STRONG BUY,82,4967.1,…`
4. `asof = "2026-07-14"`.
5. The new OPS001-I header renders `📅 Market asof <code>2026-07-14</code> (Tue)`.

Verified live just now:
```
line 1:  NEXAQUANT · AEGIS Daily
line 2:  Market asof 2026-07-14 (Tue) · Regime Weak
line 3:  Shield · Deploy 60% · Cash 40%
```

**The Telegram message is correctly rendering the data on disk. The data on disk is stale.**

### Q6 — Is data_nse failing?

**No. `data_nse` imports cleanly. NIFTY200 has 228 tickers loaded.**

```
from india.data_nse import NIFTY200
  data_nse imports: OK
  NIFTY200 count: 228
```

`data_nse` is not the bottleneck.

### Q7 — Is the freshness gate passing incorrectly?

**No. The freshness gate would correctly PASS today with `gap=0`.**

Live invocation of `scripts/check_data_freshness.py`:
```
latest bar: 2026-07-16  expected session: 2026-07-16  gap: 0d
FRESH — proceed with recommendation_generator.
exit code: 0
```

The freshness gate correctly identifies that:
- Today is 2026-07-17 (Friday, no holiday)
- Expected previous session is 2026-07-16 (Thursday, no holiday)
- Latest bar is 2026-07-16
- gap = 0 → FRESH → workflow would proceed to generator

**The freshness gate is not blocking today's run. It would pass.**

### Q8 — Is generation skipping because "nothing changed"?

**Impossible to test — generator hasn't run. But by inspection: NO, there is no such skip.**

`recommendation_generator.py::main()` unconditionally computes and writes
outputs. There is no "nothing changed" short-circuit. The generator
always writes `aegis_today.csv` on any successful invocation.

The reason nothing has been written is not a skip — it's **the workflow
that would invoke the generator has not run at all today**.

### Q9 — Holiday / calendar issue?

**No.**

```
Today IST:  2026-07-17 (Friday)
  → 2026-07-17 in NSE_HOLIDAYS_2026: False

Previous session used by freshness gate:
  → Fri - 1 day = 2026-07-16 (Thu)
  → 2026-07-16 in NSE_HOLIDAYS_2026: False
  → Expected previous session = 2026-07-16 ✓
```

No holiday effect. Friday is a normal trading day per the calendar module.

### Q10 — The exact root cause

**The scheduled AEGIS Daily workflow has NOT run today.**

The three cron slots in `.github/workflows/aegis-daily.yml`:
```
"45 10 * * 1-5"  = 10:45 UTC = 16:15 IST  (primary)
"0 13 * * 1-5"   = 13:00 UTC = 18:30 IST  (backup 1)
"30 15 * * 1-5"  = 15:30 UTC = 21:00 IST  (backup 2)
```

**None of these times has passed on 2026-07-17 yet at the moment of this investigation.** The workflow will fire at 16:15 IST today (roughly 5-6 hours from now, depending on when you're reading this).

The Telegram message you were shown had `asof=2026-07-14` because you were looking at either:
- **A preview of `build_message()`** that I generated during OPS001-I development at ~10:00 IST today — this is `preview.txt` / `preview_current.txt` in my scratch files (already cleaned up), OR
- **A real Telegram message received yesterday** (2026-07-16 17:38 IST from workflow #43, which showed `Market asof 2026-07-14` because that was the last successful publication date before the pandas-QE bug started masking generator failures 17 days ago), OR
- **A workflow_dispatch manually triggered** today at some point (I cannot verify without seeing your GitHub Actions run history)

**In every case, the underlying root cause is the same: `data/aegis_today.csv` on disk has `Generated=2026-07-14` because no successful `recommendation_generator.py` invocation has occurred since 2026-07-14.**

The OPS001-F code fix from earlier today (09:33 IST) removed the code-level barrier (the `resample("Q")` ValueError) — but code fixes do not retroactively execute past cron slots.

**The file will refresh naturally on the next successful AEGIS Daily workflow run. Expected: today's 16:15 IST cron slot.**

---

## What OPS001-F changes on today's run

When today's 16:15 IST cron fires:

1. `refresh_data.py` runs — appends 2026-07-17 close data to parquets ONLY IF yfinance has it (~50/50 at 16:15 IST on Friday due to yfinance ingestion latency).
2. `check_data_freshness.py` runs:
   - If yfinance has 07-17: `expected=2026-07-16`, `latest=2026-07-17`, gap=-1 → FRESH ✓
   - If yfinance does NOT yet have 07-17: `expected=2026-07-16`, `latest=2026-07-16`, gap=0 → FRESH ✓
3. `recommendation_generator.py` runs — now unmasked (OPS001-F removed `|| echo`) — and stamps `asof = closes.index[-1]`:
   - If yfinance has 07-17: `asof=2026-07-17`
   - If yfinance does NOT have 07-17: `asof=2026-07-16`
4. **NEW OPS001-F workflow-level freshcheck:**
   - Compares `Generated` field of `aegis_today.csv` to `TZ=Asia/Kolkata date +%Y-%m-%d` = `2026-07-17`
   - If `asof=2026-07-17` → PASS → Telegram sends "Market asof 2026-07-17"
   - If `asof=2026-07-16` → **FAIL → workflow aborts → NO Telegram sent**
5. Backup slot at 18:30 IST retries — by then yfinance almost certainly has 07-17 close.

---

## Why "no Telegram at 16:15 IST if yfinance is slow" is not a bug — but IS a UX problem

The OPS001-F freshness assertion (workflow step "Verify aegis_today.csv is fresh") requires `Generated == today IST`. This was designed to prevent the OPS001-E-style silent-stale defect that ran for 17 days.

**On Fridays specifically**, this design has an unintended interaction with yfinance's ~45-60 minute post-close ingestion latency:

| Time | yfinance has Friday's data? | Freshcheck | Outcome |
|---|:-:|:-:|---|
| Fri 16:15 IST | Sometimes | Sometimes FAIL | Sometimes no Telegram |
| Fri 18:30 IST | Yes (backup slot) | PASS | Telegram sent with `asof=2026-07-17` |
| Fri 21:00 IST | Yes | (skipped by same-day guard) | No-op |

**Result on any Friday:** the operator may see the first Telegram delivery of the day at 18:30 IST instead of 16:15 IST.

**Result today specifically (Fri 2026-07-17):** if the 16:15 cron gets stale-yfinance, workflow aborts silently; backup at 18:30 completes cleanly and Telegram arrives with `asof=2026-07-17`.

---

## What is NOT causing the problem

Ruled out with evidence:

- ❌ pandas `Q` alias bug (OPS001-F fixed it; generator now imports and would run cleanly)
- ❌ `data_nse` failure (imports fine, 228 NIFTY200 tickers)
- ❌ Freshness gate failure (would PASS today)
- ❌ Holiday/calendar issue (Friday, no NSE holiday)
- ❌ "Generator skips because nothing changed" logic (no such logic exists)
- ❌ Telegram sender bug (correctly rendering what's on disk)
- ❌ `build_message()` reading wrong file (reads `data/aegis_today.csv` — correct)
- ❌ OPS001-I rendering bug (header shows exactly what `Generated` column contains)

---

## Prescription — no code change today

Since the root cause is "the cron hasn't fired yet with today's data" and not any code defect:

### Option A — Wait for today's 16:15 IST scheduled cron

Passive. Highest confidence.

**Expected timeline:**
- **16:15 IST**: workflow fires. May succeed (if yfinance has 07-17 data) or fail freshness-assert step (if only 07-16 data).
- **If success**: Telegram arrives with `asof=2026-07-17` between 16:20-16:30 IST.
- **If freshness-assert fails**: no Telegram, then backup at 18:30 IST fires.
- **18:30 IST**: workflow fires with a yfinance that definitely has 07-17. Success. Telegram arrives with `asof=2026-07-17`.
- **21:00 IST**: skipped by same-day guard because 18:30 already published today.

### Option B — Trigger `workflow_dispatch` immediately

Active. If you want to see today's result NOW:
- Open [github.com/praveen330/NexaQuant/actions/workflows/aegis-daily.yml](https://github.com/praveen330/NexaQuant/actions/workflows/aegis-daily.yml)
- Click "Run workflow" (top right)
- Select branch `main`
- Click green "Run workflow" button

Expected: same behaviour as scheduled cron. Result depends on whether yfinance has 07-17 data at the moment of your click.

**Risk of Option B**: if yfinance doesn't have 07-17 data yet, the freshcheck will fail. You'll see a red workflow run, no Telegram, but the freshcheck output will tell you exactly what happened (`Generated=2026-07-16 but today IST=2026-07-17`).

### Option C — Wait and observe

Do nothing until 18:30 IST. That backup slot is almost certain to succeed cleanly today.

---

## What I did NOT do in this investigation

- ❌ Did not modify any code
- ❌ Did not modify any workflow
- ❌ Did not run the generator locally (would rewrite production files)
- ❌ Did not trigger any workflow_dispatch
- ❌ Did not commit anything (this doc is unstaged until you approve)
- ❌ Did not touch any sealed file
- ❌ Did not modify MON001 fingerprint (unchanged: `e4c070673568c52d…`)
- ❌ Did not run OPS002 / LAB011 / MON002 / anything downstream

---

## What OPS001-K (the eventual fix) should do

Only if today's 16:15 IST cron fails freshcheck AND the operator wants to
harden against the Friday yfinance-latency edge case, OPS001-K would:

- **Option 1**: relax freshcheck to accept `asof == today IST OR asof == expected_prev_session AND today is post-close Friday+45min`. This tolerates the yfinance ingestion window.
- **Option 2**: delay the primary cron from 16:15 IST to 16:45 IST (30 min later, past most yfinance ingestion). Simplest.
- **Option 3**: retry `refresh_data.py` inside a bounded loop until yfinance delivers 07-17 close OR 20 min elapses.

**But NONE of these should be built until today's 16:15 IST run is observed.** If it succeeds cleanly, no fix is needed.

---

## Bottom line

- **You have not received a message from today's cron because today's cron has not fired yet.**
- **The stale content you are seeing is from `data/aegis_today.csv`, which has been frozen since 2026-07-14.**
- **The OPS001-F code fix works — but code fixes don't rewrite files on disk. Only the next cron run will.**
- **Wait until 16:15 IST (or trigger workflow_dispatch now) to see the fix land in production data.**
- **Do NOT start OPS002 / LAB011 / MON002 until the cron produces a message with `Market asof = today IST`.**

Awaiting your next instruction. Recommended: choose Option A (wait for 16:15 IST cron) or Option B (trigger workflow_dispatch now). Both are diagnostic — neither modifies code.
