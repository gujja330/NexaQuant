# Validation Engine · v2.0

**Live paper-trading harness · P1 in [PHASE2_MASTER_ROADMAP.md](../../docs/PHASE2_MASTER_ROADMAP.md).**

Turns DEV021's historical backtest into a continuous, live validation
loop. Advisory-only — never executes real trades. Deterministic ledger
with content-addressed IDs (ADR-006, ADR-009).

## What it does

Every daily run:

1. Pulls the current DEV023 recommendations.
2. **Opens** paper positions for any new Strong-Buy / Buy / Accumulate
   not already in the paper book. Uses latest close from
   `data/raw/india/{ticker}_D1.parquet`.
3. **Closes** positions whose recommendation flipped to Sell / Reduce /
   Avoid.
4. **Marks to market** every open position at latest close.
5. **Reconciles** closed trades against DEV023's target / stop /
   holding-period predictions (expected vs actual).
6. **Detects drift** — 1st-half vs 2nd-half Sharpe + win-rate; fires
   `sharpe_degrading` / `winrate_degrading` flags.
7. **Tracks opportunity cost** — tickers with strong recent win-rate
   that were NOT recommended this cycle.

Publishes:

- `reports/validation_v2_latest.json` — headline
- `reports/validation_v2_daily_{YYYY-MM-DD}.json` — timestamped snapshot
- `reports/validation_v2_daily_{YYYY-MM-DD}.md` — human report
- `reports/validation_v2_open_positions_{YYYY-MM-DD}.csv` — snapshot
- `reports/validation_v2_closed_trades.csv` — full ledger

Ledger written to (never in `reports/`):

- `data/market_intelligence/derived/validation_v2/paper_positions.parquet`
- `data/market_intelligence/derived/validation_v2/paper_trades.parquet`
- `data/market_intelligence/derived/validation_v2/paper_mtm.parquet`

## Contract

Every paper trade is content-addressed. Same inputs → same trade_id.
Duplicates are silently ignored. The ledger is append-only; there is no
way to delete or modify a past trade through this engine's API.

## Governance

- Advisory-only. Paper trades never execute against a broker.
- Deterministic (fixed impute rules, fixed content-hash, stable
  file-write order).
- The engine writes its ledger under `data/market_intelligence/derived/`
  which is git-ignored — the source of truth is the derived data, not
  the `reports/` snapshots.

## Exit criterion (Phase 2 §6)

Validation v2.0 is DONE only when:

- Daily paper-trading run publishes to `reports/`
- Weekly + monthly + quarterly reports auto-generate
- Expected-vs-actual reconciliation alerts on divergence
- ≥ 30 days of continuous operation without silent failure

This engine ships v2.0's foundation. The 30-day continuous-operation
proof is data, not code — it accrues from the daily runs.

## Run

```
python research/validation_v2/run.py             # persist ledger
python research/validation_v2/run.py --dry-run    # do not persist
python research/validation_v2/tests/test_smoke.py
```

## Layout

```
research/validation_v2/
  lib/
    paper_portfolio.py     — content-addressed paper ledger + MTM
    expected_actual.py     — reconciliation vs DEV023 targets
    drift.py               — metric drift + rolling edge
    opportunity_cost.py    — missed-edge tracking
  compute/
    engine.py              — orchestration
  publish/
    bundle.py              — daily JSON + MD report
  tests/
    test_smoke.py
  run.py
```
