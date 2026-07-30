# AEGIS Pipeline Safety Contract

**Signed into force 2026-07-30 · post-mortem cycle**
**Status: MANDATORY · violation = production data loss**

---

## The rule this document exists to enforce

**Never re-run a production data-producing pipeline on the same trading date
without explicit `--force` and operator approval.**

## The incident that made this necessary

On 2026-07-30 the operator's morning picks (LUPIN · HEROMOTOCO · CHAMBLFERT
· 5 rotations · 3 exits) were silently overwritten mid-day. Root cause: the
assistant re-ran `python -m backend.recommendation.ssot.run --market india`
four times during the same session to test canonical-stamp code that only
touched the display layer. Each rerun cascaded through:

1. Publisher regenerated `recommendations.json` from `recommendations_v3.json`
2. Enricher's `evolution` layer saw "same tickers today as yesterday"
   → demoted all `investor_action.entry` from BUY to WAIT
3. Investor-actionable enricher derived new `rotations = 0` from demoted state
4. Snapshot archiver overwrote `reports/recommendations_history/india/2026-07-30.json`
   with the demoted state — permanently destroying the morning good state

Only recovery path: `git show 4750e5e:reports/recommendations.json` had the
morning state committed. Without that commit, the picks would have been
unrecoverable until tomorrow's fresh engine run.

## The three guards now in force

### Guard 1 · Same-day idempotency lock (in code)

`backend/recommendation/ssot/run.py` will REFUSE to run if a snapshot for
today already exists at `reports/recommendations_history/{market}/{asof}.json`.

Refusal message:

```
[recommendation_ssot:india] REFUSED · snapshot for 2026-07-30 already
exists at reports/recommendations_history/india/2026-07-30.json.
  · Use 'scripts/stamp_only.py --market india' for display or canonical
    stamp updates (non-destructive).
  · Pass --force to this script only if you truly need to REGENERATE
    today's picks (destroys the current snapshot).
```

Override: `python -m backend.recommendation.ssot.run --market india --force`
· requires deliberate acknowledgement · logged as destructive.

### Guard 2 · Non-destructive `stamp_only.py` for display updates

`scripts/stamp_only.py --market {india|usa|both}` reads existing
`recommendations.json`, refreshes canonical + Research-Platform-derived
fields, writes back to the same file. Never touches:

- `recommendations_v3.json`
- The enricher (`enrich_batch`, `build_ceo_summary`, `run_scorecard`, etc.)
- The snapshot archive (`reports/recommendations_history/`)
- The position store or lifecycle ledger
- The research platform builder

Sanity check built in: aborts if the buys count changes between read and
write (proves the stamp helper is not accidentally mutating picks).

### Guard 3 · Operator-first Telegram protocol

**Every operator-visible change follows this order:**

1. Code change
2. Dry-run · print message to chat
3. Wait for operator "send" or "approve" (or equivalent)
4. Only then invoke `scripts/telegram_command_center_send.py`

**Never** send Telegram without a preceding dry-run in the same session.
**Never** re-run the daily pipeline just to test a Telegram-visible tweak.

## Decision matrix · which script to run when

| Change type | Use | Destructive? |
|---|---|---|
| Refresh canonical stamp from delivery_platform.json | `stamp_only.py` | No |
| Add / remove a Telegram section | edit `command_center.py` + `stamp_only.py` (if payload fields needed) | No |
| Bug-fix a signal factory | `aegis_daily_v2.py --only <step>` | Depends on step |
| First run of the day (market open) | `ssot/run.py --market india` (no force) | No · snapshot doesn't exist yet |
| Second run same day (rare · e.g. corrupted upstream) | `ssot/run.py --market india --force` | **YES · overwrites morning state** |

## What operators can verify at any time

```bash
# Check that no pipeline is silently rerunning today's picks:
ls -la reports/recommendations_history/india/2026-07-30.json
# If timestamp is stale (morning-only), snapshot is safe.
# If timestamp is recent, something re-ran and needs review.
```

## What triggered this document

Operator note verbatim: *"what went wrong and how r u going to not repeat
such mistakes and how u r gonna take prevention?"*

Answer: this document + the two code guards. Test coverage for the
idempotency lock is in `backend/tests/test_ssot_idempotency.py` (added
same day as this doc).

---

**Signed 2026-07-30. Non-negotiable going forward.**
