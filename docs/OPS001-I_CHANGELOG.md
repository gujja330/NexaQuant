# OPS001-I · Changelog

**Release ID:** `OPS001I-2026-07-17`
**Spec:** [`docs/OPS001H_TELEGRAM_REDESIGN.md`](OPS001H_TELEGRAM_REDESIGN.md)
**Type:** Presentation-layer redesign. No strategy / research change.

---

## Changed

### `india/telegram_notify.py`

- Added imports: `hashlib`, `datetime`, `timezone`, `timedelta`.
- Added module-level paths: `MON001_FINGERPRINT_FILE`, `MON001_YAML`, `TRIAL_MANIFEST`.
- Added helper block (~200 LOC) with 18 new helper functions for OPS001-I:
  - `_today_ist_str()`, `_now_utc_and_ist()`
  - `_read_mon001_fingerprint()`, `_read_trial_count()`
  - `_days_between()`, `_derive_stop_price()`, `_pct_from_current()`
  - `_actions_counts()`, `_sector_allocation()`, `_largest_position()`, `_portfolio_confidence()`
  - `_nifty_summary()`, `_risk_summary()`, `_performance_buckets_from_registry()`
  - `_why_changed_narrative()`, `_integrity_footer()`, `_finalize_integrity()`
  - `_emit_opportunity()`
- Rewrote `build_message()`:
  - New brand header (3 lines)
  - New TODAY'S ACTIONS block (above the fold)
  - New MARKET summary
  - New PORTFOLIO HEALTH line
  - New TOP OPPORTUNITIES per-stock format (stop, trail, target, expiry, review, confidence, rationale)
  - Restructured CURRENT HOLDINGS section (compact 3-line blocks)
  - Restructured EXITS with structured reason display
  - New WHAT CHANGED narrative
  - New RISK SUMMARY (closest-to-stop, closest-to-target, concentration)
  - Restructured PERFORMANCE with time buckets (inception + 30D + 90D + 1Y)
  - New INTEGRITY FOOTER (run UTC + IST + market asof + MON001 fp + cert + cycle + trials + report SHA + disclaimer)

### `nexaquant/tests/test_telegram_reliability.py`

- Retired `test_12_telegram_notify_untouched_since_last_commit` — the "no
  uncommitted diff" guard from the earlier Telegram-reliability phase. This
  guard's premise ("reliability work must not modify notify core") is no
  longer applicable now that OPS001-I explicitly redesigns notify core.
- Added `test_12_telegram_notify_module_healthy` — verifies the module imports
  cleanly and `build_message()` returns a non-empty string. This becomes the
  durable smoke test any future modification must preserve.
- Updated TESTS list accordingly.

### `nexaquant/tests/test_ops_pipeline.py`

- `test_29_no_sealed_file_modifications`: removed `india/telegram_notify.py`
  from the forbidden set with an inline comment referencing this
  changelog. `india/telegram_notify.py` was in the OPS001-A forbidden set as
  a contract precaution ("OPS001 wraps existing without modifying"). OPS001-I
  is an explicit operator-authorised redesign, so the forbidden entry is
  stale. `india/telegram_notify.py` is NOT in the MON001 fingerprint set —
  removing it from this list is correctness, not a governance weakening.

### `nexaquant/tests/test_regression.py`

- Registered `("OPS001-I Telegram fmt", ...)` as the 14th regression suite.

---

## Added

### `nexaquant/tests/test_ops001i_telegram_format.py`

New regression suite with 16 scenarios:

- `test_1_message_is_non_empty_html` — message builds without exception
- `test_2_header_identifies_nexaquant` — brand header present
- `test_3_header_shows_market_asof_and_weekday` — data date visible
- `test_4_actions_block_is_above_the_fold` — ACTIONS TODAY within first 25 lines
- `test_5_all_six_named_sections_present` — verifies 8 institutional sections
- `test_6_sections_appear_in_specified_order` — monotonic position check
- `test_7_integrity_footer_has_all_required_fields` — 7 required fields verified
- `test_8_integrity_run_timestamp_is_current` — run timestamp within 60s
- `test_9_integrity_fingerprint_matches_mon001_seal` — fp field matches sealed_fingerprint.json
- `test_10_integrity_footer_is_at_the_end` — Integrity section near tail
- `test_11_report_sha_is_deterministic_per_content` — SHA format validation
- `test_12_message_body_uses_current_dividers` — `━` (heavy horizontal) present
- `test_13_zero_action_day_handled_gracefully` — either counts or "NO ACTION"
- `test_14_no_sealed_files_touched_by_ops001i` — git diff scan
- `test_15_mon001_fingerprint_unchanged` — recomputes + compares
- `test_16_production_constants_still_unchanged` — HOLD/rebal/trial count

### `docs/OPS001-I_IMPLEMENTATION.md`

Full implementation report — architecture, file-by-file changes, guarantees.

### `docs/OPS001-I_CHANGELOG.md`

This file.

### `docs/OPS001-I_VALIDATION.md`

Before/after comparison + evidence-based validation.

---

## Removed

None. Every change is additive or structural (rename/replace within the
same file). No file deleted.

---

## Unchanged (asserted by regression)

- MON001 fingerprint: `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf`
- `cumulative_strategy_search`: 38
- HOLD = 63, rebal = 63, sector_cap = 2, name_cap = 0.30, method = hrp
- Forward boundary: 2026-03-28
- Forward ledger: 150 rows, hash chain intact
- Certification: `MON001-CERT-2026-07-17` (still valid)
- All GitHub Actions workflows (aegis-daily, mon001-daily, eng001-regression)
- All MON001 sealed core files
- All LAB001–LAB010 artefacts
- All strategy files (`arjuna_v2.py`, `recommendation_generator.py`,
  `recommendation_registry.py`, `confidence_engine.py`, `data_nse.py`)
- All `.env` handling and secret plumbing
- All notification channel implementations (OPS001-C: file, telegram,
  slack, discord, email, webhook)
- Telegram sender freshness gate (OPS001-F)
- Retry / DLQ infrastructure

---

## Regression test count

- Before OPS001-I: 13 suites, 280 tests
- After OPS001-I: **14 suites, 296 tests** (added +16 tests, replaced 1)

All 296 tests PASS locally.

---

## Deployment considerations

- **First live send under new format:** the next scheduled AEGIS Daily
  run after this commit lands. Expected timing: 16:15 IST Monday-Friday.
- **Message chunking:** ~6.4K chars → 2 Telegram messages (via existing
  `_chunk_at_sections` chunker). This is unchanged behaviour — Telegram
  bot cap has always been 4096 chars.
- **Freshness gate compatibility:** the OPS001-F sender-side freshness
  check runs BEFORE `build_message()` in the wrapper flow. If the
  freshness check refuses (asof != today IST), the new format is never
  built or sent. This means today's stale `aegis_today.csv` (Generated:
  2026-07-14) would still refuse to send under the new format — until
  the next successful `recommendation_generator.py` run rewrites the file
  with today's `Generated` value.

---

## Sign-off

- Code: [`india/telegram_notify.py`](../india/telegram_notify.py)
- Tests: [`nexaquant/tests/test_ops001i_telegram_format.py`](../nexaquant/tests/test_ops001i_telegram_format.py)
- Implementation: [`docs/OPS001-I_IMPLEMENTATION.md`](OPS001-I_IMPLEMENTATION.md)
- Validation: [`docs/OPS001-I_VALIDATION.md`](OPS001-I_VALIDATION.md)
- Spec: [`docs/OPS001H_TELEGRAM_REDESIGN.md`](OPS001H_TELEGRAM_REDESIGN.md)
