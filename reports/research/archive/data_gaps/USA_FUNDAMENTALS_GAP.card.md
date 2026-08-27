# USA Fundamentals Coverage Gap

**Status:** data_gaps · **Route:** archive/data_gaps

- **Hypothesis:** USA fundamentals studies cannot be measured because parquet is empty (0/908 universe · 0/498 daily-preds).
- **Data source:** `usa/data/raw/us/fundamentals.parquet`
- **Result:** BLOCKED · zero coverage.
- **Sample size:** 0.
- **Status reason:** requires yfinance batch pull for S&P 500.
- **Revisit condition:** USA fundamentals coverage >= 95% of daily-pred set.
- **Plan:** see FUNDAMENTALS_GAP_PLAN.md.
