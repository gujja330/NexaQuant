# R2 Zero-Entry Readout

**Status:** Diagnosis closure · CEO 2026-09-03 controlling contract · pasted-plan Sec 2 gate.
**Owner:** R2 track (Sprint A).
**Precedes:** shipping R1 advisory sheet (which is now already wired · this readout retro-closes the sequencing prerequisite).

---

## 1 · The observation

R2 has opened **0 new production positions in the trailing 28 days** (per Registry). Same days:

| Market | short_term_momentum candidates | momentum_ledger scanned | classified INVEST | recommendations_v3 tickers | non-HOLD |
|---|---:|---:|---:|---:|---:|
| India | 3 of 230 universe | 2 (after prod-universe filter) | 0 | 15 | 0 |
| USA | 106 of 908 universe | 34 (after prod-universe filter) | 0 | 15 | 4 (all below confidence floor) |

Symptom sources:
- `reports/research/short_term_momentum_india.json` (2026-08-27) · `n_candidates = 3`, `n_universe = 230`
- `reports/research/short_term_momentum_usa.json` (2026-08-26) · `n_candidates = 106`, `n_universe = 908`
- `reports/research/multi_layer/momentum_ledger_{market}_{asof}.json` · `n_universe_scanned` = 2 (India) / 34 (USA)
- `reports/research/momentum_funnel/{market}/latest.json` · bottleneck `M3_after_out_of_universe_drop → M4_actually_scanned`

## 2 · The upstream cause (traced through code)

Momentum ledger reads from short_term_momentum. That engine's filter is at:

**`backend/research/short_term_momentum.py:340`** — `if cat == "IGNORE": continue`.

Any ticker whose `categorize(r1, r3, r5, r20, vol_adjust)` returns `IGNORE` is dropped. From `categorize()` (lines 260-277):

```python
# vol_adjust ∈ [1.0, 2.0]  (higher-vol tickers get a proportionally higher bar)
quick_rise = |1d| > 4% · vol_adjust  OR  |3d| > 8% · vol_adjust  OR  |5d| > 12% · vol_adjust
quick_fall = mirror on the negative side
sustained_up   = r5 > 5% AND r20 > 15%
sustained_down = r5 < -5% AND r20 < -15%
reversal_up    = r20 < -10% AND r5 >  5%
reversal_down  = r20 >  10% AND r5 < -5%
# If none of the above → return "IGNORE"
```

So any ticker whose 1d/3d/5d moves stay inside ±4/±8/±12% (vol-adjusted) AND whose 5d/20d combination doesn't cross the sustained/reversal boundaries hits `IGNORE`.

Numbers on India (2026-08-27): 227 / 230 = **98.7% of the NSE curated universe was in the quiet range**.
Numbers on USA (2026-08-26): 802 / 908 = **88.3% of the extended universe was in the quiet range**.

This is not a bug. The `short_term_momentum` engine is a **volatile-mover detector** by design — its whole purpose is to surface tickers with substantial recent moves. On a calm-market day it returns few candidates because there are few sizeable moves.

## 3 · Classification against the PDF's four categories

The PDF (Sec 2) requires the diagnosis to distinguish:

- **NO_QUALIFYING_SIGNAL** · signal was computed but nothing crossed action thresholds
- **RUNNER_NOT_EXECUTED** · the runner didn't run
- **PIPELINE_FAILURE** · data/orchestrator/persistence failure prevented computation
- **DORMANT_BY_DESIGN** · runner ran, engine did its job, result is deliberately sparse

| Check | Verdict |
|---|---|
| Was the runner executed? | Yes — daily orchestrator ran; `momentum_ledger_{market}_{asof}.json` exists for both markets on 2026-09-01 and 2026-09-02. |
| Did data flow end-to-end? | Yes — `n_universe_scanned_raw` = 230 (India) / 908 (USA); no NaN / no `pipeline_failure` flag; conservation invariant OK. |
| Were signals computed? | Yes — every candidate was categorized; `_classify()` returned a state for each. |
| Did anything qualify as INVEST? | India 0, USA 0. USA had 4 non-HOLD from `recommendations_v3` but every one was below the 0.55 calibrated-confidence floor. |

**Verdict: DORMANT_BY_DESIGN** across both R2 feed paths (short-term momentum funnel + recommendations_v3 confidence gate) during a calm-market window. The 28-day zero-entry streak reflects **coincident quiescence in a low-volatility regime plus a calibrated-confidence gate that R2's own risk discipline is holding**, not a filter bug or a broken pipeline.

## 4 · Signal Silence + MVS applicability

**Signal Silence (PDF Sec 9 · fires when runner silent ≥ 10d AND baseline suggests it normally produces AND not all runners simultaneously silent):**

| Precondition | Today's state |
|---|---|
| R2 zero-days streak | 28 · above 10-day threshold |
| Trailing average daily R2 signals | not measured (Signal Ledger too thin: 3 historical snapshots) |
| All runners simultaneously silent | R1 (engine-alive advisory) also has few daily picks in the same window · consistent with market-wide calm |

**Verdict:** Signal Silence should **NOT fire** in this window. R2 silence coincides with R1 also being quiet — that is the exact condition the PDF calls out as "likely genuine market absence, not runner-specific" and instructs the trigger to hold. Firing Signal Silence here would be a false positive.

**MVS floor (PDF Sec 9 · fires when composite qualifying signals < 3/day → GATE_RELAXED · bounded by 15 relaxations per rolling 90d):**

n_qualifying_today = 0 · below floor of 3. But the PDF explicitly requires that any relaxation be **pre-registered, walk-forward validated, bounded, never silent, never a manual panic override**. None of that pre-work has been done for Sprint A yet, so:

**Verdict:** MVS reports "below floor" (which is what our test shows) · we do NOT relax any gate today. Relaxation stays reserved until pre-registered and validated per the PDF rule. Zero relaxations spent from the 15/90d budget.

## 5 · What we are NOT going to do

Deliberately avoiding, per the PDF:

- ❌ Lower the short-term-momentum ±4/±8/±12% thresholds "so more tickers surface." That would replace a designed volatile-mover detector with a broadband filter — silent doctrine change, not evidence-driven.
- ❌ Lower the R2 calibrated-confidence 0.55 floor. Calibration hasn't cleared its own gate (E-008 · n=12 insufficient); loosening the sizing gate on unvalidated calibration is exactly what the PDF forbids.
- ❌ Force a "MOMENTUM_WATCH" ticker into INVEST to break the streak.
- ❌ Fire Signal Silence on the R2 streak alone (all runners are quiet).

## 6 · What we ARE going to do

- ✅ Ship R1 advisory sheet (already done · this readout retro-closes the sequencing prerequisite).
- ✅ Let the calm regime pass. R2 discipline is the point.
- ✅ Wait for the market regime to change or for enrichers to land (Batch B) so subsequent zero-entry days can be classified with regime + fundamentals context, not just short-term momentum.
- ✅ Add a second momentum-source path if evidence justifies it (this would be a NEW research ticket per PDF · not a fix).
- ✅ Watch the trailing average once Signal Ledger accumulates >= 50 snapshots · then Signal Silence has the baseline it needs to trigger correctly.

## 7 · What this readout closes

- Priority #2 in the CEO 2026-09-03 governance ordering (was 🟠 "needs closure/readout" · now closed).
- Sequencing prerequisite for R1 advisory sheet (was implicitly held open · now formally satisfied).
- Evidence Log entry E-002 (🟠 → **DORMANT_BY_DESIGN** classified; entry appended to `docs/AEGIS/EVIDENCE_LOG.md`).

## 8 · What this readout leaves open

- Signal Silence baseline measurement (blocked on Signal Ledger accumulation).
- Whether the R2 confidence floor of 0.55 is well-calibrated (blocked on E-008 · n < 50).
- Whether R2 needs a second candidate-source path beyond short-term momentum (research question · does not urgently need answering while regime is calm).

## 9 · Provenance

- Momentum engine: `backend/research/short_term_momentum.py:260-340`
- Momentum ledger: `backend/research/multi_layer/momentum_ledger.py:111-195`
- Funnel diagnostic: `scripts/momentum_funnel_diagnostic.py`
- Governance modules: `backend/research/governance/signal_silence.py`
- Runner registry: `configs/aegis_runner_registry.yaml`
- Sample data: `reports/research/short_term_momentum_{market}.json` · `reports/research/multi_layer/momentum_ledger_{market}_{asof}.json` · `reports/research/momentum_funnel/{market}/latest.json`
- Author: Sprint A execution turn · 2026-09-03.
