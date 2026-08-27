# Fundamentals Coverage Gap · Closure Plan

_Generated 2026-08-27T09:15:43+00:00_

## INDIA
- Fundamentals parquet: **228** tickers
- Universe: **230** tickers
- Daily-pred coverage: **100.0%**
- Uncovered daily-pred priority tickers: **0**

**Closure sources:**
- India: yfinance batch pull for uncovered NSE symbols (returnOnEquity, profitMargins, earningsGrowth, debtToEquity, trailingPE, priceToBook, quality_score) using .NS suffix
- India: NSE bhavcopy for missing shares outstanding
- USA: yfinance batch pull for uncovered S&P 500 tickers (same schema)
- USA: Compustat quarterly (paid) if free sources insufficient

**Target coverage:** 95% of daily-pred tickers

**Priority ticker list (first 30):**
```
```

## USA
- Fundamentals parquet: **0** tickers
- Universe: **908** tickers
- Daily-pred coverage: **0.0%**
- Uncovered daily-pred priority tickers: **498**

**Closure sources:**
- India: yfinance batch pull for uncovered NSE symbols (returnOnEquity, profitMargins, earningsGrowth, debtToEquity, trailingPE, priceToBook, quality_score) using .NS suffix
- India: NSE bhavcopy for missing shares outstanding
- USA: yfinance batch pull for uncovered S&P 500 tickers (same schema)
- USA: Compustat quarterly (paid) if free sources insufficient

**Target coverage:** 95% of daily-pred tickers

**Priority ticker list (first 30):**
```
  A
  AAPL
  ABBV
  ABNB
  ABT
  ACGL
  ACN
  ADBE
  ADI
  ADM
  ADP
  ADSK
  ADT
  AEE
  AEP
  AES
  AFL
  AIG
  AIZ
  AJG
  ALB
  ALGN
  ALL
  ALLE
  AMAT
  AMCR
  AMD
  AME
  AMGN
  AMP
```


## Contract

- No production changes.
- Data pulls emit into `data/raw/india/fundamentals.parquet` and `usa/data/raw/us/fundamentals.parquet` under existing schema.
- Rerun `mr_fundamentals_gap_check` after each batch.
- Block M2 fundamentals studies until coverage >= 95% on daily-pred set.