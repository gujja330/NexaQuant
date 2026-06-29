# AEGIS — Feature Registry

> The research inventory: every feature/signal, where it comes from, which markets use it, and where it
> sits in the discipline (live in production · gated · promoted). A feature is only **Promoted** after it
> beats the frozen baseline through the data-layer gate (IC · lift · walk-forward · DSR · forward paper).
> Generated/maintained alongside `india/ai_lab/experiments.yaml`.

Legend — **Live**: computed today · **Gated**: passed the evidence gate · **Promoted**: in production.

| Feature | Category | Source | Market | Live | Gated | Promoted |
|---------|----------|--------|--------|------|-------|----------|
| Volatility / risk rank | Technical | price | India, USA | Yes | Yes (India) | Yes (India) |
| HRP weighting | Portfolio | price/cov | India, USA | Yes | Yes | Yes (India) |
| Regime exposure (200-DMA + VIX + global) | Macro/Regime | price/index/vix | India, USA | Yes | Yes | Yes (India) |
| Momentum (1M/3M/6M) | Technical | price | India, USA | Yes | tested (no lift) | No |
| Relative strength vs index | Technical | price | India, USA | Yes | tested (no lift) | No |
| 200-DMA / 52-week position | Technical | price | India, USA | Yes | context | No |
| RSI | Technical | price | India, USA | Yes | context | No |
| Sector score (price momentum) | Sector | price | India | Yes | tested (no lift) | No (context) |
| **Sector Intelligence (multi-metric + rotation)** | Sector | price (enrichable) | USA (India-ready) | Yes (USA) | Pending | No |
| Dynamic tradable universe | Universe | listings + liquidity | India, USA | Yes | n/a | Yes (India) |
| Historical analogue / win rate | Evidence | registry | India | Yes | measured (RQS~0.5) | context only |
| SEC fundamentals (PIT) | Fundamental | SEC EDGAR | USA | No | Planned (LAB-002) | No |
| Earnings surprise / revisions | Fundamental | SEC / Finnhub | USA, India | No | Planned (LAB-001) | No |
| Insider buying (Form 4) | Alternative | SEC | USA | No | Planned (LAB-003) | No |
| ETF holdings / flows | Flow | issuer files | USA | No | Planned (LAB-004) | No |
| Institutional (13F) | Flow | SEC | USA | No | Planned | No |
| Macro (FRED: rates/CPI/yield curve) | Macro | FRED | USA | No | Planned | No |
| News / sentiment | Alternative | RSS / Reddit | USA, India | No | Planned | No |
| Learning-to-Rank meta-score | AI | combined features | USA | No | tested (price-only FAIL) | No |

## How a row advances
```
Planned → (acquire data) → Live → (data-layer gate: IC · lift · walk-forward · DSR) → Gated
        → (forward paper, beats frozen baseline) → Promoted (into production)
```

## Notes
- "context" = shown to the user for transparency but **not** a validated driver (e.g. RSI, sector momentum).
- Cross-market features that pass in BOTH India and USA are the strongest evidence of a real edge.
- This registry pairs with the LAB board (`python india/ai_lab/lab_status.py`) and the research journal.
