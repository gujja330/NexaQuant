# AEGIS · Sprint 7.6 · Historical Backfill & Replay Engine
### 13-Section Validation Report

**Sprint status:** ✅ SHIPPED · EXPERIMENTAL (framework + feature-snapshot backfill)
**Date:** 2026-07-21
**Engine ID:** `aegis.replay.v1`
**Version:** 1.0.0
**Markets:** India (INR) + USA (USD)
**Placement:** Inserted between Sprint 7.5 (Persistence) and Sprint 8 (Walk-Forward), per operator directive of 2026-07-21.

---

## 1 · Scope & Rationale

Sprint 8 (Walk-Forward), Sprint 9 (AI Auditor), Sprint 10 (Research Factory) all need **rich historical data** — not a 3-day framework check. Sprint 7.6 builds the Backfill & Replay Engine that populates append-only history using historical raw price data so the downstream sprints begin with an institutional dataset.

**Operator constraints honored:**
- Free-data substrate only (no paid APIs, no new AI agents, no new recommendation engines)
- No new core engines (this is a *replay* layer over existing engines)
- Fail-open (backfill errors never block the current-day pipeline)
- Deterministic per-date (walk-forward safe)
- Append-only history (never overwrites Sprint 7.5's parquets)

**Honest scoping decision:** the CURRENT-STATE runners (Rec/Risk/Portfolio/Execution) do NOT accept an `--asof` cursor — they read "latest" from the Feature Store. Full-pipeline replay requires either a runner refactor or a headless engine-driver. That work is deferred to **Sprint 7.7** and clearly labeled in every report the sprint emits. Sprint 7.6 ships the framework + the parts that CAN be backfilled today.

---

## 2 · Modules Delivered

| # | Module | Purpose |
|---|---|---|
| 1 | `backend/replay/__init__.py` | Public API |
| 2 | `backend/replay/types.py` | `ReplayPlan · ReplayResult · HistoryValidation · WalkForwardReadiness · DataQuality · TARGET_HISTORY_FILES` |
| 3 | `backend/replay/data_quality.py` | 0-100 scoring: completeness × freshness × source count → verdict (high/medium/low/unusable) |
| 4 | `backend/replay/integrity.py` | Missing-days · duplicates · schema check · canonical trading-day extraction from raw price parquets |
| 5 | `backend/replay/controller.py` | Orchestrator + resume + 5 reports emitter |
| 6 | `backend/replay/__main__.py` | Enables `python -m backend.replay backfill --from --to --market --resume` |
| 7 | `backend/tests/test_sprint76.py` | 19 tests (framework + resume + integrity + quality + determinism) |

---

## 3 · CLI

```bash
python -m backend.replay backfill \
    --from 2026-06-01 --to 2026-07-21 \
    --market usa \
    --steps features,macro,factor,learning \
    --resume
```

Flags:
- `--from` / `--to` — window boundaries (YYYY-MM-DD)
- `--market` — `india` | `usa`
- `--steps` — comma-separated: `features,macro,factor,learning`
- `--resume` (default) — skip already-persisted snapshots
- `--no-resume` — force recompute
- `--parallel` — worker count (framework accepts; sequential in v1)
- `--repo-root` — override repo root (default cwd)

---

## 4 · Regression Suite

```
======================================================================
  SPRINT 7.6 · Historical Backfill & Replay · Regression Tests
======================================================================
  [OK] TARGET_HISTORY_FILES manifest covers all 7 histories
  [OK] quality score = high for complete + fresh + multi-source
  [OK] quality score penalises missing fields
  [OK] quality score penalises staleness
  [OK] quality score honours treat_zero_as_missing
  [OK] quality verdict bands (high/medium/low/unusable)
  [OK] batch_average_quality handles None and empty
  [OK] enumerate_trading_days skips weekends
  [OK] validate_history returns FAIL when file missing
  [OK] validate_history reads populated parquet as PASS
  [OK] validate_history flags duplicate dates as WARN
  [OK] validate_history flags missing trading days
  [OK] validate_history market isolation
  [OK] controller: resume skips already-persisted snapshots
  [OK] controller emits all 5 reports with engine stamp
  [OK] walk-forward readiness verdict reflects history depth
  [OK] deferred steps report status honestly (no silent success)
  [OK] replay deterministic across identical runs
  [OK] _market_paths distinguishes india vs usa roots

  19 passed, 0 failed of 19
```

No-regression across all prior sprints:
- Sprint 6.5: 22/22 ✅
- Sprint 7.5: 18/18 ✅
- Telegram fallback: 10/10 ✅

---

## 5 · Live Runtime Output (2026-07-21)

**USA backfill window `2026-06-01 → 2026-07-21`:**
- Feature snapshots: **32 new · 1 skipped (resume) · 0 failed · 20.55 s** (0.64 s / date)
- Total feature snapshots on disk: **35 days**
- Walk-forward verdict: `PARTIAL` (unblocked by future Rec history rows)

**India backfill window `2026-06-15 → 2026-07-21`:**
- Feature snapshots: **24 new · 0 skipped · 0 failed · 63.35 s** (2.6 s / date · 229 tickers)
- Total feature snapshots on disk: **26 days**
- Walk-forward verdict: `PARTIAL`

Both markets went from `NOT_READY` (< 3 days) → `PARTIAL` (rec ledger empty, features rich).

---

## 6 · Data Quality Score (0-100)

Every history row can carry a `data_quality_score` computed as:

```
score = 50 × completeness + 30 × (1 - staleness_penalty) + 20 × (min(sources, 5) / 5)
```

Verdict bands: **high** ≥ 85 · **medium** ≥ 65 · **low** ≥ 40 · **unusable** < 40.

The scoring utility is production-ready. Wiring into every history writer happens naturally when Sprint 7.7 backfills Rec/Risk/Portfolio/Execution history — each row will carry its score at write time.

---

## 7 · Reports Produced (per market, on every backfill run)

1. `backfill_summary.json` — per-step results (n_ok, n_skipped, n_failed, elapsed, failed_samples)
2. `history_validation.json` — per-history-file verdict (PASS/WARN/FAIL, n_rows, n_missing, n_dup, schema)
3. `walkforward_readiness.json` — READY/PARTIAL/NOT_READY verdict with structured counts + notes
4. `factor_library_summary.json` — deferred-step status + row counts
5. `learning_backfill_summary.json` — corpus size + deferred-work reason

Every report carries `engine=aegis.replay.v1`, `market`, `run_utc`, `asof`.

---

## 8 · Contracts Enforced

| Contract | Status |
|---|---|
| Deterministic per-date (same asof → same feature snapshot) | ✅ tested |
| Resume support (skip already-persisted snapshots) | ✅ tested |
| Fail-open (single-date failure never blocks the run) | ✅ tested |
| Walk-forward safe (uses Feature Store's native asof cursor) | ✅ |
| Free-data substrate only (uses raw ticker parquets already on disk) | ✅ |
| Honest reporting (deferred steps flag their status; no silent success) | ✅ tested |
| No new AI agents | ✅ |
| No new recommendation engines | ✅ |
| Sealed OPS001/MON001 files untouched | ✅ |
| Fingerprint `b65ceb49a83a` preserved | ✅ |

---

## 9 · What This Sprint Backfills TODAY

| History file | Backfilled? | Notes |
|---|---|---|
| `features/india/<D>.parquet` | ✅ 26 days | Fully deterministic from raw ticker parquets |
| `features/usa/<D>.parquet` | ✅ 35 days | Same |
| `macro_history.parquet` | ⚠️ framework ready, no data | Needs Sprint 7.7 yfinance macro-symbol fetcher (CL=F, GC=F, ^TNX, UUP, ...) |
| `factor_library_history.parquet` | ⚠️ framework ready, no data | Depends on `macro_history` |
| `recommendation_history.parquet` | ⚠️ framework ready, no data | Needs Sprint 7.7 headless Rec Engine driver |
| `risk_history.parquet` | ⚠️ chain-dependent | Depends on `recommendation_history` |
| `portfolio_history.parquet` | ⚠️ chain-dependent | Depends on `risk_history` |
| `execution_history.parquet` | ⚠️ chain-dependent | Depends on `portfolio_history` |
| `learning_corpus.parquet` | ⚠️ framework ready, no data | Depends on `recommendation_history` for outcome computation |

**The critical unlock this sprint provides:** per-date feature snapshots. This IS the substrate every downstream historical replay needs. Sprint 7.7 builds on top of these snapshots.

---

## 10 · Integration

| Integration point | Change |
|---|---|
| `.github/workflows/aegis-ci.yml` | Sprint 7.6 tests wired in |
| CLI | `python -m backend.replay backfill ...` operator-invocable |

Deliberately NOT wired into `aegis_daily_v2.py` / `usa_daily.py`: backfill is a manual replay tool, not a daily step. Running it accidentally in a daily orchestrator would waste minutes per run.

---

## 11 · Cumulative Test Health

```
Sprint 1   backend validation                  12/12   ✅
Sprint 2   canonical + market intel + AI       12/12   ✅
Sprint 2.5 feature store + AI                  12/12   ✅
Sprint 2.6 feature intel + registry + gate     18/18   ✅
Sprint 2.7 model factory + 11 models           14/14   ✅
Sprint 3   recommendation intelligence v3      22/22   ✅
Sprint 4   risk engine                         23/23   ✅
Sprint 5   portfolio engine                    20/20   ✅
Sprint 6   learning engine                     19/19   ✅
Sprint 6.5 macro & intermarket intelligence    22/22   ✅
Sprint 7   execution simulator + statistics    26/26   ✅
Sprint 7.5 persistence + factor library        18/18   ✅
Sprint 7.6 historical backfill + replay        19/19   ✅  ← NEW
Telegram HTTP 400 fallback                     10/10   ✅
─────────────────────────────────────────────────────────
TOTAL                                         237/237  ✅
```

---

## 12 · Known Limits — deferred to Sprint 7.7

**Sprint 7.7 · Full-pipeline historical replay** must add:

1. **yfinance macro-symbol fetcher** (`backend/replay/data_fetcher.py`)
   - Pulls CL=F, BZ=F, GC=F, SI=F, HG=F, NG=F, UUP, USDINR, EURUSD, USDJPY,
     ^TNX, ^TYX, ^FVX, ^IRX, ^VIX daily bars for 5 years
   - Persists to `data/raw/macro/<SYMBOL>_D1.parquet` (append-only)
   - One-time run, then daily append via existing refresh_data pattern

2. **Headless engine drivers** — programmatic re-run of Rec/Risk/Portfolio/Execution
   engines per historical asof, WITHOUT touching the current runner files (which
   the daily pipeline depends on). Options:
   - `backend/replay/engine_drivers.py` — bypass runners, call engine classes with
     historical inputs constructed from the per-date feature snapshots already backfilled
   - or add a `--asof` flag to each runner (12 files) — more invasive

3. **Macro + Factor + Learning backfill** — trivial once (1) + (2) exist, since the
   framework in Sprint 7.6 already wraps them.

Estimated effort: one focused sprint, all deterministic, no new engines.

---

## 13 · NEXT BOTTLENECK

**Runner-level `--asof` OR headless engine drivers.** Sprint 7.6 landed feature-snapshot backfill (the biggest single unlock). What remains is threading historical asof through the four remaining pipeline stages. Two paths:

1. **Headless driver** (recommended) — a `backend/replay/engine_drivers.py` module that instantiates Rec/Risk/Portfolio/Execution engine classes directly with historical inputs. Zero runner changes, zero risk to the daily pipeline.
2. **Runner refactor** — add `--asof` to each of 12 runners. More invasive but makes historical replay a first-class runner feature.

**Recommended:** headless driver in Sprint 7.7, so the daily pipeline stays untouched and historical replay lives in its own module. This also matches the operator's "never affect current pipeline" rule.

Below that (still open): Sprint 8 walk-forward metrics arrive gradually as (a) daily runs append to history and (b) Sprint 7.7 seeds historical rec/execution rows. The dashboard's `walkforward_readiness.verdict` moves `PARTIAL → READY` once both conditions clear the 60-day threshold.

---

**End of Sprint 7.6 · Historical Backfill & Replay Report**
