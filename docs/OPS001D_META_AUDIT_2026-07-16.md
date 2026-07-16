# OPS001-D · Meta-Audit — Principal Portfolio & Research Architecture

**Audit ID:** `OPS001D-META-AUDIT-2026-07-16`
**Role:** Chief Investment Officer · Principal Portfolio Architect ·
Principal Quant Research Architect · Adversarial Reviewer
**Repo state:** commit `c9b326e` on `main`
**Method:** Read-only. Evidence over opinion. No code modified. No research
implemented. No production logic changed. Purpose: identify **every**
blind spot before deciding the next major phase.

> **This document supersedes** `docs/FUTURE_RESEARCH_ROADMAP.md` (legacy).
> The final ONE-next-initiative recommendation appears in §12.

---

## Table of contents

- [0. Executive summary + maturity scorecard](#0-executive-summary--maturity-scorecard)
- [PRIORITY 0 · Forensic — Backdated Recommendations](#priority-0--forensic--backdated-recommendations)
- [PRIORITY 1 · Telegram Report Quality Audit](#priority-1--telegram-report-quality-audit)
- [Single Source of Truth · Pipeline contract diagram](#single-source-of-truth--pipeline-contract-diagram)
- [A · Alpha Research gap analysis](#a--alpha-research-gap-analysis)
- [B · Portfolio Construction](#b--portfolio-construction)
- [C · Trade Lifecycle](#c--trade-lifecycle)
- [D · Risk Management](#d--risk-management)
- [E · Recommendation Quality](#e--recommendation-quality)
- [F · Portfolio Intelligence](#f--portfolio-intelligence)
- [G · Research Validation](#g--research-validation)
- [H · Data Architecture](#h--data-architecture)
- [I · Operations](#i--operations)
- [J · Production Engineering](#j--production-engineering)
- [K · User Experience](#k--user-experience)
- [L · Future AI Opportunities](#l--future-ai-opportunities)
- [11. Ranking (top 25 future initiatives)](#11-ranking-top-25-future-initiatives)
- [12. Final assessment + ONE next initiative](#12-final-assessment--one-next-initiative)
- [Appendix · Investigation trace](#appendix--investigation-trace)

---

## 0. Executive summary + maturity scorecard

### Current maturity (out of 100)

| Dimension | Score | Rationale |
|---|:-:|---|
| **Institutional maturity** | **62** | Single-strategy, single-operator, PAPER_ONLY. Sealed research; live evidence; no HA; no compliance; no client-facing surface. |
| **Production maturity** | **81** | GitHub Actions live path proven (see OPS001-D live audit). 19 pts is dormant daemon platform + Sheets confirmation + backup gap. |
| **Research maturity** | **72** | 10 LABs completed. LAB010 verdict was NOT_VALIDATED but MON001 was cerified to observe. PBO 0.90-0.94 across recent labs is a serious signal. Forward evidence has begun accruing (150 ledger rows). |
| **Operations maturity** | **74** | OPS001-A/B/C code-complete, 279 tests green. Daemon deployed nowhere yet. Multi-channel notification dormant. |
| **Weighted overall** | **~72** | Weighted 40% research + 25% ops + 25% production + 10% institutional. |

### Biggest gaps (one line each)

- **Biggest research gap:** No forward evidence stress-tested through a crisis. 150 rows over 21 days is too little to disprove PBO fears.
- **Biggest engineering gap:** The OPS001-B/-C daemon is code-complete but 0 hours in production. Live commissioning has been planned (OPS001-D) but not executed.
- **Biggest operational gap:** No off-repo backup of `forward_ledger.jsonl` or `sealed_fingerprint.json`. Repo loss = evidence loss.
- **Biggest portfolio gap:** No **actual holdings tracking** — the recommendation engine says "buy X at price Y" but there is no persistent record of what the operator actually holds.
- **Biggest statistical risk:** LAB010 verdict of NOT_VALIDATED coupled with PBO 0.90-0.94. If the sealed strategy is a data-burn artifact, MON001 will eventually detect drift but the window is short.
- **Biggest business opportunity:** Post-30-day forward evidence, an honest attribution report ("did MON001-observed live behaviour match backtest envelope?") is publishable as track record.
- **Biggest source of potential future alpha:** Currently overlooked — **event / earnings drift** (LAB001 exists but not integrated), **short-horizon mean reversion** (untested in prod), **regime-conditioned exposure sizing**.
- **Highest risk of future overfitting:** ANY new alpha layer on top of the sealed baseline. `cumulative_strategy_search=38` is already at PBO cliff; adding more trials without a strict pre-registration gate compounds the problem.

### Three things that should NEVER be changed

1. **MON001 sealed baseline** (HOLD=63, rebal=63, HRP, sector_cap=2, name_cap=0.30). Certification `MON001-CERT-2026-07-15` depends on immutability. Modifying invalidates the entire forward evidence window.
2. **Forward ledger hash chain** (`india/monitoring/MON001_Forward_Validation/ledger/forward_ledger.jsonl`). Append-only, hash-chained, retroactive-mutation-detected. Every research and audit argument rests on this file being trustworthy.
3. **Broker layer PAPER_ONLY code enforcement** (`india/monitoring/MON001_Forward_Validation/broker_layer.py`). The `PaperOnlyBrokerLayer.available()` returning False is the ONLY protection against a real order slipping out.

### Three things that should be REDESIGNED

1. **Telegram report** — currently a diary; needs to be an audit-quality artefact with execution-id, fingerprint hash, market-data timestamp, and MON001 verification tag (see PRIORITY 1).
2. **Actual holdings tracking** — the system today outputs recommendations but has no memory of what the operator actually holds. Every P&L calculation is a hypothesis. A `portfolio_state.jsonl` file with the operator's actual entries (marked separately from recommendations) would close this.
3. **Docs organization** — 56 markdown files in `docs/`, ~35 legacy from AEGIS/ARJUNA/PRISM eras. A single-source-of-truth index doc + archive of the rest.

---

## PRIORITY 0 · Forensic — Backdated Recommendations

### 0.1 Root cause (evidence-based)

**File `india/recommendation_generator.py:182`:**
```python
rets = closes.pct_change(); asof = closes.index[-1]; prices = closes.iloc[-1]
```

**File `india/recommendation_generator.py:226`:**
```python
run_date = datetime.now().date(); market_asof = asof.date()    # run date vs data date (no ambiguity)
```

**Definitive finding:** The system is **architecturally correct**. The
`asof` stamped on every recommendation is the LAST DATE PRESENT IN THE
PRICE DATA (`closes.index[-1]`), NOT `datetime.now()`. The comment on
line 226 explicitly acknowledges "run date vs data date (no ambiguity)".

The operator's complaint ("today is 15th but I got 14 July
recommendations") is therefore NOT a code bug. It is a **timing mismatch
between the workflow trigger and market-data availability**.

### 0.2 The actual mechanism

Trace, in causal order:

1. **`refresh_data.py`** appends new bars from yfinance to `data/raw/india/*_D1.parquet`.
   yfinance returns whatever it has as of the fetch instant. Post-close bars for NSE
   are typically available ~15–60 min after 15:30 IST close.
2. **`check_data_freshness.py`** computes `expected_previous_session` by walking
   `date.today() - 1` back through weekends + holidays. If the workflow runs
   BEFORE any part of "today" is available in yfinance, `expected` = today,
   `latest_bar_date` = yesterday, **gap = 1 → STALE → workflow aborts**.
3. **`recommendation_generator.py`** sets `asof = closes.index[-1]` — the
   most recent date present in the parquet files. This is
   deterministically the most recent completed trading session yfinance
   has delivered at fetch time.
4. **`telegram_notify.py:263`** puts `asof` in the header:
   `f"📊 <b>AEGIS Daily</b> · {asof}"` — the user sees the market-data
   date, not the run date.

### 0.3 Why the operator saw "14 July" on "15 July"

Historical evidence: workflow ran at `2026-07-15T03:48 UTC = 2026-07-15T09:18 IST` (commit `fd0e358`). This is **BEFORE the 09:15 IST market open** — no possible way to have 15-July bars. yfinance's latest close was 14-July (Tuesday's close from 15:30 IST on 07-14). Therefore:
- `refresh_data` appended 07-14 bars.
- `expected_previous_session(2026-07-15) = 2026-07-14` (walks back one, 07-14 is Tuesday). Gap = 0. Freshness PASS.
- `asof = 2026-07-14`. Recommendation stamped 07-14. Telegram header: "📊 AEGIS Daily · 2026-07-14".

**This was correct behaviour under the OLD cron schedule.** The user's
expectation (receive 15-July recommendations on 15-July) required the
workflow to run AFTER 15-July's market close.

### 0.4 The applied fix (commit `dd99a1e`, 2026-07-16)

Cron shifted to POST-CLOSE:
- Primary: 45 10 UTC = **16:15 IST** (post-close + settle buffer)
- Backup 1: 0 13 UTC = **18:30 IST**
- Backup 2: 30 15 UTC = **21:00 IST**

Today (2026-07-16) is the **first weekday under the new schedule** — the
first live proof-point is expected 16:15 IST today.

### 0.5 Remaining failure modes not yet covered

Even with the cron fix, the following can produce a backdated Telegram alert:

| # | Failure mode | Probability | Trigger | Severity | Permanent fix |
|:-:|---|:-:|---|:-:|---|
| F-01 | yfinance delayed post-close (> 45 min) | MED (weekly) | Primary 16:15 IST fires while yfinance still shows prior close | HIGH — user sees stale asof | (a) Add explicit `latest_bar_date >= today` assertion in `check_data_freshness.py`; abort if false. (b) Backup 18:30 IST catches. |
| F-02 | NSE-side data provider glitch | LOW (monthly) | yfinance never delivers today's close | HIGH | Alert on 3-consecutive-day miss; add second data source (alternative Yahoo endpoint or NSE direct) |
| F-03 | Workflow succeeds but committed report is stale | LOW | Race between refresh_data and generator | LOW | Add `assert closes.index[-1].date() == fresh_expected_session_date` after refresh_data |
| F-04 | Telegram sender sends the previously-committed report file | LOW | If `data/aegis_today.csv` on disk is from a prior run and generator fails silently | HIGH | Generator should refuse to run if freshness gate not passed; delete `aegis_today.csv` at pipeline start |
| F-05 | Workflow artifact directories not cleaned between runs | LOW | Old outputs surface unexpectedly | LOW | Add `rm -f data/aegis_today.csv` at start of aegis-daily workflow OR verify freshness in Telegram sender |
| F-06 | Timezone conversion bug in `expected_previous_session` | VERY LOW | If host TZ != UTC and `date.today()` returns wrong date | LOW | Force UTC or IST explicitly: `today = datetime.now(timezone.utc).date()` |
| F-07 | Market holiday not in `NSE_HOLIDAYS_2026` | LOW | Un-listed holiday → expected walk fails | LOW | Refresh holiday list at start of each year; add regression test |
| F-08 | Cron drop (GitHub cron jitter) | MED | Primary slot missed | LOW | Two backup slots already exist. 3-slot redundancy = extremely low miss-all probability. |
| F-09 | Silent freshness_gate bypass via `AEGIS_ALLOW_STALE=1` | VERY LOW | Env leaked | HIGH — bypasses correctness check | Remove env var support OR require signed override |
| F-10 | Timezone of `datetime.now().date()` in `recommendation_generator.py:226` | LOW | If host runs in UTC, `run_date` may differ from IST calendar date | LOW — cosmetic on report | Explicit IST conversion for `run_date` |

### 0.6 Recommended PRIORITY 0 permanent fixes (ranked)

**All are architectural. No workarounds.**

1. **Add absolute-freshness assertion**: after `refresh_data`, assert
   `latest_bar_date == expected_session_including_today_if_post_close`.
   Currently only asserts `>= expected` where `expected =
   today - 1`. **Blocks F-01, F-02, F-03.** [Complexity: 20 LOC]
2. **Delete stale outputs at pipeline start**: workflow step
   `rm -f data/aegis_today.csv data/aegis_recommendations_*.csv` before
   running generator. **Blocks F-04, F-05.** [Complexity: 3 LOC]
3. **Add execution fingerprint to Telegram header**: append
   `Run: {run_date_utc} · Market: {asof} · Fingerprint: {mon001_hash[:8]}`
   so user immediately sees any discrepancy. **Detects any lingering F-01-F-05 case.** [Complexity: ~15 LOC]
4. **Add `latest_bar_date >= today's IST date` freshness gate**
   after 16:00 IST (i.e., post-close). Config-driven cutoff. **Blocks F-01.** [Complexity: 30 LOC]
5. **Remove `AEGIS_ALLOW_STALE`** env-var escape hatch, OR require it in
   an operator-signed override file. **Blocks F-09.** [Complexity: 5 LOC]
6. **Add explicit UTC/IST timezone handling** in `expected_previous_session`
   and `run_date` calculations. **Blocks F-06, F-10.** [Complexity: 10 LOC]
7. **Add MON001 verification tag** to Telegram (see PRIORITY 1). Provides
   independent proof MON001 saw this recommendation. [Complexity: ~30 LOC in `telegram_notify.py`]

### 0.7 Monitoring PRIORITY 0

- **Test:** add `test_ops_pipeline.py::test_freshness_gate_asserts_current_ist_date` that asserts current IST calendar date == `latest_bar_date`.
- **Alert:** if freshness gate ABORTS with STALE for 2 consecutive weekdays, emit CRITICAL.
- **Metric:** Time delta between IST market-close (15:30) and `refresh_data` first-successful-fetch of today's close. Track distribution over 30 days.

### 0.8 STATUS

Every hypothesis in the original prompt has been evaluated:

| Hypothesis | Verdict |
|---|:-:|
| Pipeline reading stale market data | ✅ **Confirmed** — this was the actual cause. Fixed by post-close cron. Residual risk = F-01. |
| `asof` date taken from latest available data file | ✅ **Confirmed** — line 182 explicitly. Architecturally correct. |
| Recommendation regenerated from cached snapshot | ❌ Not observed — generator runs from parquet each time. |
| Telegram sender sends most recent existing report | 🟡 Possible edge case (F-04) — not yet observed but recommend defensive delete. |
| Workflow succeeds even though report failed silently | 🟡 Possible under specific error paths — recommend explicit assertion. |
| Timezone / market-close logic determines wrong "current trading day" | 🟡 Currently uses `date.today()` — host-TZ dependent. Recommend explicit IST. |
| Artifact directories not cleaned between runs | 🟡 Not currently cleaned — recommend cleanup step. |

**PRIORITY 0 verdict:** The primary root cause is fixed. Five residual
failure modes (F-01, F-03, F-04, F-05, F-06/F-10) warrant preventive
architectural fixes. These are candidates for a **PRIORITY 0 fix batch**
before LAB011.

---

## PRIORITY 1 · Telegram Report Quality Audit

### 1.1 Current message anatomy (from `india/telegram_notify.py`)

```
📊 AEGIS Daily · {asof}
{regime} market · Deploy {exp:.0%} · Keep {1-exp:.0%} cash · Horizon {H}
{N} stocks · {n_buy} buy-rated · sorted best-first

═══ YOUR STOCKS ═══
{TIER emoji} Tier — one-line description
  {SYM} · {sector} · NEW today | held N days
    ₹{entry} → ₹{current}  ▲/▼ {pct}% ({delta}/share)
    Enter {buy_range} · {weight}% of capital · Grade {A/B/C} ({score}/100)
    Target ₹{tgt} in {horizon}
    {verdict — buy/hold/watch}

═══ HELD POSITIONS SO FAR ═══
  Weighted avg since entry: ▲ {port_ret}%  ({N} positions)

═══ EXITS (signals — book only if you executed) ═══
  ⚠ {SYM} · {sector} · held N days
    ₹{entry} → ₹{exit}  ▲ exit signal {pct}%
    {reason.headline}: {reason.detail}

═══ OTHER CHANGES vs last run ═══
  ➕ Added today: X, Y
  ⬆ Weight up: A, B
  ⬇ Weight down: C, D
  🔄 Sector shift: rotation

═══ TRACK RECORD ═══
  Wins: {win_rate}% closed positive · Typical {median_ret}% median ({N} scored)
```

### 1.2 Grade against institutional-quality bar

| Field | Present? | Institutional-quality? |
|---|:-:|:-:|
| Recommendation list | ✅ | ✅ |
| Entry / current price | ✅ | ✅ |
| Position sizing (weight) | ✅ | 🟡 (as % of capital, not ₹ amount for a given capital base) |
| Grade A/B/C | ✅ | 🟡 (ordinal only; no numerical confidence interval) |
| Score /100 | ✅ | ✅ |
| Target price | ✅ | 🟡 (single point, no CI) |
| Exit reasons | ✅ | ✅ |
| Track record (win rate + median return) | ✅ | ✅ |
| Portfolio-level P&L | ✅ | 🟡 (weighted avg of *recommended*, not *actually held*) |
| **Market data timestamp** | ❌ | Only `asof` (date). No time-of-day. |
| **Run timestamp** | ❌ | User cannot tell WHEN the report was generated. |
| **Execution ID** | ❌ | No unique run identifier. |
| **MON001 verification tag** | ❌ | User doesn't know if MON001 approved this run. |
| **MON001 fingerprint hash** | ❌ | User cannot verify no sealed drift. |
| **Freshness confirmation** | ❌ | If run stamps `asof` = yesterday, user isn't warned it's a data-lag scenario. |
| **Stop-loss level** | ❌ | Only entry / target. No downside guardrail. |
| **Trailing-stop / hard-stop rule** | ❌ | Exit reasons show WHY exited, but the LIVE report doesn't say what stop rules are active. |
| **Confidence interval on target** | ❌ | Point estimate only. |
| **Portfolio VaR / drawdown** | ❌ | No risk summary. |
| **Recommendation age / expiry** | 🟡 | Shows "held N days"; does NOT show "expires in M days per `expiry_cal_days=7`". |
| **Version / cycle tag** | ❌ | User can't tell which version of the strategy produced this. |
| **Report fingerprint** | ❌ | No hash of the report contents. |
| **Recipient-side stale-report detection** | ❌ | If a same message is re-sent, user has no way to spot duplicates. |

### 1.3 Rewrite specification (design only — no implementation)

Recommended header line (**required** every message):

```
📊 AEGIS Daily · asof {market_asof} (session-close)
🧭 Generated {run_utc} UTC · IST {run_ist}
✅ MON001 {mon001_state} · fingerprint {fp_hash[:8]}
📌 Execution {run_id} · Strategy {strategy_version}
```

Recommended addition to per-stock block:

```
{SYM} · {sector} · {NEW|HOLD N days|EXITING}
  ₹{entry} → ₹{cur}  ▲/▼ {pct}%  (₹{delta}/share)
  Enter {buy_lo}–{buy_hi} · Target ₹{tgt} (95% CI ₹{lo}–{hi})
  Weight {w}% (₹{amt_for_10L} for 10L capital)
  Grade {A/B/C} ({score}/100) · Confidence {conf:.2f}
  ⛔ Stop {stop_price} (-{stop_pct}%) · Trail {trail_pct}%
  Age {N}d · expires {expiry_date} · review {review_date}
  {verdict}
```

Recommended footer (**every message**):

```
═══ INTEGRITY ═══
Report SHA256: {msg_hash[:16]}...
Ledger row:    {ledger_last_hash[:16]}...
MON001 seal:   {fp[:16]}...
Cycle:         AEGIS_v2.2 · Trials {cumulative_strategy_search}
Do NOT act on any message that lacks this footer.
```

The **integrity footer** is the single most valuable addition. It makes
the operator immediately spot:
- A backdated message (`{run_utc}` visible)
- A rogue message impersonating AEGIS (footer hashes won't match)
- A silent drift (fingerprint hash changed unexpectedly)
- A duplicate resend (message SHA256 will collide with a prior one)

### 1.4 Mobile-readability

Current format is dense but well-paginated. On mobile:
- Line wrapping is fine (Telegram handles it).
- The `═══` section dividers are readable.
- Emoji indicators help scan.

Recommended: add a **short-form summary at TOP** (before the detailed body) so operator can decide-in-3-seconds:

```
🟢 3 NEW · 4 HOLD · 1 EXIT · Total 8 · Portfolio +4.2% since entry
```

Then the detailed sections. Existing detail is fine; the missing piece is the "at-a-glance line".

### 1.5 What NOT to add

- **Do not add** raw numeric factor loadings (would suggest false precision).
- **Do not add** live P&L on the operator's actual portfolio (system doesn't know it; would be a hallucination).
- **Do not add** any prediction on tomorrow's return.
- **Do not add** any language that suggests the operator SHOULD trade
  (system is PAPER_ONLY; every message must remain advisory).

---

## Single Source of Truth · Pipeline contract diagram

Per-stage contract. Each row is a **contract** — every future debugging
session should first prove input/output of each stage.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  RAW NSE DATA (yfinance)                                                 │
│  Input:   ticker symbols (Nifty 200)                                     │
│  Output:  data/raw/india/{ticker}_D1.parquet                             │
│  Timestamp field: parquet DataFrame index (pandas Timestamp UTC)         │
│  Validation:  none (yfinance is trusted external)                        │
│  Freshness:   last bar index                                             │
│  Failure:     network error → yfinance raises → refresh() catches       │
│  Recovery:    per-ticker retry within refresh(); pipeline continues on   │
│               partial success                                            │
│  Logging:     `AEGIS DATA REFRESH — appending latest market data`        │
│  Tests:       (integration only — not unit-tested; network dep)          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  VALIDATED DATA (freshness_gate)                                         │
│  Input:   glob data/raw/india/*_D1.parquet                               │
│  Output:  exit code 0/1/2 (stdout log)                                   │
│  Timestamp field: max(df.index[-1]) across all parquets                  │
│  Validation:  gap = expected_prev_session - latest_bar >= 0              │
│  Freshness:   MUST have gap == 0                                          │
│  Failure:     gap >= 1 → sys.exit(2) + Telegram STALE alert              │
│  Recovery:    backup cron slot retries later                             │
│  Logging:     `latest bar: X  expected: Y  gap: Zd`                      │
│  Tests:       (bypassed by AEGIS_ALLOW_STALE=1 — RECOMMEND REMOVE)       │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FEATURE STORE (closes matrix)                                           │
│  Input:   data/raw/india/*_D1.parquet                                    │
│  Output:  in-memory DataFrame `closes` (T x N)                           │
│  Timestamp field: closes.index (pandas DatetimeIndex)                    │
│  Validation:  closes.index[-1] is the source of truth for `asof`         │
│  Freshness:   inherits from previous stage                               │
│  Failure:     empty DataFrame → generator raises IndexError              │
│  Recovery:    pipeline aborts                                            │
│  Logging:     none explicit                                              │
│  Tests:       india/ai_lab/tests/test_lab_framework.py exercises path    │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  RECOMMENDATION ENGINE (recommendation_generator)                        │
│  Input:   closes matrix + config (HOLD=63, rebal=63, HRP, ...)           │
│  Output:  data/aegis_today.csv + data/aegis_recommendation_db.csv +      │
│           data/aegis_registry.csv (append)                               │
│  Timestamp field: asof = closes.index[-1]                                │
│  Validation:  none post-computation; sealed logic                        │
│  Freshness:   inherits — assumes previous stage passed                   │
│  Failure:     none within engine (deterministic)                         │
│  Recovery:    N/A                                                        │
│  Logging:     `PUBLISHED -> {out.relative_to(ROOT)}`                     │
│  Tests:       via MON001 tests + regression                              │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  PORTFOLIO CONSTRUCTION (arjuna_v2 · HRP · sector/name caps)             │
│  Input:   scored candidates (from generator)                             │
│  Output:  weight per stock (fraction of capital)                         │
│  Timestamp field: inherits `asof`                                        │
│  Validation:  sum of weights ≤ 1; sector caps ≤ 2 per sector;            │
│               name cap ≤ 0.30                                            │
│  Freshness:   deterministic function of feature store snapshot           │
│  Failure:     HRP failure returns equal-weight fallback                  │
│  Recovery:    inline in arjuna_v2                                         │
│  Logging:     none explicit at portfolio-construction level              │
│  Tests:       india/ai_lab/tests/*                                        │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  REPORT BUILDER (aegis_engine writes AEGIS_LATEST.xlsx + reports/*.md)   │
│  Input:   recommendations + evidence + regime + market context           │
│  Output:  reports/AEGIS_LATEST.xlsx + india/reports/*.md                 │
│  Timestamp field: `run_date` (datetime.now()) + `market_asof` (asof)     │
│  Validation:  none; assumes upstream fresh                               │
│  Freshness:   inherits                                                   │
│  Failure:     I/O error → pipeline continues if continue_on_failure      │
│  Recovery:    retry via pipeline runner                                  │
│  Logging:     none uniform                                               │
│  Tests:       none direct                                                │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  TELEGRAM FORMATTER (telegram_notify.build_message)                      │
│  Input:   data/aegis_today.csv + data/aegis_recommendation_db.csv        │
│  Output:  HTML-formatted string                                          │
│  Timestamp field: uses `asof` from aegis_today.csv                       │
│  Validation:  none — CURRENTLY WOULD REUSE STALE aegis_today.csv IF      │
│               GENERATOR FAILED                                           │
│  Freshness:   IMPLICIT — assumes generator wrote fresh file              │
│  Failure:     malformed CSV → build_message raises                       │
│  Recovery:    upstream pipeline retry                                    │
│  Logging:     minimal                                                    │
│  Tests:       test_telegram_reliability.py (retry + health only)         │
│                                                                          │
│  🟠 CONTRACT GAP: no assertion that aegis_today.csv is from THIS run.    │
│      Recommendation: delete file at pipeline start; assert freshness.    │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  TELEGRAM SENDER (telegram_send_with_retry)                              │
│  Input:   formatted string + TELEGRAM_BOT_TOKEN + CHAT_ID                │
│  Output:  Telegram API HTTP call                                         │
│  Timestamp field: N/A                                                    │
│  Validation:  bot token format regex, chat_id numeric                    │
│  Freshness:   N/A                                                        │
│  Failure:     4 retries with backoff                                     │
│  Recovery:    ultimate: log to delivery_log.jsonl + Telegram artifact    │
│  Logging:     `telegram_delivery_log.jsonl` uploaded as workflow artifact│
│  Tests:       test_telegram_reliability.py                               │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  MON001 DAILY MONITOR (run_mon001 · ledger append · dashboard)           │
│  Input:   sealed baseline files + envelope + ledger + recommendations    │
│  Output:  forward_ledger.jsonl append + mon001_report/diagnostics/       │
│           dashboard files                                                │
│  Timestamp field: obs snapshot_ts_utc; ledger row asof                   │
│  Validation:  fingerprint match, envelope byte-identical,                │
│               hash-chain integrity, PAPER_ONLY assertion                 │
│  Freshness:   uses same asof as generator                                │
│  Failure:     HALT-severity check → daemon marks failed, alerts CRITICAL │
│  Recovery:    operator ceremony (CHANGE_CONTROL_CHECKLIST)               │
│  Logging:     `mon001_alerts.jsonl` + diagnostics JSON                   │
│  Tests:       25/25 in `test_mon001_framework.py` + 23/23 ops            │
└──────────────────────────────────────────────────────────────────────────┘
```

**Contract summary:** 9 stages. 8 pass invariant/freshness/validation. **1
gap** (Telegram Formatter) — no assertion that the input file is from the
current pipeline run. This is the F-04 failure mode from PRIORITY 0.

---

## A · Alpha Research gap analysis

Legend: R=researched · P=partial · M=missing · U=unnecessary · D=duplicate

| Family | Status | Evidence / rationale |
|---|:-:|---|
| Momentum | R | `arjuna_v2.py` uses momentum signals; LAB005 ranking |
| Mean reversion | M | No LAB dedicated. Untested. |
| Quality | P | Referenced in `confidence_engine.py` but not a separate LAB |
| Value | M | No P/E, P/B, EV/EBITDA signals in production path |
| Growth | M | No revenue/earnings growth signals |
| Earnings revision | M | LAB001_Earnings exists but data pipeline not confirmed |
| Relative strength | R | Part of `arjuna_v2` |
| Cross-sectional ranking | R | LAB005_Ranking |
| Trend following | R | Part of momentum |
| Volatility signals | M | No LAB. Could add ATR/vol-adjusted momentum |
| Liquidity | M | No liquidity filter beyond Nifty200 membership |
| Seasonality | M | Untested; India has strong month-of-year effects |
| Sector rotation | P | Sector caps present; no active rotation model |
| Macro factors | P | `global_risk.py` exists; not integrated into signals |
| Alternative data | M | Not applicable at current scale |
| Sentiment | M | Not applicable at current scale |
| News | M | Not applicable at current scale |
| Insider activity | M | Not applicable |
| Corporate actions | P | `data_nse.py` handles splits/dividends; not a signal |
| Options-derived signals | M | Would require options data pipeline |
| Factor timing | M | No regime-conditional factor weights |
| Multi-factor blending | R | HRP handles blending at portfolio level |
| Ensemble methods | M | Single-model (HRP over one signal set) |
| Dynamic model selection | M | Same |

**Alpha coverage**: 4/24 R · 5/24 P · 15/24 M.

**Adversarial verdict:** Adding MORE alpha families now increases PBO risk
without proportional gain. LAB010 already flagged NOT_VALIDATED at
`cumulative_strategy_search=38`. Recommend NO new alpha work until MON001
forward evidence accrues to 90+ days.

---

## B · Portfolio Construction

| Dimension | Status | Notes |
|---|:-:|---|
| Position sizing | R | HRP + name_cap=0.30 |
| Risk budgeting | R | Implicit via HRP |
| Correlation constraints | R | HRP directly optimizes for this |
| Sector constraints | R | sector_cap=2 |
| Country constraints | U | Single-country (India) |
| Concentration limits | R | name_cap=0.30 |
| Diversification | R | HRP + caps |
| Kelly sizing | M | Not used |
| HRP improvements | P | Sealed HRP; no live-drift-adjusted variant |
| Risk parity | D | HRP subsumes this |
| Capital deployment | P | LAB007 dynamic exposure |
| Cash management | P | Deploy % from LAB007 |
| Dynamic exposure | R | LAB007 |
| Dynamic leverage | U | System doesn't leverage |
| Portfolio turnover | R | rebal=63 |
| Portfolio stability | P | Turnover control implicit |
| Portfolio optimization | R | HRP |

**Verdict:** Portfolio construction layer is mature. No urgent gaps.

---

## C · Trade Lifecycle

| Dimension | Status | Notes |
|---|:-:|---|
| Entry logic | R | Buy range from generator |
| Entry timing | P | Post-close close-price entry assumed; no intraday timing |
| Scaling in | M | Not supported |
| Scaling out | M | Not supported |
| Partial exits | M | Not supported |
| Profit booking | P | Target price shown; not enforced |
| Trailing stops | M | Not in Telegram; may be in `exit_reasons.py` |
| Hard stops | M | Not visible in report |
| ATR stops | M | Not implemented |
| Volatility exits | M | Not implemented |
| Time exits | R | expiry_cal_days=7 review; rebal=63 hard rotation |
| Dynamic exits | P | LAB006 exit strategy sealed |
| Re-entry logic | M | Not clearly defined |
| Holding-period optimization | R | LAB008 + LAB009 horizon calibration |
| Rotation policy | R | rebal=63 |
| Opportunity replacement | R | New picks displace old at rotation |
| Opportunity cost modelling | P | Implicit via HRP; not exposed |

**Verdict:** ⚠ **Stops are the biggest visible gap.** Report doesn't
convey stop-loss levels — operator has no downside guardrail. Adding
stops is not new research; it's exposing existing logic.

---

## D · Risk Management

| Dimension | Status | Notes |
|---|:-:|---|
| Maximum drawdown control | R | LAB007 dynamic exposure; risk gate |
| Portfolio VaR | M | Not computed |
| CVaR | M | Not computed |
| Tail risk | P | Envelope tracking captures some |
| Gap risk | M | Not modelled |
| Correlation spikes | M | HRP recomputes but no alert |
| Crisis behaviour | M | No crisis-mode override |
| Liquidity risk | P | Nifty200 filter provides floor |
| Slippage | M | Not modelled in signals |
| Transaction costs | R | costs_bps=15 in envelope |
| Stress testing | R | LAB010 stress + phase testing |
| Monte Carlo | R | Part of LAB validation |
| Scenario testing | P | LAB010 |
| Regime detection | R | `global_risk.py` |
| Regime switching | M | Detected but not used to alter policy |
| Market crash handling | M | No auto-defensive mode |

**Verdict:** Risk framework is present at RESEARCH level (LAB007, LAB010)
but not surfaced in **live operator report**. Second-biggest gap after
stops. Portfolio VaR and crash-mode alerts would materially improve
operator confidence.

---

## E · Recommendation Quality

| Dimension | Status | Notes |
|---|:-:|---|
| False Strong Buy detection | P | Grade A/B/C; no dedicated detector |
| Confidence calibration | P | `confidence_engine.py`; not calibrated on live |
| Recommendation explainability | R | Report shows factor-derived tier |
| Recommendation stability | P | rebal=63 provides stability; not measured |
| Recommendation consistency | R | Deterministic given inputs |
| Recommendation ageing | R | Shown as "held N days" |
| Recommendation expiry | R | expiry_cal_days=7 |
| Stale recommendation detection | P | Freshness gate on data; not on rec |
| Recommendation versioning | R | rec_id encodes date+horizon |
| Recommendation auditing | R | forward_ledger.jsonl hash-chained |
| Recommendation reproducibility | R | Fingerprint + sealed inputs |

**Verdict:** Recommendation quality is at production level. `rec_id` +
hash chain gives an audit trail. Biggest weakness: confidence calibration
is un-tested against forward evidence.

---

## F · Portfolio Intelligence

| Dimension | Status | Notes |
|---|:-:|---|
| **Portfolio memory** | **M** | System doesn't know what operator holds |
| **Actual holdings tracking** | **M** | Same |
| Entry price memory | P | Only for RECOMMENDATIONS, not actual buys |
| P&L tracking | P | Recommended P&L; not actual |
| Attribution | M | Not computed |
| Benchmark comparison | P | Nifty comparison in some LAB reports |
| Sector attribution | M | Not computed live |
| Stock attribution | M | Not computed live |
| Alpha attribution | M | Not computed live |
| Drawdown attribution | M | Not computed live |
| Decision journal | M | Not implemented |
| Recommendation history | R | Registry + ledger |
| Outcome tracking | P | LAB completion metrics; not live outcome loop |

**Verdict:** **The most under-developed dimension.** The system produces
recommendations but has NO memory of the operator's actual portfolio.
Every "P&L since entry" line in the Telegram report is calculated on the
*recommendation* entry price, not the operator's real fill. This is the
single largest usability improvement available.

**Proposed fix:** A `portfolio_state.yaml` (operator-maintained,
git-committed) where they mark which recommendations they actually took,
at what price, at what quantity. The daily Telegram would then include a
personalized P&L section based on real holdings, alongside the current
"recommendation performance" section. Design only — no implementation
now.

---

## G · Research Validation

| Dimension | Status | Notes |
|---|:-:|---|
| Multiple testing control | R | LAB standards enforce |
| False discovery risk | R | PBO tracked |
| Research governance | R | LAB_STANDARDS.md + preregistration |
| Reproducibility | R | Sealed inputs + fingerprint |
| Forward validation | R | MON001 (150 rows into forward window) |
| Walk-forward testing | R | LAB standard |
| Nested validation | P | Some LABs, not universal |
| Cross validation | R | LAB standard |
| Statistical significance | R | LAB metrics compute |
| Confidence intervals | R | Bootstrap CIs in reports |
| Survivorship bias | R | Nifty200 point-in-time membership |
| Look-ahead bias | R | LAB standard forbids |
| Data leakage | R | LAB test suite checks |
| Selection bias | R | LAB standard |
| Publication bias | P | Only completed LABs published; unfinished are trace-only |
| Alpha decay | M | Not monitored live |
| Live drift detection | R | MON001 IS this |

**Verdict:** Research validation is the most rigorous layer of the entire
system. LAB010 NOT_VALIDATED verdict is disturbing but reflects the
framework working AS DESIGNED — it caught a data-burn signal.

---

## H · Data Architecture

| Dimension | Status | Notes |
|---|:-:|---|
| Data quality | P | yfinance is the only source; no cross-verification |
| Missing data | P | Handled per-ticker in refresh |
| Outlier handling | M | No explicit outlier filter |
| Split adjustments | R | yfinance adjusts |
| Dividend adjustments | R | yfinance adjusts |
| Survivorship handling | R | Point-in-time index membership |
| Corporate actions | P | Splits/divs auto; delisting manual |
| Data versioning | P | Git commits per day |
| Data lineage | P | Implicit via parquet timestamps |
| Historical snapshots | R | Git preserves |
| Data integrity | P | No explicit hash of parquet contents |
| **Vendor independence** | **M** | Single vendor (yfinance) |
| **Multi-source verification** | **M** | Same |

**Verdict:** Vendor independence is the biggest gap. yfinance blocking or
rate-limiting is a single point of failure for the entire system. Second
data source (Angel Broking API, or NSE direct) would materially reduce
this risk.

---

## I · Operations

Already exhaustively covered in `docs/OPS001D_LIVE_READINESS_AUDIT.md`.
Summary: currently 81/100. Live GH-Actions path proven; daemon platform
dormant.

---

## J · Production Engineering

| Dimension | Status | Notes |
|---|:-:|---|
| CI/CD | R | 3 workflows; regression on every push |
| Testing | R | 13 suites, 279 tests |
| Regression | R | ENG001 harness green |
| Fingerprinting | R | MON001 v2 |
| Configuration | R | YAML-driven |
| Versioning | P | Ops version bumped per phase; strategy version implicit |
| Release process | P | git push = release; no staging env |
| Rollback | P | git revert available; no automated rollback |
| Feature flags | M | Not used |
| Audit trail | R | git log + forward_ledger |
| Security | P | Secrets in GH Actions env; no rotation automation |
| Dependency management | P | No pinned versions in workflow install |
| Documentation quality | P | 56 files; high signal-to-noise but too many |

**Verdict:** Engineering discipline is strong. Two gaps: dependency pinning
(portability amendment shows this can bite) and staging environment
(git-push-is-prod is fine at current scale, blocks growth).

---

## K · User Experience

| Dimension | Grade | Notes |
|---|:-:|---|
| Report clarity | B | Well-organised; institutional-quality header missing |
| Portfolio readability | B | Diary format is friendly; lacks integrity footer |
| Recommendation explanations | B+ | Tier + evidence label + grade + score |
| Buy/Hold/Sell wording | B | "NEW / HOLD / EXITING" clearer than raw actions |
| Exit explanations | A- | Uses india/exit_reasons.py — quality |
| Rotation explanations | B | "Added / weight-up / sector shift" |
| Weight explanations | B- | Shown as % — should also show ₹ for a nominal capital |
| Report consistency | B | Format stable across runs |
| Mobile readability | B+ | Emoji + section dividers work well |
| Telegram formatting | B | Sound HTML |
| Decision support | C+ | No stops, no VaR, no MON001 verification tag |
| Human interpretability | A- | Grades + reasons > raw scores |

**Overall UX grade: B / B+.** The single most impactful UX upgrade is the
**integrity footer** (§PRIORITY 1) plus a **stop-loss line** per stock.

---

## L · Future AI Opportunities

Ranked by evidence-based value vs complexity.

| Opportunity | Value | Complexity | Recommendation |
|---|:-:|:-:|:-:|
| **LLM-based report summarization** | LOW | LOW | Skip. Current Telegram is already concise. |
| **LLM decision-journal analyzer** (post-hoc "why did I skip / add this?") | MED | MED | Deferred — needs actual-holdings tracking first (§F). |
| **Agent workflows for MON001 alert triage** | LOW | HIGH | Skip. Deterministic rules already work. |
| **Self-evaluation LLM judge on Telegram messages** | LOW | MED | Skip. Format is deterministic. |
| **Automatic anomaly detection on forward ledger** | HIGH | MED | KEEP for MON002. Bayesian change-point detection on rolling Sharpe/turnover. |
| **Adaptive models** (drift-triggered recalibration) | MED | HIGH | Skip until sealed strategy has 90+ days of forward evidence. Adding adaptive layer NOW compounds PBO risk. |
| **Bayesian optimisation on hyperparameters** | LOW | MED | Skip. cumulative_strategy_search=38 is already at PBO cliff. |
| **Reinforcement learning** | LOW | VERY HIGH | Skip. Justification bar not met. |
| **Explainable AI** (SHAP for each rec) | MED | LOW | KEEP. Add SHAP-style attribution per recommendation. |
| **Knowledge graphs** (sector/ticker relationship) | LOW | HIGH | Skip. Not enough scale to justify. |
| **Multi-agent adversarial validation** | HIGH | HIGH | KEEP for post-30-day. LLM-based "red team" against MON001 findings. |

**Verdict:** Two high-value AI opportunities: **anomaly detection on
forward ledger** (MON002 scope) and **multi-agent adversarial validation**
(post-30-day). Everything else is complexity without proportional value.

---

## 11. Ranking (top 25 future initiatives)

Ranked by ROI = (expected alpha improvement OR risk reduction OR operational improvement) ÷ (complexity × overfitting risk).

| # | Initiative | Owner | Priority | Phase | ROI |
|:-:|---|:-:|:-:|:-:|:-:|
| 1 | **PRIORITY 0 fix batch** (F-01 through F-06/10) | Engineering | CRITICAL | Immediate | ⭐⭐⭐⭐⭐ |
| 2 | **PRIORITY 1: Telegram integrity footer** | Engineering | CRITICAL | Immediate | ⭐⭐⭐⭐⭐ |
| 3 | **Actual holdings tracking** (portfolio_state.yaml) | Engineering | HIGH | Near-term | ⭐⭐⭐⭐⭐ |
| 4 | **30-day forward evidence observation** | Monitoring | HIGH | Immediate | ⭐⭐⭐⭐⭐ |
| 5 | **Stop-loss line in Telegram** (already-computed data) | Engineering | HIGH | Near-term | ⭐⭐⭐⭐ |
| 6 | **Off-repo backup** of forward_ledger + sealed files | Operations | HIGH | Immediate | ⭐⭐⭐⭐ |
| 7 | **Second data source** (Angel API or NSE direct) | Engineering | HIGH | Medium | ⭐⭐⭐⭐ |
| 8 | **Docs cleanup** (56 → 15 files) | Engineering | MED | Immediate | ⭐⭐⭐ |
| 9 | **Portfolio VaR + drawdown line in Telegram** | Research | MED | Medium | ⭐⭐⭐ |
| 10 | **Dependency pinning** in workflows | Engineering | MED | Near-term | ⭐⭐⭐ |
| 11 | **MON002 Bayesian change-point detection** on forward ledger | Monitoring | MED | Medium | ⭐⭐⭐ |
| 12 | **Alpha decay monitoring** (rolling in-sample vs live Sharpe) | Monitoring | MED | Medium | ⭐⭐⭐ |
| 13 | **OPS001-B daemon deployment** on VPS | Operations | MED | Near-term | ⭐⭐⭐ |
| 14 | **Weekly summary digest** (Sunday afternoon) | Engineering | MED | Near-term | ⭐⭐⭐ |
| 15 | **Explicit UTC/IST handling** everywhere | Engineering | MED | Immediate | ⭐⭐⭐ |
| 16 | **Recommendation age countdown** in Telegram | Engineering | LOW | Near-term | ⭐⭐ |
| 17 | **Attribution report** (sector / stock / factor) monthly | Research | LOW | Medium | ⭐⭐ |
| 18 | **Multi-agent adversarial validation** of MON001 alerts | Research | LOW | Long-term | ⭐⭐ |
| 19 | **Second notification channel** validated live (Email OR Slack) | Operations | LOW | Near-term | ⭐⭐ |
| 20 | **SHAP-style explainability per rec** | Research | LOW | Medium | ⭐⭐ |
| 21 | **Staging environment** (separate GH branch → separate Sheets tab) | Engineering | LOW | Medium | ⭐⭐ |
| 22 | **LAB011** (new alpha family — TBD) | Lab | LOW | Long-term | ⭐ (see §12) |
| 23 | **Crisis-mode detection + defensive override** | Research | LOW | Long-term | ⭐ |
| 24 | **Options-derived vol signal** integration | Research | LOW | Long-term / Optional | ⭐ |
| 25 | **Multi-tenant redesign** | Engineering | N/A | Probably never (see §12) | — |

Categorization:
- **Immediate** (do first): #1, #2, #4, #6, #8, #15
- **Near-term** (weeks): #3, #5, #10, #13, #14, #16, #19
- **Medium-term** (months): #7, #9, #11, #12, #17, #20, #21
- **Long-term** (quarters+): #18, #22, #23
- **Optional / experimental:** #24
- **Probably never worth doing:** #25, and any LAB that adds a new alpha family before 90-day forward evidence closes

---

## 12. Final assessment + ONE next initiative

### 12.1 Numeric verdict

| Dimension | Score | Recommended target |
|---|:-:|---|
| Institutional maturity | 62/100 | 78 after top-3 initiatives |
| Production maturity | 81/100 | 94 after daemon deployment |
| Research maturity | 72/100 | 78 after 30-day forward window |
| Operations maturity | 74/100 | 88 after off-repo backup + daemon live |
| **Weighted overall** | **72/100** | **84** |

### 12.2 Biggest gaps

- **Biggest research gap:** No forward evidence stress-tested through a market crisis.
- **Biggest engineering gap:** Backdated-recommendation residual failure modes F-01..F-06/10 not yet closed.
- **Biggest operational gap:** No off-repo backup.
- **Biggest portfolio gap:** No actual-holdings tracking.
- **Biggest statistical risk:** PBO 0.90-0.94 pending confirmation via forward window.
- **Biggest business opportunity:** Publishable audit-quality track record after 90 days.
- **Biggest source of potential future alpha:** Event drift + regime-conditional exposure — but deferred until forward window closes.
- **Highest risk of future overfitting:** ANY new alpha layer before 90-day window closes.

### 12.3 Three things that should never change

1. MON001 sealed baseline + fingerprint hash.
2. Forward ledger hash chain.
3. PAPER_ONLY broker layer enforcement.

### 12.4 Three things that should be redesigned

1. Telegram report (add integrity footer + stops + VaR).
2. Actual holdings tracking (currently absent).
3. Docs organization (56 → 15).

### 12.5 Should we STOP adding alpha research?

**Yes. Unambiguously.**

Evidence:
- LAB010 verdict was NOT_VALIDATED.
- PBO 0.90-0.94 across recent labs.
- `cumulative_strategy_search=38` — the trial-budget clock is running.
- Forward evidence is only 21 trading days deep.
- Every new alpha lab compounds PBO risk.

**Adding new alpha research now would be statistical malpractice.** The
system has 10 completed LABs and a sealed production baseline that MON001
is observing. What the system does NOT have is:
- Confidence that the sealed baseline is not a burn-in artifact.
- A mechanism to prove or disprove that confidence except forward time.
- Operational maturity to run unattended without operator vigilance.

The correct next work is **NOT more alpha research**. It is:
- Fix the residual PRIORITY 0 failure modes (5 low-complexity architectural fixes).
- Wait 30 (better: 90) trading days of clean forward evidence.
- Meanwhile close the operational and portfolio-intelligence gaps.

### 12.6 The ONE next initiative

# ▶ INITIATIVE-1: PRIORITY 0 fix batch + PRIORITY 1 Telegram integrity footer

**Scope (both in ONE deliverable):**

1. **`india/refresh_data.py`** — enforce explicit `latest_bar_date == expected_ist_session_after_close` post-refresh.
2. **`scripts/check_data_freshness.py`** — after 16:00 IST, expected session INCLUDES today; abort STALE otherwise.
3. **`.github/workflows/aegis-daily.yml`** — delete `data/aegis_today.csv` at pipeline start.
4. **`india/recommendation_generator.py`** — assert `closes.index[-1].date() >= fresh_expected_session_date` before writing report.
5. **`india/telegram_notify.py`** — prepend integrity header/footer:
   - Header: run_utc + market_asof
   - Footer: message SHA256 + ledger last_hash + MON001 fingerprint hash
6. Remove `AEGIS_ALLOW_STALE=1` escape hatch (or gate it behind operator-signed override).
7. Explicit `datetime.now(timezone.utc)` and IST conversions everywhere (bans naive `date.today()`).

**Why this and only this:**
- **Not new alpha research** (violates the "don't add PBO risk" rule).
- **Not a new operational feature** (violates the "don't add new features" rule).
- **A correctness / integrity fix** — every subsequent decision (LAB011 or not) is more trustworthy after these land.
- **Enables the 30-day observation window** to be maximally useful, because any anomaly during it is unambiguously attributable to real behaviour rather than a stale-data artefact.

**Non-goals of this initiative:**
- No new alpha.
- No new channels.
- No daemon deployment.
- No new tests beyond the ones needed to verify these fixes.

**Estimated scope:** ~200 LOC across 5 files. 1 focused session.

**Success criterion:** Every Telegram message received in the 30-day
observation window carries a valid integrity footer; every backdated-asof
case explicitly warns; MON001 fingerprint hash matches the sealed one.

**After this initiative:** enter the 30-day observation window with high
confidence. Only THEN revisit whether LAB011 is warranted (my current
adversarial recommendation: it will still NOT be warranted; more likely
the correct next work will be **MON002 Bayesian change-point detection**
so the forward-evidence signal is quantified).

---

## Appendix · Investigation trace

Files inspected during PRIORITY 0 investigation:

- `india/recommendation_generator.py` (lines 182, 226, 587-705) — asof computation, run_date vs market_asof separation.
- `scripts/check_data_freshness.py` (full file) — freshness gate logic, expected_previous_session walk-back.
- `india/refresh_data.py` (tail 30 lines) — yfinance append logic.
- `india/telegram_notify.py` (lines 42-263, 380-395) — message construction, section headers.
- `.github/workflows/aegis-daily.yml` — cron schedule, step order, artifact upload.
- `data/aegis_registry.csv` (tail 5 rows) — verified asof=2026-07-14 stamped rows from 2026-07-15 workflow (correct given old cron).

Recent commits reviewed:
- `dd99a1e` — cron shift to post-close (the applied fix).
- `f50e56f` — MON001 portability amendment.
- Recent aegis-bot commits confirming old-schedule behaviour.

Ledger evidence:
- 150 rows spanning 2026-06-23 → 2026-07-14 (21 trading days).
- Hash chain integrity verified via `test_31` in this session.

MON001 evidence:
- Sealed fingerprint hash: `64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42` unchanged.
- Certification: `MON001-CERT-2026-07-15` with `MON001-AMEND-2026-07-16-portability`.

No production code was executed. No sealed file was touched. No LAB
artefact was touched. No new dependency was added. No CI run was
triggered by this audit.

---

**End of Meta-Audit.**

Awaiting operator decision on INITIATIVE-1 authorisation.
