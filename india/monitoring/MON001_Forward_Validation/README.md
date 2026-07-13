# MON001 — Forward Paper-Trading + Monitoring

**Sealed 2026-07-13.** Not an alpha lab. Does not increment `cumulative_strategy_search`.
Does not modify production strategy logic.

## Purpose

Answer one question:

> Does the frozen NexaQuant production system achieve behaviour consistent with its
> backtested risk, drawdown, turnover, cost, and portfolio characteristics on genuinely
> fresh forward data (asof ≥ `2026-03-28`)?

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     FROZEN PRODUCTION (unchanged)                                │
│  recommendation_registry.py  ·  recommendation_generator.py                      │
│  confidence_engine.py        ·  arjuna_v2.py         ·  data_nse.py              │
│                       ↓ writes to data/aegis_registry.csv                        │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        │  READ-ONLY
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        MON001 · Forward Observation Layer                        │
│                                                                                   │
│   ┌──────────────────┐    ┌───────────────────┐    ┌────────────────────────┐    │
│   │  fingerprint.py  │    │  forward_ledger   │    │  baseline_envelope     │    │
│   │  (SHA-256 hash   │    │  (append-only     │    │  (from LAB009 State C) │    │
│   │  of production   │    │  JSONL + hash     │    │  N0=63 phase envelope) │    │
│   │  files/consts)   │    │  chain integrity) │    │                        │    │
│   └──────────────────┘    └───────────────────┘    └────────────────────────┘    │
│           │                       │                          │                    │
│           └───────────┬───────────┴──────────────┬───────────┘                    │
│                       ▼                          ▼                                │
│              ┌───────────────────────────────────────┐                            │
│              │       monitor.py · drift engine       │                            │
│              │  D1–D10 dimensions · state machine    │                            │
│              └───────────────────────────────────────┘                            │
│                                    │                                              │
│                                    ▼                                              │
│              ┌───────────────────────────────────────┐                            │
│              │   report.py · JSON + markdown output  │                            │
│              │   append-only alerts JSONL            │                            │
│              └───────────────────────────────────────┘                            │
│                                                                                   │
│   ┌──────────────────┐                                                            │
│   │  broker_layer.py │  PAPER_ONLY at seal — plumbing for future ENG003          │
│   │  (READ-ONLY)     │                                                            │
│   └──────────────────┘                                                            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Files

| File | Purpose |
|---|---|
| `preregistration.md` | Sealed hypothesis, thresholds, adversarial audit log |
| `mon001.yaml`        | Sealed configuration (drift envelopes, minimum evidence, boundaries) |
| `fingerprint.py`     | Deterministic SHA-256 hash of the frozen production baseline files + constants |
| `forward_ledger.py`  | Append-only JSONL ledger with hash-chain integrity (retroactive mutation detection) |
| `baseline_envelope.py` | Builds/caches N0=63 envelope from LAB009 period-corrected diagnostics |
| `broker_layer.py`    | READ-ONLY broker interface. Currently PAPER_ONLY; refuses order placement |
| `monitor.py`         | Metric evaluation + D1–D10 drift detection + global state machine |
| `report.py`          | JSON diagnostics + markdown report + append-only alerts JSONL |
| `run_mon001.py`      | Daily orchestration entrypoint |
| `test_mon001_framework.py` | 25 adversarial tests |
| `reports/`           | Dated diagnostics JSON + markdown + sealed_fingerprint.json + baseline_envelope cache (once produced) |
| `ledger/`            | Append-only forward observation JSONL + corrections JSONL (once produced) |

## Sealed thresholds at a glance

See `preregistration.md` for full detail.

| Dim | Metric | WATCH | DIVERGED | Min days |
|---|---|:-:|:-:|:-:|
| D1 | Config fingerprint | — | on any change | 0 |
| D2 | Forward Sharpe | < median − 1σ | < envelope_min − 1σ | 30 |
| D3 | Forward MaxDD | envelope_worst × 1.10 | envelope_worst × 1.20 | 126 |
| D4 | Cycle turnover | 1.30 × backtest | 1.50 × backtest | 63 (1 cycle) |
| D5 | Cost drag | 1.10 × canonical | ≥ stress cost | 63 (1 cycle) |
| D6 | Regime exposure | 0.10 abs diff | 0.15 abs diff | 63 per bucket |
| D7 | Concentration | — | name_cap × 1.05 breach; sector_cap+1 breach | 1 rec |
| D8 | Data quality | 5% missing / 10% stale | 10% missing / 20% stale | any |
| D9 | Execution slippage | — | 15bps median (PAPER_ONLY at seal) | any |
| D10 | Data integrity | — | hash-chain break; retroactive mutation; boundary breach | 0 |

## Global states

`INSUFFICIENT_EVIDENCE` · `PASS` · `WATCH` · `DIVERGED` · `HALT_REVIEW_REQUIRED` · `DATA_INTEGRITY_FAILURE`

HALT is triggered by:
1. `D1_CONFIG_DRIFT` (immediate)
2. `D10_DATA_INTEGRITY_FAILURE` (immediate)
3. Any single dimension DIVERGED for ≥ 4 consecutive weekly reports (persistence rule)

HALT emits an alert and preserves evidence. It does **not** automatically modify
production. Operator review required.

## Operational procedure

### First-time seal (once)
```
python india/monitoring/MON001_Forward_Validation/run_mon001.py --seal-init
```
Writes the sealed fingerprint and baseline envelope to `reports/`. Ingests any existing
forward-eligible recommendations.

### Daily / weekly monitoring
```
python india/monitoring/MON001_Forward_Validation/run_mon001.py
```
Idempotent — recommendations already in the ledger are not re-appended. Produces a dated
report and diagnostics JSON. Alerts appended to `reports/mon001_alerts.jsonl`.

### Dry-run (no ledger append)
```
python india/monitoring/MON001_Forward_Validation/run_mon001.py --dry-run
```

## Tests

```
python india/monitoring/MON001_Forward_Validation/test_mon001_framework.py
```

25 adversarial tests covering: clean paper observation, pre-boundary leakage,
duplicate rec_ids, retroactive-mutation detection, paper/broker separation, fingerprint
stability + drift, missing-file rejection, envelope-cache byte-identity, broker read-only
enforcement, name_cap + sector_cap breach, data-quality drift, correction append discipline,
INSUFFICIENT_EVIDENCE state, CONFIG_DRIFT → HALT, DATA_INTEGRITY_FAILURE → HALT, DIVERGED
persistence requirement, hand-inserted pre-boundary row detection, LAB009 evidence
read-only, evidence-threshold enforcement, cumulative_strategy_search unchanged, and
production constants unchanged.

## Governance

- Does NOT modify `HOLD`, `CONFIG`, `current_regime`, HRP, sector_cap, name_cap.
- Does NOT place, modify, or cancel broker orders (order-placement methods raise RuntimeError).
- Does NOT increment `cumulative_strategy_search`.
- Does NOT promote any LAB001–LAB010 candidate.
- Does NOT rewrite historical registry rows (append-only + hash chain).
- Does NOT rewrite historical LAB001–LAB010 evidence (envelope build is read-only).
- Does NOT authorize LAB011 or any new alpha lab.

## Known limitations at seal time

- Paper equity reconstruction uses regime-label midpoint as exposure proxy (Strong=1.0,
  Neutral=0.75, Weak=0.6). Actual `current_regime()` produces continuous float — divergence
  detected in D6 against backtest exposure distribution, not against this proxy.
- Broker fill history is not ingested (`broker_layer.PaperOnlyBrokerLayer`). D9 EXECUTION_DRIFT
  is a plumbing stub until ENG003 wires real fills.
- Benchmark loaded via `feature_engine.load_panels()` `idx` series — this is the Nifty-50
  proxy used by production. Confirmation of benchmark provenance is a first-week
  operational check.
- MON001 daily-metrics engine uses paper-cost model (canonical 15bps × turnover); realized
  cost is D5 alert only when broker fills exist.

## Future ENG003 linkage

Once broker fill history is ingested (out of scope for MON001 seal):
1. Replace `PaperOnlyBrokerLayer` with `AngelBrokerLayer` returning real fills.
2. Extend ledger schema to populate `broker_order_id`, `broker_fill_id`, `fill_price`,
   `fill_ts_utc`.
3. D9 EXECUTION_DRIFT becomes evaluable (paper price vs fill price divergence).
4. Cost model in D5 switches to realized slippage.
5. ENG003 execution/slippage calibration study uses the accumulated fill data.
