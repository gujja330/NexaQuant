# AEGIS USA — Architecture (Parallel Build)

> A parallel USA market built on the SAME engine as India, via a thin `MarketAdapter`. USA runs in
> **paper mode** only. **Nothing from USA touches India production** (frozen). Designed from day one as a
> **multi-factor** engine — but every factor must earn its weight through the evidence gate, never hardcoded.

## Principle
Same philosophy as India, with USA's richer free data: **price = free, everything calculated or free,
no paid APIs initially, AI on top.** The difference from India's history: USA is architected multi-factor
from the start, so fundamentals/sector/insider/etc. are first-class inputs — each validated before it
influences anything.

## Engine (shared, market-agnostic)
```
MarketAdapter (india | usa)
   → get_market_data · get_universe · get_index · get_sector · get_calendar
        → core/engine.py:  low-vol selection · sector cap · HRP weighting · regime exposure
        → [ future: multi-factor ranking, gated ]
            → paper recommendations  (USA)  /  production  (India, frozen)
```
- `core/market_adapter.py` — `IndiaAdapter` (wraps frozen code) · `USAAdapter` (yfinance, ^GSPC, ^VIX).
- `core/engine.py` — the market-neutral core (done; USA paper baseline live).

## Target multi-factor design (each factor gated before it counts)
```
Technicals · Fundamentals · Macro · Sector strength · Earnings · Insider · ETF flows · News · Hist. evidence
        → per-factor Information Coefficient + incremental lift (data-layer gate)
        → meta-ranking with weights LEARNED via research (not hardcoded)
        → portfolio construction → evidence/registry → daily workbook
```

## Free data stack (no paid APIs initially)
| Layer | Source (free) | Notes |
|-------|---------------|-------|
| Price / OHLCV | yfinance (Stooq/AlphaVantage backup) | daily, same as India |
| Technicals | computed (pandas/numpy/ta) | EMA/RSI/ATR/ADX/Bollinger/200-DMA/52w |
| Fundamentals | **SEC EDGAR CompanyFacts API** | official, point-in-time, no scraping |
| Earnings | SEC + Finnhub free / Nasdaq calendar | surprise, estimates, actuals |
| Insider | **SEC Form 4** | CEO/director/insider buys & sells, daily |
| ETF holdings/flows | issuer holdings files | SPY/QQQ/XLK… sector & name demand |
| Institutional | **13F filings** | quarterly (PIT-lagged) |
| Short interest | exchange/FINRA | short float, days-to-cover |
| Options | yfinance | put/call, IV, OI (optional) |
| Sector strength | computed | 20D/50D/200D, breadth, momentum, rel-strength |
| Macro | **FRED API** | rates, CPI, PPI, GDP, unemployment, yield curve |
| Volatility / Dollar / Bonds | yfinance (^VIX, DXY, ^TNX) | regime inputs |
| News | RSS (Reuters/MarketWatch/Benzinga) + SEC | collect first; LLM summarize later |
| Sentiment | Reddit (WSB/stocks), Google Trends (pytrends) | research signal |
| AI earnings summary | LLM over filings | the genuinely useful LLM use |

## Roadmap (one factor at a time, each through the gate)
| Phase | Feature | State |
|-------|---------|-------|
| 1 | Price + Technicals | ✅ adapter + core engine (paper baseline) |
| 2 | Dynamic universe | ⬜ liquidity/market-cap screen (S&P/Nasdaq) |
| 3 | Fundamentals (SEC EDGAR, PIT) | ⬜ gate it |
| 4 | Sector ranking | ⬜ gate it |
| 5 | Insider (Form 4) | ⬜ gate it |
| 6 | Earnings | ⬜ gate it |
| 7 | ETF holdings & flows | ⬜ gate it |
| 8 | Macro (FRED + VIX) | ⬜ gate it (likely regime-level) |
| 9 | News & sentiment | ⬜ gate it |
| 10 | AI meta-ranking | ⬜ only after factors are kept |

## Discipline (non-negotiable)
- **USA is paper-only** until it has its own validated, forward-tested track record.
- **No factor is hardcoded** into the ranking — it enters the same `data_layer_gate.py` (IC · lift ·
  walk-forward · DSR), and the meta-ranker's weights are learned, not assumed.
- **Cross-market research is the prize:** a factor that lifts in BOTH India and USA is far stronger
  evidence of a real edge — and proven factors flow back to India via the promotion process.
- **India production stays frozen and uninterrupted.**

## Folder direction (incremental, non-breaking)
`core/` (shared engine + adapters) · `data/raw/usa/` (USA price cache) · `data/usa/` (paper outputs).
The frozen `india/` tree is left in place; a future `markets/` re-layout is optional and done carefully,
never at the cost of destabilising India.
