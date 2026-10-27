# AEGIS · Evidence-First Recovery Plan
**Opened 2026-10-26 · decision gate 2026-12-31**

## Why this plan exists

Three months of live operation (2026-08-04 → 2026-10-23) produced
**171 closed trades, a 21.6% win rate and −349.5pp realized**. The
decisive finding is not the loss. It is this:

> With **no stop and no target at all**, India's entries still lose and
> still underperform the index — and the gap *widens* with holding
> period (30-day alpha **−1.53%**, beats index **35.9%** of the time).

So this is not an exit-policy problem. The selection has no measured
edge in this regime. An earlier read of "entries work, exits destroy
them" was wrong: it was based on the open book being 62.8% green, which
is survivorship — the losers had already been removed by the stop.

The second finding is structural: **you cannot evaluate a strategy you
keep changing.** Selection has been modified continuously while the
pipeline itself was unreliable, so no clean evidence ever accumulated.
The binding constraint is **date units, not model quality** — 36 India
entry dates, 18 USA, against a 20-date floor.

This plan therefore stops building and starts accumulating.

---

## Evidence base (measured 2026-10-26, all recomputed from prices)

Ledger integrity: **0 of 171 price-recompute mismatches**.

| | India | USA |
|---|---|---|
| Closed trades | 143 | 28 |
| Unique tickers | 98 | 28 |
| Win rate | 18.9% | 35.7% |
| Mean / trade | −2.49% | +0.22% |
| Sum | −355.7pp | +6.2pp |
| Profit factor | 0.21 | 1.09 |
| Entry dates | 36 | 18 |

**Counterfactual — no stop, no target, vs index:**

| Hold | India alpha | India beat | USA alpha | USA beat |
|---|---|---|---|---|
| 10d | +0.22% | 48.2% | −0.59% | 46.0% |
| 20d | −0.23% | 46.5% | −0.09% | 50.2% |
| 30d | **−1.53%** | **35.9%** | **+0.98%** | **59.9%** |

**Root causes identified:**

1. **No selection edge (India).** Underperforms the index with or
   without a stop; decays with horizon.
2. **No re-entry memory.** 25 tickers lost repeatedly; **55 of 116
   losses (47%)** are re-entries into a name that had just stopped out
   (OFSS ×3, ATUL ×3, MARUTI ×3, COALINDIA ×3, OIL ×3).
3. **Confidence score is uninformative and slightly inverted.** All 112
   scored trades below 60; winners averaged **31.4**, losers **33.7**.
4. **Regime-blind sector concentration.** Basic Materials −103.5pp at
   15.6% win; Utilities 0 for 7. Consumer Defensive was the only
   positive sector (+0.4pp, 50% win).
5. **Dead substrate.** 35 engine datasets 28–43 days past a 1-day SLA.

---

## Phase 0 · Stop the bleeding — week of 2026-10-27

**P0.1 · Reclassify India R2 output as advisory**
Delivery, XLSX and Telegram continue unchanged. The picks are relabelled
so they are not read as actionable BUY instructions.

- Acceptance: workbook + Telegram carry an explicit advisory label;
  no change to lifecycle, scoring or counts; delivery tests green.
- **Requires CEO authorization** — this changes operator-visible
  wording, which standing policy forbids doing silently.

**P0.2 · Record the kill criterion**
Written into this document now, before anyone is attached to an outcome.

> By **2026-12-31**, with ≥20 clean date units per market and selection
> frozen: if out-of-sample alpha is not positive at the chosen horizon
> with a beat-index rate **>55%**, the strategy is **retired and rebuilt
> from scratch — not tuned**.

---

## Phase 1 · Three defects with measurable impact — weeks of 2026-10-27 / 11-03

**P1.1 · Re-entry cooldown** *(highest impact per effort)*
Block re-entry into a ticker for N trading days after it exits on a
stop. Addresses 47% of the loss count directly.

- Build as a **shadow filter first**: replay all 143 India trades with
  the cooldown applied and report what it would have removed, at
  N ∈ {5, 10, 20}.
- Acceptance: counterfactual report showing trades suppressed, P&L
  delta, and the date-unit count behind the result. **No production
  wiring until the replay is reviewed.**
- Does NOT touch scoring, ranking or thresholds.

**P1.2 · Revive the 35 dead engine datasets**
Portfolio, risk, learning, feature intelligence, factor library,
execution. Inputs to scoring that have not refreshed in 28–43 days.

- Acceptance: `backend_validation` FAIL count drops from 44/73; every
  non-optional producer reports SUCCESS with a non-empty
  `not_refreshed: []`; `ops_check` verdict improves from CRITICAL.
- Each producer fixed is reported individually with before/after as-of
  dates.

**P1.3 · Clean USA Exit History**
490 `ORPHAN AUTO-CLOSE` rows hide 28 real trades (SMCI +26.08% sits at
row 530 of 566).

- Acceptance: EXIT HISTORY shows realized trades only, or orphans move
  to a separate audit sheet; A23 invariant
  (`REGISTRY_CLOSED − EXIT_HISTORY − ORPHAN_AUDIT == ∅`) still holds;
  delivery tests green.
- **Touches the locked XLSX contract — requires CEO authorization.**

**P1.4 · Fix the cron clock** *(discovered 2026-10-26)*
Crons are set to 00:30 / 01:30 / 02:30 UTC and actually fired at
**05:07 / 06:41 / 07:58** — delayed 4.5–5.5h. The "06:00 IST, three
hours before market open" design does not hold. Today's delivery
happened only because a push triggered a run.

- Acceptance: a documented, reliable firing path that lands before
  market open, or an explicit decision to accept best-effort timing.

---

## Phase 2 · Accumulate, do not build — weeks of 2026-11-10 → 2026-12-22

**SELECTION IS FROZEN FOR THIS ENTIRE PHASE.** No new models, no new
agents, no threshold changes, no architecture work. Every change resets
the evidence clock, which is precisely why three months produced no
verdict.

**P2.1 · Date-unit accumulation**
Run both markets daily in shadow. Track effective date units weekly.

- Target: **≥20 clean date units per market** with frozen selection.
- Weekly one-line report: dates accumulated, dates remaining.

**P2.2 · USA 30-day horizon — the only live candidate**
+0.98% alpha, 59.9% beat rate, median +2.84%, on 18 entry dates.

- Acceptance: re-measured at ≥20 dates with a within-date permutation
  null and a date-block bootstrap. Promote only if it survives both.

**P2.3 · CANON-2 authorization** — **CEO decision, blocks everything**
The only lever that converts existing on-disk history into date depth
without waiting on the calendar. Known substrate defects (`tail()`
before `cutoff` collapsing historical windows; `sma_200` 0% populated)
are diagnosed and deliberately unfixed pending this call.

Without it, Phase 2 is gated purely on calendar time.

---

## Phase 3 · Rebuild selection on evidence — only after Phase 2 clears

Not started until Phase 2 produces a verdict. Ordered by evidence
strength:

**P3.1 · Regime filter.** The single most evidence-supported change:
the model bought falling high-beta cyclicals in a falling market.

**P3.2 · Rebuild or remove the confidence score.** A score that ranks
backwards is worse than no score — it manufactures false conviction.

**P3.3 · Target exit.** `TARGET_EXIT_ENABLED` is built, tested and
shadow-logging at 11 of 20 date units. Revisited only after P2.

---

## Explicitly out of scope

- Adding AI models or agents — six exist; the constraint is dates, not
  intelligence
- Lowering thresholds to generate more trades
- Flipping `TARGET_EXIT_ENABLED` below its evidence floor
- Re-architecting — the architecture is not the problem

---

## Decisions required from the CEO

| # | Decision | Blocks |
|---|---|---|
| 1 | Reclassify India R2 as advisory | P0.1 |
| 2 | Authorize CANON-2 | P2.3, and all date-depth work |
| 3 | Approve XLSX change for orphan rows | P1.3 |
| 4 | Accept the 2026-12-31 kill criterion | the whole plan's credibility |

Items needing no authorization and starting immediately: **P1.1
(shadow replay), P1.2, P1.4.**

---

## Honest caveat

This is three months in **one falling Indian regime**. It is not a
verdict on the strategy for all time. It is the only evidence that
exists, and it says: do not trade India R2 live today, and do not spend
the next three months building on an unmeasured base.

The infrastructure work of 2026-10-20 → 10-26 is what makes this plan
executable — for the first time the pipeline runs, commits its own
verdict, and measures honestly. That is the precondition for every item
above.
