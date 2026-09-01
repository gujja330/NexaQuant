# AEGIS · R1 Retirement · 2026-09-01

**CEO authorization**: `R1 RETIREMENT — AUTHORITATIVE CHANGE`.

R1 is formally retired from AEGIS production. R2 becomes the sole
active production runner.

## What "retirement" means (STRENGTHENED CONTRACT · CEO 2026-09-01)

**R1 is COMPLETELY absent from the delivered production XLSX ·
every sheet · every cell** (except the `Definitions` sheet which
may name R1 as a reference explaining the retirement itself).

**Historical R1 data is PRESERVED in canonical / audit sources ·
never in the delivered workbook.**

- R1 does **NOT** appear in:
  - Portfolio (any row · any column · any Position ID)
  - Today Decisions
  - Exit History (90d) — R1 CLOSED events do not become production exits
  - Monthly Summary — aggregates exclude R1
  - AEGIS History sheet (workbook view · not canonical audit)
  - Runner Performance
  - Research Quality
  - Research Timing
- R1 **does** remain in (canonical / audit only · not delivered):
  - `reports/research/opportunity_registry.jsonl` (full audit lineage)
  - `reports/audit/r1_producer_audit_*.json` (retirement proof)
  - `reports/audit/r1_retention_review_*.md` (historical evidence)
  - `reports/research/runner1/history.jsonl` (dormancy event log)
- The `Definitions` sheet may reference R1 as a reference sentence
  explaining the retirement · this is metadata about the contract,
  not runner-row data.

## What this commit changes (delivery-layer scope)

| Change | File | Behavior |
|---|---|---|
| Config authority | `configs/aegis_retirement.yaml` | Declares R1 retired · R2 active · retirement event log |
| Resolver | `backend/delivery/canonical/retirement.py` | `is_retired()` · `active_runners()` · `retired_runners()` |
| Portfolio filter | `scripts/telegram_command_center_send.py` | Portfolio final-reconciliation loop drops R1 rows from visible body |
| Path-A filter | `scripts/telegram_command_center_send.py` | Path-A completeness pass no longer appends retired-runner Registry-ACTIVE rows |
| Reconciler C10 | `scripts/aegis_final_reconciler.py` | New gate `C10_no_retired_in_production_portfolio` fails if any retired-runner row is present in Portfolio |
| Runner accountability | (unchanged) | Continues to compute R1/R2 stats separately · labels R1 as historical |

## What this commit does NOT change (LOCKED · out of scope)

- `backend/research/opportunity_registry.py` (Registry decision logic)
- `backend/recommendation/*` (SSoT / adaptive_rec_v2 — where R1 signals originate)
- `backend/portfolio/*` · `backend/risk/*` · `backend/execution/*` · `backend/learning/*`
- `nexaquant/lib/*`
- `configs/ensemble_weights_adaptive.yaml`
- No `overrideallow`
- No modification to R2 trading logic / weights / thresholds
- No modification to Registry entries (16 R1 ACTIVE positions in India Registry
  remain in Registry unchanged · they are filtered out of the Portfolio VIEW only)

## Engine-level dormancy · IMPLEMENTED 2026-09-01

Engine-level dormancy is now active at the paper-portfolio ingest layer
(`backend/research/paper_portfolio.py::ingest_runner1_picks_for_date`
+ `backend/research/intraday_paper.py::ingest_runner1_intraday_picks_for_date`).
Both functions read `configs/aegis_retirement.yaml` and short-circuit to
a `DORMANT_BY_DESIGN` no-op when R1 is retired.

Behaviour when R1 retired:
- No new R1 positions opened in paper portfolio
- No mark-to-market updates on R1 positions
- Existing R1 positions REMAIN in place (not dropped) · frozen for audit
- Intraday R1 picks captured as empty snapshot
- History log records `DORMANT_BY_DESIGN` event with reason

Still pending (upstream of ingest · not yet gated):
- `data/aegis_today.csv` generator (external R1 signal source) still
  emits R1 rows · they are ignored by the retired ingest but the CSV
  itself is unchanged. Not a leak · nothing downstream reads R1 rows
  from the CSV outside the guarded ingest.
- Registry `oreg.get_or_create()` remains unchanged · Registry is
  LOCKED · out of scope for this change. 16 existing R1 ACTIVE Registry
  entries still need disposition (see below).

## Handling of existing R1 ACTIVE Registry positions

India Registry currently has 16 R1 ACTIVE positions (post-C9-sync). Under
this retirement:

- Their Registry status remains ACTIVE (Registry unchanged)
- They are HIDDEN from Portfolio production view (filter)
- They are HIDDEN from Path-A completeness Registry-sourced rows (filter)
- They REMAIN in AEGIS History sheet (audit trail)
- They REMAIN visible to the R1 Retention Review script (historical record)
- Future signal-refresh cycles will not modify them (engine-level disable
  pending · see above)

The 16 positions effectively become "orphaned held" · they will need one
of these dispositions in a subsequent CEO decision:
- **Option A**: Auto-close all 16 at current price with reason
  `R1_RETIREMENT_2026-09-01` (calls `oreg.close()` on each)
- **Option B**: Let them run to natural exit signal (but engine won't
  emit signals for retired runner, so they'd run forever without exit)
- **Option C**: Migrate to R2 (invalid · different strategy)
- **Option D**: Explicit CEO decision per position

Recommended: Option A but requires explicit CEO authorization (touches
Registry data). Not executed as part of this delivery-layer retirement.

## Reconciler gate

After this change, `scripts/aegis_final_reconciler.py` adds:

```
C10_no_retired_in_production_portfolio
```

that fails if any row in Portfolio body has `Runner == R1` (or any
future retired runner). Combined with existing C1-C9, the full 12-check
reconciler enforces the retirement invariant.

## Provenance

- Retirement authorized by CEO on 2026-09-01
- Recorded in `configs/aegis_retirement.yaml` with retirement date +
  authorization note
- R1 Retention Review (`reports/audit/r1_retention_review_20260901.md`)
  documents the evidence base for the decision (n=4 India eligible ·
  INSUFFICIENT_EVIDENCE per statistical test · CEO authorized retirement
  based on broader strategic considerations beyond statistical
  significance alone)

## Not claiming

- No lock claim
- No "green" claim
- No "final candidate" (per CEO's PUSH FREEZE rule · this is one of
  many changes accumulating locally until final certification)

## Push status

- 🔒 PUSH FREEZE active
- All changes local
- Next commit will be part of the ONE FINAL COMMIT authorized by CEO's
  explicit `GO FINAL PUSH` after full local certification
