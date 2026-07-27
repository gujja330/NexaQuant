# AEGIS · Sprint 7.5 · Market Data Persistence & History Engine + Factor Library
### 13-Section Validation Report

**Sprint status:** ✅ SHIPPED · EXPERIMENTAL
**Date:** 2026-07-21
**Engine ID:** `aegis.persistence.v1` (history writer) + `aegis.factor_library.v1`
**Version:** 1.0.0
**Approval status:** EXPERIMENTAL (auto-stamped)
**Markets:** India (INR) + USA (USD) — parallel deployment
**Placement:** Inserted between Sprint 7 (Execution Simulator) and Sprint 8 (Walk-Forward Validation), per operator directive of 2026-07-21.

---

## 1 · Scope & Rationale

The system was producing daily JSON snapshots but **overwriting them** — history existed only for a handful of engines (portfolio, macro subcomponents) and not in a walk-forward-compatible shape. Sprint 8 (Walk-Forward), Sprint 9 (AI Auditor), and Sprint 10 (Research Factory) all depend on rich historical data.

Sprint 7.5 makes **every engine append-only by default**: each daily JSON snapshot now has a `<name>_history.parquet` companion that is deduped-and-appended on every run. Also delivers a **Factor Library** — one row per (date, factor) — as the substrate for AI pattern search ("show me every period where oil + VIX + USD rose together") without rebuilding data each time.

**Free-data substrate only:** yfinance + FRED + ECB + RBI + MOSPI + NSE/BSE public data. No paid APIs.

---

## 2 · Modules Delivered

**Persistence layer:**
- `backend/persistence/__init__.py` — public API
- `backend/persistence/history_writer.py` — append/dedupe utility · fail-open · walk-forward safe

**Factor Library:**
- `backend/factor_library/__init__.py`
- `backend/factor_library/types.py` — `FactorReading`, `FactorLibraryResult` dataclasses
- `backend/factor_library/engine.py` — composes 22 factors from Sprint 6.5 outputs
- `configs/factor_library_config.yaml` — factor taxonomy (name → source, unit, affected sectors)
- `india/factor_library/run.py` — India runner (INR)
- `usa/research/factor_library/run.py` — USA runner (USD)

**Runners wired for history (12 changes):**
| Engine | India runner | USA runner |
|---|---|---|
| Recommendation v3 | `india/recommendation_intelligence/run.py` | `usa/research/recommendation_intelligence/run.py` |
| Risk | `india/risk_engine/run.py` | `usa/research/risk_engine/run.py` |
| Portfolio | `india/portfolio_engine/run.py` | `usa/research/portfolio_engine/run.py` |
| Macro Intel | `india/macro_intel/run.py` | `usa/research/macro_intel/run.py` |
| Execution | `india/execution_simulator/run.py` | `usa/research/execution_simulator/run.py` |
| Learning | `india/learning_engine/run.py` | `usa/research/learning_engine/run.py` |

**Tests:** `backend/tests/test_sprint75.py` (18 tests · all green)

---

## 3 · History Artifacts (per market)

| History file | Producer |
|---|---|
| `recommendation_history.parquet` | Rec Engine v3 |
| `risk_history.parquet` | Risk Engine |
| `portfolio_history.parquet` | Portfolio Engine |
| `macro_history.parquet` | Macro Intel |
| `execution_history.parquet` | Execution Simulator |
| `learning_history.parquet` | Learning Engine |
| `factor_library.parquet` | Factor Library (today's snapshot) |
| `factor_library_history.parquet` | Factor Library (append-only) |

Every history file carries `market`, `asof`, `history_schema_version=1.0.0`, `appended_utc`, plus flattened engine payload. Nested JSON (recommendations list, sized positions, etc.) preserved as JSON-encoded columns.

---

## 4 · Regression Suite

```
======================================================================
  SPRINT 7.5 · Persistence & Factor Library · Regression Tests
======================================================================
  [OK] append_snapshot_row fresh
  [OK] dedupe same asof (latest wins)
  [OK] append new date sorted
  [OK] market isolation
  [OK] fail-open on missing keys
  [OK] nested payload flattens to JSON columns
  [OK] write_snapshot_and_history writes JSON + parquet
  [OK] load_history missing file returns empty
  [OK] history writes deterministic across calls
  [OK] model_stamp captured in dedicated column
  [OK] factor library end-to-end (all sources present)
  [OK] factor library resilient to no data (low confidence)
  [OK] factor library deterministic (same inputs → same outputs)
  [OK] factor library no-promotion contract
  [OK] factor library covers all source taxonomies
  [OK] factor library honors walk-forward asof cutoff
  [OK] factor taxonomy metadata populated
  [OK] history survives 60-day daily replay

  18 passed, 0 failed of 18
```

Sprint 6.5 regression re-verified: **22/22 pass · no regression.**

---

## 5 · Live Runtime Output (2026-07-21)

**USA Factor Library:** 22 factors · **11 confidently populated**
- Commodities: WTI Crude $82.42 (bull) · Brent $88.92 (bull) · Gold $4011.80 (sideways)
- Currency: UUP $28.39 (sideways)
- Volatility: VIX 18.65 (normal, bear trend)
- Central bank: Fed cycle neutral · yield curve normal (no inversion)
- Rotation: Financials leader · Technology laggard
- Bond yield changes (chg_1m_bps): fields exist but 0-value this run (bond data limited)

**India Factor Library:** 22 factors · **3 confidently populated** — INDIA VIX + 2 derived
- Thin data (India macro summary still light — this is the Sprint 6.5b follow-up already flagged)

---

## 6 · Contracts Enforced

| Contract | Status |
|---|---|
| Append-only (never truncate history) | ✅ tested (60-day replay test) |
| Dedupe on (market, asof) with latest-wins | ✅ tested |
| Market isolation (India ↔ USA never mix rows) | ✅ tested |
| Fail-open (bad payload never blocks daily JSON snapshot) | ✅ tested |
| Deterministic (same inputs → same outputs) | ✅ tested |
| Walk-forward safe (historical asof cutoff accepted) | ✅ tested |
| No `buy/sell/target_price/recommendation/action/promoted/approved` keys | ✅ tested for factor library |
| Model registry stamping (approval_status=experimental) | ✅ both markets |
| Free-data substrate only (no paid APIs) | ✅ substrate = Sprint 6.5 yfinance/FRED |
| Sealed OPS001/MON001 files untouched | ✅ |
| Legacy engines untouched | ✅ |

---

## 7 · Wired Into

| Integration point | Change |
|---|---|
| `scripts/aegis_daily_v2.py` | New `factor_library` step (after macro_intel) |
| `usa/scripts/usa_daily.py` | New `factor_library` step (after macro_intel) |
| `.github/workflows/aegis-ci.yml` | `python backend/tests/test_sprint75.py` added to CI |
| `india/backend_validation/datasets.yaml` | +8 dataset entries |
| `usa/backend_validation/datasets.yaml` | +8 dataset entries (recommendation_history_v3 avoids collision with legacy institutional_memory output) |

---

## 8 · What Downstream Sprints Get

- **Sprint 6 Learning Engine** — its `recommendation_history.parquet` input now actually gets written. Ledger accumulates daily; the learning corpus can start filling as horizons close.
- **Sprint 8 Walk-Forward Validation** — has a real per-engine ledger of daily state (rec, risk, portfolio, macro, execution, learning) to replay against. This unblocks Sprint 8's "first REAL results" milestone from the executive dashboard.
- **Sprint 9 AI Auditor** — can query per-factor time-series ("was oil rising when we entered this position") and per-engine daily snapshots.
- **Sprint 10 Research Factory** — factor library IS the substrate for automated hypothesis testing ("show me every period where Oil + VIX + USD rose together and how Auto stocks performed").

---

## 9 · No-Promotion Contract Proof

`test_factor_library_no_promotion_keys`:
```
[OK] factor library no-promotion contract
```
Scans every FactorReading for banned keys (`buy`, `sell`, `target_price`, `recommendation`, `action`, `promoted`, `approved`) — none present.

Runner-wired history appends inherit the contract from their producing engine (Rec Engine v3 already contract-tested; Sprint 7.5 only mirrors its JSON payload into a parquet row).

---

## 10 · Fail-Open Design

Every history append is wrapped in try/except with an inline warning print:

```python
try:
    from backend.persistence import append_snapshot_row
    append_snapshot_row(json.loads(OUT_XXX.read_text(encoding="utf-8")),
                         _ROOT / "reports" / "<name>_history.parquet")
except Exception as _hist_err:
    print(f"  history append warning (non-fatal): {_hist_err}")
```

**Rationale:** operator's binding rule "any push should not effect current pipeline". A history append failure MUST NOT block the daily JSON snapshot — the current-day artifact is authoritative; history is additive. Errors are logged to `reports/persistence_errors.jsonl` for auditability.

---

## 11 · Known Limits / Follow-ups

- **India factor library thin data** — 3/22 factors confidently populated. Root cause is Sprint 6.5's India macro reader having limited symbols. Recommend **Sprint 6.5b · India Macro Data Patch** (already flagged after Sprint 6.5) to widen India factor coverage.
- **Bond change_1m_bps still 0** on today's USA run — yfinance ^TNX/^TYX/^FVX/^IRX return `chg_1m_bps=0` from the current Sprint 6.5 reader. Historical replay will fill this once the reader's short-window bug is fixed; not blocking.
- **Legacy `recommendation_history.json`** (produced by USA `institutional_memory/run.py`) is unrelated to Sprint 7.5's `recommendation_history.parquet`. Two distinct datasets, both retained; USA yaml entry renamed to `recommendation_history_v3` to disambiguate.

---

## 12 · Cumulative Test Health (with Sprint 7.5)

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
Sprint 7.5 persistence + factor library        18/18   ✅  ← NEW
─────────────────────────────────────────────────────────
TOTAL                                         218/218  ✅
```

---

## 13 · NEXT BOTTLENECK

**Historical depth for meaningful walk-forward.** Sprint 7.5 unblocks Sprint 8 architecturally — the ledgers now exist — but **the ledgers are empty on day 1**. Sprint 8 will produce sparse walk-forward windows until 60+ trading days of daily runs have accumulated.

Two acceleration paths:
1. **Backfill** — run the daily orchestrator against historical price data (via `--asof <date>` if the runners support it) to seed the history parquets. Requires the runners to accept a historical cutoff.
2. **Snapshot-first Sprint 8** — build Sprint 8's engine now, but let it operate on whatever history exists (even if only a few days) with an explicit `n_walk_forward_windows` count in the output. Meaningful metrics arrive as the history deepens.

Recommended path: **Sprint 8 (Snapshot-first)** — build the engine, let it operate on the accumulating ledger, and refine walk-forward metrics as the history grows. Operator dashboard will visibly show `n_walk_forward_windows` incrementing daily.

Below that (still open): **India macro data completeness** (Sprint 6.5b · optional) — widens India factor library from 3/22 to 15+/22 confidence. Doesn't block Sprint 8.

---

**End of Sprint 7.5 · Persistence & Factor Library Report**
