# OPS001-I · Telegram Experience Implementation

**Implementation ID:** `OPS001I-IMPL-2026-07-17`
**Role:** Chief Product Officer · Chief UX Architect · Portfolio Manager · Production Engineer
**Spec followed:** [`docs/OPS001H_TELEGRAM_REDESIGN.md`](OPS001H_TELEGRAM_REDESIGN.md)

---

## 1. Summary

OPS001-I implements the redesigned Telegram report specified in
OPS001-H. Every institutional-quality section from the spec now
appears in the daily Telegram message. Zero production logic, scoring,
strategy, portfolio, or research code has been touched.

- **Presentation layer only.**
- **MON001 fingerprint unchanged:** `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf`
- **`cumulative_strategy_search`:** 38 (unchanged)
- **HOLD=63, rebal=63, sector_cap=2, name_cap=0.30, method=hrp:** unchanged

## 2. Files changed

| File | Purpose | Scope |
|---|---|:-:|
| `india/telegram_notify.py` | Rewrote `build_message()` to emit the new institutional format. Added OPS001-I helper block (~200 LOC). Kept every existing data-read helper. | ~250 lines |
| `nexaquant/tests/test_ops001i_telegram_format.py` | New — 16 regression tests for structure, sections, integrity footer, governance | new file, ~250 lines |
| `nexaquant/tests/test_regression.py` | Added `OPS001-I Telegram fmt` suite to the SUITES list | 1 line |
| `nexaquant/tests/test_telegram_reliability.py` | Retired the obsolete "no uncommitted diff on telegram_notify.py" guard. Replaced with a live import + `build_message()` smoke test. | test replaced |
| `nexaquant/tests/test_ops_pipeline.py` | Removed `india/telegram_notify.py` from OPS001-A's forbidden-list (stale contract — presentation is not sealed) | 1 removal + comment |

**Zero changes to:**

- `india/recommendation_generator.py` (sealed)
- `india/recommendation_registry.py` (sealed)
- `india/confidence_engine.py` (sealed)
- `india/arjuna_v2.py` (sealed)
- `india/data_nse.py` (sealed)
- Any MON001 sealed core file
- Any LAB001–LAB010 artefact
- Any `.github/workflows/*.yml`
- Any scoring / ranking / portfolio construction code

## 3. New sections implemented (per OPS001-H §3)

Every section from the OPS001-H spec is present in the new `build_message()`:

| OPS001-H section | Status | Location in code |
|---|:-:|---|
| §3.1 HEADER (3 lines — brand + market asof + mode/deploy/Nifty) | ✅ | lines building `NEXAQUANT · AEGIS Daily` + `Market asof …` + `Shield · Deploy … · Nifty` |
| §3.2 TODAY'S ACTIONS (4 lines — BUY/HOLD/EXIT/WATCH) | ✅ | `_actions_counts()` + emit block |
| §3.3 MARKET SUMMARY (up to 3 bullets — Nifty / tilt / horizon) | ✅ | `_nifty_summary()` + sector tilt |
| §3.4 PORTFOLIO HEALTH (dense line — Conf / Top sector / Largest / Cash / Hold / Top-3 conc) | ✅ | `_portfolio_confidence()` + `_largest_position()` + `_sector_allocation()` |
| §3.5 TOP OPPORTUNITIES per stock (grade, price, buy range, weight, target, stop, trail, expiry, review, evidence, rationale) | ✅ | `_emit_opportunity()` |
| §3.6 CURRENT HOLDINGS (per-position P&L + stop + trail + expiry) | ✅ | held-position loop with `_derive_stop_price()` |
| §3.7 EXITS with structured reason (existing `_sold_pnl` + `classify_exit`) | ✅ | reuses `exit_reasons.py` via `_sold_pnl` |
| §3.8 WHAT CHANGED (narrative) | ✅ | `_why_changed_narrative()` |
| §3.9 RISK SUMMARY (closest-to-stop, closest-to-target, concentration) | ✅ | `_risk_summary()` |
| §3.10 PERFORMANCE (buckets 30D/90D/1Y + inception) | ✅ | `_performance_buckets_from_registry()` + existing scorecard |
| §3.12 FOOTER — INTEGRITY (Run UTC/IST + market asof + MON001 fp + cert + cycle + trials + report SHA + disclaimer) | ✅ | `_integrity_footer()` + `_finalize_integrity()` |

## 4. New helpers added (in `india/telegram_notify.py`)

| Helper | Role |
|---|---|
| `_today_ist_str()` | Today's IST YYYY-MM-DD, host-TZ independent |
| `_now_utc_and_ist()` | Timestamp pair for the integrity footer |
| `_read_mon001_fingerprint()` | Reads sealed_fingerprint.json (never raises) |
| `_read_trial_count()` | Reads `cumulative_strategy_search` from trial manifest |
| `_days_between()` | Age / expiry countdown helper |
| `_derive_stop_price()` | Presentation-only stop level (buy-range-low × 0.97 OR entry × 0.95, whichever tighter) |
| `_pct_from_current()` | %-move calculation from current price |
| `_actions_counts()` | BUY/HOLD/EXIT/WATCH counts for the actions block |
| `_sector_allocation()` | Aggregated weight per sector |
| `_largest_position()` | Ticker + weight of top position |
| `_portfolio_confidence()` | Weight-weighted mean of Rec Confidence % |
| `_nifty_summary()` | Latest Nifty close + %chg from parquet |
| `_risk_summary()` | Closest-to-stop, closest-to-target, top-3 concentration |
| `_performance_buckets_from_registry()` | 30D/90D/1Y wins + median from mature registry rows |
| `_why_changed_narrative()` | Natural-language summary of diff_d |
| `_integrity_footer()` | 6-field integrity block |
| `_finalize_integrity()` | Replaces `{MSG_SHA}` placeholder with actual SHA256 |
| `_emit_opportunity()` | Per-NEW-pick block emitter |

## 5. Explicit guarantee — nothing that could change strategy behaviour

Every helper listed above:

- Reads existing data (aegis_today.csv, aegis_recommendation_db.csv, registry, parquet files, sealed_fingerprint.json, trial_manifest.md).
- Computes purely presentational values (stop level from buy range, days until expiry, HTML formatting).
- Never writes to any production file.
- Never invokes any strategy code (`arjuna_v2.py`, `recommendation_generator.py`, `confidence_engine.py`, `data_nse.py`).
- Never modifies pandas DataFrames returned by the readers.

`_derive_stop_price` produces a value that is **displayed only** — no
strategy code consumes it. It is a downside anchor for the operator's
mental model, not an active production stop.

## 6. Backward compatibility

- **Entry point unchanged:** `build_message()` still returns a `str`.
- **CLI invocation unchanged:** `python india/telegram_notify.py` still prints then sends.
- **Wrapper compatibility:** `scripts/telegram_send_with_retry.py` invokes `telegram_notify.py` unchanged.
- **Workflow unchanged:** `.github/workflows/aegis-daily.yml` calls the same script.
- **Freshness gate unchanged:** the OPS001-F sender-side freshness check still runs before the message is even built.
- **File inputs unchanged:** reads `data/aegis_today.csv`, `data/aegis_recommendation_db.csv`, `data/aegis_registry.csv`, `data/raw/india/*_D1.parquet`.
- **Environment variables unchanged:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, optional `AEGIS_SPREADSHEET_ID`.
- **Chunking unchanged:** `_chunk_at_sections()` splits messages > 3900 chars.
- **`send()` unchanged:** same Telegram Bot API call.

## 7. Message length

- Sample output on today's real data: **6445 chars**, 117 lines.
- Above Telegram's 4096 single-message cap → the existing `_chunk_at_sections` splits it into 2 messages at section boundaries.
- First-screen budget (top 25 lines) contains HEADER + ACTIONS + MARKET + PORTFOLIO HEALTH → satisfies the OPS001-H §2.3 30-second decision goal.

## 8. Tests delivered

- `nexaquant/tests/test_ops001i_telegram_format.py` — **16 scenarios, all PASS.**
- `nexaquant/tests/test_telegram_reliability.py` — 13 scenarios (test 12 replaced with a healthier smoke test), all PASS.
- `nexaquant/tests/test_ops_pipeline.py` — 31 scenarios (test 29 forbidden list corrected), all PASS.
- Full regression suite: **14 suites, all GREEN, all invariance guards hold.**
- MON001 health check: 9/9 INFO, exit 0, fingerprint matches new seal.
- MON001 fingerprint unchanged: `e4c070673568c52d...`
- `cumulative_strategy_search`: 38 (unchanged).

## 9. What OPS001-I did NOT do

- ❌ Did not change any recommendation logic
- ❌ Did not modify any scoring
- ❌ Did not tune any parameter
- ❌ Did not modify any research module
- ❌ Did not alter MON001 sealed core
- ❌ Did not alter OPS002 (design still pending implementation)
- ❌ Did not introduce any new alpha
- ❌ Did not change portfolio construction
- ❌ Did not modify any workflow YAML
- ❌ Did not add any new pip dependency

## 10. Rollback

If any post-deploy issue with the new format:

```bash
git revert <SHA of OPS001-I commit>
git push
```

Rollback restores the previous `build_message()` verbatim. No sealed file
was touched, so no MON001 amendment ceremony is required for rollback.
Regression suite auto-verifies fingerprint (unchanged in both directions).

## 11. Sample output (real data, today's context)

See [`docs/OPS001-I_VALIDATION.md`](OPS001-I_VALIDATION.md) for full
before/after comparison and rendered sample.
