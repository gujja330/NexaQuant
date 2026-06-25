# AEGIS Data Layers — drop any information source here

This folder is the **plug-in point** for the Data-Layer Gate (`india/data_layer_gate.py`).
Any tidy file you put here is auto-enrolled and faces the full battery
(IC · RQS lift · walk-forward · rolling OOS · DSR) — KEEP or DISCARD, no new code.

## File contract

A `.parquet` or `.csv` with **at minimum** these columns:

| column   | meaning                                                                 |
|----------|-------------------------------------------------------------------------|
| `date`   | **point-in-time AVAILABILITY date** — when this fact was *publicly known* |
| `symbol` | NSE symbol, matching `india/data_nse.py` (e.g. `RELIANCE`, `HDFCBANK`)   |
| *any other column* | becomes its own layer (`<file>:<column>`), scored higher = better |

Example `data/layers/earnings.parquet`:

```
date         symbol      surprise_pct   guidance_score
2024-07-19   RELIANCE    +4.2           1
2024-07-22   TCS         -1.1           0
```

## The one rule that matters: NO LOOKAHEAD

`date` must be the **day the information became available**, never the period it
describes. A Q1 result for quarter-ending June that was announced on July 19 has
`date = 2024-07-19`. Using the period-end (June 30) would leak the future and the
gate's KEEP verdict would be a lie. The adapter only ever uses, per symbol, the
latest row with `date <= today` — so PIT correctness lives entirely in your `date`.

## Candidate sources to acquire (each a separate file)

- `earnings.parquet` — surprise %, guidance, revisions
- `flows.parquet` — FII / DII net flow, delivery %
- `insider.parquet` — promoter/insider buy-sell
- `analyst.parquet` — rating changes, target revisions
- `sector_fundamentals.parquet` — sector earnings momentum, valuation

A KEEP here is still only **"pending forward paper"** — it must also survive live
cycles before it touches production. That status is tracked in
`data/aegis_layer_registry.csv`.
