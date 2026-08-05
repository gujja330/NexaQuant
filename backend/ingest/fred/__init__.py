"""FRED · Federal Reserve Economic Data ingest.

Sprint F · ships 2026-08-05. 800k+ economic time series from the Federal
Reserve Bank of St Louis. FREE public API · no key required for CSV
downloads at https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES}

We ingest a curated set of high-impact series that feed the CIL macro +
bond + currency + commodity adapters with authoritative source data
(vs today's yfinance proxies).
"""
