"""NSE bhavcopy · daily equity + F&O archive from NSE India (free).

Sprint F · ships 2026-08-05. Downloads NSE's daily equity bhavcopy which
gives us:
    · every listed stock's OHLCV (authoritative · exchange source)
    · corporate action flags (splits/dividends/bonuses)
    · trading turnover per stock (institutional-level flow signal)

Replaces yfinance's derivative data with source-of-truth exchange data.

URL pattern: https://archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv
"""
