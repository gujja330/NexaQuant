# LAB-003 — Corporate Actions / Events

**Hypothesis:** discrete events — large order wins, regulatory/FDA approvals, M&A, buybacks, management
change — carry short-to-medium-horizon information.

**Dataset:** `data/layers/events.parquet` — `date, symbol, event_type, magnitude/score`
(`date` = the public-announcement date). Events can be encoded as a recency-decayed score per symbol.

**Run:** `python india/data_layer_gate.py` → IC / lift / walk-forward / DSR → update `experiments.yaml`.

**Note:** event studies are prone to look-ahead and survivorship — be strict on the announcement date and
on how long the signal is held. Promotion only via the standard gate + forward paper.

**Status:** planned.
