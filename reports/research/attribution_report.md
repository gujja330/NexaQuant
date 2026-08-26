# AEGIS Attribution Report

**Generated:** 2026-08-26T04:50:25+00:00
**Source:** `reports/research/outcome_dataset.parquet`
**Positions:** 51 total · 28 closed · 23 open

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
| R2 | 28 | 50.0% | 0.583% | 0.02% | 1.99 | SIG |

### cap
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| LargeCap | 5 | 80.0% | 3.15% | 2.43% | 226.0 | HYP |
| MidCap | 23 | 43.5% | 0.025% | -0.03% | 1.04 | SIG |

### sector
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| Technology | 4 | 75.0% | 3.343% | 3.94% | 192.0 | OBS |
| Utilities | 2 | 50.0% | 1.49% | 1.49% | 4.24 | OBS |
| Basic Materials | 4 | 75.0% | 1.295% | 0.805% | 20.19 | OBS |
| Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | 2.03 | OBS |
| Industrials | 2 | 100.0% | 0.245% | 0.245% | None | OBS |
| Real Estate | 1 | 0.0% | -0.03% | -0.03% | 0.0 | OBS |
| Healthcare | 3 | 0.0% | -0.45% | -0.16% | 0.0 | OBS |
| Financial Services | 6 | 66.7% | -0.978% | 0.365% | 0.39 | HYP |
| Energy | 1 | 0.0% | -1.36% | -1.36% | 0.0 | OBS |
| Consumer Defensive | 1 | 0.0% | 0.0% | 0.0% | None | OBS |

### initial_investability_verdict
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | 5.6 | HYP |
| 🏆 QUALITY | 3 | 66.7% | 0.8% | 0.6% | 9.89 | OBS |
| ✓ OK | 7 | 57.1% | 0.783% | 0.99% | 1.71 | HYP |
|  | 6 | 50.0% | -0.418% | 0.02% | 0.23 | HYP |
| ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | 0.0 | OBS |

## Interaction cross-tabs
### runner x cap
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap | 5 | 80.0% | 3.15% | 2.43% | HYP |
| R2 x MidCap | 23 | 43.5% | 0.025% | -0.03% | SIG |

### runner x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x Technology | 4 | 75.0% | 3.343% | 3.94% | OBS |
| R2 x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | OBS |
| R2 x Industrials | 2 | 100.0% | 0.245% | 0.245% | OBS |
| R2 x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x Healthcare | 3 | 0.0% | -0.45% | -0.16% | OBS |
| R2 x Financial Services | 6 | 66.7% | -0.978% | 0.365% | HYP |
| R2 x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| R2 x Consumer Defensive | 1 | 0.0% | 0.0% | 0.0% | OBS |

### cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| LargeCap x Financial Services | 1 | 100.0% | 2.07% | 2.07% | OBS |
| MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| MidCap x Industrials | 2 | 100.0% | 0.245% | 0.245% | OBS |
| MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| MidCap x Healthcare | 3 | 0.0% | -0.45% | -0.16% | OBS |
| MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| MidCap x Financial Services | 5 | 60.0% | -1.588% | 0.15% | HYP |
| MidCap x Consumer Defensive | 1 | 0.0% | 0.0% | 0.0% | OBS |

### runner x cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| R2 x MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| R2 x LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| R2 x LargeCap x Financial Services | 1 | 100.0% | 2.07% | 2.07% | OBS |
| R2 x MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x MidCap x Industrials | 2 | 100.0% | 0.245% | 0.245% | OBS |
| R2 x MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x MidCap x Healthcare | 3 | 0.0% | -0.45% | -0.16% | OBS |
| R2 x MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| R2 x MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| R2 x MidCap x Financial Services | 5 | 60.0% | -1.588% | 0.15% | HYP |
| R2 x MidCap x Consumer Defensive | 1 | 0.0% | 0.0% | 0.0% | OBS |

### runner x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | HYP |
| R2 x 🏆 QUALITY | 3 | 66.7% | 0.8% | 0.6% | OBS |
| R2 x ✓ OK | 7 | 57.1% | 0.783% | 0.99% | HYP |
| R2 x  | 6 | 50.0% | -0.418% | 0.02% | HYP |
| R2 x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |

### cap x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x ✓ OK | 1 | 100.0% | 5.76% | 5.76% | OBS |
| LargeCap x ⚠ MARGINAL | 3 | 66.7% | 2.64% | 2.43% | OBS |
| LargeCap x 🏆 QUALITY | 1 | 100.0% | 2.07% | 2.07% | OBS |
| MidCap x ⚠ MARGINAL | 8 | 37.5% | 0.671% | -0.14% | HYP |
| MidCap x 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | OBS |
| MidCap x ✓ OK | 6 | 50.0% | -0.047% | 0.44% | HYP |
| MidCap x  | 6 | 50.0% | -0.418% | 0.02% | HYP |
| MidCap x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |

### sector x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| Consumer Cyclical x ✓ OK | 1 | 100.0% | 5.76% | 5.76% | OBS |
| Technology x ✓ OK | 1 | 100.0% | 5.45% | 5.45% | OBS |
| Basic Materials x ⚠ MARGINAL | 1 | 100.0% | 3.84% | 3.84% | OBS |
| Technology x ⚠ MARGINAL | 3 | 66.7% | 2.64% | 2.43% | OBS |
| Financial Services x 🏆 QUALITY | 1 | 100.0% | 2.07% | 2.07% | OBS |
| Utilities x ⚠ MARGINAL | 2 | 50.0% | 1.49% | 1.49% | OBS |
| Basic Materials x ✓ OK | 1 | 100.0% | 1.01% | 1.01% | OBS |
| Industrials x ⚠ MARGINAL | 1 | 100.0% | 0.45% | 0.45% | OBS |
| Basic Materials x 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | OBS |
| Industrials x  | 1 | 100.0% | 0.04% | 0.04% | OBS |
| Real Estate x ⚠ MARGINAL | 1 | 0.0% | -0.03% | -0.03% | OBS |
| Healthcare x  | 1 | 0.0% | -0.16% | -0.16% | OBS |
| Consumer Cyclical x ⚠ MARGINAL | 2 | 0.0% | -0.255% | -0.255% | OBS |
| Healthcare x ✓ OK | 2 | 0.0% | -0.595% | -0.595% | OBS |
| Financial Services x  | 3 | 66.7% | -0.797% | 0.15% | OBS |
| Energy x ⚠ MARGINAL | 1 | 0.0% | -1.36% | -1.36% | OBS |
| Consumer Cyclical x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| Financial Services x ✓ OK | 2 | 50.0% | -2.775% | -2.775% | OBS |
| Consumer Defensive x  | 1 | 0.0% | 0.0% | 0.0% | OBS |

## Winner profile (top 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R2 | LargeCap | Consumer Cyclical | 1 | 100.0% | 5.76% | OBS |
| 2 | R2 | MidCap | Technology | 1 | 100.0% | 5.45% | OBS |
| 3 | R2 | LargeCap | Technology | 3 | 66.7% | 2.64% | OBS |
| 4 | R2 | LargeCap | Financial Services | 1 | 100.0% | 2.07% | OBS |
| 5 | R2 | MidCap | Utilities | 2 | 50.0% | 1.49% | OBS |

## Failure profile (bottom 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R2 | MidCap | Financial Services | 5 | 60.0% | -1.59% | HYP |
| 2 | R2 | MidCap | Energy | 1 | 0.0% | -1.36% | OBS |
| 3 | R2 | MidCap | Consumer Cyclical | 3 | 0.0% | -0.95% | OBS |
| 4 | R2 | MidCap | Healthcare | 3 | 0.0% | -0.45% | OBS |
| 5 | R2 | MidCap | Real Estate | 1 | 0.0% | -0.03% | OBS |

---
**Governance:** No R1/R2 changes above tier 'observation only'. No interaction claims below tier 'research signal' (n≥15). Winner/failure profiles are early observations · sample sizes noted.