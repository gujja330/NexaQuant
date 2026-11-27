# AEGIS dynamic trading plan — picks, profits, trailing stops, AI

2026-11-27 · status: **PROPOSED** (nothing below is built unless stated)

## Goal

One dynamic system rather than separate fixes:

- which stocks to buy (picks)
- where to book profit (targets)
- how to protect gains and limit losses (trailing profits and stops)
- how long to hold

All four should adapt to each stock, each market and each regime, and every
rule must earn its place on held-out evidence before it touches production.

## The binding constraint is evidence, not models

| finding | source |
|---|---|
| "The binding constraint is DATES, not models" | R3 AI programme, frozen 2026-09-08 |
| Severe-loss meta-label REJECTED in both markets (BH-FDR 0/24) | PIT replay closure, 2026-09-15 |
| AEGIS's own history ≈ 20 USA / 47 India mature entry dates | exit replay, 2026-11-26 |
| 5–6 years of price bars ≈ 740 USA / 1,013 India entry dates | exit robustness study, 2026-11-26 |

An AI model trained on AEGIS's own few months of history would fail the way
the meta-label did. The years of price bars are the way out, but replaying
R2's own picks that far back needs point-in-time features, which runs into a
known defect (Phase 0).

## Phase 0 — Evidence substrate (unlocks every later phase)

**Problem.** The recorded CANON substrate defects, diagnosed at `9c360992` and
left unfixed pending a CEO decision:

- `tail()` applied before `cutoff` shrinks historical windows to 0 bars at
  six months back.
- `sma_200` is 0% populated.

This is why every R3 historical wave reported INSUFFICIENT HISTORY. It will be
verified against current code before any fix.

**Work.**

1. Fix the window ordering.
2. Backfill point-in-time feature snapshots over the full bar history.
3. Make R2's picks replayable across 5+ years.

**Gate.** A replay-twice-identical determinism check, plus a leak test (no
feature reads a bar after its date).

**Lock:** a data fix, so it falls within Sprint M scope.

## Phase 1 — Dynamic exits (BUILT, advisory)

Already in place:

- Volatility-scaled stop, target and time barrier per stock.
- Self-calibrating every 5 days inside `aegis_run_all.py`.
- USA on (held-out SUPPORTED), India off (NOT SUPPORTED).
- Profit booking: book all at target. A split was tested on 121k episodes
  and the pre-registered rule rejected it.

Remaining:

- **Enforcement decision for USA.** Needs `override the sprint m lock`.
- **Market-specific regime hold.** The robustness study found USA rewards
  holding after selloffs and in chop, India in uptrends. Test it held-out on
  the 5-year sample before any adoption.

## Phase 2 — Dynamic trailing stops and profits (one engine)

**Today.** Three mechanisms disagree with each other:

- `dynamic_risk_v2` stops, ratcheting only in India. USA ratcheting was
  rejected on 2026-09-11 on about 6 effective date units.
- The new advisory barriers.
- `apply_dynamic_exits`, which made 154 decisions and enforced 0.

**Work.** One position-management engine, applied per stock:

1. Volatility-scaled initial stop.
2. Ratcheting trail after a profit threshold.
3. Chandelier trail from the post-entry high.
4. Time barrier.

**Gate.** Re-test the USA ratchet decision on 740 entry dates instead of 6.
Keep it only if it holds out-of-sample in at least 3 of 5 blocks with no worse
per-date return.

**Lock:** stop policy, so it needs explicit approval per market.

## Phase 3 — Dynamic stock picks

The leads already in the data:

| lead | evidence | status |
|---|---|---|
| **Re-entries underperform** | USA RE-ENTRY 20-day win rate 28.3% (n=174) vs NEW 56.5%, profit factor 1.16 (n=210); 13 of 14 USA admissions on 2026-11-26 were re-entries | from the pipeline's own outcome log; rows, not yet date-units |
| **Confidence is not calibrated** | USA median entry confidence 52.6, realized win rate 41.2%, profit factor 0.93 on 245 closed | per-market scales, not comparable |
| **Rotation is not wired** | `capital_rotation` reports `n_positions=0` | a bug; Sprint M scope |

Work, in order:

1. **Re-entry evidence.** Measure the re-entry gap in entry-date units on the
   5-year replay. If it holds, add a re-entry filter or cooldown.
2. **Confidence calibration.** Fit per market on held-out dates, so a number
   means a win probability.
3. **Wire `capital_rotation`.** Point it at real held positions, so freed
   capital moves to the best unheld candidate.
4. **Regime-aware selection.** Test whether ranking weights should differ by
   market breadth regime.

## Phase 4 — AI, where it can actually help

Under the existing architecture rule ("AI explains and validates, never
computes or recommends on its own authority"):

| use | why it can work now | gate |
|---|---|---|
| **Meta-labeling on R2 picks** (take, skip, size) | Rejected on ~20–50 dates; retest on the 5-year PIT replay from Phase 0 | effective-sample gate in date units, BH-FDR, held-out blocks |
| **Regime classifier** (clustering or HMM on breadth, volatility, trend) | Feeds the market-specific hold in Phase 1 | must beat the simple breadth rule held-out |
| **Exit-event explainer** | Plain-language reason for each flag in the workbook | never changes a number |
| **Anomaly review** | Flags outliers such as gap losses and fossil artifacts before delivery | advisory only |

Not planned: reinforcement learning or autonomous trading, already deferred
in the research roadmap.

**Lock:** the R3 AI programme is frozen, "no new AI architecture search".
Restarting it needs the CEO's explicit decision. Phase 0 is what makes a
restart worth doing.

## Order and decisions needed

| # | phase | can start now? | needs |
|---|---|---|---|
| 0 | evidence substrate | yes, data fix | verify the defect is still present |
| 3.3 | wire capital_rotation | yes, bug fix | — |
| 1 | USA exit enforcement | after the CEO says so | `override the sprint m lock` |
| 3.1 | re-entry evidence | after Phase 0 | — |
| 2 | unified trailing engine | after Phase 0 | stop-policy approval per market |
| 3.2, 3.4 | calibration, regime selection | after Phase 0 | — |
| 4 | AI layer | after Phase 0 | lift the R3 freeze |

Every phase ends with a pre-registered held-out test, written before its
results are seen, and both markets ship together.
