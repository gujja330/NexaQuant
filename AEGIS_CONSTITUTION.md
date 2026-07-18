# AEGIS Constitution

**Version:** AEGIS v2.0 · Production Baseline
**Frozen:** 2026-07-18
**Fingerprint:** `e4c070673568c52d…` (MON001 sealed baseline, invariant)

This document defines what may and may not change in AEGIS from
2026-07-18 onward. Every contributor and every automated agent
(including the assistant that wrote much of this codebase) must
consult it before proposing work.

---

## The Freeze

AEGIS's architecture is FROZEN. The 13-step daily orchestrator, the
research engines, the fusion layer, the risk engine, the institutional
memory archive, the winner genome, the decision attribution engine,
the continuous benchmark, the investor dashboard, the validation
sheet, the morning report — all of it stays as it is.

The next milestone is not a code change. It is 30 live trading days of
archived evidence. Then 90 live days. Then, if — and only if — the
evidence supports it, targeted parameter changes.

## The 13 Locked Steps

The daily orchestrator (`scripts/aegis_daily_v2.py`) runs exactly these
steps in this order. No steps may be added or removed:

1. `adaptive_rec_v2` — Confidence rebuild + Precision@K
2. `validation_v2` — Paper harness + drift + opportunity cost
3. `risk_capital_v2` — Position sizing + budget
4. `dna_feedback` — Recommendation DNA v1.5 pattern priors
5. `knowledge_graph` — v1.6 communities + propagation + stress
6. `fusion` — v2.1 Intelligence Fusion (10 dimensions)
7. `stock_validation` — Per-ticker historical rollup
8. `price_context` — CMP + 52W high/low from raw data
9. `decision_center` — v1.0 overnight diff + exit center + watchlist
10. `institutional_memory` — v1.0 archive + lifecycle + missed-opps + rec-history
11. `winner_genome` — Recommendation DNA v2.0 Alpha Signatures
12. `decision_attribution` — v1.0 credit assignment + subsystem creators/destroyers
13. `benchmark` — Continuous Benchmark v1.0 (AEGIS vs NIFTY + synthetic sector)
14. `morning_report` — v1.0 daily HTML + Markdown digest
15. `ops_check` — Operational hardening gate
16. `telegram` — Opt-in delivery (optional)

---

## Allowed

Changes in these categories may be made without evidence review:

- **Bug fixes** — where existing code contradicts its own documented behaviour
- **Parameter tuning** — thresholds inside existing engines (e.g. min_lift,
  min_n, threshold_pct) supported by 30+ archive days of evidence
- **Weight tuning** — `SUBSYSTEM_WEIGHTS` in
  `research/decision_attribution/lib/attribution.py`, supported by 90+ days
  of evidence showing the subsystem is a persistent alpha creator or destroyer
- **UI polish** — presentation improvements that don't add new metrics or
  new interpretive layers
- **Documentation** — this file, `docs/`, docstrings, comments
- **Operational monitoring** — extensions to `aegis_ops_check.py` or the
  Morning Report, provided they are pure aggregation of existing artifacts
- **Tests** — adding regression / schema / smoke tests

## Not Allowed

Changes in these categories are forbidden unless supported by
**90+ days of live archive evidence** AND explicit operator sign-off:

- **New engines** — no new DEV modules, no new subsystems, no new
  scoring layers beyond the 13 locked steps above
- **New scoring systems** — no new dimensions in Fusion beyond the 10
  currently locked (plus the reserved slot for Alpha Signature v2.1)
- **New pipeline steps** — no additions to the orchestrator's step list
- **New architecture** — no new artefact types, no new data-flow shape,
  no new artefact locations
- **New dashboards** — no new SPA routes beyond `/`, `/admin`,
  `/stock/{ticker}`, `/sheet/{ticker}`
- **New AI layers** — no ML models added to the pipeline. The existing
  HistGradientBoosting, personalized PageRank, χ² association mining,
  Platt scaling, and permutation-importance are the only permitted
  learned components
- **Bypassing the fingerprint** — MON001 sealed baseline fingerprint
  `e4c070673568c52d…` is invariant. Any drift = production halt

## Alpha Signature v2.1 — the ONE reserved exception

`Alpha Signature v2.1` is pre-approved to ship after ≥30 live archive
days have accumulated. It is the only additive engine allowed. Its
scope is fixed:

- Mines the Institutional Memory archive (NOT `learning.parquet`)
- Emits `reports/alpha_signatures.json` and enriches Winner Genome
- Adds an 11th dimension `alpha_signature_match` to Fusion (v2.2)
- Adds a "Signature Match" chip to the Decision Card

Anything beyond that scope requires evidence review.

---

## The Constitutional Test

Before writing any code, answer these five questions. If any answer is
"no" or "unclear", **do not build**.

1. **What problem does it solve?**
   If the problem can be described only in terms of the code itself
   ("the metric is scattered", "the abstraction feels weak"), it is not
   a real problem yet.

2. **Can it be solved by aggregating existing data?**
   Nine times out of ten, the answer is yes. If a new metric can be
   computed from existing artifacts, build it as a view (Validation
   Sheet, Morning Report, etc.), not as a new engine.

3. **Will it measurably improve alpha or reliability?**
   Improvement is measured against the Continuous Benchmark, not
   against internal engine scores. If the change cannot articulate a
   testable hypothesis of the form "AEGIS's alpha vs NIFTY over the
   next N days will improve by X%", it is speculation, not
   engineering.

4. **What evidence justifies building it?**
   Pre-LOCK, evidence could come from the historical backtester. Post-
   LOCK, evidence must come from the live archive. Backtester
   findings are treated as hypotheses, not conclusions.

5. **Will it break the fingerprint?**
   Any change that modifies the sealed OPS001/MON001 file set requires
   both operator sign-off and a fingerprint re-computation.

## Operational Cadence

- **Daily:** orchestrator runs, archive grows by one day, morning
  report generated
- **Weekly:** operator reviews decision attribution trends, benchmark
  performance, missed opportunities. No changes to code
- **Monthly:** AEGIS Monthly Evidence Review published (a manual
  document, one per calendar month, in `docs/monthly/`)
- **Day 30:** Alpha Signature v2.1 unlocks (only if evidence supports
  it). See the pre-approved scope above
- **Day 90:** First Evidence Review. Weight adjustments considered.
  Only changes with statistically defensible evidence proceed
- **Day 180+:** Continue operating. Change AEGIS through data, not code

## Rollback

If any operator action results in verifiable evidence damage
(fingerprint drift, orchestrator failure > 3 consecutive days, ops
verdict CRITICAL for > 5 days), the immediate response is to `git
revert` to the last known-good commit, not to patch forward.

---

## Amendment

This Constitution may be amended, but only through a formal amendment
recorded at the bottom of the file with:

- ISO date
- The specific rule being amended
- The evidence base for the amendment (≥ 90 days of archive data)
- The operator's sign-off

The first amendment cannot occur before 2026-10-18 (90 days from
freeze).

---

## Amendment History

_None. Constitution effective 2026-07-18._
