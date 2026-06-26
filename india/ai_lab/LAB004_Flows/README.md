# LAB-004 — Institutional Money

**Hypothesis:** institutional positioning — FII / DII net flows, mutual-fund and ETF holdings *changes* —
leads or confirms moves at the stock and sector level.

**Dataset:** `data/layers/flows.parquet` — `date, symbol, fii_net, dii_net, mf_holding_chg, ...`
(`date` = the disclosure date; monthly/quarterly holdings are PIT-lagged to their publication date).

**Run:** `python india/data_layer_gate.py` → IC / lift / walk-forward / DSR → update `experiments.yaml`.

**Note:** aggregate FII/DII is index-level (may help the regime overlay more than single-stock ranking);
stock-level holdings changes are the per-name signal. Promotion via the standard gate + forward paper.

**Status:** planned.
