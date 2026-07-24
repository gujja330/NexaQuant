# AEGIS Phase 3 · Sprint C1 · Trade State Engine (v2)
### Scoped Sprint Spec (docs only · NOT YET BUILT · pending operator "start")

**Revised 2026-07-24** per operator review. Six architectural refinements applied:
1. **Two state machines** — separate Recommendation State + Position State
2. **Dynamic targets** — `TARGET(+X%)` where X is config/data-driven, never hardcoded `TARGET1/2/3`
3. **Data-only scope** — no intelligence calculations (those live in C2 · Lifecycle Intelligence)
4. **A1 + A2 are literal blockers** — cannot start C1 without those on disk
5. **All new engines are additive** — no existing engine modified
6. **Recommendation Drift Intelligence (C4) queued** as new engine after C1/C2/C3

---

## The Problem This Sprint Fixes

Recommendations today are stateless labels. `BUY APOLLO ₹8592` on day 0, 1, 2, …, 20 with only the date changing. No holding day, no %-move, no target progress, no exit signal. Operator confusion + stale notifications are downstream symptoms.

**Fix:** two state machines running independently but linked.

---

## Two State Machines (Refinement 2)

Institutionally these solve different problems and MUST NOT be conflated:

### RecommendationState (what the model believes)

```
GENERATED → APPROVED → ACTIVE → SUPERSEDED → EXPIRED
```

- `GENERATED` — model emitted the rec today
- `APPROVED` — passed conflict/calibration/regime gates (Sprint 3 Rec Engine v3)
- `ACTIVE` — currently the model's view on this ticker
- `SUPERSEDED` — the model has issued a NEWER rec for the same ticker (this one is no longer the current opinion)
- `EXPIRED` — horizon reached, or ticker no longer in universe

### PositionState (what the paper portfolio looks like)

```
NEW → OPEN → TARGET(+X%) → EXIT → POST_EXIT → REVERSAL → REENTRY → CLOSED
                       ↘ STOPLOSS → CLOSED
                       ↘ EXPIRED (horizon) → CLOSED
```

- `NEW` — position just opened (day 0)
- `OPEN` — active position, no target hit yet
- `TARGET(+X%)` — position has crossed X% return, where X is dynamic (see Refinement 3)
- `STOPLOSS` — stoploss threshold hit
- `EXIT` — position closed (operator marks or trailing-stop triggers or horizon expires)
- `POST_EXIT` — day+1..N after exit; monitoring for reversal
- `REVERSAL` — price re-crosses exit level within reversal_window
- `REENTRY` — reversal confirmed → new PositionState row spawned
- `CLOSED` — terminal; no further transitions

**Link:** every PositionState carries a `recommendation_id` referring to the RecommendationState that spawned it. When RecommendationState `→ SUPERSEDED`, the corresponding PositionState may or may not transition — that's a policy decision, not a hard rule.

---

## Dynamic Targets (Refinement 3)

**Wrong (v1 spec):** hardcoded slots `TARGET1 · TARGET2 · TARGET3`.

**Right (v2 spec):** targets are a config-owned or data-owned LIST. State labels carry the actual threshold:

```
State transitions in order the position crosses them:
  OPEN → TARGET(+2%) → TARGET(+3%) → TARGET(+5%) → TARGET(+7%) → TARGET(+10%) → EXIT
```

If tomorrow the operator (or a research promotion) changes the target ladder to `[+1%, +2%, +4%, +6%, +8%]`, the engine picks it up from config without code changes. State label becomes `TARGET(+1%)` etc.

The engine does NOT know how many targets exist. It reads the list, iterates the ladder, transitions when each threshold crosses.

**Config shape:**
```yaml
# configs/trade_state_config.yaml
market_defaults:
  india:
    target_ladder_pct: [2.0, 3.0, 5.0, 7.0, 10.0]   # dynamic — any length
    stoploss_pct: -8.0
    horizon_expiry_days: 60
    reversal_window_days: 20
    reversal_confirm_days: 3
    trailing_stop_pct: 5.0
  usa:
    target_ladder_pct: [2.0, 4.0, 6.0, 8.0]
    stoploss_pct: -6.0
    horizon_expiry_days: 45
    reversal_window_days: 15
    reversal_confirm_days: 3
    trailing_stop_pct: 4.0
```

---

## Data-Only Scope (Refinement 4 — critical)

The Trade State Engine **only carries deterministic facts**:

| Field | Purpose |
|---|---|
| `recommendation_state` | current RecommendationState label |
| `position_state` | current PositionState label |
| `state_since` | date this state was entered |
| `days_in_state` | days since state entered |
| `holding_day` | days since NEW (0-indexed) |
| `entry_price` · `current_price` · `highest_price` · `lowest_price` | price facts |
| `current_return_pct` · `highest_return_pct` · `lowest_return_pct` · `current_drawdown_pct` | arithmetic from prices |
| `target_crossed` | list of thresholds crossed so far (e.g. `[2.0, 3.0]`) |
| `next_target_pct` | next un-crossed threshold from the ladder (or `null` if all crossed) |
| `state_transitions` | append-only list of `(from, to, asof)` tuples |

**The Trade State Engine does NOT emit:**
- ❌ `exit_confidence` (belongs in C2 · Lifecycle Intelligence)
- ❌ `historical_probability` (belongs in C2)
- ❌ `expected_holding` (belongs in C2)
- ❌ `expected_exit` (belongs in C2)
- ❌ `reentry_probability` (belongs in C2)
- ❌ `lifecycle_score` (belongs in C2)
- ❌ any BUY/SELL/HOLD recommendation (that's Rec Engine)
- ❌ any AI narrative or renderer output

If a downstream layer wants a probability, it computes it from state — not from the state engine.

---

## Modules to be Delivered (Sprint C1 · code — v2)

| # | File | Purpose | LOC (est) |
|---|---|---|---|
| 1 | `backend/trade_state/__init__.py` | Public API — `TradeStateEngine`, both state enums | ~40 |
| 2 | `backend/trade_state/types.py` | `RecommendationState` enum · `PositionState` enum · `PositionStateRow` dataclass · `RecommendationStateRow` dataclass · `StateTransition` | ~180 |
| 3 | `backend/trade_state/recommendation_state_machine.py` | RecommendationState transitions: reads rec_history, marks SUPERSEDED / EXPIRED per rules | ~120 |
| 4 | `backend/trade_state/position_state_machine.py` | PositionState transitions: reads rec + prices, iterates target ladder from config, computes state per (position, asof) | ~200 |
| 5 | `backend/trade_state/engine.py` | `TradeStateEngine.update(asof)` — orchestrates both state machines, emits rows | ~120 |
| 6 | `backend/trade_state/persistence.py` | Append-only writer for `trade_state.parquet` + `recommendation_state.parquet` + `state_transitions.parquet`; dedupe on natural keys | ~90 |
| 7 | `india/trade_state/run.py` | India runner | ~90 |
| 8 | `usa/research/trade_state/run.py` | USA runner | ~90 |
| 9 | `configs/trade_state_config.yaml` | Target ladders + stoploss + horizons per market | ~50 |
| 10 | `backend/tests/test_sprint_c1.py` | Regression suite (target ≥ 25 tests) | ~450 |

Total: ~1430 lines · 10 files · zero sealed engine touched · no AI agent added.

---

## Data Flow (v2)

```
INPUTS (all existing, read-only):
  reports/recommendation_history.parquet          (Runner 2 / Rec v3)
  reports/recommendation_history_runner1.parquet  (Runner 1 legacy audit)
  data/raw/india/<TICKER>_D1.parquet              (India prices)
  usa/data/raw/us/<TICKER>_D1.parquet             (USA prices)
  configs/trade_state_config.yaml                 (target ladders + stoploss + horizons)
  (A1/A2 outputs)                                 (repo audit + engine inventory — for validation only)

PROCESSING:
  1. RecommendationStateMachine.update(asof)
       - Read all recommendations in history
       - For each ticker: mark newer recs as ACTIVE, older ones SUPERSEDED
       - Mark past-horizon recs EXPIRED
  2. PositionStateMachine.update(asof)
       - For each APPROVED/ACTIVE recommendation:
         - Look up entry_price (rec_asof close)
         - Look up price series entry_asof..asof
         - Compute current/highest/lowest returns
         - Iterate target ladder from config: for each threshold, mark crossed if hit
         - Determine current state: OPEN vs TARGET(+X%) vs STOPLOSS vs EXIT vs …
         - Emit state transition if state changed
  3. Persistence — write today's snapshot + append to history parquets

OUTPUTS (all new, additive):
  reports/trade_state.json                    (today's snapshot)
  reports/trade_state.parquet                 (today's snapshot table — one row per open position)
  reports/trade_state_history.parquet         (append-only, one row per (position, day))
  reports/recommendation_state.parquet        (append-only, one row per (rec_id, day))
  reports/state_transitions.parquet           (append-only, one row per transition event)
  usa/reports/… (mirror for USA)
```

---

## Transition Rules (data-driven)

**PositionState transitions** (deterministic, per-day):

| From | To | Trigger |
|---|---|---|
| `NEW` | `OPEN` | day+1 after rec_asof |
| `OPEN` | `TARGET(+X%)` | current_return_pct crosses first uncrossed threshold in ladder |
| `TARGET(+X%)` | `TARGET(+Y%)` | current_return_pct crosses next threshold (Y > X) |
| any `OPEN/TARGET*` | `STOPLOSS` | current_return_pct ≤ stoploss_pct |
| any `OPEN/TARGET*` | `EXIT` | operator marks exit OR trailing_stop triggers OR horizon reached |
| `STOPLOSS` | `CLOSED` | day+1 after stoploss |
| `EXIT` | `POST_EXIT` | day+1 after exit |
| `POST_EXIT` | `REVERSAL` | price re-crosses exit_level within reversal_window_days |
| `REVERSAL` | `REENTRY` | reversal confirmed by reversal_confirm_days of trend |
| `REENTRY` | new `OPEN` row | new position lifecycle spawned |
| any | `CLOSED` | horizon_expiry_days reached |

**RecommendationState transitions:**

| From | To | Trigger |
|---|---|---|
| — | `GENERATED` | rec appears in recommendation_history |
| `GENERATED` | `APPROVED` | passed Sprint 3 Rec Engine v3 gates (this is instantaneous today) |
| `APPROVED` | `ACTIVE` | day+1 after generation, still current opinion for this ticker |
| `ACTIVE` | `SUPERSEDED` | a newer recommendation exists for the same ticker/runner |
| `ACTIVE` / `SUPERSEDED` | `EXPIRED` | horizon_expiry_days reached OR ticker leaves universe |

Every transition deterministic from `(prior_state, price_series, other_recs, config)` → `NEXT_state`. Replayable. Walk-forward-safe.

---

## Regression Tests (Sprint C1 · v2 · target ≥ 25)

**PositionState transitions (10 tests):**
1. `NEW → OPEN` on day+1
2. `OPEN → TARGET(+2%)` when current_return crosses first threshold
3. `TARGET(+2%) → TARGET(+3%)` on next threshold cross
4. `OPEN → STOPLOSS` on stoploss cross
5. `TARGET(+5%) → EXIT` on trailing-stop trigger
6. `EXIT → POST_EXIT` on day+1
7. `POST_EXIT → REVERSAL` on price re-cross within window
8. `REVERSAL → REENTRY` after confirm-days
9. `REENTRY → new OPEN` spawned as separate lifecycle row
10. State never regresses (TARGET(+5%) → OPEN forbidden)

**RecommendationState transitions (5 tests):**
11. New rec appears → `GENERATED → APPROVED → ACTIVE`
12. Newer rec on same ticker → old rec `ACTIVE → SUPERSEDED`
13. Horizon reached → `ACTIVE → EXPIRED`
14. Same rec appears twice on same day → dedup (no duplicate ACTIVE)
15. Ticker leaves universe → `ACTIVE → EXPIRED`

**Dynamic-target invariants (3 tests):**
16. Target ladder `[+2, +3, +5]` produces exactly 3 possible TARGET states
17. Changing ladder to `[+1, +4, +8, +12]` produces 4 TARGET states, no code change
18. Target labels carry actual threshold (`TARGET(+5%)` not `TARGET1`)

**Data-only scope invariants (2 tests):**
19. Trade State output contains NO `exit_confidence`, `historical_probability`, `expected_holding`, `expected_exit`, `reentry_probability`, `lifecycle_score`, `buy`, `sell`, `hold` keys
20. All emitted fields are deterministic-from-data (property test on 100 random inputs)

**Anti-lookahead (2 tests):**
21. State at asof=D uses only price data ≤ D (lookahead guard passes)
22. Reversal detection uses only post-exit price ≤ replay asof

**Integration (3 tests):**
23. Reads Runner 1 audit-trail rec history correctly
24. Reads Runner 2 (Rec v3) rec history correctly
25. Handles missing price parquet gracefully (state = UNKNOWN, not crash)

**End-to-end (2 tests):**
26. India runner on real data produces valid `trade_state.json` + `trade_state.parquet`
27. USA runner produces same

Target: **27 tests** (up from 20 in v1).

---

## What C1 Explicitly Does NOT Do (unchanged from v1)

- Does NOT emit BUY/SELL/HOLD (Runner 1/2's job — untouched)
- Does NOT touch `india/telegram_notify.py` (sealed contract)
- Does NOT modify any existing engine
- Does NOT compute probabilities, confidences, expected exits, re-entry probabilities, lifecycle scores — all C2's job
- Does NOT change any Telegram / dashboard output — Phase E
- Does NOT auto-close positions or auto-execute — pure descriptive layer
- Does NOT invent new metrics beyond deterministic price arithmetic + state labels

---

## Blockers (Refinement 1 — must be literally green before C1 can start)

- [ ] `docs/AEGIS_REPO_AUDIT.md` exists on disk with Runner 1/2 dependency maps + every recommendation entry point + every history producer + every consumer
- [ ] `reports/research_engine_inventory.json` exists on disk with per-engine status matrix
- [ ] Operator has reviewed both and given explicit "audit complete, start C1"

Otherwise C1 may later discover another history source (there are already TWO — Runner 1's `aegis_recommendation_db.csv` and Runner 2's `recommendation_history.parquet`; A1/A2 may find a third) and require redesign. Cheaper to audit first.

---

## Success Criteria for C1 (revised 2026-07-24 · dual-market hard rule)

Per the Phase 3 dual-market rule, ALL of these must be true — missing any = sprint NOT COMPLETE:

- [ ] Shared engine complete (`backend/trade_state/`)
- [ ] India adapter complete (`india/trade_state/run.py`)
- [ ] USA adapter complete (`usa/research/trade_state/run.py`)
- [ ] India tests pass
- [ ] USA tests pass
- [ ] India real runtime: ≥ 10 open positions tracked across current lifecycle states
- [ ] USA real runtime: same
- [ ] `reports/global/trade_state_comparison.json` generated — India vs USA state distributions, per-state count deltas, avg holding-day deltas, target-crossing rate deltas
- [ ] Zero lookahead leaks (validated by `backend/replay/lookahead_guard.py`) on BOTH markets
- [ ] Zero regressions on ENG001 + all Sprint 6.5/7.5/7.6/7.7/7.8 suites
- [ ] 27+ regression tests passing (across the shared engine + both adapters)
- [ ] Sprint report enumerates: India results · USA results · Global comparison

---

## What Happens BEFORE Build Starts (unchanged)

1. Operator reviews this spec.
2. Operator confirms:
   - [ ] Approve TWO state machines (RecommendationState + PositionState)
   - [ ] Approve dynamic target ladder shape
   - [ ] Approve data-only scope (no intelligence in C1)
   - [ ] Approve config thresholds (or adjust ladder / stoploss / horizon)
   - [ ] Approve output shape (or adjust fields)
   - [ ] Approve file layout (`backend/trade_state/` + runners)
3. **Then and only then:** operator says "start C1".
4. I run full local test baseline BEFORE any code.
5. Build in small increments, each with tests.
6. Full local test sweep BEFORE push.

---

## Follow-ups AFTER C1 (queued, spec-only pending)

- **Sprint C2** — Trade Lifecycle Intelligence — consumes C1 state, adds probabilities + confidence + expected exit + lifecycle score
- **Sprint C3** — Target Horizon · Exit Intelligence · Re-entry Intelligence sub-modules
- **Sprint C4** — Recommendation Drift Intelligence (monthly rec-vs-current-model-vs-outcome analysis)
- **Sprint D1** — Recommendation Lifecycle Manager (THIN RENDERER — composes state + lifecycle + risk + portfolio + macro into JSON)
- **Sprint D2** — Operator Intelligence Layer with PRIORITIZATION buckets (Immediate Action / Review Today / Healthy / Watchlist)
- **Sprint E1-E3** — Unified Telegram + Dashboard + Operator Daily Report
- **Sprint F1** — Portfolio Decision Intelligence (per-position + portfolio-health answers)
- **Sprint G1** — Research Factory ↔ Trade Lifecycle promotion loop

Each with its own scoped spec BEFORE build.

---

**End of Sprint C1 Spec · v2 · Awaiting operator "start C1" · No code touched · Docs only.**
