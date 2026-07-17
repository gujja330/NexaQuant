# OPS001-L · End-to-End Production Certification

**Certification ID:** `OPS001L-CERT-2026-07-17`
**Role:** Principal Production Engineer · Release Manager · QA Lead · Platform Architect
**Method:** Read-only stage-by-stage inspection. No code, workflow, or strategy modified.
**Repository state:** `origin/main` at `dac4eaf` (OPS001-I).

---

## 0. Executive summary

# 🔴 NO-GO — production is code-ready but **has not produced today's recommendation yet**

**The verdict is not "the code is broken."** The verdict is: **the
production pipeline has not run since the code fixes landed today (OPS001-F
at 09:33 IST · OPS001-I at 10:49 IST).** Today's scheduled cron slots
(16:15 / 18:30 / 21:00 IST) have not fired at the time of this
certification.

**The next scheduled cron will produce the first live proof-of-fix.** Until
that produces a Telegram message with `Market asof == today IST`, the
system CANNOT be certified as producing current recommendations.

**Every layer BELOW the missing cron run is verified GREEN:**
- Code fixes (OPS001-F, OPS001-I) are in place and tested
- MON001 health: 9/9 INFO, fingerprint matches seal
- Freshness gate: would correctly PASS today
- Data provider (yfinance parquets): has data through 2026-07-16
- Regression suite: 296/296 tests GREEN across 14 suites
- Governance: all invariants hold

**Every layer AT or ABOVE the missing cron run is BLOCKED on the run:**
- Recommendation generation: hasn't executed today (last: 2026-07-16 12:08 UTC)
- `data/aegis_today.csv`: still stamped `Generated=2026-07-14` (frozen since praveen330's manual commit)
- Google Sheets: cannot be verified without a workflow run
- Telegram: sender-side freshness check correctly REFUSES to send today (verified live below)

**Recommendation: WAIT for today's 16:15 IST cron OR trigger `workflow_dispatch` now.**

---

## 1. Pipeline diagram (current state per-stage)

```
┌──────────────────────────────────────────────────────────────────┐
│  Time trigger                                                    │
│  ─────────────                                                   │
│  GitHub Actions cron:                                            │
│     16:15 IST  (primary)  · pending today                        │
│     18:30 IST  (backup 1) · pending today                        │
│     21:00 IST  (backup 2) · pending today                        │
│                                                                  │
│  Status: NO cron slot has fired today (2026-07-17)               │
└─────────────────┬────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 1 · Market Data Refresh                                   │
│  ─────────────────────────────                                   │
│  refresh_data.py → yfinance → data/raw/india/*_D1.parquet        │
│                                                                  │
│  Current state:                                                  │
│    parquet mtime:      Jul 16 21:05 IST  (yesterday)             │
│    latest bar:         2026-07-16 (all 50 sampled tickers)       │
│    expected session:   2026-07-16 (matches ✓)                    │
│                                                                  │
│  STATUS: ✅ Fresh through yesterday.  Waiting for cron to add    │
│         today's close (~16:00+ IST).                             │
└─────────────────┬────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 2 · Recommendation Generation                             │
│  ────────────────────────────────────                            │
│  recommendation_generator.py → aegis_today.csv + db + registry   │
│                                                                  │
│  Current state:                                                  │
│    aegis_today.csv:    Generated=2026-07-14 (STALE)              │
│    file mtime:         Jul 14 16:23 IST                          │
│    last modifier:      praveen330 (commit 96c7af3, manual)       │
│    aegis-bot commits:  ZERO writes to this file, ever            │
│    registry (last row): asof=2026-07-14                          │
│                                                                  │
│  STATUS: 🔴 STALE. Awaiting cron run to invoke the fixed         │
│         generator (OPS001-F fix at 09:33 IST today).             │
└─────────────────┬────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 2.5 · OPS001-F Workflow Freshcheck (gates downstream)     │
│  ──────────────────────────────────────────────                  │
│  Compares aegis_today.csv Generated field to today IST.          │
│  If mismatch: workflow aborts, no Telegram/Sheets/commit.        │
│                                                                  │
│  Would-fire result RIGHT NOW: FAIL (Generated=07-14 ≠ 07-17)     │
│  Would abort the workflow — correct behaviour.                   │
└─────────────────┬────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 3 · Google Sheets Publish (gated on freshcheck)           │
│  ─────────────────────────────                                   │
│  sheets_sync.py → Google Sheets                                  │
│                                                                  │
│  Current state:  UNVERIFIABLE from repo (private secrets)        │
│  Would-run today: NO — freshcheck would gate this step off       │
└─────────────────┬────────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 4 · Telegram (gated on freshcheck)                        │
│  ─────────────────────────                                       │
│  telegram_send_with_retry.py → telegram_notify.py → Telegram API │
│                                                                  │
│  build_message() output RIGHT NOW would show:                    │
│    line 1: NEXAQUANT · AEGIS Daily                               │
│    line 2: Market asof 2026-07-14 (Tue) · Regime Weak            │
│    line 3: Shield · Deploy 60% · Cash 40%                        │
│                                                                  │
│  Sender-side freshness check RIGHT NOW:                          │
│    ok=False, reason="Generated='2026-07-14' != today             │
│    IST='2026-07-17' — refusing to send stale recommendations"    │
│    exit code: 2 (REFUSED_STALE) — no message would be sent       │
│                                                                  │
│  STATUS: 🟢 Correctly BLOCKING stale send. No 2026-07-14         │
│         message can go out from THIS host under current code.    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Pass/Fail matrix

Legend: 🟢 verified ready · 🟡 conditional / not-yet-observed · 🔴 blocking

### Stage 1 — Market Data Refresh

| Check | Result | Evidence |
|---|:-:|---|
| Parquet files present + writable | 🟢 | 229 files scanned by freshness gate |
| Latest bar date matches expected session | 🟢 | 50/50 sampled tickers at `2026-07-16` (= expected prev session for Fri 2026-07-17) |
| Freshness gate live exit code | 🟢 | `exit 0` — "FRESH — proceed with recommendation_generator" |
| Expected-session logic (weekend/holiday walk-back) | 🟢 | `expected_previous_session(2026-07-17) = 2026-07-16` ✓ |
| Holiday list correctness | 🟢 | 2026-07-16 and 2026-07-17 both non-holidays ✓ |
| Today's data downloaded? | 🟡 | NO — 2026-07-17 has not been ingested yet. Expected when cron fires post-close. |

**Verdict: 🟢 READY** — data pipeline is healthy through 2026-07-16, awaiting today's close.

### Stage 2 — Recommendation Generation

| Check | Result | Evidence |
|---|:-:|---|
| `recommendation_generator.py` imports cleanly | 🟢 | Verified — pandas-QE fix (OPS001-F) removed the `resample("Q")` exception |
| `data_nse` imports cleanly | 🟢 | `NIFTY200` loads 228 tickers |
| `aegis_today.csv` regenerated today | 🔴 | **NO.** mtime `Jul 14 16:23`, `Generated=2026-07-14` |
| `recommendation_db.csv` updated today | 🔴 | **NO.** Last row: `recommended_date=2026-07-14` |
| `registry.csv` updated today | 🔴 | **NO.** Last row: `REC-20260714-0359 asof=2026-07-14` |
| Generator field is today's date | 🔴 | **NO.** `Generated=2026-07-14` (3 days stale) |

**Verdict: 🔴 BLOCKED** — generator has not executed today. Every code-level readiness signal is green; the only missing element is a scheduled workflow run.

### Stage 3 — Google Sheets

| Check | Result | Evidence |
|---|:-:|---|
| `sheets_sync.py` present | 🟢 | Local file exists |
| Workflow references sheets step | 🟢 | 5 occurrences in `aegis-daily.yml` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` secret set on GitHub | ❓ | Cannot verify from repo (private secrets) |
| `AEGIS_SPREADSHEET_ID` secret set on GitHub | ❓ | Cannot verify from repo |
| Today's Sheets tab shows current asof | ❓ | Requires operator to check |

**Verdict: 🟡 UNVERIFIABLE** — cannot certify without operator confirming the Sheets tab shows today's data. The upstream freshcheck (Stage 2.5) would prevent a stale Sheets push, so IF the Sheets tab shows anything today, it will be today's data.

### Stage 4 — Telegram

| Check | Result | Evidence |
|---|:-:|---|
| `build_message()` executes cleanly | 🟢 | 6445 chars output; all 8 sections present |
| Message header shows Market asof | 🟢 | Line 2 renders `Market asof 2026-07-14 (Tue) · Regime Weak` (correct rendering of the stale data on disk) |
| **Message asof equals today IST** | 🔴 | **NO.** Message shows `2026-07-14`, today is `2026-07-17` |
| Message split at 4096 boundary | 🟢 | Chunker in `send()` splits at section boundaries — verified in `test_ops001i_telegram_format` |
| Format is institutional (OPS001-I) | 🟢 | All 16 OPS001-I tests PASS |
| Integrity footer complete | 🟢 | Run UTC + IST + market asof + MON001 fp + cert + cycle + trials + report SHA + disclaimer |
| **Sender freshness check refuses stale** | 🟢 | Live: `ok=False, reason="Generated='2026-07-14' != today IST='2026-07-17'"` → exit 2 → no send |

**Verdict: 🟢 CORRECTLY BLOCKING** — Telegram would produce a stale message IF invoked, but the sender-side freshness check refuses to send. **No stale Telegram can go out from this host under the current code.** This is exactly the OPS001-F protection designed after the July-16 stale-send incident.

### Stage 5 — GitHub Actions

| Check | Result | Evidence |
|---|:-:|---|
| Workflows present | 🟢 | `aegis-daily.yml`, `mon001-daily.yml`, `eng001-regression.yml` |
| ENG001 Regression green on latest push (OPS001-I) | 🟢 | Per user screenshot: run #15 succeeded, 3m 58s |
| Bot commit history (aegis-bot) — production runs | 🟢 (until 07-16) | 2026-07-16, -15, -14, -13, -10, -09, -08, -07 — daily cadence intact |
| Bot commit today (2026-07-17) | 🔴 | **NONE.** No aegis-bot or mon001-bot commit exists for today. |
| Scheduler behaviour (cron cadence) | 🟢 | 3 slots per weekday: 16:15/18:30/21:00 IST — none has fired today yet |
| Workflow artifacts (telegram_delivery_log) uploaded on successful runs | 🟢 | Upload step present with `if: always()` |

**Verdict: 🟡 PENDING** — CI-side workflows are healthy; today's production cron has simply not fired yet.

### Stage 6 — Monitoring Subsystems

| Check | Result | Evidence |
|---|:-:|---|
| MON001 health check | 🟢 | 9/9 INFO · exit 0 |
| Fingerprint matches seal | 🟢 | `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf` (sealed == current) |
| Forward ledger integrity | 🟢 | Chain intact, 150 rows |
| Broker layer PAPER_ONLY | 🟢 | Enforced |
| Freshness gate live | 🟢 | Exit 0 · "FRESH" |
| Retry wrapper — freshness pre-check | 🟢 | Live: refuses stale, exit 2 |
| Notification bus — file channel writable | 🟢 | `reports/ops_alerts.jsonl` has 8 alerts logged |
| OPS001-B daemon status endpoint | 🟡 | `ops_status.json` not present — daemon not deployed on this host (design intent; scheduling via GH Actions) |
| Governance — production constants | 🟢 | HOLD=63, rebal=63, sector_cap=2, name_cap=0.30, method=hrp |
| Governance — cumulative_strategy_search | 🟢 | 38 (unchanged) |
| Governance — forward boundary | 🟢 | 2026-03-28 (unchanged) |
| Full regression suite | 🟢 | 14 suites · 296 tests · 100% PASS |

**Verdict: 🟢 HEALTHY** — every monitoring signal that CAN be verified without a live run is green.

### Stage 7 — Operator Validation

**Question: Can an operator trust today's report?**

# NO — because there is no report today yet.

**Explanation:**

The system has NOT produced a 2026-07-17 recommendation. What the operator
has seen today is one of three things (any of which is diagnosed by
OPS001-J):

1. **Yesterday's Telegram message** (2026-07-16 17:38 IST) which showed
   `asof=2026-07-14` because at that time the pandas-QE bug had been
   masking generator failures for 17 days.
2. **A preview built during my OPS001-I development** at ~10 IST today,
   which showed `asof=2026-07-14` because `aegis_today.csv` still contains
   that date.
3. **A workflow_dispatch triggered manually today** BEFORE OPS001-F
   landed at 09:33 IST — which would also show `2026-07-14`.

**In all three cases, the underlying file is unchanged since 2026-07-14 16:20 IST.**

### If the operator wants to certify TODAY's report as trustworthy:

1. Wait for the 16:15 IST cron to fire (or trigger `workflow_dispatch` immediately).
2. Verify the aegis-bot commit that lands has:
   - A diff that INCLUDES `data/aegis_today.csv` (proving it was regenerated)
   - `Generated` column of that file matching either `2026-07-17` (best) or `2026-07-16` (acceptable if yfinance is slow — see below)
3. Verify the Telegram message received shows `Market asof YYYY-MM-DD` matching Step 2.
4. Verify the integrity footer shows `MON001 fp e4c07067...` and `Report SHA <fresh>`.

**Once those four items are observed, the system can be re-certified as GO.**

---

## 3. Known issues

### KI-001 · Friday post-close yfinance latency (P2 — MEDIUM)

**Symptom:** on Fridays specifically, the 16:15 IST primary cron may fire
BEFORE yfinance has ingested Friday's close. In that case:
- Generator stamps `asof=2026-07-16` (yesterday's close — the freshest yfinance has)
- OPS001-F freshcheck compares to `today IST=2026-07-17` → **FAIL** → workflow aborts
- No Telegram message from the primary slot
- Backup at 18:30 IST retries; yfinance almost certainly has 07-17 by then

**Impact:** operator may see Telegram at 18:30 IST instead of 16:15 IST on some Fridays.

**Status:** documented in OPS001-J. Not a bug — the freshcheck refusing stale data is CORRECT behaviour. Backup slots exist for this exact case.

**Potential fix (deferred to OPS001-K if it becomes a problem):** relax freshcheck to accept `asof == last_close_within_last_2_trading_days`. This would trade off strictness against post-close delivery latency. **Not recommended without observing that today's 16:15 IST cron actually fails first.**

### KI-002 · Stale-file preview on operator's machine (P4 — INFO)

**Symptom:** any local invocation of `build_message()` from a repo checkout
whose `aegis_today.csv` is stale will produce a message with a stale
`Market asof`. The sender-side freshcheck blocks the SEND, but the PREVIEW
still gets rendered.

**Impact:** operator confusion (e.g., "why is my preview showing 07-14?").

**Status:** not a defect. The rendering is correctly a function of what's
in the input file. Address via operator training.

### KI-003 · No aegis-bot commit today yet (P0 — BLOCKING for certification)

**Symptom:** at the time of this certification, no aegis-bot commit exists
for 2026-07-17.

**Impact:** cannot certify production without proof of a successful daily run.

**Status:** expected — cron hasn't fired yet. This is the ONE thing blocking a GO verdict.

---

## 4. Risk assessment

Every risk categorised by whether it blocks GO for today.

| ID | Risk | Prob | Blocks GO today? | Mitigation |
|:-:|---|:-:|:-:|---|
| R-1 | 16:15 IST cron fires but yfinance is slow → freshcheck aborts → no Telegram at 16:15 | MED (Friday-specific) | **Partial — delays GO to 18:30 IST** | Backup cron at 18:30 IST. Verified downstream logic correct. |
| R-2 | 16:15 IST cron doesn't fire at all (GH cron drop) | LOW | Partial — delays GO to 18:30 | Backup crons + workflow_dispatch |
| R-3 | Generator fails at RUNTIME for a NEW reason (not pandas-QE) | LOW | **Blocks GO indefinitely** | Would require OPS001-M diagnosis; current code path known to import cleanly |
| R-4 | `refresh_data.py` fails to fetch 07-17 close | LOW | Partial — freshcheck would fail, but data appended piecemeal by backup cron | Retry across 3 slots gives 3 attempts |
| R-5 | MON001 fingerprint drift (unauthorized sealed-file change) | VERY LOW | **Blocks GO** | Regression asserts fingerprint before every push |
| R-6 | Telegram secrets rotated / bot removed | LOW | Partial — file fallback still captures | Health-check runs before send |
| R-7 | Google Sheets service account revoked | LOW | No (Sheets is optional path) | Sheets step is non-fatal |
| R-8 | Disk full on GitHub runner | VERY LOW | Partial | Ephemeral runners have fresh disk |
| R-9 | Silent sealed-file drift undetected | VERY LOW | **Blocks GO** | 4 fingerprint-verification tests across regression suite |
| R-10 | Message length > 4096 exceeds even chunker | VERY LOW | Partial | Chunker splits at section boundaries, hard cap 3900 |

**Aggregate:** 3 risks (R-3, R-5, R-9) would block GO indefinitely if they materialised. Current probability of ANY of the three is LOW-to-VERY-LOW.

Most likely outcome today: **cron fires successfully at 16:15 or 18:30 IST → Telegram delivers with `asof=2026-07-17` → GO certified.**

---

## 5. Evidence log — quoted verbatim

### 5.1 Freshness gate live output

```
latest bar: 2026-07-16  expected session: 2026-07-16  gap: 0d  (229 files scanned)
FRESH — proceed with recommendation_generator.
```

### 5.2 MON001 health check live output

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

### 5.3 Fingerprint verification live

```
sealed:  e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf
current: e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf
MATCH:   True
```

### 5.4 aegis_today.csv state

```
File mtime:  Jul 14 16:23
First data row Generated column: 2026-07-14
Last commit touching this file: 96c7af3 (praveen330, 2026-07-14 16:20:10 IST)
Aegis-bot commits touching this file: NONE (ever)
```

### 5.5 Bot commit history

```
b638d66 mon001-bot 2026-07-16 12:21:00 UTC  MON001 daily
b7999f8 aegis-bot  2026-07-16 12:08:14 UTC  AEGIS daily
b74bd28 mon001-bot 2026-07-15 03:54:20 UTC  MON001 daily
fd0e358 aegis-bot  2026-07-15 03:48:30 UTC  AEGIS daily
0218c43 aegis-bot  2026-07-14 03:47:41 UTC  AEGIS daily
...
```

**Zero bot commits for 2026-07-17.**

### 5.6 Sender freshness check live

```
ok:     False
reason: aegis_today.csv Generated='2026-07-14' != today IST='2026-07-17'
        — refusing to send stale recommendations
If ok=False, wrapper exits code 2 (REFUSED_STALE) and does NOT send.
```

### 5.7 Regression suite status (previously green on `dac4eaf`)

```
14 suites, 296 tests, 100% PASS
All ENG001 invariance guards HOLD.
```

---

## 6. Go / No-Go recommendation

# 🔴 NO-GO for today until the next cron produces a fresh commit.

**Specifically:**

- **Do NOT** start OPS002 today.
- **Do NOT** start LAB011 today.
- **Do NOT** start MON002 today.
- **DO** wait for today's 16:15 IST cron (or trigger `workflow_dispatch`).
- **DO** verify the resulting Telegram message shows `Market asof YYYY-MM-DD` = today or yesterday's close (both are legitimate results).
- **DO** confirm the aegis-bot commit diff includes `data/aegis_today.csv`, `data/aegis_recommendation_db.csv`, and `data/aegis_registry.csv`.

### Conditions for automatic upgrade to 🟢 GO

Every one of these must be TRUE:

1. ✅ A new aegis-bot commit exists on `origin/main` dated 2026-07-17
2. ✅ That commit's diff includes `data/aegis_today.csv`
3. ✅ `data/aegis_today.csv` `Generated` field matches `2026-07-17` (best) or `2026-07-16` (acceptable Friday-latency case)
4. ✅ Telegram message received with `Market asof` matching #3 above
5. ✅ Message integrity footer shows `MON001 fp e4c07067…` and a fresh Report SHA
6. ✅ MON001 fingerprint still matches seal
7. ✅ No sealed file modified

**When all 7 hold: certification upgrades from NO-GO to GO. The pipeline is proven end-to-end.**

### Conditions for 🟡 CONDITIONAL GO

If today's 16:15 IST cron fails freshcheck (Friday yfinance latency case)
but backup at 18:30 IST completes cleanly → CONDITIONAL GO with a
follow-up ticket for OPS001-K (freshcheck-relaxation) so future Fridays
don't have delayed delivery.

### Conditions for 🔴 CONTINUED NO-GO

If both today's 16:15 IST AND 18:30 IST cron slots fail → escalate to
OPS001-M diagnostic session. Almost certainly a new failure mode (data
provider blocked, secret rotated, git-push failure on runner).

---

## 7. What OPS001-L did NOT do

- ❌ Did not modify any code
- ❌ Did not modify any workflow YAML
- ❌ Did not tune any strategy parameter
- ❌ Did not implement any fix
- ❌ Did not run `recommendation_generator.py` (which would have rewritten production files)
- ❌ Did not trigger any workflow_dispatch
- ❌ Did not touch MON001 sealed core (fingerprint unchanged)
- ❌ Did not modify LAB001–LAB010 artefacts
- ❌ Did not change `cumulative_strategy_search` (38, unchanged)
- ❌ Did not commit anything (this doc is unstaged pending review)

---

## 8. Next actions (operator's decision)

Three choices:

**Choice A — Passive: wait for 16:15 IST cron**
Expected first Telegram: 16:20-18:35 IST today. Zero operator effort.

**Choice B — Active: trigger workflow_dispatch now**
Open [github.com/praveen330/NexaQuant/actions/workflows/aegis-daily.yml](https://github.com/praveen330/NexaQuant/actions/workflows/aegis-daily.yml) → "Run workflow" → main → click. See result in ~4-8 min. **Risk:** if yfinance doesn't have 07-17 data yet, freshcheck fails — but that's diagnostic, not damaging.

**Choice C — Escalate: request OPS001-K fix**
If you want the yfinance-latency edge case fixed before observing today's run. Not recommended — observe first, fix second.

Standing by for your call. No code changes will occur without your explicit greenlight.

---

**Certification Status: 🔴 NO-GO (temporary — awaiting today's cron)**
**Expected next status: 🟢 GO within 6 hours of this doc**
**Signed:** OPS001-L Cert Board — Principal Production Engineer / Release Manager / QA Lead / Platform Architect
