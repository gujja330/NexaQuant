# AEGIS Final Certification · Section 18 · 2026-09-01

**Verdict**: `LOCK_CANDIDATE`  (never claims LOCKED · CEO explicit authorization only)

**By status**: {'PASS': 50, 'FAIL': 0, 'WARN': 0, 'BLOCKED': 0}

| Gate | Status | Detail |
|------|--------|--------|
| G01_full_test_suite | PASS | 545 passed · 0 failed · 3 skipped |
| G02_e2e_build_india | PASS | xlsx.asof=2026-09-01 · dated=True |
| G03_e2e_build_usa | PASS | xlsx.asof=2026-09-01 · dated=True |
| G04_canonical_identity_india | PASS | 671 new-format PIDs · 0 legacy |
| G05_registry_canonical_recon_india | PASS | Registry india: 25 ACTIVE · 41 CLOSED-90d |
| G06_portfolio_lifecycle_recon_india | PASS | banner=9 body=9 |
| G07_portfolio_exit_recon_india | PASS | 0 UNEXPLAINED lifecycle collisions (same ticker+runner+entry_date active AND closed) · 0 EXPLAINED overlaps (different e |
| G08_exit_history_recon_india | PASS | 0 Registry-CLOSED tickers not in EH body |
| G13_pnl_reconciliation_india | PASS | 0 UNEXPLAINED dupes (bit-identical) · 56 EXPLAINED dupes (multi-observation same-day) |
| G14_provenance_validation_india | PASS | 50/50 opened rows have Position ID (100.0%) |
| G09_population_counts_india | PASS | HISTORICAL_CLOSED=41 · CURRENT_HOLDING=9 · FRESH_RECOMMENDATION=4 |
| G10_runner_counts_india | PASS | R1(RETIRED_DORMANT·opened=20·active=16) · R2(ACTIVE_PRODUCTION·opened=46·active=9) · COMBINED(ACTIVE_PRODUCTION·opened=6 |
| G11_r1_production_absence_india | PASS | 0 retired-runner rows in Portfolio · retired=['R1'] |
| G12_r2_integrity_india | PASS | status=ACTIVE_PRODUCTION · signals=46 · opened=46 · closed=37 |
| G15_xlsx_structural_india | PASS | all 8 required sheets present |
| G16_visual_inspection_india | PASS | auto-audit PASS · sign-off: visual_signoff_india_2026-09-01.md |
| G17_standard_filename_india | PASS | dated=True byte_match=True · expected=aegis_india_2026-09-01.xlsx |
| G18_three_run_determinism_india | PASS | 3-run data-only hash: 9400f827 / 9400f827 / 9400f827 |
| G19_fabrication_scan_india | PASS | 0 holding rows with LOW/PENDING |
| G22_research_pit_india | PASS | 136 evidence rows · 68 AVAILABLE |
| G04_canonical_identity_usa | PASS | 37 new-format PIDs · 0 legacy |
| G05_registry_canonical_recon_usa | PASS | Registry usa: 18 ACTIVE · 528 CLOSED-90d |
| G06_portfolio_lifecycle_recon_usa | PASS | banner=6 body=6 |
| G07_portfolio_exit_recon_usa | PASS | 0 UNEXPLAINED lifecycle collisions (same ticker+runner+entry_date active AND closed) · 0 EXPLAINED overlaps (different e |
| G08_exit_history_recon_usa | PASS | 2 Registry-CLOSED tickers not in EH body |
| G13_pnl_reconciliation_usa | PASS | 0 UNEXPLAINED dupes (bit-identical) · 0 EXPLAINED dupes (multi-observation same-day) |
| G14_provenance_validation_usa | PASS | 508/508 opened rows have Position ID (100.0%) |
| G09_population_counts_usa | PASS | HISTORICAL_CLOSED=502 · CURRENT_HOLDING=6 |
| G10_runner_counts_usa | PASS | R1(RETIRED_DORMANT·opened=38·active=12) · R2(ACTIVE_PRODUCTION·opened=508·active=6) · COMBINED(ACTIVE_PRODUCTION·opened= |
| G11_r1_production_absence_usa | PASS | 0 retired-runner rows in Portfolio · retired=['R1'] |
| G12_r2_integrity_usa | PASS | status=ACTIVE_PRODUCTION · signals=508 · opened=508 · closed=502 |
| G15_xlsx_structural_usa | PASS | all 8 required sheets present |
| G16_visual_inspection_usa | PASS | auto-audit PASS · sign-off: visual_signoff_usa_2026-09-01.md |
| G17_standard_filename_usa | PASS | dated=True byte_match=True · expected=aegis_usa_2026-09-01.xlsx |
| G18_three_run_determinism_usa | PASS | 3-run data-only hash: d87eee3e / d87eee3e / d87eee3e |
| G19_fabrication_scan_usa | PASS | 0 holding rows with LOW/PENDING |
| G22_research_pit_usa | PASS | 136 evidence rows · 68 AVAILABLE |
| G20_overrideallow_false | PASS | no overrideallow=true |
| G21_locked_layer_diff | PASS | 0 diffs vs fe1fff18 |
| G23_universe_sp500_only | PASS | n=516 label=sp500 range=[480,550] expected=sp500 |
| G24_overlap_classification_india | PASS | 1 overlap tickers · defects=0 · {'LEGITIMATE_DIFFERENT_LIFECYCLE': 0, 'LEGITIMATE_DIFFERENT_RUNNER': 1, 'LEGITIMATE_REEN |
| G25_r1_producer_wide_india | PASS | PROVEN_RETIRED · total_violations=0 · n_producers=6 |
| G26_stress_regime_india | PASS | n_trades=37 · overall_mean_pnl_pct=0.152 · regimes=['UNKNOWN', 'NEUTRAL', 'BEAR', 'BULL'] |
| G27_momentum_conservation_india | PASS | conservation_ok=True · silent_disappearances=0 · universe=230 · by_state={'ACCEPTED': 0, 'WATCH': 0, 'REJECTED': 1, 'NO_ |
| G28_crash_resilience_india | PASS | today_regime=WEAKENING · n_r2_trades_tagged=37 · n_days_classified=1535 |
| G24_overlap_classification_usa | PASS | 0 overlap tickers · defects=0 · {'LEGITIMATE_DIFFERENT_LIFECYCLE': 0, 'LEGITIMATE_DIFFERENT_RUNNER': 0, 'LEGITIMATE_REEN |
| G25_r1_producer_wide_usa | PASS | PROVEN_RETIRED · total_violations=0 · n_producers=6 |
| G26_stress_regime_usa | PASS | n_trades=502 · overall_mean_pnl_pct=0.208 · regimes=['UNKNOWN', 'BULL'] |
| G27_momentum_conservation_usa | PASS | conservation_ok=True · silent_disappearances=0 · universe=908 · by_state={'ACCEPTED': 0, 'WATCH': 4, 'REJECTED': 1, 'NO_ |
| G28_crash_resilience_usa | PASS | today_regime=NORMAL · n_r2_trades_tagged=502 · n_days_classified=1254 |