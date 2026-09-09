# How to run the AEGIS pipeline

One command runs everything. The same command runs in CI, so there is no
"manual version" that can drift from the scheduled one.

```bash
python -m backend.pipeline.contract.runner --market both --refresh
```

That acquires today's data, checks eight gates, and prints a certification.
It ships nothing unless every gate passes.

---

## The everyday commands

| What you want | Command |
|---|---|
| **Morning / evening run** | `python -m backend.pipeline.contract.runner --market both --refresh` |
| **Run and deliver** | `... --market both --refresh --send` |
| **India only** | `... --market india --refresh` |
| **USA only** | `... --market usa --refresh` |
| **Check without touching data** | `... --market both` |
| **Replay a past date** | `... --market both --asof 2026-09-08` |

`--refresh` acquires data first. Without it the run judges whatever is
already on disk — useful for re-checking, never for a real daily run.

`--send` delivers the message and the dated XLSX **only if every gate
passes**. Without it nothing leaves the machine.

### Running one market

Each market is fully independent — its own data, its own gates, its own
certification and lineage record. India blocking never stops USA.

```bash
# India
python -m backend.pipeline.contract.runner --market india --refresh --send

# USA
python -m backend.pipeline.contract.runner --market usa --refresh --send
```

Use this when one market is already certified and you only need the other,
or when you are diagnosing a single market and want a fast loop.

`--market both` runs the two markets' **acquisition concurrently** (they
share nothing) and then gates each one separately. Two single-market runs
back to back are correct but slower.

---

## What comes back

```
════════════════════════════════════════════════════════════
AEGIS DAILY RUN CERTIFICATION
Run: AEGIS-2026-09-09-USA-0532
Requested ASOF: 2026-09-09   ·   trigger: manual
════════════════════════════════════════════════════════════

DATA_READY          feature_snapshot / price_bars / macro / universe
INTERMARKET         S&P · VIX · DXY · USD/INR · US10Y · oil · gold …
FEATURES_READY      snapshot for THIS date · coverage · duplicates
SCORES_READY        full universe scored · nothing cut before eligibility
DECISION_READY      N scored → N terminal dispositions · orphans 0
LIFECYCLE_READY     CURRENT / EXIT counts
FIELDS_COMPLETE     every actionable row has entry · stop · confidence
DELIVERY_READY      gate ALLOW · override false · A19 / A23

FINAL: ✅ CERTIFIED
```

Exit code `0` certified, `1` blocked.

When something fails it stops at the **first** failure and says so:

```
FINAL: ❌ BLOCKED
FIRST FAILURE: FEATURE_SNAPSHOT_ASOF_MISMATCH  (FEATURES_READY)
No downstream stages executed. No XLSX. No Telegram.
```

Everything after the first failure is a consequence, so it is reported as
`downstream NOT RUN` rather than as more red crosses to read through.

---

## Where the output goes

| File | What it is |
|---|---|
| `reports/context/run_certification_<market>.txt` | the report above |
| `reports/context/lineage/AEGIS-<date>-<MARKET>-<HHMM>.json` | every stage's contract |
| `reports/context/lineage/latest_<market>.json` | pointer to the most recent run |
| `reports/telegram/AEGIS_<MARKET>_<date>.xlsx` | the dated workbook |
| `reports/telegram/canonical_message_<market>.txt` | the message text |

The lineage file answers "where did this stock come from" without
detective work: it records `run_id`, `asof`, row and ticker counts,
coverage, source as-ofs and the status of every stage.

---

## The eight gates, and why each exists

Each one was added because it had already failed silently in production.

**1 · DATA_READY** — sources present and inside their freshness budget.
The feature snapshot budget is **0 days**: today's scoring needs today's
features. On 2026-09-09 the feature store had fallen back to 2026-07-21
and every downstream guard truthfully reported its own artifact fresh.

**2 · INTERMARKET** — S&P, VIX, DXY, USD/INR, US 10Y, oil, gold, India
VIX, Nifty Bank, commodities, currencies, bonds, sector rotation, macro
regime, FII/DII. India's global set had frozen on 2026-06-19 and sat
three months stale. Regime multiplies into the confidence that gates
entry, so a stale regime moves every threshold silently.

**3 · FEATURES_READY** — the snapshot for **this date**, not the latest
one that exists. Plus coverage, duplicates, and shrinkage against the
previous snapshot.

**4 · SCORES_READY** — the full universe was scored and nothing was cut
before eligibility. Persisting only `top_10 + bottom_5` once discarded
COP, DVN, MPC and TRV — four qualified BUYs that never reached a rule.

**5 · DECISION_READY** — conservation. If 516 are scored, 516 must hold
exactly one terminal disposition. 515 is red, not "probably fine".

**6 · LIFECYCLE_READY** — the canonical lifecycle is the only producer of
CURRENT and EXIT HISTORY.

**7 · FIELDS_COMPLETE** — every actionable row carries entry price, stop
and confidence. Twelve NEW rows once shipped with a blank stop.

**8 · DELIVERY_READY** — gate ALLOW, no override, A19/A23 pass, R3
production writes zero.

---

## Refreshing one domain by hand

The single command covers all of these. They are listed for when you are
diagnosing one stage and want to run only it.

```bash
# India
python india/global_risk.py                        # S&P VIX DXY USDINR US10Y oil gold
python india/macro_intel/run.py                    # commodities · currencies · bonds · regime
python india/market_intelligence/run.py            # regime · breadth · sector rotation
python india/fii_dii.py                            # flows
python india/feature_store/run.py                  # feature snapshot
python india/model_factory/run.py                  # ensemble
python india/recommendation_intelligence/run.py    # recommendations
python -m backend.recommendation.ssot.run --market india --force

# USA
python usa/scripts/refresh_market_data.py          # bars + index series
python usa/research/macro_intel/run.py
python usa/research/market_intelligence/run.py
python usa/research/model_factory/run.py
python usa/research/recommendation_intelligence/run.py
python -m backend.recommendation.ssot.run --market usa --force

# both
python scripts/run_dynamic_risk_v2.py --market both   # stops
```

`--force` on the SSOT is required to regenerate a snapshot that already
exists for today. That lock is deliberate: it stops a re-run silently
overwriting the morning's picks. Pass it only when you intend to replace
them.

---

## Diagnostics

```bash
# where every scored ticker ended up, and why
python -m backend.delivery.lifecycle.why_not_current --market both

# what production sees vs the full universe
python -m backend.research.shadow.full_universe_shadow --market both

# every guard, every stale/fallback entry point, the five gates
python -m backend.observability.pipeline_audit

# freshness of all 95 tracked artifacts
python backend/observability/data_freshness.py
```

---

## Measured runtime

| | India | USA |
|---|---|---|
| Acquisition (parallel) | 36s | 361s |
| Gates | ~1s | ~1s |
| **Wall clock, both markets, full refresh** | **8m 49s** | |
| Gates only, no refresh | | **~2m 20s** |

USA acquisition dominates: 520 tickers of bars from yfinance. The two
markets run concurrently, so the total is USA's time, not the sum.

---

## Rules the runner enforces

**Fail closed.** A stage refuses to run when its upstream contract is
invalid. There is no "use the latest file" path anywhere on the
production route.

**One as-of.** The run's date is chosen once at the top and handed to
every stage. No stage decides for itself which day it is working on.

**Parallel only across independent work.** India and USA acquire
concurrently because they share nothing. Scoring never starts before its
own market's features exist.

**Collection is not promotion.** The intermarket series are collected and
freshness-gated; not one of them is fed to R2. Cross-market transmission
stays evidence-blocked until it earns out-of-sample and incremental
value.

**R3 is shadow.** It annotates R2 candidates and changes nothing. Every
row reads `ABSTAIN` until a specialist passes its evidence gate.
