# AEGIS Knowledge Graph (lineage rollup)

Auto-generated (`python tools/trace.py graph`) from the registries + leaderboard. The entity chain:
`Dataset -> Feature -> Experiment -> Leaderboard result -> Promotion -> Production`.

## Which datasets produced the most kept/promoted/investigate features
- **price_ohlcv** (3): t_vol_ann, t_mom_3m, t_rel_str_3m

## Program success rate (promoted+investigate / results)
- X-CrossMarket: 2/2 (100%)
- IND-PortfolioConstruction: 1/4 (25%)
- A-Fundamentals: 0/10 (0%)
- IND-UniverseSizing: 0/1 (0%)
- B-Earnings: 0/2 (0%)

## Most-tested factors
- f_rev_growth_yoy: 2
- f_roe: 2
- lgbm_learned_blend_purged: 2
- regime_overlay: 2
- earnings_surprise_yoy: 2

## Results held back by LOW confidence (need more power)
- RC001.1 f_net_margin — 46 (Low) (weak)
- RC001.0 composite_equal_weight — 37 (Low) (not-promoted)
- RC001.1 f_roe — 48 (Low) (not-promoted)
- RC001.1 f_rev_growth_yoy — 41 (Low) (not-promoted)

## Production features and their origin dataset
- t_vol_ann <- price_ohlcv (program Technical)
- t_mom_3m <- price_ohlcv (program Technical)
- t_rel_str_3m <- price_ohlcv (program Technical)
