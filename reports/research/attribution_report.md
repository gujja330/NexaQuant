# AEGIS Attribution Report

**Generated:** 2026-08-25T03:33:16+00:00
**Source:** `reports/research/outcome_dataset.parquet`
**Positions:** 50 total · 27 closed · 23 open

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
| R2 | 27 | 51.9% | 0.764% | 0.15% | 2.43 | SIG |

### cap
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| LargeCap | 6 | 83.3% | 2.65% | 2.25% | 228.14 | HYP |
| MidCap | 21 | 42.9% | 0.226% | -0.03% | 1.33 | SIG |

### sector
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| Technology | 4 | 75.0% | 3.343% | 3.94% | 192.0 | OBS |
| Utilities | 2 | 50.0% | 1.49% | 1.49% | 4.24 | OBS |
| Basic Materials | 4 | 75.0% | 1.295% | 0.805% | 20.19 | OBS |
| Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | 2.03 | OBS |
| Industrials | 1 | 100.0% | 0.45% | 0.45% | None | OBS |
| Unclassified | 5 | 60.0% | 0.36% | 0.15% | 2.43 | HYP |
| Real Estate | 1 | 0.0% | -0.03% | -0.03% | 0.0 | OBS |
| Healthcare | 2 | 0.0% | -0.595% | -0.595% | 0.0 | OBS |
| Financial Services | 3 | 66.7% | -1.16% | 0.99% | 0.47 | OBS |
| Energy | 1 | 0.0% | -1.36% | -1.36% | 0.0 | OBS |

### initial_investability_verdict
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | 5.6 | HYP |
| 🏆 QUALITY | 3 | 66.7% | 0.8% | 0.6% | 9.89 | OBS |
| ✓ OK | 7 | 57.1% | 0.783% | 0.99% | 1.71 | HYP |
|  | 5 | 60.0% | 0.36% | 0.15% | 2.43 | HYP |
| ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | 0.0 | OBS |

## Interaction cross-tabs
### runner x cap
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap | 6 | 83.3% | 2.65% | 2.25% | HYP |
| R2 x MidCap | 21 | 42.9% | 0.226% | -0.03% | SIG |

### runner x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x Technology | 4 | 75.0% | 3.343% | 3.94% | OBS |
| R2 x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | OBS |
| R2 x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| R2 x Unclassified | 5 | 60.0% | 0.36% | 0.15% | HYP |
| R2 x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| R2 x Financial Services | 3 | 66.7% | -1.16% | 0.99% | OBS |
| R2 x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |

### cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| LargeCap x Financial Services | 1 | 100.0% | 2.07% | 2.07% | OBS |
| MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| MidCap x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| MidCap x Unclassified | 4 | 50.0% | 0.413% | 0.28% | OBS |
| LargeCap x Unclassified | 1 | 100.0% | 0.15% | 0.15% | OBS |
| MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| MidCap x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| MidCap x Financial Services | 2 | 50.0% | -2.775% | -2.775% | OBS |

### runner x cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| R2 x MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| R2 x LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| R2 x LargeCap x Financial Services | 1 | 100.0% | 2.07% | 2.07% | OBS |
| R2 x MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x MidCap x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| R2 x MidCap x Unclassified | 4 | 50.0% | 0.413% | 0.28% | OBS |
| R2 x LargeCap x Unclassified | 1 | 100.0% | 0.15% | 0.15% | OBS |
| R2 x MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x MidCap x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| R2 x MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| R2 x MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| R2 x MidCap x Financial Services | 2 | 50.0% | -2.775% | -2.775% | OBS |

### runner x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | HYP |
| R2 x 🏆 QUALITY | 3 | 66.7% | 0.8% | 0.6% | OBS |
| R2 x ✓ OK | 7 | 57.1% | 0.783% | 0.99% | HYP |
| R2 x  | 5 | 60.0% | 0.36% | 0.15% | HYP |
| R2 x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |

### cap x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x ✓ OK | 1 | 100.0% | 5.76% | 5.76% | OBS |
| LargeCap x ⚠ MARGINAL | 3 | 66.7% | 2.64% | 2.43% | OBS |
| LargeCap x 🏆 QUALITY | 1 | 100.0% | 2.07% | 2.07% | OBS |
| MidCap x ⚠ MARGINAL | 8 | 37.5% | 0.671% | -0.14% | HYP |
| MidCap x  | 4 | 50.0% | 0.413% | 0.28% | OBS |
| MidCap x 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | OBS |
| LargeCap x  | 1 | 100.0% | 0.15% | 0.15% | OBS |
| MidCap x ✓ OK | 6 | 50.0% | -0.047% | 0.44% | HYP |
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
| Unclassified x  | 5 | 60.0% | 0.36% | 0.15% | HYP |
| Basic Materials x 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | OBS |
| Real Estate x ⚠ MARGINAL | 1 | 0.0% | -0.03% | -0.03% | OBS |
| Consumer Cyclical x ⚠ MARGINAL | 2 | 0.0% | -0.255% | -0.255% | OBS |
| Healthcare x ✓ OK | 2 | 0.0% | -0.595% | -0.595% | OBS |
| Energy x ⚠ MARGINAL | 1 | 0.0% | -1.36% | -1.36% | OBS |
| Consumer Cyclical x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| Financial Services x ✓ OK | 2 | 50.0% | -2.775% | -2.775% | OBS |

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
| 1 | R2 | MidCap | Financial Services | 2 | 50.0% | -2.77% | OBS |
| 2 | R2 | MidCap | Energy | 1 | 0.0% | -1.36% | OBS |
| 3 | R2 | MidCap | Consumer Cyclical | 3 | 0.0% | -0.95% | OBS |
| 4 | R2 | MidCap | Healthcare | 2 | 0.0% | -0.6% | OBS |
| 5 | R2 | MidCap | Real Estate | 1 | 0.0% | -0.03% | OBS |

---
**Governance:** No R1/R2 changes above tier 'observation only'. No interaction claims below tier 'research signal' (n≥15). Winner/failure profiles are early observations · sample sizes noted.