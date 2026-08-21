# AEGIS Attribution Report

**Generated:** 2026-08-21T06:26:16+00:00
**Source:** `reports/research/outcome_dataset.parquet`
**Positions:** 59 total · 32 closed · 27 open

## Sample-size tiers
| Tier | N range | Meaning |
|---|---|---|
| observation only | 0-4 | anecdote · not actionable |
| hypothesis | 5-14 | worth testing |
| research signal | 15-29 | investigate seriously |
| stronger evidence | 30-49 | candidate for model change |
| validation candidate | 50+ | ready for walk-forward |

## Single-dimension breakdowns (closed positions only)
### runner
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| R2 | 32 | 50.0% | 0.093% | 0.045% | 1.07 | STR |

### cap
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| MidCap | 17 | 41.2% | 0.182% | -0.11% | 1.23 | SIG |
| LargeCap | 15 | 60.0% | -0.007% | 0.31% | 1.0 | SIG |

### sector
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| Tech | 2 | 100.0% | 3.48% | 3.48% | None | OBS |
| Technology | 4 | 75.0% | 3.343% | 3.94% | 192.0 | OBS |
| Utilities | 2 | 50.0% | 1.49% | 1.49% | 4.24 | OBS |
| Basic Materials | 4 | 75.0% | 1.295% | 0.805% | 20.19 | OBS |
| Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | 2.03 | OBS |
| Industrials | 1 | 100.0% | 0.45% | 0.45% | None | OBS |
| Real Estate | 1 | 0.0% | -0.03% | -0.03% | 0.0 | OBS |
| Healthcare | 2 | 0.0% | -0.595% | -0.595% | 0.0 | OBS |
| Energy | 1 | 0.0% | -1.36% | -1.36% | 0.0 | OBS |
| Unclassified | 9 | 44.4% | -2.306% | 0.0% | 0.23 | HYP |
| Financial Services | 2 | 50.0% | -2.775% | -2.775% | 0.15 | OBS |

### initial_investability_verdict
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| ✗ AVOID | 2 | 50.0% | 2.27% | 2.27% | 2.95 | OBS |
| ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | 5.6 | HYP |
| ✓ OK | 8 | 62.5% | 0.696% | 0.54% | 1.72 | HYP |
| 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | 2.22 | OBS |
|  | 9 | 44.4% | -2.306% | 0.0% | 0.23 | HYP |

## Interaction cross-tabs
### runner x cap
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x MidCap | 17 | 41.2% | 0.182% | -0.11% | SIG |
| R2 x LargeCap | 15 | 60.0% | -0.007% | 0.31% | SIG |

### runner x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x Tech | 2 | 100.0% | 3.48% | 3.48% | OBS |
| R2 x Technology | 4 | 75.0% | 3.343% | 3.94% | OBS |
| R2 x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | OBS |
| R2 x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| R2 x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| R2 x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| R2 x Unclassified | 9 | 44.4% | -2.306% | 0.0% | HYP |
| R2 x Financial Services | 2 | 50.0% | -2.775% | -2.775% | OBS |

### cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| LargeCap x Tech | 2 | 100.0% | 3.48% | 3.48% | OBS |
| LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| MidCap x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| MidCap x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| LargeCap x Unclassified | 9 | 44.4% | -2.306% | 0.0% | HYP |
| MidCap x Financial Services | 2 | 50.0% | -2.775% | -2.775% | OBS |

### runner x cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| R2 x MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| R2 x LargeCap x Tech | 2 | 100.0% | 3.48% | 3.48% | OBS |
| R2 x LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| R2 x MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x MidCap x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| R2 x MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x MidCap x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| R2 x MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| R2 x MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| R2 x LargeCap x Unclassified | 9 | 44.4% | -2.306% | 0.0% | HYP |
| R2 x MidCap x Financial Services | 2 | 50.0% | -2.775% | -2.775% | OBS |

### runner x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x ✗ AVOID | 2 | 50.0% | 2.27% | 2.27% | OBS |
| R2 x ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | HYP |
| R2 x ✓ OK | 8 | 62.5% | 0.696% | 0.54% | HYP |
| R2 x 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | OBS |
| R2 x  | 9 | 44.4% | -2.306% | 0.0% | HYP |

### cap x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x ✗ AVOID | 1 | 100.0% | 6.87% | 6.87% | OBS |
| LargeCap x ✓ OK | 2 | 100.0% | 2.925% | 2.925% | OBS |
| LargeCap x ⚠ MARGINAL | 3 | 66.7% | 2.64% | 2.43% | OBS |
| MidCap x ⚠ MARGINAL | 8 | 37.5% | 0.671% | -0.14% | HYP |
| MidCap x 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | OBS |
| MidCap x ✓ OK | 6 | 50.0% | -0.047% | 0.44% | HYP |
| LargeCap x  | 9 | 44.4% | -2.306% | 0.0% | HYP |
| MidCap x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |

### sector x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| Tech x ✗ AVOID | 1 | 100.0% | 6.87% | 6.87% | OBS |
| Consumer Cyclical x ✓ OK | 1 | 100.0% | 5.76% | 5.76% | OBS |
| Technology x ✓ OK | 1 | 100.0% | 5.45% | 5.45% | OBS |
| Basic Materials x ⚠ MARGINAL | 1 | 100.0% | 3.84% | 3.84% | OBS |
| Technology x ⚠ MARGINAL | 3 | 66.7% | 2.64% | 2.43% | OBS |
| Utilities x ⚠ MARGINAL | 2 | 50.0% | 1.49% | 1.49% | OBS |
| Basic Materials x ✓ OK | 1 | 100.0% | 1.01% | 1.01% | OBS |
| Industrials x ⚠ MARGINAL | 1 | 100.0% | 0.45% | 0.45% | OBS |
| Basic Materials x 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | OBS |
| Tech x ✓ OK | 1 | 100.0% | 0.09% | 0.09% | OBS |
| Real Estate x ⚠ MARGINAL | 1 | 0.0% | -0.03% | -0.03% | OBS |
| Consumer Cyclical x ⚠ MARGINAL | 2 | 0.0% | -0.255% | -0.255% | OBS |
| Healthcare x ✓ OK | 2 | 0.0% | -0.595% | -0.595% | OBS |
| Energy x ⚠ MARGINAL | 1 | 0.0% | -1.36% | -1.36% | OBS |
| Unclassified x  | 9 | 44.4% | -2.306% | 0.0% | HYP |
| Consumer Cyclical x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| Financial Services x ✓ OK | 2 | 50.0% | -2.775% | -2.775% | OBS |

## Winner profile (top 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R2 | LargeCap | Consumer Cyclical | 1 | 100.0% | 5.76% | OBS |
| 2 | R2 | MidCap | Technology | 1 | 100.0% | 5.45% | OBS |
| 3 | R2 | LargeCap | Tech | 2 | 100.0% | 3.48% | OBS |
| 4 | R2 | LargeCap | Technology | 3 | 66.7% | 2.64% | OBS |
| 5 | R2 | MidCap | Utilities | 2 | 50.0% | 1.49% | OBS |

## Failure profile (bottom 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R2 | MidCap | Financial Services | 2 | 50.0% | -2.77% | OBS |
| 2 | R2 | LargeCap | Unclassified | 9 | 44.4% | -2.31% | HYP |
| 3 | R2 | MidCap | Energy | 1 | 0.0% | -1.36% | OBS |
| 4 | R2 | MidCap | Consumer Cyclical | 3 | 0.0% | -0.95% | OBS |
| 5 | R2 | MidCap | Healthcare | 2 | 0.0% | -0.6% | OBS |

---
**Governance:** No R1/R2 changes above tier 'observation only'. No interaction claims below tier 'research signal' (n≥15). Winner/failure profiles are early observations · sample sizes noted.