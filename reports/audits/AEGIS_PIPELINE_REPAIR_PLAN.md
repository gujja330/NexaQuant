# AEGIS — Pipeline Repair Plan (Phase C)
**2026-10-27 · minimal safe repair · no strategy change**

Derived from `AEGIS_ARTIFACT_LIFECYCLE_AUDIT.md`. Each item cites the
confirmed defect it addresses. Nothing here alters scoring, ranking,
eligibility, entries, exits, stops or position sizing.

---

## R1 · Declare `portfolio_history.parquet` as a produced artifact
**Defect 1, 5** · `scripts/aegis_daily_v2.py`, `portfolio_engine` step

Add it to `produces`. One line. Without it `_check_produced` cannot see the
file, so the step reports SUCCESS even when the only durable weight history
in the system was not written.

Risk: none. Declaring an artifact the step genuinely writes.
Side effect (intended): a non-write now surfaces as
`SUCCESS_NO_REFRESH` → critical, per the 2026-10-26 gate.

---

## R2 · Persist `portfolio_history.parquet` to Git
**Defect 1** · `.github/workflows/aegis-daily.yml`

Category **C** — authoritative durable state. Already tracked (last
committed 2026-09-04), small, append-only, dedupes on (market, asof).

Risk: low. Dedupe prevents duplicate rows on replay; file is ~19KB.
Explicitly **not** category B: a 30-day CI artifact cannot hold a
multi-month series, and capital-weighted return needs the whole thing.

---

## R3 · Surface the silent history-append failure
**Defect 6** · `india/portfolio_engine/run.py:167`

`append_snapshot_row` is documented fail-open and returns `None` on
failure; the caller discards the return value. Check it and print an
explicit failure line.

Risk: none to behaviour — the function still never raises, so a failed
append cannot abort the run. It becomes visible instead of silent, and
R1 makes the missing file fail the step.

**Not** changing `append_snapshot_row` itself: fail-open is deliberate so a
history problem cannot destroy the run's primary JSON snapshot. The defect
is the caller ignoring the signal.

---

## R4 · Persist category-B run outputs as a CI artifact
**Defect 2** · `.github/workflows/aegis-daily.yml`

Add one `actions/upload-artifact` step covering the risk/portfolio run
outputs, with an explicit path list, 30-day retention, and `if: always()`
so a failed run still retains diagnostic evidence.

Explicit paths only — no globs that could sweep `.env`, credentials or
account data. Named files:

```
reports/sized_positions.json
reports/risk_report.json
reports/portfolio_v3.json
reports/portfolio_diff.json
reports/portfolio_state.json
reports/portfolio_history.parquet
reports/backend_validation_summary.json
reports/ops_check.json
reports/context/orchestrator_verdict_india.json
reports/context/run_certification_india.txt
```

Risk: low. Upload-only; changes no pipeline logic.
**Claim discipline:** retention is not verified until an actual run shows
the artifact listed. This plan does not assert it works.

---

## R5 · Post-production artifact integrity gate
**Defect 3** · new `scripts/ci_artifact_integrity.py` + one workflow step

The audit shows `backend_validation` runs at step 6 and grades artifacts
produced at steps 24–26. **The existing step is NOT moved** — it also
validates source data that must be checked before scoring, and relocating
it would remove a genuine pre-flight.

Instead a *second*, post-production check runs after the producers and
verifies, for a declared required set: file exists, parses, and its `asof`
belongs to this run.

Risk: medium — it is a new gate that can fail the run. Mitigated by
starting with the portfolio/risk set only, and by R6's status contract so a
legitimately empty portfolio passes.

---

## R6 · VALID_EMPTY contract
**Defect 4** · `scripts/ci_artifact_integrity.py`

Today `risk_engine` exits 0 with `sized: 0 active` because all 228
recommendations are `HOLD`. That is correct and must not be reported as a
failure — nor may a genuine failure hide behind it.

States (reusing the existing verdict vocabulary, not a parallel system):

| State | Condition |
|---|---|
| `VALID_EMPTY` | inputs fresh and parseable, zero positions, and the input genuinely contains no BUY actions |
| `VALID_NONEMPTY` | inputs fresh, positions present |
| `INVALID_INPUT` | required input missing, stale, or malformed |
| `OUTPUT_MISSING` | expected output absent |
| `OUTPUT_STALE` | output `asof` does not belong to this run |

The distinguishing evidence for `VALID_EMPTY` is the **recommendation
action distribution** — zero positions is valid only when the upstream
recommendation set actually contains no actionable BUYs.

---

## Explicitly out of scope

- moving `backend_validation` (R5 rationale)
- adding the other 89 unpersisted artifacts to Git (audit §6)
- changing `append_snapshot_row` fail-open semantics (R3 rationale)
- any change to scoring, ranking, stops, exits, sizing, thresholds
- CANON-2, USA advisory, cooldown promotion, regime gate

## Stop conditions honoured

Implementation halts and reports if a change would alter production
strategy behaviour, if persistence for authoritative state remains
ambiguous, or if tests cannot establish the intended contract.

## Verification required before claiming completion

1. Focused tests on each change
2. Full relevant suite
3. **An actual CI run** showing: the integrity gate executing after the
   producers, `portfolio_history.parquet` committed, and the uploaded
   artifact listed with its retention

Items 1–2 are local evidence. **Item 3 is the only evidence that the
persistence repair works**, and will not be claimed without the run id.
