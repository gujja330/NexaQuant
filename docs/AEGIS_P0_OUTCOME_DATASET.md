# AEGIS · P0 · Canonical Outcome Dataset

**Locked 2026-08-11** · single source of truth for all AEGIS research and analytics.

## Why this exists

The Investability 75%-vs-25% mismatch that triggered this lock was NOT a model bug · it was a **data-integrity bug**. Two analyses of the same XLSX produced contradictory numbers because they disagreed on:
- Which rows count as "latest observation"
- Whether open positions count as win/loss
- How to resolve ties in Position ID
- Whether to include ARTIFACT rows

Same failure mode will recur every time we run interaction analysis (Cap × Sector × Investability × Runner) directly on the XLSX. A multi-factor cross-tab is **far more sensitive** to definition drift than a single-variable Investability breakdown.

**Solution: one canonical dataset · one definition per field · every research query sources from it.**

## Files delivered

| File | Purpose |
|---|---|
| `configs/outcome_dataset_schema.yaml` | Data dictionary · field definitions · sample-size tiers |
| `backend/research/outcome_dataset.py` | Builder module |
| `scripts/build_outcome_dataset.py` | CLI driver · `python scripts/build_outcome_dataset.py` |
| `reports/research/outcome_dataset.parquet` | Canonical dataset · one row per Position ID |
| `reports/research/outcome_dataset_summary.json` | Rollup + sample-tier flags |

## Schema · one row per Position ID

**Identity (immutable · set at Position creation):**
- `position_id` · `{TICKER}_{MARKET}_{YYYYMMDD}` · never re-used
- `country` · IND / USA
- `runner` · R1 / R2 (never R3 · Constitutional invariant)
- `ticker` · `sector` · `cap`

**Initial engine values (frozen at creation · never re-derived):**
- `initial_rank` · from rank_history earliest entry
- `initial_confidence` · same
- `initial_model_score` · same
- `initial_investability` · from investability report snapshot at creation
- `initial_investability_verdict` · QUALITY/OK/MARGINAL/AVOID at creation
- `entry_date` · original recommendation date
- `entry_price` · parquet close on Entry Date

**Horizon returns (computed once per horizon per Position):**
- `ret_1d_pct` · `ret_3d_pct` · `ret_5d_pct` · `ret_10d_pct` · `ret_17d_pct` · `ret_30d_pct` · `ret_60d_pct` · `ret_90d_pct`
- Formula: `(price_at_horizon / entry_price - 1) * 100`
- Null if horizon not yet observable

**Running extremes (updated daily):**
- `max_gain_pct` · rolling max close / entry - 1
- `max_drawdown_pct` · rolling min close / entry - 1
- `current_price` · `current_perf_pct`

**Terminal fields (set only at Position closure):**
- `exit_date` · `exit_price` · `exit_pnl_pct` · `exit_reason`
- `win_flag` · **null for open positions** (governance rule · never counted)
- `lifecycle` · NEW / ACTIVE / REVIEWING / CLOSED / ARTIFACT
- `is_closed` · bool
- `sample_tier_note` · derived from runner N

## Sample-size tiers (LOCKED)

| n | Label | Color |
|---|---|---|
| 0-4 | observation only | gray |
| 5-14 | hypothesis | yellow |
| 15-29 | research signal | amber |
| 30-49 | stronger evidence | light green |
| 50+ | validation candidate | dark green |

**Rule: no research claim above the tier its sample size supports.** Technology (n=5) and Healthcare (n=3) results are currently **observation only** · not "signal" · even though the numbers are eye-catching.

## Governance rules (locked)

1. Every analytical query sources from `outcome_dataset.parquet` · never XLSX
2. Open positions never counted as win/loss · `win_flag=null` until closure
3. Initial fields immutable · never re-derived after Position creation
4. Position ID immutable across every export · India + USA
5. No engine changes based on n<50 · only observation
6. Interaction analysis (Cap × Sector × Runner) waits for n≥15 per cell
7. Cross-tab publication requires `sample_tier_note` visible on every cell

## Usage

**Build/refresh the dataset:**
```
python scripts/build_outcome_dataset.py
```

**Query in Python:**
```python
import pandas as pd
df = pd.read_parquet("reports/research/outcome_dataset.parquet")

# Cap × Runner (closed only)
closed = df[df["is_closed"]]
grouped = closed.groupby(["runner", "cap"]).agg(
    n=("position_id", "count"),
    win_rate=("win_flag", lambda x: x.mean() * 100),
    avg_pnl=("exit_pnl_pct", "mean")
)
```

## Acceptance criteria

- [x] Every field has one owner
- [x] Every field has one definition
- [x] Every field has one source
- [x] Initial fields immutable across rebuilds
- [x] `win_flag` null on open positions
- [x] Sample-tier note attached to every row
- [x] Same schema for India + USA + R1 + R2
- [ ] Wired into CI (Sprint K Part 25 work · after 30 days of data)
- [ ] Interaction analysis published (R-CTX-01 · after n≥100 per bucket)

## What comes next (per CEO lock)

**NOT changing R1/R2. NOT adding indicators. NOT changing weights.**

Instead:
1. Run this builder daily (add to cron with `scripts/aegis_run_all.py`)
2. Wait for n≥30 closed per bucket
3. Interaction analysis: `outcome_dataset.parquet` → Cap × Sector × Runner × Investability cross-tab
4. Only THEN propose engine changes · with evidence at proper tier

Next review checkpoint: **2026-09-08** (~30 trading days).
