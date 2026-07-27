# archive/ — deprecated code preserved for reference

**Constitution reference:** Articles 79 · 80 · 81 · 82.

Deprecated modules move here after their 2-sub-wave grace period. NEVER imported by `backend/`. May be referenced from `research/` for historical backtests only.

## Structure

```
archive/
  YYYY/
    NN_<capability>/
      README.md      what it did · what replaced it · when archived · why kept
      <original files>
```

## Rules

- Deletion requires ADR at `docs/decisions/`
- Preserves `git mv` history (never delete-and-recreate)
- Every archived module has a README explaining replacement path

## Current contents

(empty — populated as Wave 4 sub-waves archive deprecated code)

## Queued for archive (from Wave 4/5 audits)

- `research/recommendations/run.py` (DEV023) — after D4 keystone SSoT decision
- Runner 1 v1 legacy scripts — after Sprint 7.9 orchestrator supersedes
- Legacy `strategy/` modules with no consumers — after Phase 2 verification
- Legacy top-level `execution/`, `backtest/`, `markets/`, `experiments/` — after Phase 2 verification
