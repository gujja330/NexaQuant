# AEGIS · Delivery Data Contract v2 · 🔒 Runner-specific PIDs + 3-axis banner

CEO 2026-08-31 · Decision A1 + B2 · executed as one coherent
stabilization pass. Supersedes v1 for the identity/banner sections;
v1's population definitions still apply.

## Population identity

### Canonical Position ID (A1)

Every Position ID is **runner-specific** at source. Format:

```
{MKT}-{RUNNER}-{TICKER}-{YYYYMMDD}-{HASH6}

MKT     = IND | USA
RUNNER  = R1 | R2 | SHADOW | MOMENTUM
HASH6   = first 6 hex chars of sha256("{MKT}-{RUNNER}-{TICKER}-{YYYYMMDD}")
```

Generated deterministically by
`backend.research.opportunity_registry.make_opportunity_id`.

Legacy `{TICKER}_{MKT_TAG}_{YYYYMMDD}` PIDs (runner-agnostic) are
migrated deterministically by `scripts/migrate_position_id_a1.py`.
Migration is **stop-on-ambiguous**: any row whose runner is not
unambiguously deducible aborts the migration; no guessing.

### Uniqueness grain per population

**Correct grain per population** — the reconciler validates the
appropriate key for each sheet, NOT a universal `(PID, date)` rule.

| Population | Canonical uniqueness key |
|---|---|
| Registry ACTIVE | `(market, position_id)` where position_id is runner-inclusive |
| Snapshot ledger events | `(market, position_id, runner, snapshot_date)` |
| Portfolio body (visible) | `(market, position_id, runner)` at asof=today |
| Exit History body | `(market, position_id, runner, closed_date)` |
| AEGIS History (audit) | `(market, position_id, runner, snapshot_date)` |

Same TICKER on the same date for different runners produces DIFFERENT
Position IDs, so the key is unique naturally. No dedup required.

## Banner semantics (B2 · 3 distinct axes)

**Lifecycle**, **Decision**, and **Suggested** are three orthogonal
axes. The banner must label them separately, never conflate them.

| Axis | Question it answers | Column source |
|---|---|---|
| **Lifecycle** | What is this position's state? | Portfolio col 4 (`Lifecycle`) |
| **Decision** | What did AEGIS decide today? | Portfolio col 20 (`Status`) + col 3 (`Decision`) for NEW-REC |
| **Suggested** | How is this recommendation being presented/classified? | Portfolio col 9 (`Runner`) == `SHADOW` OR col 3 contains `SUGGESTED` |

### Row 2 (Lifecycle + P&L + Realized 90d)

```
🟢 Lifecycle: N ACTIVE · M NEW  ·
🟣 Suggested: K (display category · not currently held)  ·
Unrealized P&L — ACTIVE holdings, equal-weight per position — X.XX%  ·
Today's P&L: Y.YY%  ·
Realized 90d — historical · see Exit History sheet —
  (Z exits · WR W% · P&L V% · equal-weight per trade)
```

Where `N` + `M` count body rows by Lifecycle column (never Decision).
`K` counts SUGGESTED display class (never included in Lifecycle counts).

### Row 3 (Today's decisions + Positive/Negative)

```
📋 Today's decisions: X STRONG-BUY · Y BUY · Z HOLD · W FRESH-REC  ·
✅ ACTIVE positive: N pos avg +X.XX%  ·
❌ ACTIVE negative: M pos avg -Y.YY%  ·
(equal-weight per position · capital-weighted return TBD)
```

`FRESH-REC` = row with `Decision=NEW` (fresh recommendation today for
an already-held ACTIVE position). Never counts as Lifecycle=NEW.

## Missing-data semantics (unchanged from v1)

Any field the engine did not evaluate renders as `—` (em-dash) · never
as `LOW` · `PENDING` · `0` · or blank.

## Monthly Summary (unchanged from v1)

Monthly Summary is a separate sheet · never trailer rows inside Exit
History body.

## What is NOT covered by this contract

- R1 / R2 / E1 / E2 / E3 decision logic (LOCKED)
- Registry decision logic (LOCKED)
- Trading rules (LOCKED)
- AEGIS vs baseline counterfactual (separate work · needs baseline
  definition + costs)
- Portfolio-level capital-weighted return (separate work · needs cost
  model)

## Locked layers · UNCHANGED by A1/B2

- xlsx_validator.py invariant semantics
- xlsx_contract.py
- ensemble_weights_adaptive.yaml
- Research promotion path
- Signal-generation logic

## Not final-locked yet

This contract is the *specification*. Final lock requires the full
end-to-end certification: India + USA production runs, reconciliation
across Registry ↔ Snapshot ↔ Portfolio ↔ Telegram ↔ XLSX ↔ Exit History
↔ AEGIS History, 3-run determinism, all CI + delivery validators green,
zero unexplained discrepancies · CEO's explicit lock authorization.
