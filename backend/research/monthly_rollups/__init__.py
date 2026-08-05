"""Monthly rollup reports · R006 Phase 9 · ChatGPT Module C partial ship.

Three reports per market · every month · produced automatically by daily
orchestrator (last-day-of-month or on-demand via CLI):

    · confidence_calibration.py  · predicted confidence bucket vs actual hit rate
    · rotation_accuracy.py       · expected alpha vs realized alpha per rotation
    · feature_attribution.py     · which features correlate with wins vs losses

All three degrade gracefully on sparse data · emit an explicit
`insufficient_data` flag when sample size below minimum · never fabricate
statistics from too-few samples. Reports land in:

    reports/research/monthly/{report}_{market}_{YYYY-MM}.json
    reports/research/monthly/{report}_{market}_{YYYY-MM}.md

Zero coupling to Runner 1 (SEALED) · both markets identical logic.
"""
