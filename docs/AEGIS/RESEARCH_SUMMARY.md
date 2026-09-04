# AEGIS R1/R2/R3 Research Summary · Mechanically Recomputed

*Recomputed: 2026-09-04 · single source: `backend/research/research_registry.py`*

**Total items in registry:** 51

## Grand totals (mechanical · sums equal total)

| State | Count |
|---|---:|
| WORKED_LEGACY | 31 |
| PENDING | 11 |
| REJECTED | 7 |
| CONDITIONAL | 1 |
| BLOCKED | 1 |
| **Sum** | **51** |
| Reconciles? | **✅ YES** |

## Per runner

| Runner | BLOCKED | CONDITIONAL | PENDING | REJECTED | WORKED_LEGACY | Total |
|---|---:|---:|---:|---:|---:|---:|
| COMPOSITE | 0 | 0 | 0 | 0 | 3 | **3** |
| DOMAIN | 0 | 0 | 0 | 3 | 6 | **9** |
| FUNDAMENTALS | 0 | 0 | 0 | 3 | 1 | **4** |
| R1 | 0 | 0 | 0 | 0 | 7 | **7** |
| R2 | 0 | 1 | 7 | 0 | 4 | **12** |
| R3 | 0 | 0 | 4 | 1 | 8 | **13** |
| STANDALONE | 1 | 0 | 0 | 0 | 2 | **3** |

## STP verdict → 13-stage Coverage Tracker mapping (single vocabulary)

| STP verdict | 13-stage equivalent |
|---|---|
| WORTH | Corrected |
| CONDITIONAL | OOS |
| NOT_WORTH | Tested |
| BLOCKED | Data-required |

## Per-item detail (compact)

| ID | Runner | Category | Name | State |
|---|---|---|---|---|
| R1.1 | R1 | Self-analysis | R1 engine self-analysis · 3 candidate models | **WORKED_LEGACY** |
| R1.2 | R1 | Perf-analysis | R1 real 25-trade performance analysis | **WORKED_LEGACY** |
| R1.5.3 | R1 | KG-filter | KG-community rolling group filter | **WORKED_LEGACY** |
| R1.7 | R1 | Governance | 8th Research Trigger · Signal Silence | **WORKED_LEGACY** |
| R1.9-S1 | R1 | Delivery | R1 advisory sheet 05_R1_Advisory | **WORKED_LEGACY** |
| R1-OPT1 | R1 | Delivery | R1 rows in 01_Investments ACTIVE section | **WORKED_LEGACY** |
| R1-BANNER | R1 | Delivery | R1 no-dynamic-exit-protection banner | **WORKED_LEGACY** |
| P0 | R2 | P0 | Dynamic Exit Bridge · retrospective replay | **WORKED_LEGACY** |
| P1 | R2 | P1 | Confidence Calibration on Delivered Output | **CONDITIONAL** |
| P2 | R2 | P2 | Sector/Regime-Adjusted Ranking | **PENDING** |
| P3 | R2 | P3 | KG Community-Relative Scoring | **PENDING** |
| P4 | R2 | P4 | Cap × Sector Interaction Study | **PENDING** |
| P5.1 | R2 | P5 | Ensemble disagreement display + sizing | **PENDING** |
| P5.2 | R2 | P5 | Regime-conditional ensemble weights | **PENDING** |
| P5.3 | R2 | P5 | Daily turnover / rotation cap | **PENDING** |
| P5.4 | R2 | P5 | PIT universe audit | **WORKED_LEGACY** |
| P5.5 | R2 | P5 | Standing post-R1 fixed comparator | **PENDING** |
| R2-USA-PARQUET | R2 | Data | USA price parquet drift root fix | **WORKED_LEGACY** |
| R2-ZERO-DIAG | R2 | Diagnostic | R2 zero-entry diagnosis | **WORKED_LEGACY** |
| II.1-GBM | R3 | II.1 | GBM primary model family | **WORKED_LEGACY** |
| II.1-STK | R3 | II.1 | Ensemble stacking | **PENDING** |
| II.1-GNN | R3 | II.1 | GraphSAGE on KG | **PENDING** |
| II.1-BMA | R3 | II.1 | Bayesian model averaging | **PENDING** |
| II.2-FN | R3 | II.2 | Factor-neutral scoring | **WORKED_LEGACY** |
| II.2-PAIR | R3 | II.2 | Peer-pair statistical arbitrage | **PENDING** |
| II.3-CUSUM | R3 | II.3 | CUSUM change-point detection | **REJECTED** |
| II.4-PIOT | R3 | II.4 | Piotroski F-score | **WORKED_LEGACY** |
| II.4-BENE | R3 | II.4 | Beneish M-score | **WORKED_LEGACY** |
| II.4-GOV | R3 | II.4 | Governance India screen | **WORKED_LEGACY** |
| II.5-REV | R3 | II.5 | Analyst estimate revision momentum | **WORKED_LEGACY** |
| II.5-TONE | R3 | II.5 | Transcript tone Q&A | **WORKED_LEGACY** |
| II.6-MH | R3 | II.6 | Multi-horizon consensus | **WORKED_LEGACY** |
| F01-05-COMP | FUNDAMENTALS | F01-05 | F01-05 Composite (Piotroski + FCF + IntCov − Beneish) | **REJECTED** |
| F01-05-GRID | FUNDAMENTALS | F01-05 | F01-05 Filter Grid (11 threshold variants) | **REJECTED** |
| F01-05-OOS | FUNDAMENTALS | F01-05 | F01-05 OOS ticker-partition | **REJECTED** |
| FUND-ACCUM | FUNDAMENTALS | F01-05 | Fundamentals daily PIT accumulator | **WORKED_LEGACY** |
| D06-CS | DOMAIN | D06 | D06 Sector momentum cross-sectional rank | **WORKED_LEGACY** |
| D06-P2 | DOMAIN | D06 | D06 P2 Regime Ranking backtest | **REJECTED** |
| D08-FLOWS | DOMAIN | D08 | D08 Flows walk-forward (volume-spike) | **REJECTED** |
| T09-BRK | DOMAIN | T09 | T09 Deep Technical breakout quality | **REJECTED** |
| D14-RISK | DOMAIN | D14 | D14 Risk correlation + tail VaR + HHI | **WORKED_LEGACY** |
| D15-KELLY | DOMAIN | D15 | D15 Portfolio fractional Kelly | **WORKED_LEGACY** |
| D16-MAE | DOMAIN | D16 | D16 Exit Science MAE/MFE | **WORKED_LEGACY** |
| D18-INT | DOMAIN | D18 | D18 Data Integrity audit | **WORKED_LEGACY** |
| D19-STAT | DOMAIN | D19 | D19 Statistical Robustness compliance | **WORKED_LEGACY** |
| COMP-META | COMPOSITE | META | Meta-ensemble composite score | **WORKED_LEGACY** |
| COMP-SHEET | COMPOSITE | META | 06_Composite_Signals sheet | **WORKED_LEGACY** |
| COMP-ADM | COMPOSITE | META | Trust_Weight=0 admission gate | **WORKED_LEGACY** |
| LT-COMPOUNDER-01 | STANDALONE | Part C | Compounder Watchlist · Winner/Failure Genome | **BLOCKED** |
| STP | STANDALONE | Framework | Standard Testing Pattern (STP) | **WORKED_LEGACY** |
| COV-13 | STANDALONE | Framework | 13-stage Coverage Tracker | **WORKED_LEGACY** |