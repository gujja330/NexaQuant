"""FII/DII flow ingest · fills reports/fii_dii_flow.json daily.

Source: NSE published daily FII/DII activity (free · exchange bulletin).
Fallback: derive proxy from institutional-holdings deltas when NSE feed
is unavailable.

Zero paid vendor cost.
"""
