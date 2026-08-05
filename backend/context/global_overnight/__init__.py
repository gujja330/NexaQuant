"""Global overnight signals ingest · Phase 2 prep (2026-08-05).

Answers operator's IT-down question: when NASDAQ moves overnight, we need
to KNOW that BEFORE we recommend Indian IT stocks the next morning.

Fetches from yfinance (FREE) the most recent close vs prior close for:
    · ^GSPC   · S&P 500
    · ^IXIC   · NASDAQ Composite
    · ^DJI    · Dow Jones
    · ^N225   · Nikkei 225 (Japan)
    · ^HSI    · Hang Seng (Hong Kong)
    · ^FTSE   · FTSE 100 (UK)
    · ^GDAXI  · DAX (Germany)
    · ^NSEI   · Nifty 50 (yesterday's close for India · benchmark)

Sector routing: NASDAQ weakness → India IT/Tech gets -X pts context drag.
Nikkei/HSI red → India export-heavy sectors weaken.
DXY strong → India IT gains (dollar earners) · Oil/Aviation weakens.
"""
