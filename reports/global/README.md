# reports/global/

Cross-market comparison artifacts. **Every Phase 3 sprint that produces per-market outputs MUST also produce a comparison here** (per [Phase 6 dual-market rule](../../docs/AEGIS_PHASE6_EXECUTION_BLUEPRINT.md#merge-rules-locked--block-pr-merge)).

## Naming Convention

```
<engine>_comparison.json     ← always
<engine>_comparison.parquet  ← always
<engine>_comparison.md       ← always
```

## Contents (per [Phase 3 global-comparison spec](../../docs/AEGIS_PHASE3_MASTER_ROADMAP.md#global-comparison-artifact-mandatory-per-sprint))

- India value · USA value · delta (absolute + %)
- Sample sizes for each market
- Statistical significance flag (using `backend.benchmark.statistical_significance` sample-size verdict)
- Per-dimension deltas (win rate · Sharpe · holding period · target achievement · exit efficiency · re-entry success · factor performance · sector performance · recommendation quality · portfolio performance)

## Merge Gate

Missing comparison for a shipped per-market engine = **PR blocked** ([Phase 6 merge rules](../../docs/AEGIS_PHASE6_EXECUTION_BLUEPRINT.md#merge-rules-locked--block-pr-merge)).

## Empty on 2026-07-24 · By Design

No files yet — no Phase 3 dual-market sprint has shipped since the rule was locked. First files land with Sprint C1 (Trade State Engine · `trade_state_comparison.json`) or Module 20 (Cross-Market Intelligence · aggregator over existing per-market outputs).
