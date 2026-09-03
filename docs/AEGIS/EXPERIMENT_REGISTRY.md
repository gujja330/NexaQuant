# AEGIS · Experiment Registry

**Per V2 master prompt Section 26 · immutable trial matrix.**
**Every attempted variant recorded · no hidden trials.**
**Evidence Log entries in `docs/AEGIS/EVIDENCE_LOG.md`.**

| Experiment ID | Family | Trial count | PIT | OOS | Stat test | MT correction | Effect size | 95% CI | p | Decision | Evidence |
|---|---|---:|---|---|---|---|---|---|---|---|---|
| P0-original | R2 exit-bridge | 1 | ✓ | pending | paired bootstrap 10k | n_trials=1 | Δ=−0.03% (USA) | [−0.12%, +0.06%] | 0.56 | **FAIL** · preserved forever | E-001 |
| P0-EXTENSION-01 | R2 exit-bridge | 60 (declared) | pending | pending | 10k bootstrap + DSR | n_trials=60 | — | — | — | DECLARED · not run · gated on regime enricher (now landed) | E-001 (linked) |
| R2-EXT-EXIT-DOCTRINE-01 | R2 exit-doctrine | 4 doctrines × TBD | pending | pending | — | separate ticket | — | — | — | DECLARED · additive research | E-001 (linked) |
| P1-calibration | R2 calibration | 1 (weekly refit) | ✓ | ongoing | ECE trend | n_trials=1 | ECE=? | — | — | **INSUFFICIENT_SAMPLE** (n=12<50) · previous calibration retained per PDF | E-008 |
| P2-sector-regime | R2 ranking | 9 (3×3 α×β) | ✓ | naive folds (not WF) | paired bootstrap | n_trials=9 | best (α=0, β=0) zero lift | — | — | **BLOCKED** · regime features 0 everywhere · substrate gap | E-005 |
| P3-KG-γ | R2 KG ranking | 5 (γ grid) | PIT snapshots UNKNOWN | pending | paired bootstrap | n_trials=5 | γ effectively 0 | — | — | **BLOCKED** · no persisted historical community | E-006 |
| P4-cap-sector | R2 interaction | 1 (LR test) | pending | pending | LR test (Wilson-Hilferty) | n_trials=1 | n=0 fit | — | — | **BLOCKED** · cap_bucket null · Investability axis undeclared | E-007 |
| P5.1-disagreement | R2 sizing | 1 | pending | pending | Pearson correlation | n_trials=1 | — | — | — | **INSUFFICIENT_SAMPLE** | — |
| P5.2-regime-weights | R2 ensemble | per regime · min_n=30 | ✓ | pending | — | separate | — | — | — | **INSUFFICIENT_SAMPLE** per regime | — |
| P5.3-turnover-cap | R2 execution | 3 (X ∈ {0.5%, 1%, 2%}) | ✓ | pending | — | n_trials=3 | — | — | — | ILLUSTRATIVE run only | — |
| P5.5-standing-comparator | permanent yardstick | 0 (never optimized) | ✓ | ongoing | — | not applicable | — | — | — | 🟢 PERMANENT | — |
| R3-GBM-baseline | R3 Tier-1 | 1 | pending | 5-fold CV | Brier + AUC + ECE | n_trials=1 | Brier=0.254 · AUC=0.45 · ECE=0.01 · IC≈−0.10 | — | — | **FAIL** on baseline-replicate gate (IC gap 0.10 > tol 0.02) · Tier-2 correctly BLOCKED | E-004 |
| R3-Day30-gate | R3 shadow | 2-of-3 criteria | ✓ | ongoing | Sharpe / Brier / SHAP | not applicable | — | — | — | **INSUFFICIENT_SAMPLE** (5 picks < 20) · Day-30 clock started | E-015 |
| R3-Day60-scorecard | R3 shadow | interim | pending | pending | — | — | — | — | — | pending Day 60 | — |
| R3-Day90-promotion | R3 shadow | final | pending | pending | — | — | — | — | — | pending Day 90 · then CEO auth required | — |
| NEG-PNL-CONTROL-60D | additive R2-exit research | **9** variants (6 static-% + 3 timing) | ✓ | ✓ | 10k paired bootstrap | n_trials=9 · DSR ready | best variant Δ=−0.008% (static_pct@−7%) · every tighter variant SIG WORSE | see E-016 | 0.016 / 0.012 / 0.018 / 0.000 (SIG) | **FAIL** (successful REJECT · no variant improves) | E-016 |
| POS-PNL-CAPTURE-60D | additive winner-capture research | **16** winner definitions (4 horizons × 4 thresholds · PREDECLARED) | ✓ | ✓ | precision/recall/F1 · missed-winner cost | n_trials=16 · DSR ready | precision ~0.011 h5_t5pct · recall 0.000 · 100% of misses = C_FUNNEL_STAGE_MISS | — | — | **FAIL/BLOCKED per definition** · not a threshold-change recommendation | E-017 |
| JOINT-POS-NEG-PNL | additive joint objective (V2 §11) | 9 (NEG) × 16 (POS) · scored per candidate strategy | ✓ | pending | joint capture-vs-damage frontier | n_trials pending strategy | — | — | — | 🟢 substrate shipped this batch · results appended when strategies proposed | E-018 |
| CRASH_DETECTOR_01 | regime detector · additive | pending | pending | pending | — | — | — | — | — | DECLARED | E-009 (linked) |
| RECOVERY_DETECTOR_01 | regime detector · additive | pending | pending | pending | — | — | — | — | — | DECLARED (gates on CRASH_DETECTOR_01) | E-009 (linked) |
| CAP_PIT_STRICT_01 | cap enricher · additive strict PIT | pending | pending | pending | — | — | — | — | — | DECLARED · needs historical shares_outstanding | E-010 (linked) |
| UNIVERSE_EXT_NIFTY200 | India universe · additive | pending | pending | pending | — | — | — | — | — | DECLARED · needs authoritative NIFTY 200 source | E-014 (linked) |
| MIDCAP400_EXT | USA universe · additive | pending | pending | pending | — | — | — | — | — | DECLARED per V2 §4 (S&P MidCap 400 not currently sourced) | — |
| WINNER_GENOME_FULL | POS-PNL genome extension | pending | pending | pending | — | — | — | — | — | DECLARED · unblocks on B6 fundamentals batch | E-017 (linked) |
| RELATED_PARTY_TXN_SIGNAL | Fundamentals L5 · India · additive | pending | — | — | — | — | — | — | — | REQUIRES NEW SOURCE (NSE SAST scraper) | — |
| TRANSCRIPT_TONE_SIGNAL | Fundamentals L5 · additive | pending | — | — | — | — | — | — | — | REQUIRES NEW SOURCE · Q&A must be SEPARATE from prepared remarks per V2 §5 | — |
| CUSUM_REGIME_SUPPLEMENT | Regime · Tier-3 research (V2 §7) | pending | pending | pending | leading-indicator test vs classifier transitions | — | — | — | — | DECLARED · never replaces classifier | — |

## Totals

- **Live experiments:** 12
- **Declared additive extensions:** 12
- **Total trials counted for deflation:** P0=1 · P0-ext=60 (when run) · P1=1 · P2=9 · P3=5 · P4=1 · P5.1=1 · P5.2 per regime · P5.3=3 · P5.5=0 · R3_GBM=1 · NEG-PNL=9 · POS-PNL=16 → currently ~47 trials counted · deflation math kept in individual entries.

## Additions · 2026-09-03 late-day (V2 §26 experiment registry updates)

| Experiment ID | Family | Trial count | PIT | OOS | Stat test | MT correction | Decision | Evidence |
|---|---|---:|---|---|---|---|---|---|
| JOINT-PARETO-USA | joint pos+neg (V2 §11) | 9 NEG × 1 POS-def = 9 pairs | ✓ | naive | 4-axis dominance | n_trials=9 | **REJECT** all frontier candidates (frontier=1 · null-action strategy) | E-018 |
| PAPER-COMPARATOR-DAILY-TICK | forward validation (V2 §27) | ongoing daily | ✓ | forward | tracking only | not applicable | **KEEP** · accumulate | E-019 |
| R1-ATTRIBUTION-EARLYWARN | R1 vs R2 diagnostic (V2 §18) | 1 | ✓ | not applicable | early-warning count | n_trials=1 | **BLOCKED** · R1 daily archive gap | E-020 |
| FUNDAMENTALS-SMOKE-INDIA-TOP10 | substrate priming (V2 §5) | 1 batch (synthetic) | not PIT · flagged | not applicable | not applicable | not applicable | **not a research result** · substrate priming only · genuine PIT batch pending | E-021 |
| FINAL-28-REPORT-AGGREGATION | governance (V2 §37) | 1 | ✓ | not applicable | not applicable | not applicable | **KEEP** · rebuild each cycle | E-022 |

## Governance rules preserved

- No experiment overwrites another.
- Every variant tried counts as a trial · silent trial inflation is a V2 violation.
- Deflated Sharpe deflation applied per experiment family, not globally.
- REJECT is a valid successful research outcome (E-016 and E-017 both reported REJECT).
- Additive extensions are declared, dated, and gated on named substrate before running.
- No production change flows from any 🔴 or 🟠 result.
