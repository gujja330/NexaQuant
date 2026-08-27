# AEGIS · Research Topology (CEO-spec)

_Generated 2026-08-27T08:58:48+00:00_

```
research/
├── MR_V1/
│   ├── frozen/     · lock docs + experiments frozen list
│   ├── active/
│   │   ├── E1_india_r1_filter/     · shadow rule + card
│   │   ├── E2_india_r2_boost/      · shadow rule + card
│   │   └── E3_stop_loss/           · shadow rule + card
│   ├── evidence/    · India + USA history/portfolio/exit JSONLs
│   ├── daily/       · today's walk-forward captures + panel
│   ├── dashboards/  · daily control panel + CEO dashboard
│   ├── decisions/   · promotion decisions + evidence report
│   └── reports/     · consolidated learning + validation reports
│
├── archive/
│   ├── successful/   · forward PASS only · not historical hits
│   ├── promising/    · forward BORDERLINE with directional support
│   ├── failed/       · forward FAIL · never deleted
│   ├── superseded/   · retired / replaced experiments
│   └── data_quality/ · Momentum + USA fundamentals + USA canonical gaps
│
└── historical/
    └── 45d/        · immutable 45-day corpus anchor + manifest
```

## Card metadata contract

Every experiment card contains the 6 CEO-required fields:

1. **Historical evidence** · n, effect size, source
2. **Forward evidence** · N so far, WR, avg, target, source
3. **Statistical confidence** · verdict per MR_V1 discipline
4. **Decision** · promoted / rejected / pending / archived
5. **Reason** · plain-text hypothesis and current status rationale
6. **Revisit condition** · what triggers re-examination

## Successful ≠ historical hit

`archive/successful/` accepts an experiment ONLY after its forward acceptance criterion passes. Historical backtest wins are not enough. This prevents rediscovery loops.

## Compliance

- Zero production R1/R2/Registry/XLSX changes.
- Zero locked-layer edits.
- All content is a COPY of the machine-writable roots (`evidence/`, `active/MR_V1/`, `archive/` under `reports/research/`). Nothing is moved or deleted.