# LAB-001 — Earnings Intelligence

**Hypothesis:** quarterly earnings *surprise*, guidance, and estimate *revisions* carry information that
improves cross-sectional stock ranking beyond price — moving selection RQS off 0.50.

**Dataset to acquire (point-in-time):** for each NSE result —
`date` (the **announcement/availability** date, never the period-end), `symbol`, and fields like
`surprise_pct`, `guidance_score`, `revision_4w`, `eps_growth_yoy`.

**Ingestion contract:** drop a tidy file in `data/layers/earnings.parquet` with columns
`date, symbol, <fields>` (see `data/layers/README.md`). The PIT adapter uses, per symbol, the latest
row with `date <= today` — so no look-ahead.

**Run the gate:**
```
python india/data_layer_gate.py        # IC · RQS lift · walk-forward · DSR -> KEEP / DISCARD
```
Then update `experiments.yaml` (LAB-001) with the result.

**Promotion:** beat the frozen baseline OOS (lift > +0.02, IC significant), hold across folds, survive
DSR, then forward paper. Only then does it touch production. Otherwise: documented "tested, not adopted."

**Status:** planned (awaiting dataset).
