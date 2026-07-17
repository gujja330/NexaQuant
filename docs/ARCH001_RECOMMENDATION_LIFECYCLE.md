# ARCH001 · Recommendation Lifecycle & Delivery Architecture

**Spec ID:** `ARCH001-LIFECYCLE-2026-07-17`
**Role:** Chief Product Architect · Quant Platform Architect · UX Architect · Production Architect
**Deliverable type:** ARCHITECTURE ONLY. Zero code changes. Zero workflow changes. Zero scheduling changes.

---

## Table of contents

- [0. The problem in one paragraph](#0-the-problem-in-one-paragraph)
- [1. The three-dates conflation](#1-the-three-dates-conflation)
- [2. Canonical terminology](#2-canonical-terminology)
- [3. Recommendation state machine](#3-recommendation-state-machine)
- [4. Timeline diagram — the ideal flow](#4-timeline-diagram--the-ideal-flow)
- [5. Delivery-schedule model comparison](#5-delivery-schedule-model-comparison)
- [6. Sequence diagrams](#6-sequence-diagrams)
- [7. Telegram redesign — the header rewrite](#7-telegram-redesign--the-header-rewrite)
- [8. Google Sheets schema extension](#8-google-sheets-schema-extension)
- [9. Database canonical field set](#9-database-canonical-field-set)
- [10. Edge-case behaviour specifications](#10-edge-case-behaviour-specifications)
- [11. Retry policy](#11-retry-policy)
- [12. Decision matrix](#12-decision-matrix)
- [13. Final recommended architecture](#13-final-recommended-architecture)

---

## 0. The problem in one paragraph

The current AEGIS pipeline conflates **three distinct temporal
concepts** into a single field called `asof`. As a result, on a Friday
2026-07-17 at 16:20 IST, an operator receives a message stamped "Market
asof 2026-07-17" and reasonably concludes "these are for today's
market" — even though the market has been closed for 50 minutes and
the recommendations are actually for **Monday 2026-07-20's open**. This
document defines the correct separation and prescribes an architecture
that eliminates the ambiguity without changing any strategy logic.

---

## 1. The three-dates conflation

Every recommendation actually has three distinct dates. The current
pipeline uses only one field and lets the operator infer the rest.

### 1.1 The three dates

**Date-A · Market Data Date**
The date of the OHLC bar the model consumed. `closes.index[-1].date()`
in `recommendation_generator.py:182`. Always a completed trading
session (or the pipeline aborts at freshness_gate).

**Date-B · Recommendation Generated At**
The wall-clock timestamp when `recommendation_generator.py` ran.
Currently NOT persisted anywhere the operator can see.

**Date-C · Trading Action Date**
The market session in which the operator SHOULD act on the
recommendation. Currently NOT computed anywhere.

### 1.2 How the current pipeline conflates them

| System | Field | What it actually holds | What operator infers |
|---|---|---|---|
| `data/aegis_today.csv` | `Generated` (col 1) | Date-A (market data date) | Date-C (they can trade today) |
| Telegram header | `Market asof YYYY-MM-DD` | Date-A | Date-C |
| Google Sheets | (whatever col operator sees first) | Date-A | Date-C |
| Registry `asof` column | Date-A | Date-A | mixed |

### 1.3 Why this bites operators

**Example — Friday 2026-07-17, cron fires at 16:15 IST:**

- Date-A: 2026-07-17 (today's close, since yfinance has it by 16:15 IST)
- Date-B: 2026-07-17 16:18 IST (compute wall-clock)
- Date-C: **2026-07-20** (Monday open — Sat/Sun no market)

Operator receives Telegram at 16:20 IST with header "Market asof
2026-07-17". Naturally thinks: "great, act now." Market is closed.
Actual actionable session is Monday. Two-day mismatch.

**Example 2 — Same day, cron fires at 11:00 IST (hypothetically):**

- Date-A: 2026-07-16 (yesterday's close — yfinance hasn't ingested 07-17 yet)
- Date-B: 2026-07-17 11:00 IST
- Date-C: 2026-07-17 15:30 IST (today's close, but operator has all morning to place)

Operator sees "Market asof 2026-07-16". Thinks: "these are yesterday's,
stale." Actually the model correctly used yesterday's close (the freshest
data) to recommend for today's market. Not stale — correct.

**Both mistakes come from the same root cause: showing Date-A when the
operator's decision depends on Date-C.**

---

## 2. Canonical terminology

Every future document, header, database column, and log line must use
these seven terms with these exact meanings. No aliases. No shorthand
that drops the qualifier.

| Term | Type | Definition | Example |
|---|:-:|---|---|
| **Market Data Date** | `date` (IST) | Trading session whose OHLC drove the recommendation | `2026-07-17` |
| **Recommendation Generated At** | `datetime` (UTC + IST) | Wall-clock when the model computed | `2026-07-17T10:48:00Z (16:18 IST)` |
| **Published At** | `datetime` (UTC + IST) | Wall-clock when Telegram/Sheets/DB was delivered | `2026-07-17T10:50:00Z (16:20 IST)` |
| **Effective From** | `date` (IST) | First market session in which the operator should act | `2026-07-20` |
| **Valid Until** | `date` (IST) | Last market session the recommendation is actionable | `2026-07-25` |
| **Review On** | `date` (IST) | When the model will re-evaluate this position | `2026-08-14` |
| **Holding Horizon** | duration | Target holding period (config: 63 trading days = ~3 months) | `63d ~ 2M` |

### 2.1 Rules for using these terms

- **Never** say "today's recommendation" without qualifying which date.
- **Never** show "Market asof" without ALSO showing "Effective From".
- **Every** artifact (Telegram, Sheets, CSV, JSONL) MUST carry all seven fields.
- **Retire** the legacy word `asof` in all new user-facing surfaces (keep in code for backward compat only).

---

## 3. Recommendation state machine

Each recommendation traverses this state machine exactly once. Reproduced from LAB011-OI spec §4 but with dates attached.

```
        ┌─────────────┐
        │  GENERATED  │  ← recommendation_generator wrote this row
        │             │     Market Data Date, Generated At set
        └──────┬──────┘
               │  (delivery pipeline runs)
               ▼
        ┌─────────────┐
        │  PUBLISHED  │  ← Telegram + Sheets + DB confirm write
        │             │     Published At set
        └──────┬──────┘
               │  (arrival of Effective From date)
               ▼
        ┌─────────────┐
        │  EFFECTIVE  │  ← market opens on Effective From
        │             │     operator may act
        └──────┬──────┘
               │  (operator opens position OR
               │   T+1 close post-Effective observed)
               ▼
        ┌─────────────┐
        │    ACTIVE   │  ← per-day price observations updating MFE/MAE
        │             │     Days Held counter incrementing
        └──────┬──────┘
               │
      ┌────────┴────────┐
      │                 │  (exactly one of the five below)
      ▼                 ▼
┌──────────┐  ┌─────────┐  ┌────────────┐  ┌─────────┐  ┌──────────┐
│ TARGET   │  │  STOP   │  │  TRAILING  │  │ EXPIRED │  │ REPLACED │
│  HIT     │  │  HIT    │  │   HIT      │  │ (>Valid │  │ (rank-out│
│          │  │         │  │            │  │  Until) │  │  in new  │
│          │  │         │  │            │  │         │  │  cycle)  │
└────┬─────┘  └────┬────┘  └────┬───────┘  └────┬────┘  └────┬─────┘
     │             │             │              │             │
     └─────────────┼─────────────┼──────────────┼─────────────┘
                   ▼
             ┌──────────────┐
             │   RESOLVED   │  ← outcome fields all populated
             │              │
             └──────┬───────┘
                    │  (30 days after RESOLVED)
                    ▼
             ┌──────────────┐
             │   ARCHIVED   │  ← immutable historical record
             │              │
             └──────────────┘
```

**State-timing invariants:**

- `PUBLISHED.published_at >= GENERATED.generated_at` (obviously)
- `EFFECTIVE.opens_at == first_market_open >= published_at`
- `ACTIVE` state duration is bounded by `Valid Until`
- Any terminal state MUST fall on or before `Valid Until`
- `ARCHIVED` transition triggered by wall-clock, not by another event

---

## 4. Timeline diagram — the ideal flow

Show a single recommendation's lifecycle across wall-clock time. Example:
a Friday-evening compute for Monday's open.

```
       Fri 2026-07-17                      Mon 2026-07-20                       Fri 2026-07-24
       │                                   │                                    │
       │  15:30 IST   Market Close         │                                    │
       │      │                            │                                    │
       │      ▼                            │                                    │
       │  15:45 IST   yfinance settles     │                                    │
       │      │       Fri close available  │                                    │
       │      ▼                            │                                    │
       │  18:30 IST   Generation           │                                    │
       │      ●───────────────────────┐    │                                    │
       │      │ Market Data Date:     │    │                                    │
       │      │   2026-07-17 (Fri)    │    │                                    │
       │      │ Generated At:         │    │                                    │
       │      │   18:30 IST           │    │                                    │
       │      │                       │    │                                    │
       │      ▼                       │    │                                    │
       │  18:35 IST   PUBLISHED       │    │                                    │
       │      ●   evening Telegram +  │    │                                    │
       │      │   Sheets + DB commit  │    │                                    │
       │      │                       │    │                                    │
       │      │                       │    │  09:15 IST  Market Open            │
       │      │                       │    │      │                             │
       │      │                       │    │      ▼                             │
       │      │                       │    │  09:00 IST  Morning Reminder ●     │
       │      │                       │    │  (optional — same content)         │
       │      │                       │    │      │                             │
       │      │                       │    │      ▼                             │
       │      │                       │    │  09:15 IST  EFFECTIVE FROM         │
       │      │                       │    │      ●   operator may act          │
       │      │                       │    │      │                             │
       │      │                       │    │      ▼                             │
       │      │                       │    │  ACTIVE ─────────────────────────► │
       │      │                       │    │                                    ●  VALID UNTIL
       │      │                       │    │                                    │
       └──────┴───────────────────────┴────┴────────────────────────────────────┴──►

  DATA:                 Fri-close
  GENERATED AT:         Fri 18:30 IST
  PUBLISHED AT:         Fri 18:35 IST
  EFFECTIVE FROM:       Mon 09:15 IST
  VALID UNTIL:          Fri 2026-07-24 (7 trading days later — config-driven)
  REVIEW ON:            2026-10-15 (Fri + 63 trading days)
  HOLDING HORIZON:      63d ~ 2M
```

**Key insight:** Publication instant is **73+ hours before** Effective From
in this example (Fri 18:35 → Mon 09:15 = 2 days 14h 40min).
This is intentional. The operator has all weekend to review the picks before
acting at Monday's open.

---

## 5. Delivery-schedule model comparison

Three plausible schedules. Each has different trade-offs.

### 5.1 Model A · Post-close evening + morning reminder

```
Trading day D:
  15:30 IST  Market closes
  15:45 IST  yfinance settles D-close
  18:30 IST  Cron fires   ← Generate + Publish (evening report)
  18:35 IST  Telegram + Sheets + DB commit

Next trading day D+1:
  08:30 IST  Morning reminder cron
  08:32 IST  Telegram re-send of D's recommendation (NO regeneration)
  09:15 IST  Market opens → EFFECTIVE FROM
```

**Advantages:**
- Data completeness guaranteed (yfinance had 3+ hours to settle)
- Operator has evening + overnight to review before acting
- Morning reminder ensures nobody misses because they didn't check evening
- Clear temporal separation of Data / Generation / Trading Action Date

**Disadvantages:**
- Two cron windows to operate (evening + morning)
- Compute happens after operator's work-day (may miss real-time issues)
- Requires re-send logic (safe because content is identical)

### 5.2 Model B · Overnight generation, morning publish

```
Trading day D+1:
  02:00 IST  Cron fires   ← Generate using D-close (nightly compute)
  02:15 IST  Store to DB, generate reports (do NOT publish yet)
  08:30 IST  Publish cron fires
  08:32 IST  Telegram + Sheets published
  09:15 IST  Market opens → EFFECTIVE FROM
```

**Advantages:**
- Compute happens off-peak (cheap infra)
- Publication is close to actionable moment
- One publication, one delivery — no re-send needed

**Disadvantages:**
- 6+ hour gap between compute and publish — data COULD change (rare but possible in emerging markets)
- Requires two separate cron entries with dependency
- If compute fails at 02:00 IST, operator has less recovery window
- No evening review opportunity

### 5.3 Model C · Pre-market generation and publish

```
Trading day D+1:
  07:00 IST  Cron fires   ← Generate using D-close
  07:05 IST  Telegram + Sheets published
  09:15 IST  Market opens → EFFECTIVE FROM
```

**Advantages:**
- Simplest — one cron, one publish
- Compute + publish are contemporaneous → no drift

**Disadvantages:**
- Only 2h 15min buffer between compute and market open — any glitch costs a day
- No evening review
- yfinance MUST have D-close by 07:00 IST every time (usually true, but late updates on holidays or corporate actions could break)

### 5.4 What the current implementation does — Model X (broken)

```
Trading day D:
  09:15 IST  Market opens
  15:30 IST  Market closes
  16:15 IST  Cron fires   ← Generate using D-close (if yfinance has it)
  16:20 IST  Telegram published
```

Publication happens **50 minutes AFTER** D closes. Operator cannot act on D. The recommendation is really for D+1 open. But the header says "Market asof D" — misleading.

**This is what the operator has been complaining about.** Model X is
"post-close, same-day publish" — the worst of both worlds. Compute
uses D data (good), but publication timing suggests actionability that
doesn't exist.

---

## 6. Sequence diagrams

### 6.1 Model A — Full end-to-end sequence

```
                    Fri 2026-07-17                      Mon 2026-07-20
                    ─────────────                       ─────────────
                                                                    
Operator            (asleep / away)                     Reading Telegram
Cron   ──15:30──╴  (idle)          ──08:30──╴ Morning cron fires
       ──18:30──╴  Evening cron fires                              
yfinance ─── settles Fri close        ├────────  serves D data
       (D=07-17)  ├───── consumed ───┤              
Refresh data          │                                            
                      ▼                                            
                Freshness gate                                     
                      │                                            
                      ▼                                            
                Generator ─── writes aegis_today.csv ─────         
                      │  Market Data Date: 2026-07-17               │
                      │  Generated At: 18:30 IST                    │
                      │  Effective From: 2026-07-20                 │
                      │  Valid Until: 2026-07-27                    │
                      │  Review On: 2026-10-15                      │
                      ▼                                             │
                DB + Sheets + Telegram   ─── Published At:          │
                                              18:35 IST             │
                                                                    │
                Ledger append                                       │
                       │                                            │
                       ▼                                            │
                       (state: PUBLISHED)                           │
                                                                    │
                                                                    ▼
                                                             Morning reminder:
                                                             SAME content from
                                                             aegis_today.csv
                                                             Published At:
                                                             08:32 IST
                                                                    │
                                                                    ▼
                                                             (state: PUBLISHED
                                                              second time —
                                                              reminder tag)
                                                                    │
                                                                    ▼
                                                             09:15 IST
                                                             Market opens
                                                             (state: EFFECTIVE)
                                                                    │
                                                                    ▼
                                                             (Operator acts
                                                              at open OR
                                                              during Mon session)
                                                                    │
                                                                    ▼
                                                             (state: ACTIVE)
```

### 6.2 Freshness-gate decision sequence

```
Cron fires → refresh_data → freshness_gate

freshness_gate reads latest parquet:
    latest_bar_date = max across all parquets
    expected_session = "the most recent COMPLETED trading day"

if latest_bar_date >= expected_session:
    PASS → generator runs
    generator sets:
        Market Data Date = latest_bar_date
        Effective From = next_trading_day_after(latest_bar_date)
        Valid Until = Effective From + expiry_cal_days
else:
    FAIL → alert operator, abort
    backup cron retries later
```

### 6.3 Weekend / holiday flow

```
Fri 2026-07-17 (trading day):
    18:30 IST cron → publishes recommendation
    Market Data Date = 2026-07-17
    Effective From = 2026-07-20 (Mon — skip Sat/Sun)
    
Sat 2026-07-18 (weekend):
    No cron (weekday filter in workflow)
    No compute, no publish
    
Sun 2026-07-19 (weekend):
    Same as Sat
    
Mon 2026-07-20 (trading day):
    08:30 IST morning reminder → re-send Fri's message
    09:15 IST market opens (Effective From reached)
    18:30 IST evening cron → publishes NEW recommendation
        Market Data Date = 2026-07-20
        Effective From = 2026-07-21
```

**Weekend gap is 2 days between Fri evening publish and Mon morning reminder.** Operator receives NO messages Sat/Sun. Reminder Mon 08:30 IST re-anchors the operator on Fri's picks.

**Holiday flow (e.g., Tue 2026-01-26 Republic Day):**

- Mon 2026-01-25: evening cron publishes recs. Effective From = 2026-01-27 (skip Tue).
- Tue 2026-01-26: holiday. No cron.
- Wed 2026-01-27: morning reminder at 08:30, market opens 09:15.

---

## 7. Telegram redesign — the header rewrite

### 7.1 Current header (OPS001-I)

```
🏢 NEXAQUANT · AEGIS Daily
📅 Market asof 2026-07-17 (Fri) · Regime Weak
💼 Shield · Deploy 60% · Cash 40%
```

**Problem:** "Market asof" tells the operator the DATA date, not when to
act. Reading at 16:20 IST, operator assumes "today".

### 7.2 Proposed header (ARCH001)

```
🏢 NEXAQUANT · AEGIS Daily
📆 Recommendation for: 2026-07-20 (Mon open)
📊 Based on market close: 2026-07-17 (Fri)
⏱  Valid from: 2026-07-20 09:15 IST · Expires: 2026-07-27
🕰  Generated: 2026-07-17 18:30 IST · Published: 2026-07-17 18:35 IST
💼 Shield · Deploy 60% · Cash 40% · Regime Weak
```

**Every reading has a clear answer:**

- Q: "When should I act?" → A: line 2, "2026-07-20 (Mon open)"
- Q: "What data is this based on?" → A: line 3, "2026-07-17 close"
- Q: "How long is this valid?" → A: line 4, "Expires 2026-07-27"
- Q: "When was this computed?" → A: line 5, "Generated 18:30 IST"

### 7.3 Morning reminder header variant

```
🌅 NEXAQUANT · AEGIS Reminder (Mon open in 45 min)
📆 Recommendation for: 2026-07-20 (Mon open)
📊 Based on market close: 2026-07-17 (Fri)
⏱  Valid from: NOW · Expires: 2026-07-27
🕰  Same content as Fri 18:35 IST publish · (reminder — no regeneration)
💼 Shield · Deploy 60% · Cash 40% · Regime Weak
```

The word "reminder" is prominent. "Same content as previous publish"
explicitly stated so operator understands nothing new was computed.

### 7.4 Zero-action-day variant (still needed)

If NEW = HOLD = EXIT = WATCH = 0 (no changes), the header still shows
all six dates, but the body says:

```
🎯 ACTIONS TODAY
  ⚪ NO ACTION REQUIRED — portfolio stable · 9 positions held
```

---

## 8. Google Sheets schema extension

Current schema of `AEGIS_LATEST.xlsx` and Sheets tab has ~19 columns
including `Generated` (Date-A), `Review Date`, `Valid Until`.

**Proposed additional columns (5):**

| Column | Type | Purpose |
|---|:-:|---|
| `Market Data Date` | date | Date-A explicit (retire `Generated` as ambiguous) |
| `Generated At UTC` | datetime | Date-B in UTC |
| `Generated At IST` | datetime | Date-B in IST (operator-friendly) |
| `Effective From` | date | Date-C — the "actionable day" |
| `Status` | enum | GENERATED / PUBLISHED / EFFECTIVE / ACTIVE / RESOLVED / ARCHIVED |

**Retire (or rename for backward compat):**

- `Generated` (col 1) → alias for `Market Data Date`
- `Valid Until` → keep as is (unambiguous)
- `Review Date` → keep as is

**Sort order recommendation:**

- Primary: `Grade` DESC (Grade A first)
- Secondary: `Score /100` DESC

Operator sees best-first at a glance.

---

## 9. Database canonical field set

Every DB record — `aegis_registry.csv`, `aegis_recommendation_db.csv`,
`forward_ledger.jsonl`, plus the future LAB011 `recommendation_outcomes.jsonl` —
should carry all seven canonical date/time fields.

### 9.1 Field specification

```yaml
recommendation_outcomes_row:
  # Identity
  rec_id:                str      # e.g., "REC-20260717-0001"
  ticker:                str
  strategy_version:      str      # e.g., "AEGIS_v2.2"
  
  # The three dates + wall clocks
  market_data_date:      date     # Date-A
  generated_at_utc:      datetime # Date-B (UTC)
  generated_at_ist:      datetime # Date-B (IST, denormalized for convenience)
  published_at_utc:      datetime # published to Telegram/Sheets/DB
  effective_from:        date     # Date-C — first actionable session
  valid_until:           date     # last actionable session
  review_on:             date     # scheduled re-evaluation
  
  # Lifecycle state
  status:                enum     # GENERATED / PUBLISHED / EFFECTIVE / ACTIVE / RESOLVED / ARCHIVED
  
  # Recommendation content (unchanged from current)
  grade:                 str      # A / B / C
  score:                 int      # 0-100
  weight_pct:            float
  entry_range_lo:        float
  entry_range_hi:        float
  target_price:          float
  stop_price:            float    # derived, presentation
  trail_pct:             float
  horizon_days:          int
  
  # ... plus outcome fields per LAB011 spec ...
```

### 9.2 Backward-compatibility layer

The existing `Generated` field in `aegis_today.csv` continues to be
written. It aliases `market_data_date`. Any consumer that reads it
transparently gets the correct value. New consumers should read
`market_data_date` directly.

**No schema-breaking change. Additive only.**

---

## 10. Edge-case behaviour specifications

### 10.1 Weekend behaviour

- Fri evening cron publishes recs with `Effective From = next Mon`
- Sat + Sun: no cron, no publish
- Mon 08:30 IST reminder: re-send Fri's message
- Mon 18:30 IST evening cron: new recs with `Effective From = Tue`

### 10.2 Holiday behaviour

- If Fri = holiday → no evening cron on Fri
- Thu evening cron already published recs with `Effective From = Mon (skip Fri)`
- Mon 08:30 IST reminder re-anchors

**Implementation:** `NSE_HOLIDAYS_2026` list in `scripts/check_data_freshness.py` is already used by `expected_previous_session()`. Extending it to compute `next_trading_day()` is a small utility, not a schema change.

### 10.3 Missed-cron behaviour

Current design has 3 cron slots per weekday (primary + 2 backups). Under the proposed Model A schedule:

- Evening slots: 18:30 / 19:30 / 20:30 IST
- Morning slots: 08:00 / 08:15 / 08:30 IST

If ALL three of a slot-tier miss (extreme case — GitHub cron down + operator asleep):

- Evening miss: no evening publish. Morning reminder becomes the FIRST publish (with fresh Generated_At).
- Morning miss: operator doesn't get pre-open reminder. Falls back on evening's Telegram from previous evening.

**Failure envelope:** operator MAY miss a reminder, will NEVER miss the primary publish (evening slot has 3 retries + morning slot has 3 retries = 6 total attempts across ~14 hours).

### 10.4 Late-data-provider behaviour

If yfinance is slow (D-close not available at 18:30 IST evening cron):

- `freshness_gate` sees `latest_bar = D-1`, `expected = D`, gap = 1 → STALE → abort
- Backup slot at 19:30 IST retries → yfinance almost certainly has D-close by then
- If ALL three evening slots fail → next morning's cron runs against D-1 data and marks `Effective From = D+1` (skipping D)

**This is not a bug** — refusing to publish on stale data is the OPS001-F guard doing its job.

### 10.5 Freshness-gate refusal timing

The current OPS001-F sender-side freshness check compares `Generated`
field to today's IST date. Under Model A:

- Compute happens Fri 18:30 IST
- Publish happens Fri 18:35 IST — freshcheck sees `Generated=2026-07-17` = today IST = PASS
- Morning reminder Mon 08:30 IST — freshcheck sees `Generated=2026-07-17` ≠ today IST (2026-07-20) → **FAIL under current gate**

**ARCH001 prescribes:** the morning reminder uses a DIFFERENT gate.
Reminder-gate accepts:
- `Generated == today IST`, OR
- `Generated == previous trading day` AND today is a trading day AND `today - Generated ≤ 3 calendar days` (weekend tolerance)

This is a **spec change**, not an implementation. When OPS002 implements
the reminder path, this reminder-gate is what it must use.

### 10.6 First-run-of-week special case

Monday morning reminder is the ONLY time the "trading day − Generated"
can be 3 calendar days (Fri publish → Mon reminder = 3 days).

Rest of the week: `today − Generated == 1 day` always.

Reminder-gate must handle both cases. Weekend-count comes from an
explicit trading-day arithmetic, NOT a naive day-count.

---

## 11. Retry policy

Reinforces the current design; no change needed.

### 11.1 Cron redundancy

Under Model A:

- Evening slots: 18:30 / 19:30 / 20:30 IST (3 attempts)
- Morning slots: 08:00 / 08:15 / 08:30 IST (3 attempts)

Same-day guard (`data/.published` marker) prevents duplicate work.

### 11.2 Notification retry (OPS001-C already provides)

If Telegram / Slack / Discord / Email / Webhook fails a send:

- `RetryQueue` (from OPS001-C) enqueues the failed delivery
- Exponential backoff: 30s / 60s / 120s / 300s / 600s
- After max_attempts (5), moves to DLQ
- Operator alerted via `DEGRADED` state in `notify status`

### 11.3 Data-provider retry

`refresh_data.py` already handles per-ticker retry within a single run.
No inter-run retry needed — the cron-slot redundancy provides that.

---

## 12. Decision matrix

Ranked evaluation of Models A, B, C, and current X.

| Criterion | Weight | Model A | Model B | Model C | Current X |
|---|:-:|:-:|:-:|:-:|:-:|
| Actionability (operator can trade at open) | 10 | 10 | 9 | 8 | 3 |
| Data completeness (yfinance settled) | 10 | 10 | 10 | 8 | 8 |
| yfinance latency tolerance | 8 | 10 | 8 | 4 | 6 |
| Operator convenience (get during trading hours OFF) | 8 | 9 | 7 | 8 | 4 |
| Simplicity of implementation | 6 | 6 | 5 | 10 | 10 |
| Recovery windows (backup slots + retry) | 7 | 10 | 6 | 5 | 8 |
| Overnight compute cost | 3 | 8 | 10 | 8 | 8 |
| Clarity of headers (three dates visible) | 9 | 10 | 10 | 10 | 3 |
| Weekend behaviour handled | 6 | 10 | 8 | 8 | 5 |
| Holiday behaviour handled | 6 | 10 | 8 | 8 | 6 |
| **Weighted score** | **73** | **91%** | **80%** | **74%** | **58%** |

**Model A wins on 6 of 10 criteria; loses only on simplicity (Model C is simpler).**

Simplicity loss is acceptable because the added complexity (2 cron
windows, reminder logic) is well-scoped and testable.

---

## 13. Final recommended architecture

# ▶ Adopt Model A · Post-close evening + morning reminder

**Combined with** the header redesign in §7, the Sheets schema extension
in §8, and the database canonical field set in §9.

### 13.1 What this means concretely (still no code changes)

Under this architecture, a Friday would look like:

- **15:30 IST Fri:** market closes
- **17:30–18:00 IST Fri:** yfinance settles today's close
- **18:30 IST Fri:** evening cron fires
  - `refresh_data.py` → parquets updated
  - `check_data_freshness.py` → PASS (gap=0, latest=today, expected=today)
  - `recommendation_generator.py` → writes `aegis_today.csv` with:
    - `market_data_date = 2026-07-17`
    - `generated_at_utc = 2026-07-17T13:00:00Z`
    - `effective_from = 2026-07-20` (Mon — skips Sat/Sun)
    - `valid_until = 2026-07-27`
  - Telegram + Sheets + DB publish
  - Header: "Recommendation for: 2026-07-20 (Mon open) · Based on market close: 2026-07-17"
- **19:30 IST Fri:** backup 1 — skipped by same-day guard
- **20:30 IST Fri:** backup 2 — skipped
- **08:00 IST Mon:** morning reminder cron fires
  - No regeneration
  - Re-send SAME content of aegis_today.csv (unchanged since Fri)
  - Header: "AEGIS Reminder (Mon open in 45 min) · Recommendation for: 2026-07-20"
- **09:15 IST Mon:** market opens — recommendations become EFFECTIVE
- **08:15 IST Mon + 08:30 IST Mon:** backup 1 + 2 for morning — skipped if 08:00 succeeded

### 13.2 What this DOESN'T do

- **Does not change strategy.** Same `recommendation_generator.py`, same HRP, same scoring, same MON001.
- **Does not change portfolio construction.**
- **Does not change any research.**
- **Does not modify MON001 sealed core.**
- **Does not increment `cumulative_strategy_search`.**
- **Does not modify LAB001–LAB010 artefacts.**
- **Does not add pandas/numpy/scipy dependencies.**

### 13.3 What this DOES change (in the eventual implementation phase — NOT this doc)

**When someone eventually authorises implementation:**

- Add 5 fields to `aegis_today.csv` (backward-compatible)
- Add 5 columns to `AEGIS_LATEST.xlsx` (Sheets sync updates automatically)
- Rewrite Telegram header (`india/telegram_notify.py::build_message()`) to use the 3-dates format
- Split cron in `aegis-daily.yml` into evening + morning workflows (or two triggers on the same workflow)
- Add reminder-gate to `scripts/telegram_send_with_retry.py` (accepts prev trading day for morning reminder)
- Add ARCH001 test suite (~10 tests, structural checks)

**Implementation scope estimate:** ~1 focused session (3-4 hours) plus 1 day of live validation. Deferred to a future phase (call it OPS002-cadence or ARCH001-impl).

### 13.4 What happens between now and implementation

Zero code change. The current 16:15 IST post-close cron continues.
Operator continues receiving daily Telegrams. The header still says
"Market asof YYYY-MM-DD" ambiguously.

**This document is the specification. Implementation authorization is a separate approval.**

---

## 14. Diagrams appendix

### 14.1 Current architecture (Model X — for contrast)

```
Compute      →  Publish  →  (operator sees message)  →  (market closed)  →  (Monday actionable)
   ▲               ▲                    ▲                                          ▲
 16:15 IST      16:20 IST           16:22 IST                                   Mon 09:15 IST

  Data: today             Header:                     Operator thinks:              Actionable:
                          "Market asof today"          "act now"                    "Monday"
                                                            │
                                                            └─── CONFUSION
```

### 14.2 Proposed architecture (Model A)

```
Compute + Publish  →  (operator reviews)  →  (weekend)  →  Morning Reminder  →  Market Opens
       ▲                       ▲                                 ▲                    ▲
    Fri 18:30 IST           Fri evening +                    Mon 08:00 IST         Mon 09:15 IST
                            Sat/Sun

  Data: Fri close        Header:                                                      Actionable:
                         "For Mon open"                       Header:                 "Now"
                         "Based on Fri close"                 "Reminder — Mon open
                         "Valid Mon-Fri next wk"              in 45 min"

                                            NO CONFUSION
```

---

## 15. What ARCH001 does NOT do

- ❌ No code modified
- ❌ No workflow YAML modified
- ❌ No schedule change
- ❌ No implementation
- ❌ No tests added
- ❌ No dependencies added
- ❌ No sealed file touched
- ❌ No LAB artefact touched
- ❌ MON001 fingerprint `e4c070673568c52d…` unchanged
- ❌ `cumulative_strategy_search` = 38 unchanged
- ❌ No research trial started

---

## 16. Awaiting operator decisions

Three separate decisions:

1. **Approve ARCH001 as the canonical lifecycle spec.** After approval, all future code changes reference these definitions.
2. **Approve Model A as the target delivery schedule.** Locks in the evening + morning reminder pattern.
3. **Approve implementation to begin** (call it OPS002-cadence). Would run AFTER today's 16:15 IST cron proves OPS001-F works end-to-end.

Do NOT modify any code until all three approvals land.

---

**End of ARCH001. Architecture only. Zero implementation.**
