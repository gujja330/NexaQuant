# RISK001-B — ENTERPRISE RISK CONTROLLER ARCHITECTURE

**Document type:** Architecture specification
**Status:** DRAFT · design only · NO code · NO strategy change · NO implementation
**Owner role:** Chief Risk Officer · Quant Architect · Portfolio Risk Engineer
**Author:** AEGIS engineering
**Date opened:** 2026-07-17
**Preceded by:** RISK001-A (Exit Analytics Research) — findings from A gate whether B advances to implementation
**Superseded by:** RISK001-C (Implementation) — not yet chartered
**Sealed files touched:** zero
**Certification impact:** none until RISK001-C is authorised

---

## 0.  Precondition

This document may be **read and refined** independently of RISK001-A completion, but it may **not be implemented as code** (RISK001-C) until RISK001-A concludes with a `RECOMMEND-IMPLEMENT` verdict. If RISK001-A concludes `STAND-DOWN`, this document is archived and the RISK001 track closes.

Implementation of the Risk Controller **without** evidence from RISK001-A would be a discipline violation of the same class as the OPS001-E stale-Telegram silent failure — a plausible-looking safeguard adopted on intuition rather than measurement.

---

## 1.  AEGIS Investment Constitution

This constitution is the top-level design principle for every subsystem downstream. It must be quotable in ARCH001, referenced from every RISK spec, and honoured by every new engine that touches a position's life-cycle.

> **Rule 1 — Never allow preventable large losses.**
> A loss is preventable if a deterministic pre-defined rule would have exited the position at a smaller loss and the rule was in force. Every position, from the moment it enters the portfolio, has a preventable-loss ceiling.
>
> **Rule 2 — Profits are unlimited.**
> No rule caps the upside. Trailing stops adjust upward; break-even stops release; time-based tightening replaces static ceilings — but there is no return threshold above which a position is force-exited.
>
> **Rule 3 — Risk is always limited.**
> Every live position has a computed max-loss (in ₹ and in % of portfolio) known at entry and re-computed on every rebalance. If the current price path implies exceeding max-loss on the next bar, the position exits.
>
> **Rule 4 — Capital preservation overrides return maximisation.**
> When Level 1 (Capital) and Level 4 (Portfolio Optimisation) disagree, Level 1 wins. Always.
>
> **Rule 5 — The Risk Controller has veto power over every recommendation.**
> No score, no confidence value, no HRP weight, no operator override can force the system to hold a position that Level 1 has flagged for exit. Overrides that increase risk are structurally impossible; overrides that decrease risk (early exit) are always allowed.

These rules cannot be relaxed by parameter tuning. Any future proposal that would weaken them (`allow_stop_override=True`, `soft_stop_mode=True`, `disable_risk_controller=True`) is out-of-scope for this design.

---

## 2.  Position of the Risk Controller in the AEGIS pipeline

Current pipeline (pre-RISK001):

```
     Market data
         │
         ▼
   Recommendation
      engine
         │
         ▼
   Portfolio optimiser (HRP)
         │
         ▼
   Recommendation set  →  Telegram / Sheets / DB
```

Post-RISK001 pipeline:

```
     Market data
         │
         ▼
   Recommendation engine
         │
         ▼
   Portfolio optimiser (HRP)
         │
         ▼
   ┌──────────────────────────────┐
   │      Risk Controller         │   ← RISK001-C
   │  (4-level priority engine)   │
   └──────────────────────────────┘
         │
         ▼
   Final action set   →  Telegram / Sheets / DB
```

The Risk Controller sits **after** the portfolio optimiser and **before** external emission. It reads the optimiser's proposed set and produces a final set that may:

- Include positions the optimiser proposed unchanged (`APPROVE`)
- Include positions the optimiser proposed with reduced weight (`REDUCE`)
- Exclude positions the optimiser proposed to add (`REJECT`)
- Force-exit positions the optimiser proposed to keep (`FORCE_EXIT`)
- Force-exit positions regardless of optimiser input (`RISK_OVERRIDE`)

The optimiser's output is **advisory**. The Risk Controller's output is **binding**.

---

## 3.  The four-level hierarchy

Every candidate action passes through **all four levels**, in order, and the first level that fires wins. Downstream levels do not run for that position on that bar.

### Level 1 — Capital Protection (absolute priority)

Fires when a rule of type "loss now exceeds pre-defined ceiling" is true.

**Sub-rules within Level 1:**

| Rule | Trigger | Action |
|:--|:--|:--|
| **L1.a Hard stop** | `close ≤ entry × (1 − hard_stop_pct)` where `hard_stop_pct` is set per-position at entry (§6) | FORCE_EXIT at next-bar open |
| **L1.b Gap-down protection** | `open ≤ entry × (1 − gap_stop_pct)` where `gap_stop_pct > hard_stop_pct` | FORCE_EXIT at same-bar open |
| **L1.c Max daily loss** | `daily_pct < − max_daily_pct` (default 3%) | FORCE_EXIT at close |
| **L1.d Max cumulative portfolio loss** | `portfolio_drawdown_from_peak < − max_dd_pct` (default 10%) | FORCE_EXIT of the *highest-MAE position* first; iterate until portfolio DD is within limit |
| **L1.e Per-sector loss limit** | `sector_pnl_pct_from_peak < − max_sector_dd_pct` (default 6%) | REDUCE all positions in that sector proportionally until within limit |

None of these rules override each other; if more than one fires on the same bar, all of their actions are queued and applied in the order L1.a → L1.e.

### Level 2 — Profit Protection

Fires only when the position is currently profitable. Cannot fire otherwise.

| Rule | Trigger | Action |
|:--|:--|:--|
| **L2.a Trailing stop** | `close ≤ running_high × (1 − trail_pct)` and `running_high ≥ entry × (1 + trail_activation_pct)` | EXIT at next-bar open |
| **L2.b Break-even stop** | position has traded above `entry × (1 + break_even_activation_pct)` for at least 1 bar AND `close ≤ entry` | EXIT at next-bar open |
| **L2.c Time-decay tightening** | position age > `HOLD × 0.75` AND `close > entry` | Tighten trailing stop from `trail_pct` to `trail_pct / 2` |
| **L2.d Profit lock** | `close ≥ entry × (1 + target_pct)` where `target_pct` is per-position | Set new floor at `entry × 1.02` (2% profit locked) |

Level 2 rules preserve gains. They never force exit at a loss (that is L1's job).

### Level 3 — Thesis Protection

Fires when the score-generating conditions materially change. All triggers require *evidence*, not intuition.

| Rule | Trigger | Action |
|:--|:--|:--|
| **L3.a Regime change** | `regime_at_entry != regime_now` AND the shift is one of {Strong→Weak, Neutral→Weak} (i.e., risk-off transition) | REDUCE position weight by 30% |
| **L3.b Confidence collapse** | `current_score < 0.5 × entry_score` OR `current_confidence < 0.5 × entry_confidence` | EXIT at next-bar open |
| **L3.c Sector strength collapse** | Sector strength score has dropped below the 20th percentile of its own 63-day history | REDUCE position weight by 20% |
| **L3.d Technical structure break** | `close < 200_dma` for 5 consecutive sessions after entering above it | REDUCE position weight by 25% |

Level 3 actions are typically REDUCE (partial exit), not FORCE_EXIT. Level 3 respects the possibility that thesis deterioration is temporary; Level 1 does not — a hard stop is a hard stop.

### Level 4 — Portfolio Optimisation

The current behaviour. Fires only if no Level 1, 2, or 3 rule fires for the position on that bar.

| Rule | Trigger | Action |
|:--|:--|:--|
| **L4.a HRP rebalance** | rebalance day (`rebal=63` cadence) AND HRP proposes a weight change > 20% relative | ADJUST_WEIGHT |
| **L4.b Rotation out of top-N** | position drops below top-N in daily score AND another position outside top-N would enter with higher score | ROTATE (exit current, add new) — **but only if position is currently within stop budget** (see §5) |
| **L4.c Sector cap enforcement** | Adding a proposed BUY would breach `sector_cap=2` | Reject the new BUY, keep existing positions |
| **L4.d Name cap enforcement** | Any single position weight would exceed `name_cap=0.30` | Reduce that position's weight to cap |

The critical change from current behaviour: **L4.b (rotation) is subordinate to L1 and L2.** A position cannot be "rotated" if it is currently below entry — because Level 1 (if the loss is bad enough) or Level 2 (if it's profitable and needs to be protected) speaks first. Rotation is a *fair-weather* mechanism.

---

## 4.  Per-position risk parameters (set at entry)

Every new position, at entry, is stamped with a fixed set of risk parameters computed from the position's characteristics. These parameters cannot change during the position's life (they are per-position constants), but they may be **read** by every level of the controller.

| Parameter | Type | Computed from | Purpose |
|:--|:--|:--|:--|
| `hard_stop_pct` | float | max(4%, min(8%, 2 × ATR_20 / entry_price)) | L1.a threshold — volatility-aware |
| `gap_stop_pct` | float | 1.5 × hard_stop_pct | L1.b threshold — accepts wider gap losses only |
| `trail_pct` | float | 3% (fixed) or 0.5 × ATR / entry (whichever larger) | L2.a threshold |
| `trail_activation_pct` | float | 5% (fixed) | L2.a activation |
| `break_even_activation_pct` | float | 3% (fixed) | L2.b activation |
| `target_pct` | float | max(4%, 1.5 × hard_stop_pct) | L2.d threshold — target is at minimum 1.5× the loss ceiling |
| `entry_score` | float | recommendation engine's score at entry | L3.b baseline |
| `entry_confidence` | float | confidence engine's confidence at entry | L3.b baseline |
| `regime_at_entry` | enum | Strong / Neutral / Weak | L3.a baseline |
| `sector_at_entry` | str | ClientProfile sector (tenant-generic; no hardcoded sector list here) | L1.e + L3.c grouping |
| `max_position_loss_inr` | int | position_size × hard_stop_pct | L1.a and reporting |
| `max_position_loss_pct_of_portfolio` | float | max_position_loss_inr / total_portfolio_value | Portfolio-level accountability |

These parameters are computed **once** at entry and stored in the position record. Any future re-computation is a data-quality violation.

---

## 5.  Machine-readable exit reason codes

Every exit event emits **exactly one** reason code. The set is fixed; no free-text reason is ever emitted alongside without also emitting a code.

| Code | Level | Human description | Persisted with |
|:--|:-:|:--|:--|
| `HARD_STOP` | L1.a | Price crossed pre-set hard stop | trigger_price, exit_price, entry_price, loss_pct, ATR_at_entry |
| `GAP_STOP` | L1.b | Price gapped through the hard stop | gap_open_price, hard_stop_price, actual_loss_pct |
| `MAX_DAILY_LOSS` | L1.c | Single-day loss exceeded daily budget | daily_pct, threshold |
| `PORTFOLIO_DD_LIMIT` | L1.d | Portfolio drawdown limit hit; this position was highest-MAE | portfolio_dd_pct, mae_pct_this_position |
| `SECTOR_DD_LIMIT` | L1.e | Sector drawdown limit hit | sector_dd_pct, threshold |
| `TRAILING_STOP` | L2.a | Trailing stop triggered on profitable position | running_high, trail_pct, exit_price, realised_gain_pct |
| `BREAK_EVEN_STOP` | L2.b | Break-even stop caught a giveback | entry_price, high_reached, exit_price |
| `PROFIT_LOCK` | L2.d | Target reached; profit floor active (informational, not exit) | target_pct, current_pct |
| `REGIME_CHANGE` | L3.a | Regime transitioned risk-off; weight reduced | regime_at_entry, regime_now, action=REDUCE_30 |
| `CONFIDENCE_COLLAPSE` | L3.b | Score or confidence halved vs entry | entry_score, current_score, entry_confidence, current_confidence |
| `SECTOR_STRENGTH_COLLAPSE` | L3.c | Sector strength dropped to 20th percentile of its 63d history | sector_strength_at_entry, current, percentile |
| `STRUCTURE_BREAK` | L3.d | 200DMA breached for 5+ sessions | dma200_at_entry, current, breach_days |
| `PORTFOLIO_ROTATION` | L4.b | Rotated out by portfolio optimiser (fair-weather only) | new_entry_ticker, new_score, this_score, was_position_profitable |
| `TIME_EXIT` | L4.a | HOLD=63 day expiry | held_days |
| `SECTOR_CAP` | L4.c | Sector cap enforcement (rare on exits; used mostly on rejects) | sector, cap, current_sector_weight |
| `NAME_CAP` | L4.d | Name cap enforcement | ticker, cap, current_weight |
| `MANUAL_OVERRIDE_REDUCE_RISK` | any | Operator manually exited or reduced | operator_id, timestamp, notes |

`MANUAL_OVERRIDE_INCREASE_RISK` **does not exist** by design (Rule 5 — no override that increases risk is structurally allowed).

---

## 6.  State machine

Every position has a well-defined state at every moment. Transitions are deterministic; the state machine is the primary audit surface.

```
                ┌─────────┐
                │  NEW    │        (proposed by engine, awaiting first bar)
                └────┬────┘
                     │  entry filled
                     ▼
                ┌─────────┐
      ┌────────►│  LIVE   │◄─────────┐
      │         └────┬────┘          │
      │              │               │
      │              │ L2 or L3      │ L4 rebalance
      │              │ triggered     │ (fair-weather rotation not yet)
      │              ▼               │
      │         ┌─────────┐          │
      │         │AT_RISK  │──────────┘
      │         └────┬────┘
      │              │ any Level 1 trigger
      │              │ OR L2/L3 EXIT trigger
      │              ▼
      │         ┌─────────┐
      │         │ EXITING │      (order queued for next bar)
      │         └────┬────┘
      │              │  order filled
      │              ▼
      │         ┌─────────┐
      │         │ EXITED  │      (terminal, immutable)
      │         └─────────┘
      │
      │  L2/L3 conditions no longer hold on subsequent bar
      └── back to LIVE
```

### 6.1  State transition rules

| From | To | Trigger | Bar timing |
|:--|:--|:--|:-:|
| NEW | LIVE | Entry order filled | same bar |
| LIVE | AT_RISK | Any L2 or L3 rule fires but action is REDUCE (not EXIT) | same bar |
| AT_RISK | LIVE | The triggering condition no longer holds on next bar | next bar |
| LIVE | EXITING | Any L1 rule fires | same bar (queues exit for next-bar open) |
| AT_RISK | EXITING | L1 rule fires OR L2/L3 EXIT action | same bar |
| EXITING | EXITED | Exit order filled | next bar open |

The state is persisted at the end of every bar. The daily audit report emits every state transition with timestamp + reason code.

---

## 7.  Decision tree — how the controller processes one bar for one position

```
             ┌──────────────────────────────┐
             │  New bar (close) for ticker  │
             │        Position: LIVE        │
             └──────────────┬───────────────┘
                            │
                            ▼
             ┌──────────────────────────────┐
             │  L1.a  hard-stop breach?     │
             └──────────────┬───────────────┘
                            │
              yes ──────────┼────────── no
                │                        │
                ▼                        ▼
       queue FORCE_EXIT      ┌──────────────────────┐
       reason=HARD_STOP      │ L1.b  gap-stop hit?  │
                             └──────────┬───────────┘
                                        │ (repeat for L1.c–e, then L2.a–d, then L3.a–d)
                                        │
                                        ▼
                             ┌──────────────────────┐
                             │  no L1/2/3 fired?    │
                             │  → allow L4 to run   │
                             │  (fair-weather only) │
                             └──────────────────────┘
```

Only one exit reason wins per bar. The evaluation is short-circuiting: the first rule that returns "fire" ends the tree for that position on that bar. Levels 2 and 3 rules that fire but return REDUCE (not EXIT) are queued together and applied at end-of-bar in a deterministic tie-break order (L2.a, L2.b, L2.c, L2.d, L3.a, L3.b, L3.c, L3.d).

---

## 8.  Priority engine — pseudocode

Not implementation. Pseudocode to remove ambiguity about ordering.

```
def evaluate_position(position, bar, portfolio):
    if position.state == EXITED:
        return NO_OP

    # --- LEVEL 1: CAPITAL PROTECTION ---
    for rule in [L1a_hard_stop, L1b_gap_stop, L1c_max_daily,
                 L1d_portfolio_dd, L1e_sector_dd]:
        verdict = rule.evaluate(position, bar, portfolio)
        if verdict.fires:
            return Action(FORCE_EXIT, reason=verdict.code, priority=1)

    # --- LEVEL 2: PROFIT PROTECTION ---
    if position.current_return > 0:
        for rule in [L2a_trailing, L2b_break_even,
                     L2c_time_tightening, L2d_profit_lock]:
            verdict = rule.evaluate(position, bar, portfolio)
            if verdict.fires and verdict.action == EXIT:
                return Action(EXIT, reason=verdict.code, priority=2)
            elif verdict.fires and verdict.action == ADJUST:
                position.apply_adjustment(verdict)  # non-exit adjustment

    # --- LEVEL 3: THESIS PROTECTION ---
    for rule in [L3a_regime, L3b_confidence,
                 L3c_sector, L3d_structure]:
        verdict = rule.evaluate(position, bar, portfolio)
        if verdict.fires:
            if verdict.action == EXIT:
                return Action(EXIT, reason=verdict.code, priority=3)
            elif verdict.action == REDUCE:
                return Action(REDUCE, reason=verdict.code,
                              new_weight=verdict.new_weight, priority=3)

    # --- LEVEL 4: PORTFOLIO OPTIMISATION (fair-weather only) ---
    if position.current_return >= 0 or position.current_return > -position.hard_stop_pct * 0.5:
        # only allow rotation if position is above entry OR less than halfway to hard stop
        return L4_evaluate(position, bar, portfolio)

    # Position is loss-making beyond half the stop budget — do NOT rotate; hold and let L1 fire.
    return NO_OP
```

The final `if` in Level 4 is the critical change: **rotation is only permitted for positions that are not in significant drawdown**. This is what would have prevented the ICICIGI −11.5% exit in today's report — the position would have hit the hard stop long before reaching the rotation criterion.

---

## 9.  Audit trail

Every action, every state transition, every rule evaluation is logged. The audit is the ground truth; the Telegram report is a view of it.

### 9.1  Audit record schema

Every audit row has these fields:

| Field | Type | Notes |
|:--|:--|:--|
| `audit_id` | UUID | Never reused |
| `timestamp_utc` | ISO 8601 | UTC always; IST derived |
| `bar_asof` | ISO date | Market data date (three-dates discipline from ARCH001) |
| `run_id` | UUID | The pipeline run that produced this event |
| `ticker` | str | |
| `position_id` | UUID | Stable per position across its life |
| `event_type` | enum | ENTRY / STATE_CHANGE / RULE_EVAL / ACTION / EXIT |
| `state_from` | enum | Any of §6 states |
| `state_to` | enum | |
| `reason_code` | enum | §5 codes (null for pure evaluations that didn't fire) |
| `level` | int | 1..4 |
| `rule_id` | str | e.g. `L1.a` |
| `input_snapshot` | JSON | The rule's inputs — bar, portfolio state, position parameters |
| `output_snapshot` | JSON | The rule's output — fires/no-fire, action, weight change |
| `portfolio_dd_pct` | float | Snapshot at time of event |
| `position_return_pct` | float | Snapshot at time of event |
| `mfe_so_far_pct` | float | |
| `mae_so_far_pct` | float | |
| `sealed_fingerprint` | str | MON001 hash at time of event — must match sealed value |

### 9.2  Audit storage

- **Hot store:** append-only JSONL in `reports/risk001_audit/<YYYY-MM>/audit_<YYYYMMDD>.jsonl`
- **Cold store:** monthly compaction to parquet in `reports/risk001_audit/archive/audit_<YYYY-MM>.parquet`
- **Retention:** indefinite. The audit is the historical record; deletion is not authorised without a governance amendment.

### 9.3  What the audit enables

- LAB011 can compute "exit reason → downstream outcome" attributions without touching any production code
- Any post-hoc question ("did we ever violate Rule 4?") is answerable by SQL
- Any regulatory or client-facing dispute has a byte-level record
- Any change to the controller's behaviour is diff-able bar-by-bar against the pre-change baseline

---

## 10.  Override rules

### 10.1  Structurally forbidden overrides

The following overrides are **impossible** in the design — no configuration, no flag, no operator action can enable them:

1. Disable Level 1 for a position
2. Raise the hard stop after entry
3. Convert an L1 action into REDUCE (Level 1 is always FORCE_EXIT)
4. Turn off audit logging
5. Delete audit rows
6. Hold a position through a `PORTFOLIO_DD_LIMIT` breach

Any code path proposing to enable one of these must be rejected in review.

### 10.2  Permitted operator overrides

These overrides are allowed because they *decrease* risk relative to what the controller would do:

| Override | Effect | Audit code |
|:--|:--|:--|
| **Force early exit** | Operator manually EXITs a position that the controller has not yet flagged | `MANUAL_OVERRIDE_REDUCE_RISK` |
| **Reject proposed entry** | Operator refuses a new BUY from the recommendation set | `MANUAL_REJECT_ENTRY` |
| **Reduce position weight** | Operator reduces a live position below controller-proposed weight | `MANUAL_REDUCE_WEIGHT` |
| **Tighten hard stop** | Operator sets a tighter hard stop than the position's entry-computed value | `MANUAL_TIGHTEN_STOP` |
| **Halt entire pipeline** | Operator invokes the OPS001-C halt trigger; no new actions until re-enabled | `MANUAL_HALT_ALL` |

Every operator override generates its own audit row and is time-stamped and attributable.

### 10.3  What operators cannot do

- Loosen a hard stop
- Re-open an EXITED position (must be a fresh ENTRY with a new position_id)
- Suppress an EXITING queue
- Adjust an audit row after commit
- Disable a rule for a specific position

---

## 11.  Database + telemetry

### 11.1  Position table (new — additive)

`data/aegis_positions.parquet`:

| Column | Type | Notes |
|:--|:--|:--|
| `position_id` | UUID | PK |
| `ticker` | str | |
| `entry_date_ist` | date | |
| `entry_price` | float | |
| `entry_score` | float | |
| `entry_confidence` | float | |
| `entry_regime` | enum | |
| `entry_sector` | str | |
| `entry_atr_20` | float | |
| `hard_stop_pct` | float | per-position |
| `gap_stop_pct` | float | |
| `trail_pct` | float | |
| `target_pct` | float | |
| `max_position_loss_inr` | int | |
| `max_position_loss_pct_of_portfolio` | float | |
| `state` | enum | NEW / LIVE / AT_RISK / EXITING / EXITED |
| `state_updated_utc` | ISO 8601 | |
| `mfe_so_far_pct` | float | |
| `mae_so_far_pct` | float | |
| `running_high` | float | for trailing stop |
| `exit_date_ist` | date | null until EXITED |
| `exit_price` | float | |
| `exit_reason_code` | enum | §5 |
| `realised_return_pct` | float | |

### 11.2  Telemetry emitted on every run

To `reports/risk001_metrics.jsonl`:

```
{"run_id":"...", "asof":"2026-07-18", "positions_live":10, "positions_at_risk":2,
 "positions_exited_today":1, "level_fires_today": {"L1":1, "L2":0, "L3":2, "L4":0},
 "portfolio_dd_pct":-1.2, "worst_position_mae_pct":-3.4,
 "reason_counts_today": {"HARD_STOP":1, "REGIME_CHANGE":2}}
```

This telemetry is the OPS002 dashboard's primary input for RISK001 monitoring.

---

## 12.  Monitoring hooks

The Risk Controller integrates with three monitoring surfaces:

### 12.1  MON001 (sealed baseline)

- No integration. MON001 monitors the recommendation engine's fingerprint. The Risk Controller sits *after* the recommendation engine and *does not* participate in the sealed core.
- Explicit test: the MON001 fingerprint must remain `e4c070673568c52d…` after RISK001-C ships. If RISK001-C's presence somehow perturbs the recommendation engine, that is a discipline failure.

### 12.2  MON002 (Drift Detection — future)

- Will consume RISK001 telemetry (§11.2)
- Will alert if `level_fires_today.L1` exceeds a rolling percentile of its own history (Level 1 firing frequency should be low and stable; a sudden spike is either a market event or a data-quality problem)

### 12.3  OPS002 (Operational Excellence — future)

- Will surface the RISK001 telemetry on the operator dashboard
- Will provide the "kill switch" (§10.2 MANUAL_HALT_ALL) as an operator-safe UI control

---

## 13.  Analytics hooks — feeding LAB011

LAB011 (Outcome Intelligence) will consume the RISK001 audit trail without touching any production code. Specifically:

| LAB011 question | Data source |
|:--|:--|
| "Which exit reasons produce the best downstream outcomes?" | audit.exit_reason + audit.mfe_so_far + follow-up price paths |
| "Which sectors trigger L1 most often?" | audit.reason_code + audit.entry_sector |
| "How does confidence at entry correlate with L1 firing?" | position.entry_confidence + audit.reason_code |
| "Are we exiting winners too early via L2?" | position.exit_price + running_high (were prices reached later?) |
| "Do overrides improve outcomes vs the controller's default action?" | audit.reason_code=MANUAL_* + realised_return |

LAB011 is a read-only consumer. It does not influence controller behaviour.

---

## 14.  Integration with OPS002

OPS002 (Operational Excellence) treats the Risk Controller as a first-class subsystem:

- Health endpoint: `python -m india.risk_controller.health` returns `{status, positions_live, level1_last_fire_utc, sealed_fingerprint}`
- Metrics endpoint: `python -m india.risk_controller.metrics` returns the same shape as §11.2 for dashboarding
- Alert routing: L1 fires + operator-override events route through the OPS001-C notification manager to the same Telegram / Sheets / channels
- Kill switch: OPS002 dashboard exposes `MANUAL_HALT_ALL` (§10.2) with a two-step confirmation UI

---

## 15.  Testing surface (for eventual RISK001-C)

When RISK001-C is authorised, the implementation must satisfy this test matrix. These tests are the acceptance criteria; they are not part of RISK001-B, but are declared here so the future implementation knows the target.

| Test class | Count target | Purpose |
|:--|:-:|:--|
| Unit tests per rule (L1.a–L4.d) | 17 rules × 3 scenarios = 51 | fires/no-fires/edge cases |
| State-machine transitions | 6 legal + 3 illegal | Every documented transition |
| Priority-engine short-circuiting | 6 | L1 short-circuits L2/3/4; L2/3 short-circuit L4; etc. |
| Structurally-forbidden override rejection | 6 | §10.1 items — each must be structurally impossible |
| Audit-record schema | 3 | Every event type emits a valid row |
| MON001 fingerprint invariance | 1 | After RISK001-C ships, sealed fingerprint unchanged |
| Sealed-file invariance | 1 | Zero sealed files touched |
| Full-suite backtest | 1 | Replay the 285-position historical dataset under RISK001-C; results within 0.5% of RISK001-A's simulator output for the winning policy |

---

## 16.  Rollout plan (design only — not yet authorised)

If RISK001-A returns `RECOMMEND-IMPLEMENT` and this document is approved:

| Phase | Duration | Guardrail |
|:--|:-:|:--|
| RISK001-C-1: Implement controller (behind feature flag) | 1 week | Feature flag `RISK_CONTROLLER_ENABLED=false` in production |
| RISK001-C-2: Shadow-mode | 2 weeks | Controller runs in parallel; emits telemetry but does NOT alter recommendations. Compare daily against Policy A baseline |
| RISK001-C-3: Paper-trade mode | 4 weeks | Controller alters recommendations in a shadow book; real recommendations continue unchanged |
| RISK001-C-4: Live | pending operator go/no-go | Live for real book only after paper-trade shows expected behaviour |

Shadow mode is required. Direct live rollout is not permitted.

---

## 17.  Non-goals

- This document does **not** define specific numeric thresholds (5% vs 4.5% vs 5.2%). The thresholds shown in §3 are illustrative defaults; the final values come from RISK001-A's winning policy.
- This document does **not** propose changing HRP, scoring, entry logic, sector caps, name caps, HOLD, or rebal.
- This document does **not** propose any change to the sealed baseline files.
- This document does **not** describe options, futures, or hedging overlays (out-of-scope for the current cash-equity book).
- This document does **not** address broker-integration for automatic order placement — RISK001-C emits actions; execution remains operator-manual in v1.

---

## 18.  Integrity + sign-off (for when this document is adopted)

Adoption of this document as authoritative requires:

- RISK001-A `RECOMMEND-IMPLEMENT` verdict, with commit SHA
- MON001 fingerprint at adoption time (must be current sealed value)
- Sealed-file diff check: 0
- Cumulative_strategy_search: 38 (unchanged)
- Operator sign-off recorded in `docs/RISK001_APPROVALS.md` (new document, to be created if adoption proceeds)

---

## 19.  Change log

| Date | Change | Author |
|:--|:--|:--|
| 2026-07-17 | Initial architecture spec | AEGIS engineering |
