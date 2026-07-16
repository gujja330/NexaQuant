# Telegram Reliability Engineering — Preregistered Plan

**Date:** 2026-07-15
**Author:** Principal DevOps Engineer / Production Reliability Lead
**Trigger:** operator reports intermittent missing Telegram notifications
             (2026-07-14 delivered stale content; 2026-07-15 no delivery at all)
**Status:** preregistered before implementation, per user directive

---

## 1. Executive summary

Today's Telegram silence has **four possible root causes** (I cannot definitively
distinguish without GitHub Actions log access). The fix therefore addresses all
four by making the failure modes VISIBLE and RETRIABLE — not by guessing which
one bit today.

---

## 2. Root-cause analysis (from `india/telegram_notify.py` inspection)

### Bug 1 — `main()` never propagates `send()`'s return value

`india/telegram_notify.py:470`
```python
else:
    send(msg)          # return value discarded
```

Result: `send()` can return `False` (partial or total failure) and the process
still exits `0`. From the workflow's perspective, the step "succeeded" —
regardless of whether Telegram actually delivered.

### Bug 2 — Missing env vars silently no-op

`india/telegram_notify.py:428-430`
```python
if not token or not chat:
    print("  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — cannot send.")
    return False
```

If GitHub secrets are absent/expired/renamed, `send()` returns False (no error
raised). Combined with Bug 1, process exits `0`. Workflow reports green. User
gets nothing.

### Bug 3 — API `not-ok` responses are silent

`india/telegram_notify.py:441-444`
```python
ok = json.loads(resp.read()).get("ok", False)
if not ok:
    print(f"  Telegram API returned not-ok on chunk {i}/{len(chunks)}.")
```

If Telegram API returns `{"ok": false, "description": "chat not found"}` or
similar, script prints a warning but `send()` still finishes normally. Only
returns False; nothing raises.

### Bug 4 — Partial multi-chunk delivery

`_chunk_at_sections` at line 402 splits messages > 3 900 chars. If chunk 1
sends but chunk 2's `urlopen` raises (rate limit / transient), `send()`
returns False immediately WITHOUT sending chunks 3+. User receives partial
content and may not realize the rest is missing.

### Bug 5 — Workflow-level mask

`.github/workflows/aegis-daily.yml:102`
```yaml
run: python india/telegram_notify.py || echo "telegram skipped (non-fatal)"
```

Even if `main()` were fixed to exit non-zero, the `|| echo` mask would still
swallow it. Workflow reports green regardless.

### Which one hit today?

Without GH Actions log, I cannot confirm. Most likely candidates:
- **Bug 2 or Bug 3** — GitHub secret drift (token rotated, chat_id changed, bot
  removed from chat)
- **Bug 4** — message too long or Telegram rate limit
- **All are masked by Bug 5.**

The fix below addresses ALL five without needing to know which one actually hit.

---

## 3. Proposed changes

### A. New: `scripts/telegram_health_check.py`
Standalone script. Validates GitHub secrets ARE present AND active by calling:
- `https://api.telegram.org/bot{TOKEN}/getMe` (validates token, prints bot username)
- `https://api.telegram.org/bot{TOKEN}/getChat?chat_id={CHAT_ID}` (validates
  chat_id, prints chat title / user name)

Exits 0 on both success, 1 on any failure with a clear error message. Runs
BEFORE the notify step in the workflow so a stale secret fails the pipeline
immediately with a legible error.

Does NOT send any message. Read-only against Telegram API.

### B. New: `scripts/telegram_send_with_retry.py`
Non-invasive wrapper around `india/telegram_notify.py`:
1. Runs `python india/telegram_notify.py` as subprocess (captures stdout).
2. Parses stdout for success markers (`sent (` prefix) or failure markers
   (`cannot send`, `send failed`, `not-ok`).
3. Retries on failure with exponential backoff: 5s, 15s, 45s (3 attempts).
4. Appends every attempt to `reports/telegram_delivery_<YYYY-MM-DD>.jsonl`.
5. Exits 0 only after at least one successful send. Exits 1 after all retries
   exhausted.

Does NOT modify `india/telegram_notify.py`. Preserves the operator directive
"do not touch Telegram core".

### C. Modify: `.github/workflows/aegis-daily.yml`
- Add pre-notify step: `python scripts/telegram_health_check.py` (no `|| echo`)
- Replace: `python india/telegram_notify.py || echo "telegram skipped (non-fatal)"`
  with: `python scripts/telegram_send_with_retry.py` (no mask)
- Add post-step: upload `reports/telegram_delivery_*.jsonl` as workflow artifact
  for post-mortem access

### D. Update: `nexaquant/tests/test_ci_discipline.py::GRANDFATHERED_MASKS`
Remove the aegis-daily line-102 Telegram mask entry. From now on, any new
Telegram mask fails CI.

### E. New: `nexaquant/tests/test_telegram_reliability.py`
Tests for the wrapper + health-check scripts:
- Verify health-check script exists + has correct API endpoints
- Verify retry wrapper exists + retries + writes ledger
- Verify workflow no longer contains the mask
- Verify delivery ledger schema

### F. Update: `nexaquant/tests/test_governance.py`
Add assertion: "aegis-daily.yml has NO `|| echo` on Telegram step".

---

## 4. What is NOT changing

- `india/telegram_notify.py` — untouched (operator directive)
- `india/recommendation_registry.py` — untouched (MON001-sealed)
- `india/recommendation_generator.py` — untouched (MON001-sealed)
- `india/confidence_engine.py` — untouched (MON001-sealed)
- `india/arjuna_v2.py` — untouched (MON001-sealed)
- `india/data_nse.py` — untouched (MON001-sealed)
- `india/ai_lab/**` — untouched (LAB evidence)
- MON001 sealed core files — untouched
- MON001 fingerprint algorithm v2 — remains sealed
- `cumulative_strategy_search` — unchanged at 38
- `HOLD = 63`, `rebal = 63`, portfolio construction — unchanged
- Recommendation content — the MESSAGE users receive is identical to today's,
  just delivered reliably

---

## 5. Governance impact

- **MON001 certification `MON001-CERT-2026-07-15`**: unaffected.
  The changes touch operational scripts + workflow only; no MON001-sealed
  file is modified. Fingerprint hash unchanged. Re-audit not required.

- **CHANGE_CONTROL_CHECKLIST.md**: not triggered.
  This change is monitoring/observability infrastructure, not a sealed-file
  modification.

- **ENGINEERING_CHECKLIST.md**: applies to this PR.

- **CI discipline**: strengthened — grandfathered mask registry shrinks by 1.

- **New governance rule** (enforced by test_governance.py): the Telegram
  notification step in aegis-daily.yml must never be masked.

---

## 6. Success criteria

After this PR:

1. If `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` become invalid, the aegis-daily
   workflow FAILS (red status, email to operator) instead of silently proceeding.
2. If Telegram API returns transient error, up to 3 retries with backoff give
   the message a fighting chance.
3. Every attempt is logged to `reports/telegram_delivery_*.jsonl` for
   post-mortem inspection.
4. `test_ci_discipline.py` prevents any new mask on the Telegram step.

---

## 7. Rollback

Trivially revertible via `git revert <commit>`. Restores the current
"silent-fail-on-Telegram" behaviour if a false-positive fires.

---

## Sealed 2026-07-15. Implementation follows.
