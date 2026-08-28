# AEGIS · Delivery Data Contract · v1

**Status**: DRAFT · awaiting CEO approval before any Phase 5 implementation
**Author**: senior engineer (delivery-layer stabilization mandate)
**Baseline HEAD**: `f4b13dd1`
**Baseline test suite**: 469 passed · 1 skipped · zero failures
**Push freeze**: IN FORCE · no push authorization implied by this document
**Locked layers untouched**: R1 · R2 · E1/E2/E3 · research-promotion · Registry-decision logic · `xlsx_contract.py` · `xlsx_validator.py` · `ensemble_weights_adaptive.yaml` · `model_registry.jsonl` · `aegis_history*.xlsx`

---

## 0 · Purpose

Replace the eight competing informal definitions of "Active current", "Realized 90d", and "Lineage" with **one canonical population resolver per concept**. Every producer, banner, validator, and Definitions row consumes the resolver — none re-derives.

**Anti-goal**: make the next CI run green.
**Actual goal**: make it structurally impossible for the same class of population-count / provenance / trailer-row errors to recur.

---

## 1 · Absolute rules (constitutional · must never be violated)

| # | Rule | Enforcement |
|---|---|---|
| C1 | `CURRENT ≠ HISTORICAL` · never a bare metric name | banner labels · Definitions rows · validator messages |
| C2 | `LINEAGE ≠ REALIZED_ELIGIBLE` · lineage is a superset · realized excludes rotation artifacts and same-day rotations | separate resolvers · separate consumers |
| C3 | `CURRENT_SIGNAL ≠ CURRENT_HOLDING` · a holding without today's signal is not a signal row | separate Portfolio sections · schema difference documented |
| C4 | `MISSING ≠ LOW` · `MISSING ≠ PENDING` · `MISSING ≠ 0` | producer emits explicit `—` or `NOT AVAILABLE` · never a categorical fallback |
| C5 | A validator MUST NOT need special knowledge of trailer/summary/decoration rows | trailer rows live in a different sheet · body contains only lineage |
| C6 | A banner MUST NOT independently count worksheet rows | banner reads the resolver output · workbook is a projection |
| C7 | XLSX formatting (fill/emoji/color) MUST NOT determine population membership | membership is a Registry+snapshot fact · rendering is downstream |
| C8 | Two producers MUST NOT independently compute the same population | one resolver · N consumers |

---

## 2 · Population catalogue · canonical definitions

Eight populations exist. Each has ONE canonical machine-testable resolver. Consumers reference the resolver name — no consumer re-implements the rule.

### 2.1 · `CURRENT_ACTIVE`
> Positions the operator currently holds under any runner.

| Attribute | Value |
|---|---|
| Source of truth | `opportunity_registry` (event-sourced JSONL) |
| Resolver | `backend.delivery.populations.current_active(root, market, asof)` |
| Inclusion | latest event per `opportunity_id` where `status == "ACTIVE"` AND parquet close exists on `asof` or nearest 5 trading days prior |
| Exclusion | `status ∈ {CLOSED, REJECTED}` · `status == "ACTIVE"` but parquet stale > 5 trading days (marked STALE, separate list) |
| Identity key | `opportunity_id = f(market, runner, ticker, created_date)` |
| Lifecycle | CURRENT · decision-bearing |
| Missing-value semantics | none — every ACTIVE has ticker + runner + created_date by Registry invariant |
| Consumers | Portfolio ACTIVE section · Portfolio banner "Active (current)" · canonical `INVESTMENT_ACTIVE.json` · I25 header count · I27 count reconciliation |

### 2.2 · `CURRENT_NEW`
> Subset of `CURRENT_ACTIVE` where the position was born today.

| Attribute | Value |
|---|---|
| Source of truth | `opportunity_registry` |
| Resolver | `backend.delivery.populations.current_new(root, market, asof)` |
| Inclusion | `pid ∈ CURRENT_ACTIVE` AND `created_date == asof` |
| Exclusion | positions carried from prior days |
| Identity key | same as `CURRENT_ACTIVE` |
| Lifecycle | CURRENT · decision-bearing |
| Consumers | Portfolio NEW section header · Telegram summary "n new today" |

### 2.3 · `CURRENT_SIGNAL`
> Positions for which R1 or R2 fired a signal in today's `aegis_history` XLSX.

| Attribute | Value |
|---|---|
| Source of truth | today's `aegis_history_{market}_{asof}.xlsx` produced by R1/R2 |
| Resolver | `backend.delivery.populations.current_signal(root, market, asof)` |
| Inclusion | row present in source XLSX for `asof` with `Runner ∈ {R1, R2}` AND `Status ∈ {NEW, ACTIVE, ACTIVE+}` |
| Exclusion | `Status == EXIT` · `Runner ∈ {SHADOW, MOMENTUM}` · `Status == SUGGESTED` |
| Identity key | `(market, runner, ticker, recommended_date)` |
| Schema | full engine enrichment (Investability, Health, Confidence, Sector, urgency, Inv Quality) |
| Missing-value semantics | none — engine emits every field |
| Consumers | Portfolio ACTIVE section body (enriched rows) |

### 2.4 · `CURRENT_HOLDING_NO_SIGNAL`
> Positions in `CURRENT_ACTIVE` that did NOT get today's signal from R1/R2.

| Attribute | Value |
|---|---|
| Source of truth | `CURRENT_ACTIVE` MINUS `CURRENT_SIGNAL` |
| Resolver | `backend.delivery.populations.current_holding_no_signal(root, market, asof)` |
| Inclusion | `pid ∈ CURRENT_ACTIVE` AND `(runner, ticker) ∉ CURRENT_SIGNAL` |
| Exclusion | same as `CURRENT_ACTIVE` |
| Schema | **holding-only** — ticker · runner · entry_date · entry_price · current_price · pnl_pct · days_held · sector · status="HOLD" |
| Missing-value semantics | **Investability = `—`** · **Inv Quality = `—`** · **Urgency = `—`** · **Sector = `—` if not in `configs/sector_map.json`** · **NEVER `LOW` · NEVER `PENDING` · NEVER `0`** |
| Row rendering | grey/muted background · explicit "HOLD · no signal today" tag |
| Consumers | Portfolio ACTIVE section body (holdings-only rows) · **rendered in a visually distinct segment below signal rows** |

### 2.5 · `CURRENT_SUGGESTED`
> Investability engine's top-ranked candidates that are NOT currently active.

| Attribute | Value |
|---|---|
| Source of truth | today's `aegis_history` rows with `Runner == SHADOW` OR `Status == SUGGESTED` |
| Resolver | `backend.delivery.populations.current_suggested(root, market, asof)` |
| Inclusion | source-XLSX row where runner ∈ SHADOW OR status == SUGGESTED |
| Exclusion | tickers currently in `CURRENT_ACTIVE` · tickers CLOSED in last 30d |
| Identity key | `(market, runner, ticker)` |
| Schema | Investability engine fields |
| Consumers | Portfolio SUGGESTED section (visually distinct — purple/blue rendering) |

### 2.6 · `LINEAGE`
> Every canonical Registry-CLOSED event within a 90-day exit window.

| Attribute | Value |
|---|---|
| Source of truth | `opportunity_registry` |
| Resolver | `backend.delivery.populations.lineage_90d(root, market, asof)` |
| Inclusion | latest event per pid where `status == "CLOSED"` AND `closed_date ∈ [asof - 90d, asof]` |
| Exclusion | none within window · orphans + rotations + real exits ALL included |
| Identity key | `(opportunity_id, closed_date)` |
| Sort key | (category_priority ASC · closed_date DESC · ticker ASC) where priority is `0` for real trades and `1` for ORPHAN_AUTO_CLOSE |
| Consumers | Exit History body rows · I20 validator (`Registry-CLOSED ⊆ body`) · A23 validator (`body → has Registry lineage`) |

### 2.7 · `REALIZED_90D`
> Statistical subset of `LINEAGE` eligible for win-rate / P&L computation.

| Attribute | Value |
|---|---|
| Source of truth | derived from `LINEAGE` |
| Resolver | `backend.delivery.populations.realized_90d(root, market, asof)` |
| Inclusion | `pid ∈ LINEAGE` AND `abs(pnl_pct) > 0.01` AND `closed_date != created_date` |
| Exclusion | rotation artifacts (`|pnl| ≤ 0.01`) · same-day rotations |
| Metrics | `n_exits` · `realized_pnl_pct = sum(pnls)` · `wr_pct = n_positive / n_exits · 100` · `n_positive = count(pnl > 0)` (strict) |
| Composition disclosure | 6-category breakdown MUST accompany the metric block (orphan / rotation / stop_loss / target_hit / time_stop / signal_exit) |
| Consumers | Exit History summary banner · monthly rollup |

### 2.8 · `MONTHLY_SUMMARY`
> Aggregate rollup of `REALIZED_90D` by calendar month.

| Attribute | Value |
|---|---|
| Source of truth | derived from `REALIZED_90D` |
| Resolver | `backend.delivery.populations.monthly_summary(root, market, asof)` |
| Inclusion | one row per `(year, month)` present in `REALIZED_90D` |
| Physical location | **separate XLSX sheet** named `Monthly Summary` — NEVER inside Exit History body |
| Fields per row | `month · n_exits · realized_pnl_pct · wr_pct · n_positive · n_negative` |
| Consumers | Monthly Summary sheet only · never scanned by any validator that operates on Exit History |

---

## 3 · Contract matrix (Phase 4 deliverable)

| Population | Producer / Resolver | Required Lineage | Banner-eligible | Stats-eligible | Workbook Sheet | Validator |
|---|---|:-:|:-:|:-:|---|---|
| `CURRENT_ACTIVE` | `populations.current_active` | Registry ACTIVE | ✅ | ❌ | Portfolio body (ACTIVE section) | I25 header count · I27 |
| `CURRENT_NEW` | `populations.current_new` | Registry ACTIVE + created_today | ✅ (sub-count) | ❌ | same section · flagged | (informational) |
| `CURRENT_SIGNAL` | `populations.current_signal` | source XLSX today | ❌ (subset of CURRENT_ACTIVE) | ❌ | Portfolio · enriched rows | (informational) |
| `CURRENT_HOLDING_NO_SIGNAL` | `populations.current_holding_no_signal` | Registry ACTIVE − CURRENT_SIGNAL | ❌ (subset of CURRENT_ACTIVE) | ❌ | Portfolio · holding-only rows | (informational) |
| `CURRENT_SUGGESTED` | `populations.current_suggested` | source XLSX today | ❌ (own banner) | ❌ | Portfolio · SUGGESTED section | (informational) |
| `LINEAGE` | `populations.lineage_90d` | Registry CLOSED · 90d window | ❌ (not a summary metric) | ❌ | Exit History body | I20 · A23 |
| `REALIZED_90D` | `populations.realized_90d` | LINEAGE − rotation-artifacts | ✅ | ✅ | Exit History summary block only | I25 body count reconcile |
| `MONTHLY_SUMMARY` | `populations.monthly_summary` | REALIZED_90D aggregated | ❌ | ❌ | **`Monthly Summary` sheet** | (own · doesn't touch Exit History) |

---

## 4 · Root causes (Phase 2 · what actually broke)

### 4.1 · Portfolio banner count instability

**Symptom**: banner shows 37 · Definitions declares ACTIVE definition · numbers don't match.

**Root cause**: two independent formulas in `scripts/telegram_command_center_send.py`:
- line ~1517: `_n_active = len(_active_pnls)` (Registry-native)
- line ~3591: `_n_visible = len(_visible_by_row)` (scans Portfolio sheet body · counts everything except SHADOW/MOMENTUM/EXIT/SUGGESTED)

The FINAL banner emits `_n_visible`. It counts NEW + ACTIVE + ACTIVE+ + orphan-auto-appended Path-A rows. Definitions declares "unique Position IDs classified as ACTIVE, not SUGGESTED/EXIT" — silent on whether NEW is included, silent on whether Path-A appends count.

**Fix (Phase 5)**: banner reads `populations.current_active()` count directly. `_n_visible` deleted. Definitions row updated to reference the resolver.

### 4.2 · Exit History banner ≠ body

**Symptom**: summary says 25 exits · body has 38 numeric-P&L rows.

**Root cause**: three independent "realized 90d" computations:
- `_realized_pnls` (Registry-native, excludes same-day rotations, WR=`p>0.5%`)
- `_eh_n` scan of body (includes 0% rotations, WR=`p>0`)
- `outcome_ledger.compute_realized_90d` (excludes `|pnl| ≤ 0.01`, WR=`p>0`)

Same rows · three answers.

**Fix (Phase 5)**: `LINEAGE` is body population · `REALIZED_90D` is banner population · both derive from `populations.lineage_90d`. Only ONE win threshold: `pnl > 0` strict. Only ONE zero-tolerance: `|pnl| ≤ 0.01`.

### 4.3 · Monthly summary polluting Exit History body

**Symptom**: rows "AUG 2026", "MONTH", "MONTHLY P&L SUMMARY" fabricate A23 failures.

**Root cause**: monthly summary written inline into Exit History body starting at row ~N. Every validator now has to teach itself the trailer-skip trick (`──` / `MONTH` / space check). Violates C5.

**Fix (Phase 5)**: monthly summary moves to a NEW sheet `Monthly Summary`. Exit History body contains ONLY `LINEAGE` rows. All trailer-skip logic deleted from I28/A22/A23/I25.

### 4.4 · Grey-row semantic corruption

**Symptom**: Path-A completeness appends Registry-ACTIVE rows with `LOW` urgency, `PENDING` quality, decimal P&L, blank sector.

**Root cause**: Path-A treats `CURRENT_HOLDING_NO_SIGNAL` as if it were `CURRENT_SIGNAL` and fabricates fields to match the schema. Violates C3 and C4.

**Fix (Phase 5)**: `CURRENT_HOLDING_NO_SIGNAL` has its own schema · missing engine fields render as `—` · P&L formatted as `%` (matching signal rows) · Sector reads from `sector_map.json` or `—`. NO fabricated categoricals.

### 4.5 · Duplicate rows

**Symptom**: same ticker under R1 and R2 sometimes deduped, sometimes not.

**Root cause**: dedup key is inconsistent. INDIGO filter uses `(market, runner, ticker, recommended_date)` · other paths use `ticker` alone.

**Fix (Phase 5)**: canonical position identity is `opportunity_id = f(market, runner, ticker, created_date)` everywhere. Ticker-only comparisons removed.

### 4.6 · I26 / I28 provenance

**Symptom**: EIX price drift · EA impossible closed_date.

**Root cause**: source-XLSX rows silently restamped between source builds. Prior fix (canonical resolver) works. Must preserve — canonical resolver stays authoritative.

**Fix (Phase 5)**: no change to canonical resolver. `CURRENT_SIGNAL` producer calls `canonical_entry.resolve` for every entry_date/entry_price · never trusts source-XLSX raw values.

---

## 5 · XLSX sheet contracts

| Sheet | Population | Row schema | Trailer content allowed? |
|---|---|---|:-:|
| `AEGIS {MARKET} History` | all signals (audit lineage) | full engine schema | NO |
| `Portfolio` | `CURRENT_ACTIVE ∪ CURRENT_SUGGESTED` in 3 sections | signal rows enriched · holding rows sparse · suggested rows engine | NO |
| `Exit History (90d)` | `LINEAGE` only | canonical exit schema | **NO — monthly summary moves out** |
| `Monthly Summary` (**NEW**) | `MONTHLY_SUMMARY` | month · n · pnl · wr · pos · neg | (this IS the summary sheet) |
| `Definitions` | population definitions text | 2-col · label · rule | (informational only) |

---

## 6 · Validator contracts (already locked · unchanged)

| Validator | Population validated | Passes when |
|---|---|---|
| I20 | `LINEAGE` | every pid in `populations.lineage_90d` present in Exit History body |
| I25 | `CURRENT_ACTIVE` · `LINEAGE` | banner headers = resolver counts |
| I26 | `CURRENT_ACTIVE.entry_price` | canonical resolver value matches parquet close on entry_date |
| I27 | `CURRENT_ACTIVE.entry_date` | trading-calendar valid |
| I28 | `LINEAGE.closed_date` | trading-calendar valid AND `closed_date ≥ entry_date` |
| A22 | `LINEAGE` composition | 6-category classifier is exhaustive · no `other > 0` |
| A23 | `LINEAGE` | every Exit History body row → has Registry-CLOSED lineage (no fabricated rows) |

**No validator needs trailer-skip logic after `MONTHLY_SUMMARY` moves out.**

---

## 7 · Banner counting rules

| Banner | Formula | Reads from |
|---|---|---|
| Portfolio "Active (current)" | `len(populations.current_active(root, market, asof))` | resolver ONLY |
| Portfolio NEW badge | `len(populations.current_new(...))` | resolver ONLY |
| Portfolio SUGGESTED badge | `len(populations.current_suggested(...))` | resolver ONLY |
| Exit History header | `len(populations.lineage_90d(...))` | resolver ONLY |
| Exit History realized-summary | `populations.realized_90d(...).n_exits / .wr_pct / .realized_pnl_pct` | resolver ONLY |

**No banner scans a worksheet.** (Deletes lines 3591 and 3608-3625 of the current Telegram command center.)

---

## 8 · Missing-data semantics (Rule C4 concrete)

| Field | Signal row source | Holding-no-signal row | Suggested row |
|---|---|---|---|
| Investability | engine value | `—` (never blank string, never `PENDING`) | engine value |
| Inv Quality | engine value | `—` (never `PENDING`) | engine value |
| Urgency | engine value | `—` (never `LOW`) | engine value |
| Sector | `configs/sector_map.json` | `configs/sector_map.json` OR `—` | `configs/sector_map.json` |
| P&L % | 2-decimal % (e.g. `+2.41%`) | 2-decimal % (same format) | 2-decimal % if held |
| Health / Confidence / Rank | engine value | `—` | engine value |
| Days held | integer | integer | 0 |
| Entry date | canonical resolver | canonical resolver | recommended_date |

---

## 9 · Definitions sheet content

The Definitions sheet is the operator-facing description of the resolvers. Every line MUST reference exactly one resolver by name. Proposed rows:

```
Active (current)        = populations.current_active(): Registry latest-event ACTIVE, parquet-fresh
NEW                     = populations.current_new(): CURRENT_ACTIVE where created_date == asof
Suggested               = populations.current_suggested(): SHADOW / SUGGESTED tickers not currently active
Lineage (Exit History)  = populations.lineage_90d(): Registry CLOSED events, 90-day window
Realized 90d            = populations.realized_90d(): LINEAGE minus rotation-artifacts (|pnl| <= 0.01)
Win Rate (realized)     = n_positive / n_exits · positive = pnl_pct > 0 (strict)
Monthly Summary         = populations.monthly_summary(): REALIZED_90D aggregated by month · SEPARATE sheet
Missing field           = "—" · never LOW · never PENDING · never 0
```

---

## 10 · Forbidden fallback behaviour (Rule C4 · negative form)

The following patterns are contract violations and MUST fail regression tests:

- `Urgency = "🟢 LOW"` when engine did not emit an urgency for that row
- `Inv Quality = "⏳ PENDING"` when engine did not emit a quality assessment
- `Investability = 0` when engine did not score the position
- `Sector = ""` (empty string) when the caller could have written `—`
- `P&L = 0.0241` (decimal fraction) mixed with `+2.41%` in the same column
- `orphan_auto_close` counted as a "win" because `pnl > 0` when the reason is Registry cleanup
- Two rows for same `(market, runner, ticker, created_date)` in the same section
- "Monthly summary" row physically located inside Exit History body
- Validator `if "MONTH" in row: continue` (validator taught to skip decoration)

---

## 11 · Determinism contract

Every resolver MUST be a pure function of its inputs. Called twice on unchanged Registry + parquet state at the same `asof`, it produces byte-identical output. Regression test: run pipeline generation N=3 times · compare XLSX bytewise · zero unexplained differences.

Non-deterministic sources currently in the code (to be removed in Phase 5):
- iteration order of `set()` in dedup
- `datetime.now()` used as row-identity input
- random ordering when sort key ties

---

## 12 · Change surface (Phase 5 preview · no code written yet)

**New files** (one canonical resolver module):
- `backend/delivery/populations.py` (new · ~300 lines · 8 resolver functions + tests)

**Modified files** (consume resolvers · remove local duplication):
- `scripts/telegram_command_center_send.py` (delete ~200 lines of banner/count/dedup · replace with resolver calls · Path-A schema fix for holding-only rows)
- `backend/delivery/outcome_ledger.py` (redirects to `populations.realized_90d` · keeps public API)
- `backend/delivery/portfolio_source.py` (redirects to `populations.current_active` · keeps public API)
- XLSX builder (adds new `Monthly Summary` sheet · removes trailer rows from Exit History emit)

**Deleted** (no longer needed):
- Trailer-skip logic in `wave_regression.py` (A22, A23)
- Trailer-skip logic in `xlsx_validator.py` (I28)
- `_visible_by_row` scan (Portfolio banner)
- `_eh_n / _eh_wr / _eh_sum` scan (Exit History banner)

**LOCKED · NO CHANGES**:
- R1 · R2 · E1 · E2 · E3
- `xlsx_contract.py`
- `xlsx_validator.py` invariant definitions (may add reads to resolver output but no semantic change)
- `ensemble_weights_adaptive.yaml`
- `model_registry.jsonl`
- `aegis_history*.xlsx` (source XLSX untouched)
- research-promotion path
- Registry decision logic
- Trading rules

---

## 13 · Test-plan preview (Phase 6)

Every resolver gets a dedicated test file. At minimum:

- `tests/delivery/test_populations_current_active.py` — Registry ACTIVE ↔ resolver output identity
- `tests/delivery/test_populations_lineage_90d.py` — Registry CLOSED ↔ resolver output identity
- `tests/delivery/test_populations_realized_90d.py` — rotation-artifact + same-day exclusion
- `tests/delivery/test_populations_monthly_summary.py` — aggregation correctness
- `tests/delivery/test_current_holding_no_signal_schema.py` — no `LOW`/`PENDING`/`0` fabrication
- `tests/delivery/test_banner_reads_resolver_only.py` — grep `_n_visible` absent · grep `_eh_n` absent
- `tests/delivery/test_monthly_summary_not_in_exit_history.py` — Exit History body last-row is a lineage row
- `tests/delivery/test_determinism_3_runs.py` — 3× generation · byte-identical XLSX
- `tests/delivery/test_i20_i25_i26_i27_i28_still_pass.py` — locked validators still green under new architecture
- `tests/delivery/test_a22_a23_no_trailer_skip.py` — validators contain NO string-skip logic

**Both markets** (USA + India) run the full suite. Both must pass or Phase 5 is rolled back.

---

## 14 · Absolute stop-conditions (Phase 5 will halt if any triggers)

Per the operating directive:
- Any population definition remains ambiguous
- Any producer uses a formula different from the resolver
- Any banner reconstructs a count independently
- Any workbook section mixes populations
- Any missing value is fabricated
- Any stale value presented as current
- I20 / A23 / I26 / I28 fails
- USA fails · India fails
- Repeated generation is non-deterministic
- Any production / R1 / R2 / E1-E3 diff is non-zero
- `overrideallow` is required

**On any stop condition: revert · report · halt · do not push.**

---

## 15 · Explicit non-authorization statement

This document is a specification.
No production code has been modified.
No commit has been made.
No push has been made.
Phase 5 begins ONLY when CEO explicitly authorizes with the specific words:
> "authorized to implement DELIVERY_DATA_CONTRACT_v1 · Phase 5 proceed"

Silence is not authorization. Approval of the spec content is not implicit authorization to push. Every subsequent phase (5 → 6 → 7 → 8 → 9 → 10 → 11) reports back before the next phase begins.

---

## 16 · Baseline evidence

```
HEAD                    f4b13dd1becabc3a9fd6bc5d75e42154361e80d8
origin/main             f4b13dd1becabc3a9fd6bc5d75e42154361e80d8  (in sync)
branch                  main
push freeze             ACTIVE (per CEO 2026-08-28)
PRODUCTION_LOCK.md      present
overrideallow           not set anywhere
test suite              469 passed · 1 skipped · 0 failed  (tests/delivery + tests/research)
locked-file diffs       zero
```

---

**Ready for CEO review.** Awaiting explicit go/no-go on §12 change surface and §15 authorization before writing any Phase 5 code.

---

# PART II · OBSERVED EVIDENCE + PRODUCER-CONSUMER DAG

*Added 2026-08-28 during read-only forensic reconciliation. Zero code touched.*

## II.1 · Population enumeration reconciled to CEO's 8

Prior spec §2 had 5 CURRENT_* populations. CEO's 2026-08-28 directive enumerates 8 distinct populations and separates CURRENT from ACTIVE. Reconciled mapping below.

| CEO's name | Definition | Prior spec name |
|---|---|---|
| CURRENT | Every row visible in Portfolio sheet (universe · not a status) | (merged with CURRENT_ACTIVE — split needed) |
| ACTIVE | Registry latest-event `status == "ACTIVE"` (canonical held-position set) | CURRENT_ACTIVE |
| NEW | ACTIVE where `created_date == asof` | CURRENT_NEW |
| SUGGESTED | Investability engine candidates, not currently ACTIVE | CURRENT_SUGGESTED |
| SHADOW | `Runner == "SHADOW"` rows (research/audit runner) | (nested inside SUGGESTED — split needed) |
| LINEAGE | Registry `status == "CLOSED"` events, 90d window | LINEAGE |
| REALIZED_90D | LINEAGE minus rotation artifacts + same-day rotations | REALIZED_90D |
| MONTHLY_SUMMARY | REALIZED_90D aggregated by month | MONTHLY_SUMMARY |

**Reconciliation required in Phase 5**: split my `CURRENT_ACTIVE` into distinct `CURRENT` (universe) and `ACTIVE` (canonical Registry-native). Split my `CURRENT_SUGGESTED` into `SUGGESTED` and `SHADOW`.

## II.2 · Producer → transformer → consumer DAG

```
                       ┌──────────────────────────────────────────┐
                       │       opportunity_registry (JSONL)       │  SOURCE OF TRUTH
                       │        · event-sourced · append-only     │  (never mutated)
                       └────────────────────┬─────────────────────┘
                                            │ load_all(root)
                       ┌────────────────────┴─────────────────────┐
                       ↓                                          ↓
             ┌─────────────────────┐              ┌────────────────────────────┐
             │ ACTIVE pop resolver │              │  LINEAGE pop resolver      │
             │ (latest per pid ·   │              │  (latest per pid ·         │
             │  status==ACTIVE ·   │              │   status==CLOSED ·         │
             │  parquet fresh)     │              │   closed within 90d)       │
             └──────┬─────────┬────┘              └───────┬──────────┬─────────┘
                    │         │                           │          │
                    │         │              ┌────────────┴──┐       │
                    │         │              │ REALIZED_90D  │       │
                    │         │              │ (LINEAGE      │       │
                    │         │              │  minus 0%     │       │
                    │         │              │  rotations)   │       │
                    │         │              └───────┬───────┘       │
                    │         │                      │               │
                    │         │              ┌───────┴───────┐       │
                    │         │              │ MONTHLY_SUMM  │       │
                    │         │              │ (by month)    │       │
                    │         │              └───────┬───────┘       │
                    │         │                      │               │
       ┌────────────┴──┐      │                      │               │
       │  aegis_history │     │                      │               │
       │  {mkt}.xlsx    │     │  (source XLSX enrichment layer)     │
       │  (R1/R2 signals│     │                      │               │
       │   for asof)    │     │                      │               │
       └────┬───────────┘     │                      │               │
            │                 │                      │               │
       ┌────┴──────┐          │                      │               │
       │ CURRENT_  │          │                      │               │
       │ SIGNAL    │          │                      │               │
       │ (r1/r2 x  │          │                      │               │
       │  today)   │          │                      │               │
       └────┬──────┘          │                      │               │
            │                 │                      │               │
       ┌────┴──────┐    ┌─────┴──────┐               │               │
       │ SUGGESTED │    │ CURRENT_   │               │               │
       │ SHADOW    │    │ HOLDING_   │               │               │
       │ (from src │    │ NO_SIGNAL  │               │               │
       │  XLSX)    │    │ (ACTIVE −  │               │               │
       │           │    │  CURRENT_  │               │               │
       │           │    │  SIGNAL)   │               │               │
       └────┬──────┘    └─────┬──────┘               │               │
            │                 │                      │               │
            └────────┬────────┴────────┐             │               │
                     ↓                 ↓             ↓               ↓
             ┌─────────────────────────────────────────────────────────┐
             │             XLSX BUILDER (delivery layer)               │
             │  · Portfolio sheet (3 sections + banner)                │
             │  · Exit History sheet (LINEAGE only)                    │
             │  · Monthly Summary sheet (separate)  ← Phase 5 addition │
             │  · Definitions sheet                 ← Phase 5 addition │
             │  · {Market} History sheet (full audit)                  │
             └────────────────────────┬────────────────────────────────┘
                                      │
                                      ↓
             ┌─────────────────────────────────────────────────────────┐
             │            xlsx_validator (LOCKED · unchanged)          │
             │  · I8/I25 header count reconciles                       │
             │  · I11 ACTIVE has entry_price                           │
             │  · I15 required sheets present                          │
             │  · I16 required headers present                         │
             │  · I20 Registry-CLOSED ⊆ Exit History body              │
             │  · I26 entry_price immutable                            │
             │  · I27 entry_date legitimate                            │
             │  · I28 exit_date legitimate                             │
             │  · I29 current_price reconciles to parquet              │
             │  · A22/A23 in wave_regression                           │
             └────────────────────────┬────────────────────────────────┘
                                      │ verdict == PASS
                                      ↓
             ┌─────────────────────────────────────────────────────────┐
             │        Telegram Command Center · gate + POST            │
             │  · sends per-market XLSX only if validator PASS         │
             │  · never sends unified aegis_history.xlsx               │
             └─────────────────────────────────────────────────────────┘
```

## II.3 · Observed state · shipped artifacts as of `f4b13dd1`

### II.3.1 · India `reports/telegram/aegis_history_india.xlsx`

| Sheet | Rows | Observed |
|---|---:|---|
| Portfolio | 28 | banner "Active: 19 positions" · body 24 data rows · header at r4 |
| Exit History (90d) | 42 | banner "Total: 22 exits" · **rows 40-42 are MONTHLY P&L SUMMARY trailer** (contract violation C5) |
| AEGIS INDIA History | 598 | audit lineage · OK |

**Portfolio body composition (24 rows)**:
- 5 rows Runner=SHADOW · DECISION=SUGGESTED (r5-r7 · rendered inline with ACTIVE rows · no visual separation)
- 11 rows DECISION=ACTIVE+ · Lifecycle=ACTIVE · Runner=R1
- 5 rows DECISION=ACTIVE · Lifecycle=ACTIVE · Runner=R1 or R2
- 3 rows DECISION=NEW · Lifecycle=NEW · Runner=R1

**Registry vs banner divergence**:
- Registry ACTIVE (latest-per-pid) = **28**
- canonical INVESTMENT_ACTIVE = **28** (I8 confirms)
- Portfolio banner "Active" = **19**
- **Discrepancy = 9 Registry-ACTIVE positions not surfaced in Portfolio at all**

**Exit History trailer contamination** (row 40-42):
```
r40: ── MONTHLY P&L SUMMARY (last 3 mont |  |  |  |  |  |  |  |
r41: Month | N Exits | Wins | Losses | Total P&L % | Positive... | Win Rate
r42: Aug 2026 | 22 | 10 | 12 | +13.18% | +31.61% | -18.43% | 45.5%
```
Violates C5. Both A22 and A23 must implement trailer-skip to survive (they do · confirmed).

**P&L formatting inconsistency**: body col 10 stores DECIMAL (e.g. `-0.0521`, `0.039`) · header banner states `+13.18%` (percent). Mixed format in same column class.

### II.3.2 · USA `reports/telegram/aegis_history_usa.xlsx`

| Sheet | Rows | Observed |
|---|---:|---|
| Portfolio | 30 | banner has TOTALLY DIFFERENT format from India (COMBINED PORTFOLIO / Realized / Unrealized) |
| **Exit History (90d)** | — | **SHEET MISSING** · this is validator I15 FAIL |
| AEGIS USA History | 38 | audit lineage · thin |

**USA Portfolio body (25 rows)**:
- **13 rows literally labeled `DECISION = "ARTIFACT"` and `Lifecycle = "ARTIFACT"`** · these are same-day-rotation placeholders emitted at telegram_command_center_send.py:1016 (`h_decision = "⚪ ARTIFACT · not held"`) but not filtered out of Portfolio
- 11 rows DECISION=PROTECT · Lifecycle=NEW (real signal rows)
- 1 row DECISION=HOLD · Lifecycle=NEW
- **10 duplicated tickers**: AAPL · GS · JPM · KO · NVDA · HON · MMM · MSFT · TRV · V (each appears 2×)
- 15 unique tickers total · 25 body rows

**USA banner values** (line 4 of the sheet):
```
COMBINED PORTFOLIO | -0.7878 | 25 positions | Win rate | 8.0% (2W / 11L / 12 flat)
```
- "25 positions" includes the 13 ARTIFACT junk rows (contract violation C7)
- WR 8.0% counts 12 "flat" (0% pnl) rotations in the denominator → misleading

**Validator failures on USA (9 total)**:
| Code | Detail |
|---|---|
| I4 | 10 duplicate (ticker, runner) rows |
| I6 | 19 CLOSED tickers rendered as ACTIVE |
| I11 | 13 ACTIVE rows missing entry_price |
| I15 | Exit History (90d) sheet MISSING |
| I16 | 11 required headers missing |
| I20 | 504 Registry-CLOSED · 0 in Exit History body · 504 missing (because sheet doesn't exist) |
| I23 | 26 rows with non-canonical Runner (values seen: "SECTOR", "—") |
| I27 | 1 entry_date value = literal string "Days" |
| I29 | AAPL current_price = 0.07 vs parquet 304.91 (99.98% drift) · GS 0.0 vs 1034.41 (100% drift) |

### II.3.3 · Registry state per market

| Market | Total pids | ACTIVE | CLOSED | of which ORPHAN_AUTO_CLOSE |
|---|---:|---:|---:|---:|
| India | 62 | 28 | 34 | 0 |
| USA | 546 | 18 | 528 | **490** |

**USA orphan-explosion root**: 490 of 528 CLOSED events are `ORPHAN_AUTO_CLOSE` from the 2026-08-20 07:04:20 UTC bootstrap backfill (487 pids created in one minute · not real trades · Registry-cleanup artifacts).

## II.4 · USA/India architectural divergence (proof of non-symmetry)

| Dimension | India | USA | Same? |
|---|---|---|:-:|
| Portfolio sheet exists | ✅ | ✅ | ✅ |
| Exit History sheet exists | ✅ | ❌ | ❌ |
| Definitions sheet exists | ❌ | ❌ | (both missing) |
| Monthly Summary sheet exists | ❌ (inline trailer) | ❌ | (both missing) |
| Portfolio banner format | "Active: N positions · Positive: X · Realized 90d" | "COMBINED PORTFOLIO N positions · Win rate X" | ❌ |
| Portfolio header columns | 12 (Ticker · ACTION · DECISION · Lifecycle · Month · ...) | 12 (Ticker · DECISION · Lifecycle · Price Trigger · ... · Entry Date · Exit Date) | ❌ different |
| ARTIFACT rows in Portfolio body | none | 13 | ❌ |
| Duplicate `(ticker, runner)` rows | 0 | 10 | ❌ |
| P&L column format | decimal (0.039) | percent (+7.31%) | ❌ mixed |
| Registry ACTIVE count | 28 | 18 | different scale (expected) |
| Registry CLOSED count | 34 | 528 (490 orphan) | different scale (expected) |
| Banner reads worksheet? | yes (`_n_visible`) | yes (different scanner) | both violate C6 |

**Verdict**: markets do NOT run the same architecture · they run subtly different XLSX builders and banner formatters with different filters. India is closer to spec · USA is the worse offender · both violate the same class of contract rules.

## II.5 · Complete discrepancy list (numbered · every one anchored to code)

1. **India banner "Active: 19"** ≠ Registry ACTIVE **28** ≠ canonical INVESTMENT_ACTIVE **28**
   `telegram_command_center_send.py:3591` `_n_visible` scan excludes 9 Registry-ACTIVE positions

2. **India Exit History body row 40-42** contains monthly-summary trailer rows
   `telegram_command_center_send.py:~3300` writes summary inline · violates C5

3. **India Exit History P&L column** stores decimal (0.039) · banner states percent (+13.18%)
   XLSX builder writes decimal · banner scanner reads and multiplies · format mismatch is invisible to reader

4. **USA has no Exit History sheet**
   XLSX builder for USA never creates the sheet · validator I15 FAIL · I20 FAIL

5. **USA Portfolio has 13 ARTIFACT rows**
   `telegram_command_center_send.py:1016` emits "⚪ ARTIFACT · not held" · downstream filter doesn't drop them for USA · violates C7

6. **USA Portfolio has 10 duplicated tickers**
   dedup key inconsistent between markets · violates C8 identity contract

7. **USA I11 FAIL** · 13 ACTIVE rows missing entry_price
   the 13 ARTIFACT rows have no entry_price · they should not have been rendered as ACTIVE

8. **USA I29 FAIL** · AAPL 0.07 vs 304.91 · GS 0.0 vs 1034.41
   current_price field storing wrong-scale value · likely stale P&L decimal being written to price column

9. **USA I23 FAIL** · runner column contains "SECTOR" as value
   XLSX row-offset bug · a header cell is landing in a data row · possibly the Portfolio banner rows are consuming the runner column region

10. **USA I27 FAIL** · entry_date="Days"
    Same row-offset bug · column header text ("Days Held") appears in the entry_date column

11. **USA I6 FAIL** · 19 CLOSED tickers rendered as ACTIVE
    USA Portfolio includes tickers whose Registry state is CLOSED

12. **USA banner "Win rate 8.0% (2W/11L/12 flat)"** counts 12 flat (0% rotations) in denominator
    Violates §7 canonical formula · WR should exclude `|pnl| ≤ 0.01`

13. **Both markets · Definitions sheet missing**
    Operator has no way to read the population definitions from the workbook itself

14. **Both markets · Monthly Summary is not a separate sheet**
    India: trailer rows in Exit History body · USA: no monthly rollup at all

15. **India Portfolio SUGGESTED rows (5)** rendered inline with ACTIVE rows
    No visual separation section · violates C3 (`CURRENT_SIGNAL ≠ CURRENT_SUGGESTED`)

## II.6 · Files/functions that Phase 5 would need to touch

| File | Function | Change | LOCKED? |
|---|---|---|:-:|
| `backend/delivery/populations.py` | NEW module | create 8 resolvers | new |
| `scripts/telegram_command_center_send.py` | ~1016 | stop emitting ARTIFACT as row Decision · route to separate ARTIFACT list not shown in Portfolio | no |
| `scripts/telegram_command_center_send.py` | ~1517 · ~2203 · ~3591 · ~3608-3625 | delete 4 competing banner-count formulas · replace with resolver call | no |
| `scripts/telegram_command_center_send.py` | Portfolio row emit loop | Path-A schema fix · `CURRENT_HOLDING_NO_SIGNAL` uses `—` not LOW/PENDING/0 | no |
| `scripts/telegram_command_center_send.py` | Portfolio SUGGESTED rendering | separate visual section · not inline | no |
| `scripts/telegram_command_center_send.py` | Exit History emit | drop monthly-summary trailer · move to new sheet | no |
| USA XLSX builder | (locate) | ADD Exit History sheet · ADD Definitions sheet · ADD Monthly Summary sheet · use same builder as India | no |
| USA Portfolio banner formatter | (locate) | replace with same formatter as India (unified) | no |
| `backend/delivery/outcome_ledger.py` | `compute_realized_90d` | redirect to `populations.realized_90d` | no |
| `backend/delivery/portfolio_source.py` | `build_active_positions` | redirect to `populations.active` | no |
| `backend/research/wave_regression.py` | A22 · A23 | DELETE trailer-skip logic once Monthly Summary moves out | no |
| `backend/delivery/xlsx_validator.py` | I28 · I25 | DELETE trailer-skip logic once Monthly Summary moves out | **LOCKED** — cannot modify validator semantics · only remove now-dead trailer-skip code with CEO's explicit approval |
| `xlsx_contract.py` | invariants | NO CHANGE | **LOCKED** |
| `ensemble_weights_adaptive.yaml` | any | NO CHANGE | **LOCKED** |
| `aegis_history*.xlsx` | source | NO CHANGE (Registry + parquet are truth) | **LOCKED** |
| R1 · R2 · E1/E2/E3 | any | NO CHANGE | **LOCKED** |

## II.7 · Tests required (per Phase 6 preview · unchanged)

Every resolver gets a dedicated test file · 3-run byte-identical determinism check · both markets · locked validators still green under new architecture.

## II.8 · Acceptance criteria (for post-authorization CI + XLSX)

Before Phase 5 changes can be considered "landed":
- `xlsx_validator.validate(india)` verdict = PASS (0 FAIL · 0 WARN acceptable if documented)
- `xlsx_validator.validate(usa)` verdict = PASS
- India banner "Active" count = `populations.active(india).count` = canonical INVESTMENT_ACTIVE
- USA banner "Active" count = `populations.active(usa).count`
- Exit History sheet present in BOTH markets
- Definitions sheet present in BOTH markets
- Monthly Summary sheet present in BOTH markets (not inline)
- Portfolio has zero rows with DECISION="ARTIFACT" in BOTH markets
- Portfolio has zero duplicate `(market, ticker, runner, created_date)` rows in BOTH markets
- 3-run byte-identical XLSX generation
- Full test suite green (both `tests/delivery` and `tests/research`)
- Git diff limited to files listed in §II.6 · zero LOCKED-file changes
- No `overrideallow` · no CI-signal weakening · no push without explicit authorization

## II.9 · Explicit non-authorization statement (repeat)

This document is a specification and forensic reconciliation only.
No production code has been modified.
No commit has been made.
No push has been made.

Phase 5 begins ONLY when CEO explicitly authorizes with the specific words:
> "authorized to implement DELIVERY_DATA_CONTRACT_v1 · Phase 5 proceed"

**Any deviation from the spec above (population definitions · file list · locked-layer boundary · missing-data semantics) requires spec edit and re-approval BEFORE Phase 5 begins.**
