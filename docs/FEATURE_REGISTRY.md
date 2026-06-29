# AEGIS — Feature Registry

> The research inventory: every feature/signal, its dataset & quality, whether it's point-in-time, and
> where it sits in the discipline (live · gated/tested · promoted). A feature is only **Promoted** after
> it beats the frozen baseline through the gate (IC · lift · walk-forward · DSR · forward paper).
> Pairs with the feature store (`core/feature_store.py`), the LAB board, and the research journal.

Legend — **PIT**: point-in-time (no look-ahead) · **Quality**: data trust · **Live**: in the feature
store today · **Tested**: run through the gate · **Promoted**: in production.

| Feature | Dataset | Source | Market | PIT | Quality | Live | Tested | Promoted |
|---------|---------|--------|--------|-----|---------|------|--------|----------|
| Volatility / risk rank | Technical | price | India, USA | Yes | High | Yes | Yes (India) | Yes (India) |
| HRP weighting | Portfolio | price/cov | India, USA | Yes | High | Yes | Yes | Yes (India) |
| Regime exposure (200-DMA+VIX+global) | Macro/Regime | price/index/vix | India, USA | Yes | High | Yes | Yes | Yes (India) |
| Momentum (1M/3M/6M) | Technical | price | India, USA | Yes | High | Yes | tested (no lift) | No |
| Relative strength vs index | Technical | price | India, USA | Yes | High | Yes | tested (no lift) | No |
| 200-DMA dist / 52-week pos | Technical | price | India, USA | Yes | High | Yes | context | No |
| RSI | Technical | price | India, USA | Yes | High | Yes | context | No |
| Sector classification (GICS) | Sector | Yahoo/SEC | USA | Yes | High | Yes | n/a | n/a |
| Sector Intelligence (multi-metric + rotation) | Sector | price (enrichable) | USA (India-ready) | Yes | Medium | Yes | Pending | No |
| Dynamic tradable universe | Universe | listings+liquidity | India, USA | Yes | High | Yes | n/a | Yes (India) |
| SEC fundamentals (ROE/margins/debt/growth) | Fundamental | SEC EDGAR | USA | Yes | High | No | Planned (P5) | No |
| Earnings surprise / revisions | Fundamental | SEC/Finnhub | USA, India | Yes | High | No | Planned | No |
| Insider buying (Form 4) | Alternative | SEC | USA | Yes | High | No | Planned | No |
| ETF holdings / flows | Flow | issuer files | USA | Yes | High | No | Planned | No |
| Institutional (13F) | Flow | SEC | USA | Yes | Medium | No | Planned | No |
| Macro (FRED rates/CPI/yield curve) | Macro | FRED | USA | Yes | High | No | Planned | No |
| News / sentiment | Alternative | RSS/Reddit | USA, India | Partial | Medium | No | Planned | No |
| Learning-to-Rank meta-score | AI | combined features | USA | Yes | n/a | No | tested (price-only FAIL) | No |

## How a row advances
```
Planned → (acquire raw → normalize → feature store) → Live → (gate: IC·lift·walk-forward·DSR) → Tested
        → (forward paper, beats frozen baseline) → Promoted (into production)
```

## Notes
- "context" = shown for transparency, not a validated driver (RSI, sector momentum).
- Features that pass in BOTH India and USA are the strongest evidence of a real edge.
- Every feature flows through ONE feature store so experiments are reproducible and comparable.
