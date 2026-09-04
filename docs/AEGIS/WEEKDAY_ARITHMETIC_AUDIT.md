# Weekday-Only Trading-Day Arithmetic · Non-Evidence-Engine Residual Audit

**Filed:** 2026-09-05 (HERO prompt Phase 1)
**Classification:** GOVERNANCE_BLOCKED · outside Evidence Engine scope · would touch R2 production paths

## Context

AUDIT-01 closed within the Evidence Engine · `backend/research/evidence/walk_forward.py` + `trading_calendars.py` now use exchange-aware arithmetic (NSE + NYSE holidays 2020-2026).

However, seven repo-wide sites still use `weekday() < 5` weekday-only arithmetic. Every one of them is OUTSIDE the Evidence Engine, in delivery/production/replay paths. Modifying them would violate the R2 production freeze without CEO authorization.

## Enumerated sites (residual)

| File | Line | Path type | Freeze status |
|---|---:|---|---|
| `backend/context/pipeline_heartbeat.py` | 43 | Delivery cockpit heartbeat | R2 delivery-adjacent · frozen |
| `backend/delivery/telegram/detail_xlsx.py` | 173 | Telegram XLSX detail sheet | R2 delivery contract · frozen |
| `backend/history_quality/validators.py` | 18 | History validator (used by daily pipeline) | R2 delivery · frozen |
| `backend/portfolio/rotation_outcome_tracker.py` | 88 | Portfolio rotation tracking | R2 production · frozen |
| `backend/replay/integrity.py` | 31 | Replay integrity check | Historical replay · frozen |
| `backend/research/outcome_dataset.py` | 113 | Outcome Dataset builder (P0 substrate) | Substrate for research · shared |
| `scripts/telegram_command_center_send.py` | 716 | Telegram command center sender | R2 delivery · frozen |

## Impact per site

**Small.** Every site uses weekday arithmetic for either (a) a short lookback window (5-30 days) where holiday drift is 0-1 day, (b) counting workdays for a display metric, or (c) validating history integrity where a 1-day boundary discrepancy is not materially different from the intended semantics.

## Fix effort

Small per site · call `add_trading_days(d, n, market)` with the appropriate market. But requires:

1. Every call site needs a market identity in scope (some do, some don't)
2. Regression tests for the delivery paths that touch the change
3. CEO authorization per governance rule that any R2 delivery-path change must have named + dated approval

## Recommended disposition

Track this as WEEKDAY-AUDIT-01 through -07 · one per site · each closable in a **separate CEO-authorized delivery batch** when the market attribution is verified for that site. Do NOT bundle into an evidence-engine push · would silently change R2 delivery behavior for no evidence gain.

## Verified NOT affected

- All Evidence Engine paths (`backend/research/evidence/*`) · already use `trading_calendars.py`
- All CI freshness/accumulator monitors (`fundamentals_freshness_check.py`, `accumulator_progress_verifier.py`) · use market-aware trading-day math
- The walk-forward fold generator itself
