# MON001 — Forward Paper-Trading + Monitoring · Sealed Preregistration

**Sealed 2026-07-13.** Locked BEFORE any MON001 forward evidence is evaluated. Any deviation
invalidates the preregistration.

## Origin

Post-LAB010 adversarial audit concluded that NexaQuant has zero out-of-sample forward
evidence and that PBO has trended to 0.90–0.94 across recent labs, signaling severe data-burn
on the 2021-10-01 → 2026-03-27 window. LAB010 verdict was NOT_VALIDATED. MON001 is the
monitoring layer that produces genuinely fresh evidence about the frozen production system.

MON001 is **NOT** an alpha lab. It does not test hypotheses. It does not increment
`cumulative_strategy_search`. It observes the frozen system on data postdating LAB009's
sealed confirmation window (2026-01-27 mature-bounded end) and reports how the live behaviour
compares to backtest envelopes.

## Core question

Does the frozen NexaQuant production system achieve behaviour consistent with its backtested
risk, drawdown, turnover, cost, and portfolio characteristics on genuinely fresh forward
data?

## Frozen production baseline fingerprint

MON001 tracks the frozen baseline defined by the production configuration in commit
`a702b99` (LAB010 results). The baseline components:

- `india/recommendation_registry.py:31` — `HOLD = 63`
- `india/recommendation_generator.py:44` — `CONFIG = dict(method="hrp", regime="global", sector_cap=2, rebal=63, name_cap=0.30, default_capital=500000, default_horizon=126, expiry_cal_days=7, review_cal_factor=1.46, buy_band_pct=1.5)`
- `india/confidence_engine.py:32-51` — `current_regime()` (VIX 120d q80 → 0.6/1.0, Nifty 200-DMA → 0.6/1.0, `global_exposure` multiplicative)
- `india/arjuna_v2.py` — HRP construction + `LOOKBACK` + `select_names` + `weights_for("hrp",...)`
- `india/data_nse.py` — `NIFTY200` universe

The fingerprint is a deterministic SHA-256 hash of the module source code of the above
files, plus the byte-serialization of the CONFIG dict and HOLD constant. Any change to
those files or values changes the fingerprint. See `fingerprint.py`.

## MON001 forward observation boundary

**`forward_boundary_asof = 2026-03-28`**

Rationale: LAB009's sealed confirmation window ends at `mature_date <= 2026-01-27`. Under
LAB009's period-boundary rule, cycles with `asof < 2026-03-28` may still have realized data
partially inside the sealed window (asof up to 2026-01-27, mature up to 2026-04-30
approximately). Using `2026-03-28` as the boundary ensures every MON001-eligible
recommendation is entirely post-confirmation-window — its asof is fresh AND its full
maturity is fresh.

Recommendations already logged with `asof >= 2026-03-28` in `data/aegis_registry.csv` are
eligible for immediate ingestion into the MON001 forward ledger.

## Paper vs broker distinction

MON001 clearly separates FIVE lifecycle stages per recommendation:

- **A. Model recommendation** — row in `data/aegis_registry.csv` with source in `{"live","paper"}`.
- **B. Theoretical paper execution** — reference price = row's `buy_price` (yfinance/Angel close snapshot at asof).
- **C. Broker order** — placed via `india/broker_angelone.py`. Currently NOT AUTOMATED (order placement is disabled per module comment).
- **D. Broker fill** — actual filled price/quantity/timestamp from Angel API. Currently NOT INTEGRATED.
- **E. Realized lifecycle outcome** — actual_ret + exit_price at mature_date, entered when scoring completes.

At MON001 seal time, only stages A / B / E are populated in the registry. Stages C / D are
PAPER_ONLY (unavailable). MON001 must never claim BROKER_REALIZED evidence when only paper
data exists.

## Benchmark

- **Primary benchmark:** Nifty-50 total-return index reconstructed from `data/raw/india/^NSEI_D1.parquet` (or equivalent) — matches the LAB009 benchmark used in `metric_suite`.
- **Alternate benchmark (diagnostic only, NOT a gate):** Nifty-200 equal-weight portfolio computed from `NIFTY200` universe.

## Evaluation horizons

MON001 reports at four rolling horizons:

- **T30**: rolling 30 trading days of forward observations — daily equity metrics only.
- **T63**: rolling 63 trading days — one complete HOLD cycle.
- **T126**: rolling 126 trading days — two HOLD cycles, first MaxDD reliability threshold.
- **T252**: rolling 252 trading days — annualized comparison horizon.

## Minimum observation requirements

For any metric to be reported (not `INSUFFICIENT_EVIDENCE`), the following minimums apply:

| Metric | Minimum forward trading days | Minimum cycles |
|---|:-:|:-:|
| Daily return / Sharpe / vol | 30 | — |
| Turnover / cost | 63 | 1 |
| MaxDD (reliable) | 126 | 2 |
| Sortino / Ulcer | 126 | 2 |
| Cycle-level win rate | — | 3 |
| Regime-conditioned metric | 63 (in that regime) | — |
| Annualized Sharpe vs backtest | 252 | 4 |

Below these thresholds, the specific metric reports `INSUFFICIENT_EVIDENCE`.

## Baseline expected envelopes (SEALED, derived from LAB009 State C `413a735`)

Envelopes are constructed from LAB009 N0=63 phase-level results at canonical 15bps cost, both
cash levels (0% and 6%). Envelope = `[min_across_phases, median_across_phases, max_across_phases]`.

### Full-window LAB009 N0=63 metric envelopes

| Metric | cash=0% min | cash=0% median | cash=0% max | cash=6% min | cash=6% median | cash=6% max |
|---|---:|---:|---:|---:|---:|---:|
| Sharpe (full) | 1.0765 | 1.2332 | (max derived at monitor init from phase data) | 1.2155 | 1.3855 | (idem) |
| CAGR (full) | (min derived) | 0.11239 | (max derived) | (min derived) | 0.12749 | (max derived) |
| MaxDD (worst) | -0.1682 | (median derived) | -0.06 | -0.1657 | — | — |
| Ulcer | (derived at init) | (derived at init) | (derived at init) | (derived at init) | (derived at init) | (derived at init) |
| median cost drag (canonical - stress) | — | 0.0074 | — | — | 0.0075 | — |

The complete envelope table is computed at MON001 init time by
`baseline_envelope.build_from_lab009()` and CACHED to
`reports/baseline_envelope_2026-07-13.json`. That JSON becomes the SEALED envelope — any
recomputation must produce byte-identical output or MON001 refuses to run.

## Drift thresholds (SEALED)

Thresholds are pre-declared and NOT tunable post-observation.

### D1 CONFIG_DRIFT (binary)
Baseline fingerprint at any monitoring run differs from the sealed fingerprint recorded at MON001 seal time.
→ Alert immediately. This is BLOCKING.

### D2 PERFORMANCE_DRIFT
Forward Sharpe deviates from LAB009 N0=63 envelope by more than **1.0 standard-deviation** (Sharpe SD estimated as `1/sqrt(T/252)`), where T is forward observation days. Requires T ≥ 30.
→ WATCH if forward Sharpe < median envelope − 1.0 SD.
→ DIVERGED if forward Sharpe < envelope_min − 1.0 SD.

### D3 RISK_DRIFT
Forward realized MaxDD deeper than **backtested worst MaxDD × 1.20** (20% buffer). Requires T ≥ 126.
→ WATCH if forward MaxDD < envelope_worst × 1.10 (10% buffer breach).
→ DIVERGED if forward MaxDD < envelope_worst × 1.20 (full 20% breach).

### D4 TURNOVER_DRIFT
Realized cycle-level turnover more than **1.50 × backtested mean turnover** (from LAB009 diagnostics). Requires ≥ 1 cycle.
→ WATCH at 1.30×. → DIVERGED at 1.50×.

### D5 COST_DRIFT
Realized cost drag (cost bps × turnover) exceeds LAB009 stress cost drag (50bps × turnover), or if broker slippage available: realized slippage per trade > 15bps median.
→ WATCH if realized cost > 1.10 × backtest canonical drag. → DIVERGED if realized cost > backtest stress drag.

### D6 REGIME_BEHAVIOUR_DRIFT
Forward exposure at each regime bucket (Strong/Neutral/Weak) differs from the backtest exposure mean by more than **0.15 absolute** (units of exposure).
→ WATCH at 0.10 abs. → DIVERGED at 0.15 abs.

### D7 CONCENTRATION_DRIFT
Any name in the forward ledger has intended weight > `name_cap × 1.05` (5% tolerance for float ops), OR any sector holds > `sector_cap + 1` positions.
→ DIVERGED immediately if breached (portfolio construction rules are hard constraints).

### D8 DATA_DRIFT
Forward observation ledger has >5% missing prices, OR >10% stale recommendations (mature_date passed but exit_price not populated within 5 trading days).
→ WATCH at 5% / 10%. → DIVERGED at 10% missing / 20% stale.

### D9 EXECUTION_DRIFT (paper-only until broker integrated)
Reserved. Currently reports `PAPER_ONLY` (no broker fill data). Once broker fills available,
divergence = median |paper_price - fill_price| / paper_price > 0.005 (50bps).

### D10 DATA_INTEGRITY_FAILURE
Any of: retroactive mutation of a sealed forward-ledger row detected; ledger schema mismatch;
duplicate rec_id under same fingerprint; forward-ledger row with `asof < forward_boundary_asof`.
→ HALT_REVIEW_REQUIRED immediately.

## Global MON001 state machine

States (mutually exclusive):

- **`INSUFFICIENT_EVIDENCE`** — not enough forward days accumulated for any metric threshold. Default at seal time.
- **`PASS`** — every applicable metric is within envelope + no active drift alerts + sample size sufficient for at least one non-trivial evaluation horizon (T63).
- **`WATCH`** — one or more WATCH-level alerts active; no DIVERGED alerts.
- **`DIVERGED`** — one or more DIVERGED-level alerts active.
- **`HALT_REVIEW_REQUIRED`** — DIVERGED alerts on any single dimension persist for ≥ 4 consecutive weekly reports (28 days), OR CONFIG_DRIFT (D1), OR DATA_INTEGRITY_FAILURE (D10).
- **`DATA_INTEGRITY_FAILURE`** — same as D10 — ledger cannot be trusted.

## HALT_REVIEW_REQUIRED semantics

- MON001 must NOT modify production configuration automatically.
- Alert is written to reports/mon001_alerts.jsonl (append-only).
- Human operator review required. Response is out-of-band.
- MON001 continues collecting evidence after HALT unless operator issues explicit pause.
- HALT is NOT authorization to launch a corrective alpha lab (see FUTURE_RESEARCH_ROADMAP.md governance).

## Insufficient-evidence expectations at seal time

At seal (2026-07-13), the registry already has 30 live paper recommendations logged
across two batches (asof 2026-06-25 and 2026-06-29). Both batches are after
`forward_boundary_asof = 2026-03-28`, so they are MON001-eligible. But:

- T30 threshold requires 30 forward trading days from FIRST eligible asof. From 2026-06-25
  to 2026-07-13 is ~14 trading days — below T30 threshold.
- No forward cycle has matured (63 trading days after 2026-06-25 ≈ 2026-09-24). No cycle-
  level metrics are computable.
- Expected initial global status: **`INSUFFICIENT_EVIDENCE`**.

## What MON001 does NOT do

- Does NOT modify `HOLD`, `CONFIG`, `current_regime()`, `HRP`, `sector_cap`, `name_cap`, or any strategy input.
- Does NOT tune drift thresholds after seeing forward data.
- Does NOT place, modify, or cancel broker orders.
- Does NOT increment `cumulative_strategy_search`.
- Does NOT promote any LAB001–LAB010 candidate.
- Does NOT rewrite historical registry rows.
- Does NOT rewrite historical LAB001–LAB010 evidence.

## Adversarial pre-seal review (must all PASS before seal)

Below is the pre-seal audit performed 2026-07-13. All items are addressed in the sealed design.

| # | Concern | Resolution in sealed design |
|:-:|---|---|
| 1 | Leakage: forward evidence must NOT include any period inside LAB009 confirmation window | `forward_boundary_asof = 2026-03-28` chosen to be strictly after LAB009 confirmation `mature_date <= 2026-01-27`. |
| 2 | Benchmark mismatch: backtest used one benchmark, MON001 another | Primary benchmark = same Nifty-50 total-return used in LAB009 `metric_suite`. |
| 3 | Overlapping observations | 63-day HOLD cycles overlap by construction. MON001 handles this by computing daily equity metrics for T30/T63/T126/T252 daily-cadence AND separate cycle-level metrics for cycle-cadence. Both are reported separately, not conflated. |
| 4 | Partial-lifecycle recommendations | MON001 distinguishes 5 lifecycle stages A/B/C/D/E. Cycle-level metrics only include cycles where E (realized outcome) is populated. Open cycles counted only for daily-equity metrics. |
| 5 | Survivorship: forward universe may differ from backtested universe | MON001 uses `NIFTY200` at each asof — same as production. If NIFTY200 constituents change during forward observation, this is DATA_DRIFT alert. |
| 6 | Missing prices | Explicitly a DATA_DRIFT dimension (D8). |
| 7 | Stale recommendations (mature but not scored) | Explicitly a DATA_DRIFT dimension (D8). |
| 8 | Duplicate recommendations | Ledger unique constraint on `(fingerprint, rec_id, asof)`. Duplicate = DATA_INTEGRITY_FAILURE (D10). |
| 9 | Broker fill mismatch (order without fill or vice versa) | Currently N/A (PAPER_ONLY). Once broker integrated, mismatch is EXECUTION_DRIFT (D9). |
| 10 | Transaction cost assumption vs realized | Two-tier: paper cost = 15bps × turnover (canonical); realized cost from broker fills (once available). Both reported separately (D5). |
| 11 | Look-ahead in daily monitoring | Monitor uses only market data with `date <= run_date - 1` (strictly prior close for return computation). Daily monitor run at t is bounded to data at t-1 close. |
| 12 | Retroactive recommendation mutation | Ledger is append-only. Any attempt to modify a sealed forward-ledger row is DATA_INTEGRITY_FAILURE (D10). Correction path is a NEW correction row referencing the original. |
| 13 | Timezone / date-boundary | All dates in `Asia/Kolkata` calendar (matches NSE trading days). All timestamps stored as UTC. Registry dates already use IST convention. Monitor asserts. |

## Sealed configuration

The full sealed configuration is in `india/monitoring/MON001_Forward_Validation/mon001.yaml`.
Hash of preregistration + mon001.yaml recorded at seal time.

## Seal metadata

- **Sealed:** 2026-07-13
- **Sealed at HEAD:** `a702b99`
- **Author:** operator + Principal Quant Platform Architect (assistant)
- **Change ID:** MON001-FORWARD-VALIDATION-V1
- **cumulative_strategy_search at seal:** 38 (unchanged; MON001 is not a search)
