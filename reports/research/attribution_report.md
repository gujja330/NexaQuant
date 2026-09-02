# AEGIS Attribution Report

**Generated:** 2026-09-02T12:46:10+00:00
**Source:** `reports/research/outcome_dataset.parquet`
**Positions:** 60 total · 41 closed · 19 open

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
| R2 | 38 | 34.2% | -0.163% | 0.0% | 0.89 | STR |
| R1 | 3 | 0.0% | -5.293% | -5.21% | 0.0 | OBS |

### cap
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| MidCap | 18 | 38.9% | -0.418% | -0.18% | 0.68 | SIG |
| LargeCap | 23 | 26.1% | -0.632% | 0.0% | 0.69 | SIG |

### sector
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| Tech | 1 | 100.0% | 10.51% | 10.51% | None | OBS |
| Basic Materials | 4 | 75.0% | 1.295% | 0.805% | 20.19 | OBS |
| Consumer Cyclical | 5 | 20.0% | 0.584% | -0.25% | 2.03 | HYP |
| Real Estate | 2 | 0.0% | -0.015% | -0.015% | 0.0 | OBS |
| Technology | 9 | 33.3% | -0.649% | 0.0% | 0.7 | HYP |
| Industrials | 4 | 50.0% | -0.78% | 0.225% | 0.66 | OBS |
| Energy | 4 | 0.0% | -0.873% | -0.68% | 0.0 | OBS |
| Financial Services | 3 | 66.7% | -1.16% | 0.99% | 0.47 | OBS |
| Utilities | 4 | 25.0% | -1.95% | -3.065% | 0.33 | OBS |
| Healthcare | 5 | 0.0% | -3.382% | -1.08% | 0.0 | HYP |

### initial_investability_verdict
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | 5.6 | HYP |
| ✓ OK | 8 | 50.0% | 0.419% | 0.44% | 1.34 | HYP |
| ✗ AVOID | 4 | 25.0% | -0.65% | -3.77% | 0.8 | OBS |
|  | 13 | 7.7% | -1.752% | 0.0% | 0.2 | HYP |
| 🏆 QUALITY | 5 | 40.0% | -2.664% | -0.27% | 0.17 | HYP |

## Interaction cross-tabs
### runner x cap
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap | 20 | 30.0% | 0.067% | 0.0% | SIG |
| R2 x MidCap | 18 | 38.9% | -0.418% | -0.18% | SIG |
| R1 x LargeCap | 3 | 0.0% | -5.293% | -5.21% | OBS |

### runner x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x Tech | 1 | 100.0% | 10.51% | 10.51% | OBS |
| R2 x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x Consumer Cyclical | 5 | 20.0% | 0.584% | -0.25% | HYP |
| R2 x Real Estate | 2 | 0.0% | -0.015% | -0.015% | OBS |
| R2 x Technology | 9 | 33.3% | -0.649% | 0.0% | HYP |
| R2 x Industrials | 4 | 50.0% | -0.78% | 0.225% | OBS |
| R2 x Energy | 4 | 0.0% | -0.873% | -0.68% | OBS |
| R2 x Financial Services | 3 | 66.7% | -1.16% | 0.99% | OBS |
| R2 x Healthcare | 4 | 0.0% | -2.952% | -0.595% | OBS |
| R1 x Healthcare | 1 | 0.0% | -5.1% | -5.1% | OBS |
| R1 x Utilities | 2 | 0.0% | -5.39% | -5.39% | OBS |

### cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x Tech | 1 | 100.0% | 10.51% | 10.51% | OBS |
| MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| LargeCap x Consumer Cyclical | 2 | 50.0% | 2.88% | 2.88% | OBS |
| LargeCap x Financial Services | 1 | 100.0% | 2.07% | 2.07% | OBS |
| MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| MidCap x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| LargeCap x Energy | 3 | 0.0% | -0.71% | 0.0% | OBS |
| MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| LargeCap x Industrials | 3 | 33.3% | -1.19% | 0.0% | OBS |
| MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| LargeCap x Technology | 8 | 25.0% | -1.411% | 0.0% | HYP |
| LargeCap x Healthcare | 2 | 0.0% | -2.55% | -2.55% | OBS |
| MidCap x Financial Services | 2 | 50.0% | -2.775% | -2.775% | OBS |
| MidCap x Healthcare | 3 | 0.0% | -3.937% | -1.08% | OBS |
| LargeCap x Utilities | 2 | 0.0% | -5.39% | -5.39% | OBS |
| LargeCap x Real Estate | 1 | 0.0% | 0.0% | 0.0% | OBS |

### runner x cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap x Tech | 1 | 100.0% | 10.51% | 10.51% | OBS |
| R2 x MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| R2 x LargeCap x Consumer Cyclical | 2 | 50.0% | 2.88% | 2.88% | OBS |
| R2 x LargeCap x Financial Services | 1 | 100.0% | 2.07% | 2.07% | OBS |
| R2 x MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x MidCap x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| R2 x MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x LargeCap x Energy | 3 | 0.0% | -0.71% | 0.0% | OBS |
| R2 x MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| R2 x LargeCap x Industrials | 3 | 33.3% | -1.19% | 0.0% | OBS |
| R2 x MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| R2 x LargeCap x Technology | 8 | 25.0% | -1.411% | 0.0% | HYP |
| R2 x MidCap x Financial Services | 2 | 50.0% | -2.775% | -2.775% | OBS |
| R2 x MidCap x Healthcare | 3 | 0.0% | -3.937% | -1.08% | OBS |
| R1 x LargeCap x Healthcare | 1 | 0.0% | -5.1% | -5.1% | OBS |
| R1 x LargeCap x Utilities | 2 | 0.0% | -5.39% | -5.39% | OBS |
| R2 x LargeCap x Healthcare | 1 | 0.0% | 0.0% | 0.0% | OBS |
| R2 x LargeCap x Real Estate | 1 | 0.0% | 0.0% | 0.0% | OBS |

### runner x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x ✗ AVOID | 2 | 50.0% | 4.09% | 4.09% | OBS |
| R2 x ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | HYP |
| R2 x ✓ OK | 8 | 50.0% | 0.419% | 0.44% | HYP |
| R2 x  | 13 | 7.7% | -1.752% | 0.0% | HYP |
| R2 x 🏆 QUALITY | 4 | 50.0% | -2.055% | 0.165% | OBS |
| R1 x 🏆 QUALITY | 1 | 0.0% | -5.1% | -5.1% | OBS |
| R1 x ✗ AVOID | 2 | 0.0% | -5.39% | -5.39% | OBS |

### cap x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x ⚠ MARGINAL | 3 | 66.7% | 2.64% | 2.43% | OBS |
| LargeCap x ✓ OK | 2 | 50.0% | 1.815% | 1.815% | OBS |
| MidCap x ⚠ MARGINAL | 8 | 37.5% | 0.671% | -0.14% | HYP |
| MidCap x ✓ OK | 6 | 50.0% | -0.047% | 0.44% | HYP |
| LargeCap x ✗ AVOID | 3 | 33.3% | -0.09% | -5.21% | OBS |
| LargeCap x 🏆 QUALITY | 2 | 50.0% | -1.515% | -1.515% | OBS |
| LargeCap x  | 13 | 7.7% | -1.752% | 0.0% | HYP |
| MidCap x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| MidCap x 🏆 QUALITY | 3 | 33.3% | -3.43% | -0.27% | OBS |

### sector x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| Tech x ✗ AVOID | 1 | 100.0% | 10.51% | 10.51% | OBS |
| Consumer Cyclical x ✓ OK | 1 | 100.0% | 5.76% | 5.76% | OBS |
| Technology x ✓ OK | 1 | 100.0% | 5.45% | 5.45% | OBS |
| Basic Materials x ⚠ MARGINAL | 1 | 100.0% | 3.84% | 3.84% | OBS |
| Technology x ⚠ MARGINAL | 3 | 66.7% | 2.64% | 2.43% | OBS |
| Financial Services x 🏆 QUALITY | 1 | 100.0% | 2.07% | 2.07% | OBS |
| Utilities x ⚠ MARGINAL | 2 | 50.0% | 1.49% | 1.49% | OBS |
| Basic Materials x ✓ OK | 1 | 100.0% | 1.01% | 1.01% | OBS |
| Industrials x ⚠ MARGINAL | 1 | 100.0% | 0.45% | 0.45% | OBS |
| Basic Materials x 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | OBS |
| Real Estate x ⚠ MARGINAL | 1 | 0.0% | -0.03% | -0.03% | OBS |
| Consumer Cyclical x ⚠ MARGINAL | 2 | 0.0% | -0.255% | -0.255% | OBS |
| Healthcare x ✓ OK | 2 | 0.0% | -0.595% | -0.595% | OBS |
| Industrials x  | 3 | 33.3% | -1.19% | 0.0% | OBS |
| Energy x ⚠ MARGINAL | 1 | 0.0% | -1.36% | -1.36% | OBS |
| Energy x ✓ OK | 1 | 0.0% | -2.13% | -2.13% | OBS |
| Consumer Cyclical x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| Financial Services x ✓ OK | 2 | 50.0% | -2.775% | -2.775% | OBS |
| Technology x  | 5 | 0.0% | -3.842% | 0.0% | HYP |
| Utilities x ✗ AVOID | 2 | 0.0% | -5.39% | -5.39% | OBS |
| Healthcare x 🏆 QUALITY | 2 | 0.0% | -7.86% | -7.86% | OBS |
| Consumer Cyclical x  | 1 | 0.0% | 0.0% | 0.0% | OBS |
| Energy x  | 2 | 0.0% | 0.0% | 0.0% | OBS |
| Healthcare x  | 1 | 0.0% | 0.0% | 0.0% | OBS |
| Real Estate x  | 1 | 0.0% | 0.0% | 0.0% | OBS |

## Winner profile (top 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R2 | LargeCap | Tech | 1 | 100.0% | 10.51% | OBS |
| 2 | R2 | MidCap | Technology | 1 | 100.0% | 5.45% | OBS |
| 3 | R2 | LargeCap | Consumer Cyclical | 2 | 50.0% | 2.88% | OBS |
| 4 | R2 | LargeCap | Financial Services | 1 | 100.0% | 2.07% | OBS |
| 5 | R2 | MidCap | Utilities | 2 | 50.0% | 1.49% | OBS |

## Failure profile (bottom 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R1 | LargeCap | Utilities | 2 | 0.0% | -5.39% | OBS |
| 2 | R1 | LargeCap | Healthcare | 1 | 0.0% | -5.1% | OBS |
| 3 | R2 | MidCap | Healthcare | 3 | 0.0% | -3.94% | OBS |
| 4 | R2 | MidCap | Financial Services | 2 | 50.0% | -2.77% | OBS |
| 5 | R2 | LargeCap | Technology | 8 | 25.0% | -1.41% | HYP |

---
**Governance:** No R1/R2 changes above tier 'observation only'. No interaction claims below tier 'research signal' (n≥15). Winner/failure profiles are early observations · sample sizes noted.