# AEGIS Governance Rule · Substrate Before Sophistication

**Locked:** 2026-09-04 by CEO
**Governance tier:** STANDING RULE · not one-off correction
**Precedent:** This is the same lesson learned repeatedly · v3.1 institutional-intelligence expansion, 20-folders-vs-20-programs, and now Tier 2/3 R3 techniques ahead of fundamentals substrate. Codified here so it stops being re-argued.

---

## The rule

**No Tier 2/3 R3 technique and no new R2 P-item gets scheduled work while any F0X domain feeding it has not reached a real historical-sample `Tested` stage in the 13-stage Coverage Tracker.**

Mechanical priority ordering. Not a judgment call. Not a debate.

## What "feeding it" means (dependency map)

| Sophistication item | Depends on substrate at Tested stage |
|---|---|
| R3 II.1 Stacking (Tier 2) | F01+F02+F03 (Quality + Balance + Accounting) |
| R3 II.1 GNN (Tier 2/3) | D13 KG communities (mature) + F01 (quality features) |
| R3 II.1 BMA (Tier 2) | Any base-model IC series that exists at Tested |
| R3 II.2 Factor-neutral (Tier 2) | F04 (Valuation) + F05 (Growth) |
| R3 II.4 Governance India (Tier 2) | D11 governance data at Tested |
| R3 II.5 Transcript tone (Tier 2) | D12 narrative-signal data at Tested |
| R2 P3 KG Community-Relative | F01-F05 at Tested + D13 at Tested |
| R2 P4 Cap × Sector | F01-F05 at Tested + realized-outcome dataset at Tested |
| R2 P5.2 Regime-conditional weights | Per-regime IC data at Tested (each regime bucket ≥30 samples) |

## What Tested means

Per 13-stage Coverage Tracker · `Tested` requires:
- Feature computed on real data (both markets)
- Cross-sectional or temporal test executed
- Result JSON emitted under `reports/research/`
- DSR-deflated where multiple variants tested

## Enforcement

- Every research candidate proposal must cite which substrate-items feed it AND their current Coverage-Tracker stage before work is scheduled.
- STP T1 must fail if the candidate depends on a substrate item still at `PIT-ready` or earlier.
- Only exception · candidate is itself a substrate item OR is a data-pipeline unblocker.

## Consequences of violating the rule

Every past violation produced the same failure class:
- Complex technique built on missing substrate → NOT_WORTH verdict after work is sunk
- OR technique passes on partial substrate → false-positive PROMOTE that fails silently at production time

## Concrete implication as of 2026-09-04

- P3, P4, R3 Tier 2/3 · **BLOCKED** by this rule until F01-F05 reaches `Tested` (currently `Populated` for most sub-signals · waiting for accumulator PIT history).
- P1 (Confidence Calibration) · exempt · it operates on delivered R2 confidence numbers, not on unbuilt substrate.
- P2 (Sector/Regime Ranking) · already ran through STP · NOT_WORTH · no follow-up until D06 sub-signals mature.
- P5 items · same rule · check dependency before scheduling.

## Amendment

This rule can only be lifted by verbatim CEO override · "override the substrate-before-sophistication rule". It replaces any prior instruction that scheduled sophistication work while substrate was thin.
