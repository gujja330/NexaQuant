# LAB-002 — Point-in-Time Fundamentals

**Hypothesis:** *as-reported* fundamentals and their **acceleration** (not today's trailing ratios)
rank future winners better than price alone.

**Critical:** must be **point-in-time** — ROE/margins/debt/growth keyed to the date they were *filed/known*,
not restated later. Using current values = look-ahead and the gate verdict becomes a lie.

**Dataset:** `data/layers/fundamentals.parquet` — `date, symbol, f_roe, f_margin, f_debt_eq,
f_rev_growth, f_roe_accel, ...` (availability dates).

**Run:** `python india/data_layer_gate.py` → IC / lift / walk-forward / DSR → update `experiments.yaml`.

**Promotion:** same gate as all LABs — beat frozen baseline OOS + forward paper.

**Status:** planned.
