# PIE · Phase A · Data Audit

**Date:** 2026-11-03 · **Status:** audit only · no PIE code written · nothing committed

Phase A asks whether the evidence PIE needs exists. It mostly does not, in the
window PIE was specified against. This document records what is actually on
disk, measured rather than assumed.

---

## Verdict

| Question | Answer |
|---|---|
| Is there 90 days of prediction history? | **No.** India 3 decision dates, USA 2. |
| Is there a dense history anywhere? | **Yes.** USA 137 dates Jan–Jul, India 68 Mar–Jun. |
| Are forward returns computable? | **Yes.** 99.1% of USA, 100% of India have ≥120 bars. |
| Do outcomes reconcile into one dataset? | **No.** Three disjoint populations. |
| Are point-in-time fundamentals available? | **Effectively no.** USA 12 tickers, India 2 dates. |
| Can the 45/15/30 walk-forward split run? | **Not on 90 days.** It needs ~90 decision dates. |

The binding constraint is **decision-date density**, not models, features or
price data. This is the same constraint prior R3 work hit, re-measured here
against R2 production history.

---

## 1 · Decision history · the governing finding

`reports/recommendation_history.parquet` (India) and
`usa/reports/recommendation_history.parquet` (USA). One row per decision date,
each carrying a full per-ticker recommendation list.

**Decision dates by month**

| Month | India | USA |
|---|---|---|
| 2026-01 | — | 20 |
| 2026-02 | — | 19 |
| 2026-03 | 19 | 22 |
| 2026-04 | 20 | 21 |
| 2026-05 | 19 | 20 |
| 2026-06 | 10 | 21 |
| 2026-07 | 2 | 14 |
| 2026-08 | **0** | **0** |
| 2026-09 | 2 | 1 |
| 2026-10 | 1 | 1 |
| **Total** | **73** | **139** |
| **In last 90 days** | **3** | **2** |

Two observations that matter more than the totals:

1. **August is empty in both markets.** The pipeline ran daily and committed
   daily through August, but `recommendation_history` received no rows. Daily
   append is a documented invariant of this layer, so this is a persistence
   defect, not an absence of trading days. It should be diagnosed before PIE
   consumes this table, because PIE would silently inherit the hole.

2. **Density collapses after July.** Jan–Jul is near-daily; Aug onward is
   three dates in three months. Any study framed as "the last 90 days" is
   therefore a study of 2–3 mornings, which is how the earlier USA
   meta-label came to describe two consecutive days while reporting 495 names.

**Per-ticker schema is ready.** Each recommendation row carries:

```
action · asof · ensemble_score · calibrated_confidence · raw_confidence
regime_adjusted_confidence · model_agreement · n_models_scoring
disagreement_flag · entry_zone · exit_conditions · bull_case · bear_case
key_risks · feature_set_version · model_stamp · schema_fingerprint
```

`asof`, `feature_set_version`, `model_stamp` and `schema_fingerprint` make
point-in-time reconstruction of the *decision* possible. Breadth per date is
India 15–228 tickers, USA 15–516.

---

## 2 · Outcome records · three disjoint populations

PIE requires one canonical evaluation dataset. There are three, and they do
not describe the same thing.

| Source | Rows | Market | Dates | State |
|---|---|---|---|---|
| `reports/research/outcome_dataset.parquet` | 51 | **India only** | 6 entry dates (07-31 → 09-03) | 33 closed / 18 open |
| `reports/delivery/prediction_snapshots.jsonl` | 172 | USA 160 · India 11 | 20 prediction dates (08-04 → 10-23) | **171 of 172 still ACTIVE** |
| `reports/research/opportunity_registry.jsonl` | ~2.5k events | both | — | authoritative lifecycle, episode-keyed |

Specifics:

- **`outcome_dataset.parquet` has zero USA rows.** It is the R3 P0 "canonical"
  dataset and it covers one market. `ret_5d_pct` / `ret_10d_pct` are populated
  45/51; **`ret_30d_pct` is 0/51**. The 20-day horizon PIE specifies is not
  resolvable here, and `sample_tier_note` already labels its own rows
  `hypothesis`.
- **`prediction_snapshots.jsonl` contains no resolved outcomes.** 171 of 172
  rows are `ACTIVE`. 169 unique tickers across 172 rows, so it is one row per
  name, not a time series. It cannot supply labels.
- **The registry is the only trustworthy spine.** It is event-sourced and
  keyed by `opportunity_id`, which is unique per episode — the property that
  the ticker-keyed checks lacked when they missed ZBRA's and DDOG's re-entry
  closes on 2026-10-30.

**Reconciliation requirement:** PIE must build its labels from the registry
plus raw bars, and treat the other two as derived views. Mixing portfolio
exits, mark-to-market returns and prediction outcomes is the exact failure the
directive warns about, and all three are present here under similar names.

---

## 3 · Price substrate · the one dimension that is sound

| Market | Tickers | Median bars | <120 bars |
|---|---|---|---|
| USA | 908 | 1255 | 8 (0.9%) |
| India | 230 | 1447 | 0 (0.0%) |

Thin USA names: `AVB 1 · EA 1 · EQR 1 · WBD 1 · PSKY 15 · CSRA 57 · HONA 97 ·
FDXF 110`. The four one-bar files are a known ingest defect and are the same
names that made I28 refuse the workbook.

Forward 5/10/20-day returns are therefore computable for ~99% of both
universes. **Labels are not the problem.** Exclude the eight thin names
explicitly and record the exclusion as coverage rather than dropping them
silently.

---

## 4 · Fundamentals · no usable point-in-time history

PIE assigns 20% of its score to fundamental quality and forbids using revised
data to reconstruct past decisions. Measured:

| Source | Rows | Coverage | As-of stamp |
|---|---|---|---|
| `data/fundamentals/pit/sec_first_known.parquet` | 13,620 | **12 tickers** | yes — `available_from`, `filed_date` |
| `data/raw/india/fundamentals.parquet` | 228 | 228 tickers (full) | **none** |
| `reports/research/fundamentals_history/india.parquet` | 96 | 50 tickers | yes — but **2 dates** |
| `data/fundamentals/normalized/sec_facts.parquet` | — | — | revised, not first-known |

The PIT table has correct semantics (`available_from` is exactly what a
leakage-safe join needs) and 12 of 516 USA names — 2.3% coverage. The only
full-coverage fundamentals file, India's, has **no date column at all**: it is
a current snapshot, so using it for any historical decision is look-ahead by
construction.

**Consequence:** PIE's fundamental dimension cannot be validated historically
in either market today. It must be either abstained on, or deferred until the
PIT fundamentals backfill covers the universe.

---

## 5 · Features and existing machinery

- `features/quality_history.parquet` — 1,053 rows, **7 dates** (07-20 → 10-30).
  Same density problem.
- Existing walk-forward implementations already present:
  `backend/replay/walk_forward.py`, `backend/research/evidence/walk_forward.py`,
  `backend/research/multi_layer/walk_forward.py`,
  `backend/research/backtest_historical.py`, plus
  `backend/research/r3_program/` (`historical_replay.py`, `replay_dataset.py`,
  `evidence_clock.py`, `outcome_resolver.py`, `experiment_protocol.py`).

`r3_program` already implements point-in-time replay, outcome resolution and
an evidence clock. PIE's Stages 1–2 as written would duplicate it. The
cheaper and safer route is to build PIE's dataset layer **on**
`r3_program.replay_dataset` / `outcome_resolver` and register PIE in the
existing `research_registry`, rather than starting a parallel vocabulary.

---

## 6 · What Phase B can and cannot deliver

**Can, on this data:**

- A reliable historical performance report over **Jan–Jul 2026** (USA ~137
  dates, India ~68) using registry labels and raw bars.
- Technical features and risk features at point-in-time, from bars.
- An honest walk-forward with date-blocked intervals over that window.

**Cannot, on this data:**

- Anything framed as "the last 90 days" — 2–3 decision dates.
- A validated fundamental dimension — no PIT coverage.
- A 20-day horizon from `outcome_dataset.parquet` — `ret_30d_pct` is 0/51.
- Any USA claim from `outcome_dataset.parquet` — it has no USA rows.

**Blockers to fix before Phase B, in order:**

1. The empty August in `recommendation_history` — persistence defect.
2. The four one-bar USA parquets (and PSKY).
3. One canonical label definition, built from the registry.

---

## 7 · Open questions for the CEO

1. Re-scope the historical window from "last 90 days" to **Jan–Jul 2026**, the
   only period with daily decisions? Without this, Stage 2 cannot run.
2. Abstain on the fundamental dimension and re-weight the remaining four, or
   hold PIE until PIT fundamentals are backfilled?
3. Diagnose the August gap first, or proceed and mark it as a known hole?
