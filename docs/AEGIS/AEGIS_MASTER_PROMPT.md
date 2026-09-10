# AEGIS MASTER PROMPT — XLSX Reconciliation → R3 Audit → External Recommendation Intelligence

**Status:** CONTROLLING. Supersedes the loose R3-H / External Recommendation
prompt, which is folded in below as **Phase 3**.
**Authored:** 2026-09-10 · **Standing rule while this document is open:**

> **DO NOT PUSH. DO NOT COMMIT. Until Phase 1 is actually complete.**

Phases run in order. Phase 2 does not begin until Phase 1 closes; Phase 3
does not begin until Phase 2 closes. No phase may be partially skipped to
reach the next one.

---

## Governance conflicts found while consolidating (decide before Phase 3)

**G1 · `R3-H` is already taken and cannot name the external work.**
The frozen 11-class programme is `R3-A … R3-K`, all disposed:

| | | |
|---|---|---|
| R3-A Descriptive | `DESCRIPTIVE_ONLY` | R3-G Risk/Exit `FROZEN` |
| R3-B Statistical | `RESEARCH_ONLY` | **R3-H Unsupervised `DESCRIPTIVE_ONLY`** |
| R3-C Temporal | `INSUFFICIENT_SUBSTRATE` | R3-I Intraday `BLOCKED` |
| R3-D Fundamental Forecasting | `INSUFFICIENT_SUBSTRATE` | R3-J Calibration `RESEARCH_ONLY` |
| R3-E Fundamental | `REJECTED` | R3-K Decision Synthesis `INSUFFICIENT_SUBSTRATE` |
| R3-F Market/Sector | `INSUFFICIENT_SUBSTRATE` | |

`R3-H` is **Unsupervised Intelligence**, whose 6/6 lanes died under a
ticker-block permutation. Reusing the label would overwrite a disposed
result and break the "no parallel vocabulary" rule.

→ External Recommendation Intelligence is designated **`R3-L`** throughout
this document. It is a **new class added to a FROZEN programme**, which is
a governance decision only the CEO can make. Phase 3 does not start until
that decision is explicit.

**G2 · The current prediction identity key would destroy R3-L's signal.**
`shadow.load_ledger` enforces identity on `(as_of, ticker)` and keeps the
earliest record. Market is implicit in the per-market file; **`source` and
`prediction_version` are absent**. For R3-L, where CNBC, Zerodha, Angel
One and Moneycontrol may all publish on the same ticker the same day, that
key collapses every source into one record — deleting precisely the
consensus/disagreement variance the experiment exists to measure. The
Prediction Identity Invariant below closes this, and it must be
implemented in Phase 2, before any external source is ingested.

---

## PHASE 1 — XLSX FORENSIC RECONCILIATION

Source-of-truth order: canonical lifecycle → production registry →
historical registry/orphan audit → price/source lineage → sector/market-cap
sources → XLSX renderer. **The workbook must never become a source of
truth.** Do not patch a symptom: trace source → canonical dataset →
renderer → XLSX, and report the smallest correct fix.

### Already established (2026-09-10 audit — do not re-derive)

Passing: `UNACCOUNTED = 0` both markets · Position IDs unique, zero nulls,
both sheets · `(ticker, engine)` unique · no HOLD/WATCH/AVOID leakage ·
stop-distance invariant 0 mismatches · target invariant holds (3 India +
1 USA incoherent correctly withheld as `—`) · sector 100% populated in
canonical · R3 isolated, production writes 0 · A19/A23 PASS · `override
False`.

Reconciliation, for reference:

| | India | USA |
|---|---|---|
| Registry CLOSED | 47 | 504 |
| production / administrative / advisory | 21 / 21 / 5 | 481 / 42 / 26 |
| Lifecycle exits (rows / tickers) | 58 / 57 | 547 / 506 |
| Orphan audit | 26 | 490 |
| **UNACCOUNTED** | **0** | **0** |
| Coverage begins | **2026-08-04** | **2026-08-10** |

### P1 defects to repair

**P1.1 · USA exit populations are misclassified (highest priority).**
463 rows carry `source = registry:production` with `exit_reason =
"Auto-close · orphaned position"`, and 489 of 490 orphan rows carry
**non-zero realized P&L**. The banner reads `547 exits · R1 30 · R2 517`,
which presents 517 as realized production exits. The genuine count is
**18** (14 outperformance + 4 rotation). An orphan auto-close is a
reconstructed administrative record, not realized performance.
→ Add `Record Type` ∈ `REALIZED EXIT · ADMINISTRATIVE ·
ADVISORY/HISTORICAL · STOP-BREACH MARK · ORPHAN AUTO-CLOSE`. Reclassify
orphan auto-close out of `registry:production`. Never mix these
populations in any statistic.

**P1.2 · "every closed position" is an overclaim.** Replace with the
explicit sentence `Canonical lifecycle historical coverage begins
YYYY-MM-DD.` Do not fabricate pre-coverage history; if it is not provable
in a canonical source, it does not exist.

**P1.3 · Market-data as-of is absent and the workbook mislabels its own
prices.** Header says `2026-09-10`; every price is the 2026-09-09 close.
The data is correct — a 09:15 IST run cannot hold the 09-10 close — the
labelling is not. → Add `Market Data As-of`; state generation date, data
as-of, latest-close vs intraday, and source timestamp.

**P1.4 · Same-entry/same-price rows must be explained, not flagged.**
India's 33 rows at exactly 0.00% P&L are **legitimate same-close
admissions**: admitted at the 09-09 close, still marked at the 09-09
close. Verified against the parquets (ABBOTINDIA entry 25455.0 = 09-09
close 25455.0). Explain this in the workbook; never present it as an
error, and never let it hide a genuine stale price.

**P1.5 · Sector missing from CURRENT.** Canonical carries it at 100%
(48/48 India, 21/21 USA). Pure renderer omission. Add it. Normalize USA's
split labels — `Tech` (1) and `Technology` (8) are one sector. Never use a
cap label as a sector. If sector is current rather than PIT, say so.

**P1.6 · Market Cap / Size absent.** Investigate a governed current
market-cap source. If none exists, render **`MARKET_CAP_UNAVAILABLE`**.
**Never** substitute `liquidity_bucket_60d` or `avg_dv_60d`; if liquidity
is wanted it is a separate `Avg Traded Value` column. If only current cap
is available, label it `CURRENT MARKET CAP` and never imply it held at
entry.

**P1.7 · NEW → ACTIVE+ semantics invisible.** 33 India names admitted
2026-09-09 render as ACTIVE+ with no cohort visibility. → Add `Admission
Status` (`NEW today` / `Admitted 2026-09-09` / `Admitted 2026-08-04`).
**No third sheet.**

**P1.8 · Confidence provenance.** India 15/48 and USA 21/21 CURRENT rows
show a bare `—`. Verified genuinely unavailable, not dropped: registry
`initial_score` coverage is India ACTIVE 33/59, USA ACTIVE 8/34, and
**0/57 India CLOSED, 0/562 USA CLOSED**; the 33 India rows that do have a
score all render correctly. → Render `Historical score unavailable`.
Never reconstruct a historical production confidence.

**P1.9 · Exit entry-confidence is 0% populated** (58/58, 547/547). Classify
explicitly, do not leave an unexplained dash.

**P1.10 · Breach marks sit under `Realized P&L %`.** 11 India + 5 USA rows
are marks, not realized exits. Rename the column `P&L %`; 495 of 547 USA
rows are not realized.

**P1.11 · Stale reconciliation artifacts.**
`registry_materialization_*.json` and `orphan_ban_audit_*.json` are dated
2026-09-08 and are not refreshed by the certified run. Wire them in.

**P1.12 · USA universe hygiene.** 11 of 516 names are unscoreable: 8 with
no price file (`GGP`, `SCANA`, `TSYS` delisted; `BF.B`, `BRK.B`
dot-notation mismatch; `LVMH` not US-listed; `IQVIA` should be `IQV`;
`MBIA`) and 3 stale (`AVB`, `EQR`, `EA`).

### P1 proposed column order

**CURRENT (22)**
```
Market · Ticker · Engine · Action · Admission Status · Entry Date ·
Entry Price · Last Price · Market Data As-of · P&L % · Confidence % ·
Sector · Current Market Cap · Size · Stop · Stop State · Stop Distance % ·
Max Loss if Stop % · Target · Position ID · Reason · R3 SHADOW
```

**EXIT HISTORY (16)**
```
Exit Date · Ticker · Sector · Market · Engine · Record Type · Entry Date ·
Entry Price · Exit Price · P&L % · Holding Days · Exit Reason ·
Entry Confidence % · Exit Trigger · Position ID · Source
```

### P1 exit criteria (all must hold)

CURRENT reconciles 100% · EXIT HISTORY reconciles 100% · `UNACCOUNTED = 0`
· historical coverage explicit · Sector present and valid · Market Cap
valid or explicitly unavailable · liquidity never mislabelled as cap ·
market-data as-of explicit · same-price rows explained · NEW lifecycle
semantics explicit · stop/distance invariant passes · target invariant
passes · confidence gaps classified · realized/admin/advisory/breach/orphan
populations separated · R3 isolated · R3 production writes 0 · A19 PASS ·
A23 PASS · delivery gate ALLOW · override false · full tests pass · **R2
production diff = zero** · no new AI research introduced.

Only then: **XLSX PRESENTATION CONTRACT = LOCKED.**

---

## PHASE 2 — R3 FORENSIC AUDIT

Begins only after Phase 1 closes.

Audit: R3 SHADOW is the **only** R3 column in the XLSX · R3 isolation ·
prediction identity/deduplication · prediction vs outcome separation ·
evidence clock · calibration · `READY_FOR_EVALUATION` · `may_train` · no
new model while `NONE`.

R3 must never change R2 Action, R2 Confidence, Stop, ranking, lifecycle,
position creation/closure, or production P&L. `ABSTAIN` means "no
validated R3 opinion yet" — it is **not** HOLD. `AVOID` is **not** EXIT.
`TAKE` is **not** an automatic BUY. No probability is displayed until
calibration qualifies it.

Expected state (verified 2026-09-10): `READY_FOR_EVALUATION = NONE` ·
`may_train = false` · matured outcomes 0/50 · earliest evaluation
2026-09-15 · R3 production writes 0. **While this holds, do not build a
new model, do not start a new branch, do not invent work.**

### R3 PREDICTION IDENTITY INVARIANT (binding)

```text
R3 PREDICTION IDENTITY INVARIANT

Every R3 prediction must have a stable identity:

(source/program, market, as_of, ticker, prediction_version)

Repeated execution on the same as_of/ticker must be idempotent.

No duplicate prediction may enter the evidence ledger.

If duplicate records exist:
- do not silently average them
- do not overwrite the original
- preserve the earliest valid prediction
- classify later records as duplicate/revision
- exclude duplicate revisions from outcome statistics unless explicitly
  pre-registered as a new prediction version.

Prediction and outcome records must remain separate.

A later rerun must never gain hindsight information and replace an
earlier prediction merely because the later run saw more of the day.
```

**P2 implementation note.** The current key is `(as_of, ticker)`
(`shadow.load_ledger`, earliest-wins). It must be widened to the full
five-part identity **before** Phase 3 ingests anything, per G2. Precedent
for why this matters: the India ledger held 63 raw rows against 53 unique
predictions after identity enforcement — a stash/checkout had let a run
re-append rows it had already written (GNFC recorded at 02:19 and again at
06:06). A duplicated prediction inflates the sample and double-counts one
opinion.

The evidence clock must measure day-over-day accumulation independently of
how many times it is invoked, and conservation must still be judged on a
saved baseline so that deletions remain visible.

---

## PHASE 3 — R3-L · EXTERNAL RECOMMENDATION INTELLIGENCE

Begins only after Phase 2 closes **and** the G1 naming/scope decision is
explicit.

### The research question

> **Does public financial-research/recommendation information contain
> incremental decision value beyond AEGIS R2?**

**R3-L must not become "another recommendation engine."** It produces
evidence about whether external opinion adds value. It never produces a
BUY.

### Sources

CNBC · Angel One · Zerodha · Moneycontrol · Economic Times · Business
Standard · broker/public RSS feeds.

**Historical timestamped recommendations only.** A source that cannot
supply a trustworthy publication timestamp cannot enter the ledger — an
untimestamped recommendation is indistinguishable from hindsight.

### Required construction

1. **PIT recommendation ledger** — append-only, publication-timestamped,
   with the full five-part identity from Phase 2.
2. **Entity/ticker normalization** — one issuer, one ticker, across
   sources and naming conventions.
3. **Deduplication** — RSS sources publish, update, republish, syndicate
   and duplicate the same recommendation. Syndication is not
   confirmation: two outlets carrying one wire story is **one** opinion,
   and counting it twice manufactures consensus that does not exist.
   A revision is a new `prediction_version`, never an overwrite.
4. **Source quality** — measured from forward outcomes, never assumed
   from brand.
5. **Forward outcomes** — recorded separately from predictions.
6. **Consensus / disagreement** — the primary constructed feature; it
   only exists if identity keeps sources distinct (G2).
7. **R2 vs R2 + external consensus** — the incremental-value test.

### Evidence standard (unchanged from the frozen programme)

Effective units, not rows — the binding constraint is **dates**, not
models. Ticker-block permutation nulls. Ticker-disjoint and date-disjoint
OOS. Benjamini-Hochberg FDR across the whole family. Economic value net of
costs, not just statistical significance. Incremental value **over R2**,
with a ticker-bootstrap CI.

**Three kill switches:** leakage → kill RESULT · tautology → kill RESULT ·
no incremental value over R2 → **kill MODEL**.

A negative result is a completed experiment. "External recommendations add
nothing beyond R2" is a valid and valuable Phase 3 outcome, and must be
reported as plainly as a positive one.

### R3-L may never

Write to production · alter R2 Action, Confidence, Stop, ranking or
lifecycle · create or close a position · appear in the investor XLSX
beyond the single existing `R3 SHADOW` column · be promoted without OOS +
calibration + economic value + incremental value + replication + explicit
CEO authorization.

---

## Standing constraints (apply to every phase)

- Never manufacture readiness by lowering thresholds.
- Do not fabricate PIT sector, market-cap or price history.
- Do not use `override.allow = true`.
- Do not modify R2 scoring, confidence, eligibility, ranking, thresholds,
  stops, exits, or production behaviour.
- Telegram receives only the per-market XLSX — never the unified
  `aegis_history.xlsx`, never previews or validation reports.
- Do not invent work merely to produce a commit.
- **DO NOT PUSH. DO NOT COMMIT.** Until Phase 1 is complete.
