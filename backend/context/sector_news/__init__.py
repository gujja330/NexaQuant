"""Sector news classifier · derives per-sector sentiment from divergence
between a sector's average return and the market's average return.

When most of the market is up but IT is down > 1%, that's negative sector-
specific news even if we can't parse the actual headlines. Cheap proxy ·
zero new data source · Phase 2A extends with real NLP.
"""
