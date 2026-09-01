# R2 Exit Contract · Strict Investigation · 2026-09-01

**Trigger:** stop-rule audit surfaced 3 R2 ACTIVE positions that crossed the
documented 6% stop threshold and remained ACTIVE for 4–20 days
(CHAMBLFERT · ITC · IT).

**Scope:** read-only investigation of the actual exit machinery for R2.
No code changed. No workbook rebuilt. No push made.

**Method:** static analysis of the exit-side codebase +
historical evidence from the Registry's 539 R2 CLOSED events.

---

## Verdict · SOFT / ADVISORY (not hard-enforced)

The R2 6% stop is **documented at signal-generation time and displayed
to the operator · never watched or enforced by any runtime engine.**

The engine is doing exactly what the code says. This is **not a
production defect in the code path** · it is a **contract-vs-display
mismatch** that misleads the operator about what triggers an R2 exit.

Historical Registry evidence: of 539 R2 CLOSED events all-time · **zero**
have `closed_reason` mentioning a stop. Every exit came from either
ORPHAN_AUTO_CLOSE (463 · housekeeping) or rotation into a better
opportunity (~76 · e.g. `→ GNFC.NS · +8.1PP ALPHA`).

## The three sources of "R2 stop" documentation (all inconsistent)

| Source | File | Value | Enforced? |
|---|---|---|---|
| Numeric field | `backend/recommendation/investor_actionable/engine.py:116` | **DEFAULT_STOP_PCT = 0.06** (6%) | No |
| Text exit-condition list | `backend/recommendation/explainer.py:119` | **"price-based: 8% stop-loss from entry"** | No |
| Any live monitor | (searched entire backend) | (none exists) | — |

The engine sets `entry_zone.stop_loss` on every BUY / STRONG_BUY
recommendation using 6% (`round(cp * (1.0 - 0.06), 2)`), then hands it
to the operator as advisory data. The explainer's separate text list
mentions 8% for the same concept — a documentation inconsistency.

## What actually causes R2 EXIT events

Two code paths write CLOSED events to the Registry:

1. **`backend/delivery/telegram/detail_xlsx.py:504`**
   Fires `oreg.close()` only when the upstream row's `Status` column
   already equals `"EXIT"`. Upstream `Status = EXIT` is produced by
   `backend/recommendation/investor_actionable/engine.py:64`:
   ```
   IF_HOLDING_MAP = {
       "STRONG_BUY":  "ADD",
       "BUY":         "HOLD",
       "HOLD":        "HOLD",
       "SELL":        "REDUCE",
       "STRONG_SELL": "EXIT",     ← only path to EXIT
   }
   ```
   So R2 EXIT is triggered when the ensemble score produces
   `recommendation = STRONG_SELL`. Score-driven · not price-driven.

2. **`backend/research/mr_orphan_closer.py:204`**
   Fires `oreg.close(..., reason="ORPHAN_AUTO_CLOSE")` when a Registry
   ACTIVE position has been missing from the daily snapshot for N stale
   days. This is housekeeping · not risk management.

**No third path exists.** No cron job, no exit-monitor, no risk daemon
checks `current_price ≤ entry_price × 0.94` and fires a close.

## Historical exit-reason distribution (all-time · both markets)

```
463  ORPHAN_AUTO_CLOSE                   85.9%
 ~76  Rotation (→ NEW_TICKER · +Xpp)     ~14.1%
   0  STOP_LOSS_HIT                        0%
   0  TARGET_HIT                           0%
   0  time-based expiry                    0%
   0  thesis-invert                        0%
```

The exit_conditions text list mentions time-based, price-based, and
thesis-based triggers · none of them are actually monitored at runtime.

## Per-position verdict on the 3 flagged findings

Each of CHAMBLFERT, ITC, IT is currently in a state that is 100%
consistent with the code as written:

- Ensemble score has not yet produced `STRONG_SELL`
- Position has not been abandoned by the data feed (so ORPHAN_AUTO_CLOSE
  does not fire)
- The 6% stop shown at signal time is DISPLAY only

None of the three has a `CLOSED` event yet · none should · by the
current contract. This is engine behaving as coded. **It is not a
production lifecycle defect · it is a contract clarity defect.**

## What this means

- The 6% number that appears in the recommendation JSON's `entry_zone`
  is a suggestion given to the operator at signal time · not an exit
  rule the system will enforce
- Operators looking at `-8.58%` (CHAMBLFERT) or `-7.10%` (IT · 20 days
  overdue) reasonably expect an exit that will not come
- The workbook currently reinforces this misconception by omitting the
  contract clearly

## Remediation options (for CEO decision · not implemented)

### Option A · Keep stop soft · surface it honestly (workbook fix)
- Add `Stop (advisory)` column to Portfolio with the recommendation-time
  6% price
- Add `Draw-down since entry` column
- Add `Exit trigger` column: shows only the actual triggers
  (`ensemble = STRONG_SELL` · `ORPHAN_AUTO_CLOSE` · `Rotation to better`)
- Remove the word "stop" from any legend / definition that implies
  enforcement
- Deliverable: **operator can no longer be misled**
- Code change: renderer only · no engine change
- Risk: LOW · SOFT change

### Option B · Implement a hard 6% stop (engine change)
- Add a new module `backend/execution/stop_monitor.py`
- On every daily run · scan R2 ACTIVE Registry entries · pull current
  price · compare to entry × 0.94 · if crossed · fire `oreg.close()`
  with reason `STOP_LOSS_HIT`
- Recompute historical R2 performance under the corrected exit path
- Deliverable: production actually enforces the documented risk rule
- Code change: MEDIUM · adds an execution module + backfill of history
- Risk: MEDIUM · would immediately close 3 current positions · changes
  all future R2 exits · needs regression + walk-forward validation
- Requires: explicit CEO authorization to modify `backend/execution/*`
  and `backend/recommendation/*` per lock policy

### Option C · Document 6% as time-conditioned soft floor
- Keep display · never fire on it alone · require confirming signal
  (e.g. STRONG_SELL) OR N consecutive days below stop
- Adds one filter to the ensemble aggregator
- Middle-ground · not immediate

### Option D · Explicit CEO waiver
- Declare the 6% number is a display heuristic only · exit is score-driven
- Update `explainer.py` to remove the misleading "8% stop-loss from
  entry" text
- Update `investor_actionable/engine.py` field name from `stop_loss` to
  `stop_reference_advisory` so downstream consumers don't confuse it
- No engine behavior change · pure documentation cleanup

## What I recommend

**Option A + D combined** for now.
1. Operator gets accurate visibility (A)
2. Codebase self-consistent (D)
3. No production behavior change · no engine touch · no walk-forward
   requirement
4. Preserves the choice to introduce hard stops later as a separate
   authorized change

**Option B is the correct long-term answer** but is a separate authorized
sprint · not part of the current lock cycle.

## What I will NOT do without your explicit decision

- Not modify `backend/execution/*`
- Not modify `backend/recommendation/*`
- Not fire close events on CHAMBLFERT / ITC / IT
- Not push another correction commit
- Not claim LOCK_CANDIDATE against `5965aaba` if the contract-clarity
  issue is unresolved

## Files produced by this investigation

- `reports/audit/r2_stop_rule_audit_india_2026-09-01.json`
- `reports/audit/r2_stop_rule_audit_usa_2026-09-01.json`
- This report

## Registry sample of R2 closed_reasons (proof it's never stop-driven)

```
463  ORPHAN_AUTO_CLOSE
  2  ROTATION → LUPIN.NS (+51.8PP)
  2  → BMY · +9.9PP ALPHA
  2  → MU · +5.7PP ALPHA
 ... (all others are rotation ledger entries)
  0  reasons containing "STOP"
```

Standing by for your Option A / B / C / D choice.
