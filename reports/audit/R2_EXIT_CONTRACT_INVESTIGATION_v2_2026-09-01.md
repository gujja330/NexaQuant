# R2 Exit Contract · Strict Investigation v2 · 2026-09-01

**Correction to v1 (which mis-classified the 6% stop as SOFT/ADVISORY).**

After a wider read of the codebase (portfolio_manager · lifecycle_state_machine ·
dynamic_risk_v2 · position_store) I have to revise the verdict. The R2
exit engine IS coded · IS more sophisticated than a static 6% number ·
and IS documented to enforce stop / target / horizon exits. What is
broken is not the strategy but the **wiring · the engine exists in the
codebase but is never called by the daily production pipeline**.

**Verdict: CASE B · lifecycle-persistence defect**

## Architecture map (as coded)

```
R2 signal (recommendation)
   ↓ ensemble_score → recommendation → action
   ↓ investor_actionable/engine.py::DEFAULT_STOP_PCT = 0.06  (6%)
   ↓                                   T1 = entry × 1.12  (12%)
   ↓                                   T2 = entry × 1.24  (24%)
entry_zone.{stop_loss, target_1, target_2} attached to recommendation
   ↓
Portfolio state
   ↓ ┌─────────────── DYNAMIC EXIT ENGINE (COMPLETE · CODED) ─────────┐
   │ backend/portfolio/portfolio_manager.py::_run_dynamic_cycle       │
   │   └── evaluate_position(root, market, runner, ticker, asof,     │
   │           current_price, stop_price, t1_price, t2_price,        │
   │           horizon_days)                                          │
   │         which returns one of:                                    │
   │           · EXIT_STOP    (current_price ≤ stop_price)           │
   │           · EXIT_TARGET  (current_price ≥ t1 or ≥ t2)           │
   │           · EXIT_HORIZON (days_held ≥ horizon)                  │
   │           · None → still ACTIVE · log_hold                       │
   │ backend/risk/dynamic_risk_v2.py                                  │
   │   · ATR-based stop (14-day ATR × 2.0 multiplier)                │
   │   · Vol-scaled stop when ATR% > 3.0                             │
   │   · Trailing lift when profit ≥ 5% (never lowers)               │
   │ backend/portfolio/position_store/store.py                        │
   │   · TRAIL_PCT = 0.06 · maintains high_water + current_stop      │
   │   · current_stop = max(prior_stop, high_water × 0.94)           │
   └───────────────────────────────────────────────────────────────────┘
   ↓ ← IN PRODUCTION, THIS ENGINE IS NEVER CALLED
Portfolio state (unchanged)
   ↓
Only two production paths write CLOSED events to Registry:
   1. detail_xlsx.py:503  ·  fires oreg.close() only when upstream
      Status column already = "EXIT" (which requires
      recommendation = STRONG_SELL from the ensemble)
   2. mr_orphan_closer.py:204  ·  fires oreg.close() when position
      has been missing from the daily snapshot for N stale days
Registry
```

## Evidence

### 1 · The engine exists and is fully coded

`backend/portfolio/lifecycle_state_machine.py::evaluate_position`
lines 79-104:
```
if stop_price is not None and current_price <= stop_price:
    return LifecycleDecision(... event="EXIT_STOP" ...)
if t2_price is not None and current_price >= t2_price:
    return LifecycleDecision(... event="EXIT_TARGET" ...)
if t1_price is not None and current_price >= t1_price:
    return LifecycleDecision(... event="EXIT_TARGET" ...)
if days_held >= horizon_days:
    return LifecycleDecision(... event="EXIT_HORIZON" ...)
```

The doc comment at the top explicitly names:
```
EXIT_STOP    → stop-loss triggered
EXIT_TARGET  → T1 or T2 hit
EXIT_HORIZON → holding period expired
EXIT_MANUAL  → operator override
```

### 2 · portfolio_manager is the intended orchestrator (also fully coded)

`backend/portfolio/portfolio_manager.py:104-146` iterates every active
position · looks up stop / t1 / t2 from the recommendation JSON's
`entry_zone` · calls `evaluate_position` · calls `apply_decision`.

### 3 · dynamic_risk_v2 recomputes stops daily (also runs)

`backend/risk/dynamic_risk_v2.py` IS invoked from
`backend/recommendation/new_opp_guard.py:347`. It writes ATR-based /
vol-scaled / trailing-lifted stops to
`reports/context/dynamic_risk_{market}.json`.

### 4 · But nothing consumes the engine's decisions

- Grep for `portfolio_manager` outside `backend/portfolio/` returns **zero**
  production callers. It has no daily driver.
- Grep for `evaluate_position` returns only 2 hits: definition +
  `portfolio_manager` internal call.
- Grep for `dynamic_risk_india.json` / `dynamic_risk_usa.json` returns
  only the writer · no reader.
- Grep for `apply_decision` returns only the definition + one internal
  usage in portfolio_manager.
- `reports/portfolio/` and `reports/portfolio_ledger/` **do not exist**
  on disk · confirming portfolio_manager has never persisted to them
  in this environment.
- Historical evidence: 539 R2 CLOSED events all-time, **zero**
  reference `EXIT_STOP` · `EXIT_TARGET` · `EXIT_HORIZON`. Every exit is
  either `ORPHAN_AUTO_CLOSE` (housekeeping) or a rotation entry.

### 5 · Confirmation from a comment in the code

`backend/delivery/telegram/detail_xlsx.py:467-472` (dated 2026-08-20):
```
# 2026-08-20 · Registry-SSoT fix · DO NOT take first_seen_date from
# position_store any more. position_store gets restamped daily by
# the portfolio_manager which is exactly the bug that made Zydus/
# ONGC/HINDUNILVR show NEW every day. Registry is now the SSoT for
# first_seen · consulted unconditionally below (line ~490).
```

`portfolio_manager` was blamed for a NEW-every-day defect and effectively
removed from the pipeline. Nothing was put in its place · the exit
decisions the engine was supposed to make are now not made at all.

## Per-position reconstruction (proof)

Reconstructing the 3 flagged positions day-by-day, using the exact rules
the coded engine would evaluate:

| Position | Entry | Stop@6% | T1 | Documented-engine would have EXIT_STOP on | Days after entry | Actual production state |
|---|---|---|---|---|---|---|
| **IND-R2-CHAMBLFERT-20260804** | 452.35 | 425.21 | 506.63 | **2026-08-28** @ 423.20 (−6.44%) | 24 | still ACTIVE (asof 2026-09-01 · pnl −8.58%) |
| **IND-R2-ITC-20260804** | 284.85 | 267.76 | 319.03 | **2026-08-19** @ 267.05 (−6.25%) | 15 | still ACTIVE (asof 2026-09-01 · pnl −7.00%) |
| **USA-R2-IT-20260810** | 193.17 | 181.58 | 216.35 | **2026-08-12** @ 179.46 (−7.10%) | 2 | still ACTIVE (asof 2026-09-01 · pnl −7.10%) |

Every one is a verdict-B case: the engine as coded would have fired
EXIT_STOP · production kept the position ACTIVE.

## 6% role · proven finding

```
6% STOP ROLE:  HARD EXIT (documented in evaluate_position)
                DYNAMIC BASELINE (recomputed by dynamic_risk_v2 via ATR)
                TRAILING LIFT active (position_store.TRAIL_PCT = 0.06)

CURRENT ENFORCEMENT STATUS:  NOT WIRED · dynamic_exit engine never
                              invoked · production exits are only:
                                (a) ensemble STRONG_SELL → EXIT (rare)
                                (b) ORPHAN_AUTO_CLOSE (stale-days)
                                (c) rotation-driven
```

It is NOT a fallback · NOT advisory · NOT legacy unused · it IS an
intended hard/dynamic stop that a fully-coded engine is meant to enforce
but the pipeline doesn't call.

## What this means for the release

- Not a strategy question. The strategy is already in code.
- Not a "install a 6% stop" question. The stop already exists (multiple
  ways).
- **This is a lifecycle-persistence defect**: the engine's decisions
  are not persisted to the Registry (or the Registry is not consulting
  the engine).

## What NOT to do

- Do NOT install a "new" stop rule. It exists.
- Do NOT modify `DEFAULT_STOP_PCT`. It's already the correct authoritative
  value the engine was designed around.
- Do NOT redesign the exit strategy. Diagnose why the coded strategy
  isn't invoked · then wire it correctly.
- Do NOT force EXIT rows into the workbook. The Registry must produce
  them.
- Do NOT commit or push a "workbook fix" that hides this.

## Remediation options · CEO decides · not implemented

### Option A · Wire the existing dynamic exit engine into the daily pipeline
- Add one call to `portfolio_manager._run_dynamic_cycle` (or its per-
  position equivalent) inside `new_opp_guard.py::guarded_run`, right
  after `dynamic_risk_v2.compute` produces today's per-position stops.
- Ensure `apply_decision` writes both to portfolio_ledger AND to
  `oreg.close()` when the decision is a terminal exit.
- Requires: touching `backend/portfolio/*` and `backend/recommendation/*`
  (both are LOCKED paths in the retirement contract) · needs your
  explicit authorization.
- Consequence: on next run, CHAMBLFERT / ITC / IT will exit and be
  moved to Exit History with realized P&L. Historical R2 performance
  numbers will change (mostly downward as more losing exits get booked
  at stop rather than allowed to run further).
- Walk-forward validation strongly recommended before this becomes
  permanent · would take a separate authorized sprint.

### Option B · Confirm engine is intentionally-disabled and treat 6% as advisory
- Add explicit `stop_advisory_only = True` flag to the recommendation
  emitter · rename display fields (e.g. `stop_advisory_6pct`) · add
  `no active hard stop · exit engine disabled` legend to workbook.
- Surface `documented_stop_would_have_fired` as a column in
  01_Portfolio so operator sees which positions would-have-exited
  under the coded engine.
- No exit behavior change · full transparency.

### Option C · Partial wiring · surface but don't act
- Same as B but ALSO add a daily audit that generates a "would-have-
  exited" report (like this investigation, but rerun daily) for CEO
  review before deciding whether to enable Option A.

### My recommendation

**Option C** for the current lock cycle · Option A as an authorized
follow-up sprint requiring walk-forward validation.

Rationale: The immediate correctness fix (Option B display cleanup) is
insufficient because the operator still can't see the would-have-exited
positions. Option C gives full visibility without changing production
behavior · buys time to run walk-forward on Option A properly rather
than in a rushed release.

Option A is the correct end state · but landing it in the current cycle
means:
- 3 immediate forced exits (CHAMBLFERT / ITC / IT) with locked losses
- Retroactive recomputation of R2's historical performance numbers
- Registry state change (from ACTIVE → CLOSED) that cascades everywhere

Those are all defensible outcomes but they are risky to do in a
"lock and freeze" release cycle without walk-forward first.

## What I've done

- No code changed
- No workbook rebuilt
- No commits · no pushes
- Written: `reports/audit/R2_EXIT_CONTRACT_INVESTIGATION_v2_2026-09-01.md`
- Written: `reports/audit/r2_lifecycle_reconstruction_2026-09-01.json`
- Written: `scripts/r2_lifecycle_reconstruction.py`
- Prior stop-rule audit unchanged

## Standing by

Awaiting your Option A / B / C choice before doing anything further.
No development · no push · no lock claim.
