# WORKED_LEGACY Remediation Queue · Scheduling View

*Sole source of truth for state: 13-stage Coverage Tracker + STP verdicts.*
*This file only adds work-ordering metadata · never a second state machine.*

**Rule:** Substrate Before Sophistication (locked 2026-09-04). Items with
priority 90-98 are blocked by that rule · will not be scheduled until
their upstream substrate reaches `Tested` stage.

## Schedulable · lowest-effort/highest-information first

| Priority | ID | Runner | Category | Name | Upstream substrate | Next STP action |
|---:|---|---|---|---|---|---|
| 1 | `P1` | R2 | P1 | Confidence Calibration on Delivered Output | CAL-HISTORY-4W | Weekly refit monitoring · re-run STP T4 after 4 consecutive weekly Platt refits (CEO-authorized P1 exemption) |
| 2 | `F01-05-OOS` | FUNDAMENTALS | F01-05 | F01-05 OOS ticker-partition | FUND-ACCUM | Move to temporal OOS (not ticker-OOS) once PIT history ≥ 60d |
| 3 | `F01-05-COMP` | FUNDAMENTALS | F01-05 | F01-05 Composite (Piotroski + FCF + IntCov − Beneish) | FUND-ACCUM | Re-run STP once fundamentals_history has 8+ quarters PIT |
| 4 | `F01-05-GRID` | FUNDAMENTALS | F01-05 | F01-05 Filter Grid (11 threshold variants) | FUND-ACCUM | Re-run STP once accumulator has multi-quarter PIT history |
| 5 | `P0` | R2 | P0 | Dynamic Exit Bridge · retrospective replay | — | Re-run counterfactual replay through STP · n=539 exceeds validation-candidate tier |
| 6 | `II.4-PIOT` | R3 | II.4 | Piotroski F-score | — | Already Tested in F01-05 · confirm coverage_tracker stage |
| 7 | `II.4-BENE` | R3 | II.4 | Beneish M-score | — | Same · already in F01-05 filter grid · confirm tracker |
| 8 | `P5.4` | R2 | P5 | PIT universe audit | — | STP T3 one-time · check whether prior metrics need footnoted corrections |
| 10 | `R1.5.3` | R1 | KG-filter | KG-community rolling group filter | D13-KG | STP T3+T4 backtest vs static-sector baseline · needs KG history depth |
| 12 | `P5.5` | R2 | P5 | Standing post-R1 fixed comparator | — | Wire baseline · continuous paper-run · no STP required (comparator not candidate) |
| 15 | `R1.2` | R1 | Perf-analysis | R1 real 25-trade performance analysis | — | Re-run when n_R1_closed ≥ 50 (currently 25) |
| 18 | `II.1-GBM` | R3 | II.1 | GBM primary model family | — | STP T3+T4 · baseline-replicate gate first · then live shadow |
| 20 | `R1.1` | R1 | Self-analysis | R1 engine self-analysis · 3 candidate models | — | STP T1+T2 only · self-analysis is diagnostic not predictive |
| 22 | `II.5-REV` | R3 | II.5 | Analyst estimate revision momentum | — | STP T3+T4 · already Populated · needs predictiveness test |
| 25 | `P5.1` | R2 | P5 | Ensemble disagreement display + sizing | — | STP T3+T4 · disagreement vs actual-return-error correlation |
| 28 | `II.6-MH` | R3 | II.6 | Multi-horizon consensus | II.1-GBM | Requires GBM 5d and 17d model instances · Tier 1 after GBM Tested |
| 30 | `P5.2` | R2 | P5 | Regime-conditional ensemble weights | D07-MACRO | Requires per-regime IC series ≥30 samples per bucket |
| 35 | `P5.3` | R2 | P5 | Daily turnover / rotation cap | — | Simulate historical rotation days with cap · compare realized slippage |
| 45 | `II.4-GOV` | R3 | II.4 | Governance India screen | D11-GOV | Requires SEBI RPT ingest · external data ticket |
| 50 | `II.5-TONE` | R3 | II.5 | Transcript tone Q&A | D12-NARR | Requires transcript ingest external data ticket |

## Blocked by substrate-before-sophistication rule (priority 90-98)

| Priority | ID | Runner | Waiting on | Reason |
|---:|---|---|---|---|
| 90 | `P2` | R2 | D06-CS, FUND-ACCUM | BLOCKED by substrate rule · no work until F01-F05 Tested |
| 90 | `P3` | R2 | F01-05-OOS, D13-KG | BLOCKED by substrate rule · no work until F01-F05 Tested |
| 90 | `P4` | R2 | F01-05-OOS | BLOCKED by substrate rule · no work until F01-F05 Tested |
| 90 | `II.1-STK` | R3 | II.1-GBM, F01-05-OOS | BLOCKED by substrate rule · Tier 2 · wait for GBM+F01-05 Tested |
| 95 | `II.1-GNN` | R3 | D13-KG, II.1-GBM | BLOCKED · 581 nodes small for GNN · deferred by V2 |
| 90 | `II.1-BMA` | R3 | II.1-GBM | BLOCKED by substrate rule · Tier 2 · needs base-model IC series |
| 90 | `II.2-FN` | R3 | F04-VAL, F05-GROWTH | BLOCKED · needs Valuation + Growth Tested |

## Not scheduled (governance / delivery / permanent-reject / diagnostic)

| ID | Runner | Reason |
|---|---|---|
| `R1.7` | R1 | Governance rule · no STP applicable |
| `R1.9-S1` | R1 | Delivery item · STP T5 only · already renders correctly |
| `R1-OPT1` | R1 | Delivery item · STP T5 only · verified this session |
| `R1-BANNER` | R1 | Delivery item · verified this session |
| `R2-USA-PARQUET` | R2 | Data hygiene · verified this session · monitor via freshness check |
| `R2-ZERO-DIAG` | R2 | Diagnostic · no STP · findings folded into Signal Silence Trigger 8 |
| `II.2-PAIR` | R3 | DEFERRED · needs short infrastructure we don't have |
| `II.3-CUSUM` | R3 | REJECT locked · both markets rejected · no re-open without CEO override |
| `FUND-ACCUM` | FUNDAMENTALS | Data pipeline · runs unattended daily · monitored by freshness check |
| `D06-CS` | DOMAIN |  |
| `D06-P2` | DOMAIN |  |
| `D08-FLOWS` | DOMAIN |  |
| `T09-BRK` | DOMAIN |  |
| `D14-RISK` | DOMAIN |  |
| `D15-KELLY` | DOMAIN |  |
| `D16-MAE` | DOMAIN |  |
| `D18-INT` | DOMAIN |  |
| `D19-STAT` | DOMAIN |  |
| `COMP-META` | COMPOSITE |  |
| `COMP-SHEET` | COMPOSITE |  |
| `COMP-ADM` | COMPOSITE |  |
| `LT-COMPOUNDER-01` | STANDALONE |  |
| `STP` | STANDALONE |  |
| `COV-13` | STANDALONE |  |

---

**How the queue shrinks:** as each schedulable item runs through STP,
it acquires a real WORTH verdict (WORTH / CONDITIONAL / NOT_WORTH / BLOCKED)
and moves from WORKED_LEGACY into its evidence-based state in the
recomputed summary. The queue itself is not a state · it is a schedule.