# AEGIS Phase 3 · Sprint C1 · Trade State Engine
### Scoped Sprint Spec (docs only · NOT YET BUILT · pending operator "start")

**Purpose:** Give the operator a complete look at what a Trade State Engine sprint would deliver — files, tests, invariants, verification steps — BEFORE any code is written. Operator reviews scope, approves or adjusts, THEN build begins.

---

## The Problem This Sprint Fixes

Recommendations today are stateless labels:

```
Day 0:  BUY  APOLLO  ₹8592
Day 1:  BUY  APOLLO  ₹8592     ← same label, different date
Day 2:  BUY  APOLLO  ₹8592     ← same again
...
Day 20: BUY  APOLLO  ₹8592     ← still same
```

Operator sees the SAME Telegram message with a different timestamp. No holding day, no %-move, no target progress, no exit signal. That's what caused the "IPCALAB same script daily" and "dual notification confusion" incidents.

---

## What C1 Delivers

A per-position state machine that any downstream consumer (Telegram / Dashboard / Learning / Auditor) can render into a living recommendation.

```
NEW → OPEN → TARGET1 → TARGET2 → TARGET3 → EXIT → POST_EXIT → REVERSAL → REENTRY → CLOSED
                    ↘ STOPLOSS  ↘ CLOSED
```

Every recommendation carries `state` INSTEAD of `BUY`/`SELL`/`HOLD`. The label becomes a state summary — the state machine carries the truth.

---

## Modules to be Delivered (Sprint C1 · code)

| # | File | Purpose | Lines (est) |
|---|---|---|---|
| 1 | `backend/trade_state/__init__.py` | Public API | ~30 |
| 2 | `backend/trade_state/types.py` | `TradeState` enum, `PositionState` dataclass, `StateTransition` | ~120 |
| 3 | `backend/trade_state/transitions.py` | Deterministic per-day state transition rules (price + target + stoploss → next state) | ~200 |
| 4 | `backend/trade_state/engine.py` | `TradeStateEngine.update(asof)` — reads recs + prices, emits `PositionState` per position | ~180 |
| 5 | `backend/trade_state/persistence.py` | Append-only `trade_state_history.parquet` writer, dedup on (market, ticker, asof) | ~80 |
| 6 | `india/trade_state/run.py` | India runner | ~90 |
| 7 | `usa/research/trade_state/run.py` | USA runner | ~90 |
| 8 | `configs/trade_state_config.yaml` | Target/stoploss/timeout thresholds per market | ~40 |
| 9 | `backend/tests/test_sprint_c1.py` | Regression suite (target: ≥ 20 tests) | ~350 |

Total: ~1180 lines, ~9 files. No sealed engine touched. No AI agent added.

---

## Data Flow

```
INPUTS (all existing, read-only):
  reports/recommendation_history.parquet          (Runner 2 / Rec v3 ledger)
  reports/recommendation_history_runner1.parquet  (Runner 1 legacy audit ledger)
  data/raw/india/<TICKER>_D1.parquet              (India prices)
  usa/data/raw/us/<TICKER>_D1.parquet             (USA prices)
  configs/trade_state_config.yaml                 (thresholds)

PROCESSING:
  For each open position × each trading day:
    - compute current price, %-move from entry, %-move from highest
    - evaluate transition rules: NEW → OPEN, OPEN → TARGET1, TARGET1 → EXIT, etc.
    - if state changes, emit StateTransition record
    - always emit current PositionState row

OUTPUTS (all new, additive):
  reports/trade_state.json                        (today's snapshot)
  reports/trade_state.parquet                     (today's snapshot table)
  reports/trade_state_history.parquet             (append-only, one row per position-day)
  reports/trade_state_transitions.parquet         (append-only, one row per state change)
  usa/reports/... (mirror for USA)
```

---

## State Machine Definition (transition rules)

Deterministic, price-driven, config-tunable. NO ML, NO probabilistic transitions in v1.

| From | To | Trigger |
|---|---|---|
| `NEW` | `OPEN` | day+1 after recommendation issued (no fill assumption; state = "position live") |
| `OPEN` | `TARGET1` | current_pct_move ≥ target_1_pct (config, e.g. +3%) |
| `TARGET1` | `TARGET2` | current_pct_move ≥ target_2_pct (config, e.g. +5%) |
| `TARGET2` | `TARGET3` | current_pct_move ≥ target_3_pct (config, e.g. +10%) |
| `TARGET1/2/3` | `EXIT` | operator marks exit OR trailing-stop triggers OR horizon expires |
| `OPEN/TARGET*` | `STOPLOSS` | current_pct_move ≤ stoploss_pct (config, e.g. -8%) |
| `STOPLOSS` | `CLOSED` | day+1 after stoploss |
| `EXIT` | `POST_EXIT` | day+1 after exit |
| `POST_EXIT` | `REVERSAL` | price re-crosses exit level within reversal_window_days (config) |
| `REVERSAL` | `REENTRY` | reversal confirmed by N-day trend (config) |
| `REENTRY` | `OPEN` (new position row) | re-entry becomes a new lifecycle |
| any | `CLOSED` | horizon_expiry_days reached |

Every transition is DETERMINISTIC from (prior_state, price_series, config) → NEXT_state. Replayable, walk-forward-safe.

---

## Config Shape (operator-owned thresholds)

```yaml
# configs/trade_state_config.yaml (proposed — operator adjusts)
market_defaults:
  india:
    target_1_pct: 3.0
    target_2_pct: 5.0
    target_3_pct: 10.0
    stoploss_pct: -8.0
    horizon_expiry_days: 60
    reversal_window_days: 20
    reversal_confirm_days: 3
    trailing_stop_pct: 5.0
  usa:
    target_1_pct: 2.0
    target_2_pct: 4.0
    target_3_pct: 8.0
    stoploss_pct: -6.0
    horizon_expiry_days: 45
    reversal_window_days: 15
    reversal_confirm_days: 3
    trailing_stop_pct: 4.0
```

---

## PositionState Payload (what downstream consumers see)

```json
{
  "market":            "india",
  "ticker":            "APOLLOHOSP",
  "recommendation_asof": "2026-06-26",
  "runner":            "runner1",
  "state":             "TARGET1",
  "state_since":       "2026-07-08",
  "days_in_state":     4,
  "holding_day":       16,
  "entry_price":       8592.00,
  "current_price":     8888.00,
  "highest_price":     8912.00,
  "lowest_price":      8410.00,
  "current_return_pct":   3.45,
  "highest_return_pct":   3.72,
  "lowest_return_pct":   -2.12,
  "target_progress_pct":  115.0,  // % of target_1_pct achieved
  "expected_exit_by":  "2026-08-25",
  "notes":             "reached TARGET1 on day 12; watching for TARGET2 or trailing-stop trigger"
}
```

---

## Regression Tests (Sprint C1 · target ≥ 20)

**Types transitions:**
1. `NEW → OPEN` on day+1
2. `OPEN → TARGET1` when %-move crosses target_1
3. `OPEN → STOPLOSS` when %-move crosses stoploss
4. `TARGET1 → TARGET2` on second threshold crossing
5. `TARGET2 → TARGET3` on third threshold crossing
6. `OPEN → CLOSED` on horizon_expiry
7. `STOPLOSS → CLOSED` on day+1
8. `EXIT → POST_EXIT → REVERSAL` chain
9. `REVERSAL → REENTRY → new OPEN row`
10. State never regresses (TARGET1 → OPEN forbidden)

**Deterministic invariants:**
11. Same inputs → same state (deterministic)
12. Replay same asof twice → same PositionState (idempotent)
13. append_snapshot_row dedupes on (market, ticker, asof)

**Anti-lookahead:**
14. State at asof=D uses only price data ≤ D (lookahead guard)
15. Reversal detection uses only post-exit price ≤ replay asof

**Integration:**
16. Reads Runner 1 audit-trail rec history correctly
17. Reads Runner 2 (Rec v3) rec history correctly
18. Handles missing price parquet gracefully (state = UNKNOWN, not crash)
19. Handles ticker never opened (no history) gracefully

**End-to-end:**
20. Runner on real India data produces valid trade_state.json + trade_state.parquet
21. USA runner produces same

---

## What C1 Explicitly Does NOT Do

- Does NOT emit BUY/SELL recommendations (that's Runner 1/2's job — untouched)
- Does NOT touch `india/telegram_notify.py` (sealed contract)
- Does NOT modify any existing engine
- Does NOT introduce probability / ML in v1 — pure deterministic state machine (Sprint C2 layers probabilities on top)
- Does NOT change any Telegram / dashboard output — those consume Trade State in Phase E, not Phase C
- Does NOT auto-close positions or auto-execute — pure descriptive layer

---

## Success Criteria for C1

- 20+ regression tests passing
- Real runtime on India: >= 10 open positions tracked across current lifecycle states
- Real runtime on USA: same
- Zero lookahead leaks (validated by existing `backend/replay/lookahead_guard.py`)
- Zero regressions on ENG001 + Sprint 6.5/7.5/7.6/7.7/7.8 test suites
- Output ready for Sprint C2 (Trade Lifecycle Intel) to consume

---

## What Happens BEFORE Build Starts

Operator reviews this spec and confirms:
- [ ] Approve state machine (or adjust states)
- [ ] Approve config thresholds (or adjust)
- [ ] Approve output shape (or adjust fields)
- [ ] Approve file layout (or adjust module boundaries)

**Then** I run `python nexaquant/tests/test_regression.py` + full sprint suite to confirm current-state baseline, THEN write code, THEN re-run full suite BEFORE any push.

---

## Follow-ups AFTER C1 (queued, not started)

- Sprint C2 — Trade Lifecycle Intelligence (targets probability, exit optimization, re-entry probability) — consumes C1 output
- Sprint D1 — Recommendation Lifecycle Manager — consumes C1 + C2
- Sprint D2 — Operator Intelligence Layer — consumes D1
- Sprint E1-E3 — Unified Telegram + Dashboard + Operator Daily Report — consumes D2

Each with its own scoped spec before build starts.

---

**End of Sprint C1 Spec · Awaiting operator "start" · No code touched · Docs only.**
