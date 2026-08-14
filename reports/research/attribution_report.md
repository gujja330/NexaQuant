# AEGIS Attribution Report

**Generated:** 2026-08-14T16:45:29+00:00
**Source:** `reports/research/outcome_dataset.parquet`
**Positions:** 59 total · 27 closed · 32 open

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
| R2 | 27 | 40.7% | 0.849% | 0.0% | 4.26 | SIG |

### cap
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| LargeCap | 14 | 35.7% | 0.936% | 0.0% | 9.09 | HYP |
| MidCap | 13 | 46.2% | 0.755% | -0.03% | 2.81 | HYP |

### sector
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| Utilities | 1 | 100.0% | 3.9% | 3.9% | None | OBS |
| Technology | 4 | 75.0% | 3.343% | 3.94% | 192.0 | OBS |
| Basic Materials | 2 | 100.0% | 2.22% | 2.22% | None | OBS |
| Financial Services | 1 | 100.0% | 0.99% | 0.99% | None | OBS |
| Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | 2.03 | OBS |
| Industrials | 1 | 100.0% | 0.45% | 0.45% | None | OBS |
| Real Estate | 1 | 0.0% | -0.03% | -0.03% | 0.0 | OBS |
| Unclassified | 9 | 22.2% | -0.063% | 0.0% | 0.63 | HYP |
| Healthcare | 2 | 0.0% | -0.595% | -0.595% | 0.0 | OBS |
| Energy | 1 | 0.0% | -1.36% | -1.36% | 0.0 | OBS |
| Financials | 1 | 0.0% | 0.0% | 0.0% | None | OBS |

### initial_investability_verdict
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| ✓ OK | 5 | 60.0% | 2.202% | 0.99% | 10.25 | HYP |
| ⚠ MARGINAL | 11 | 45.5% | 1.292% | 0.0% | 8.21 | HYP |
| 🏆 QUALITY | 1 | 100.0% | 0.6% | 0.6% | None | OBS |
|  | 9 | 22.2% | -0.063% | 0.0% | 0.63 | HYP |
| ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | 0.0 | OBS |

## Interaction cross-tabs
### runner x cap
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap | 14 | 35.7% | 0.936% | 0.0% | HYP |
| R2 x MidCap | 13 | 46.2% | 0.755% | -0.03% | HYP |

### runner x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x Utilities | 1 | 100.0% | 3.9% | 3.9% | OBS |
| R2 x Technology | 4 | 75.0% | 3.343% | 3.94% | OBS |
| R2 x Basic Materials | 2 | 100.0% | 2.22% | 2.22% | OBS |
| R2 x Financial Services | 1 | 100.0% | 0.99% | 0.99% | OBS |
| R2 x Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | OBS |
| R2 x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| R2 x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x Unclassified | 9 | 22.2% | -0.063% | 0.0% | HYP |
| R2 x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| R2 x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| R2 x Financials | 1 | 0.0% | 0.0% | 0.0% | OBS |

### cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| MidCap x Utilities | 1 | 100.0% | 3.9% | 3.9% | OBS |
| LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| MidCap x Basic Materials | 2 | 100.0% | 2.22% | 2.22% | OBS |
| MidCap x Financial Services | 1 | 100.0% | 0.99% | 0.99% | OBS |
| MidCap x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| LargeCap x Unclassified | 9 | 22.2% | -0.063% | 0.0% | HYP |
| MidCap x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| LargeCap x Financials | 1 | 0.0% | 0.0% | 0.0% | OBS |

### runner x cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| R2 x MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| R2 x MidCap x Utilities | 1 | 100.0% | 3.9% | 3.9% | OBS |
| R2 x LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| R2 x MidCap x Basic Materials | 2 | 100.0% | 2.22% | 2.22% | OBS |
| R2 x MidCap x Financial Services | 1 | 100.0% | 0.99% | 0.99% | OBS |
| R2 x MidCap x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| R2 x MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x LargeCap x Unclassified | 9 | 22.2% | -0.063% | 0.0% | HYP |
| R2 x MidCap x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| R2 x MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| R2 x MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| R2 x LargeCap x Financials | 1 | 0.0% | 0.0% | 0.0% | OBS |

### runner x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x ✓ OK | 5 | 60.0% | 2.202% | 0.99% | HYP |
| R2 x ⚠ MARGINAL | 11 | 45.5% | 1.292% | 0.0% | HYP |
| R2 x 🏆 QUALITY | 1 | 100.0% | 0.6% | 0.6% | OBS |
| R2 x  | 9 | 22.2% | -0.063% | 0.0% | HYP |
| R2 x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |

### cap x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x ✓ OK | 1 | 100.0% | 5.76% | 5.76% | OBS |
| LargeCap x ⚠ MARGINAL | 4 | 50.0% | 1.98% | 1.215% | OBS |
| MidCap x ✓ OK | 4 | 50.0% | 1.312% | 0.44% | OBS |
| MidCap x ⚠ MARGINAL | 7 | 42.9% | 0.899% | -0.03% | HYP |
| MidCap x 🏆 QUALITY | 1 | 100.0% | 0.6% | 0.6% | OBS |
| LargeCap x  | 9 | 22.2% | -0.063% | 0.0% | HYP |
| MidCap x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |

### sector x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| Consumer Cyclical x ✓ OK | 1 | 100.0% | 5.76% | 5.76% | OBS |
| Technology x ✓ OK | 1 | 100.0% | 5.45% | 5.45% | OBS |
| Utilities x ⚠ MARGINAL | 1 | 100.0% | 3.9% | 3.9% | OBS |
| Basic Materials x ⚠ MARGINAL | 1 | 100.0% | 3.84% | 3.84% | OBS |
| Technology x ⚠ MARGINAL | 3 | 66.7% | 2.64% | 2.43% | OBS |
| Financial Services x ✓ OK | 1 | 100.0% | 0.99% | 0.99% | OBS |
| Basic Materials x 🏆 QUALITY | 1 | 100.0% | 0.6% | 0.6% | OBS |
| Industrials x ⚠ MARGINAL | 1 | 100.0% | 0.45% | 0.45% | OBS |
| Real Estate x ⚠ MARGINAL | 1 | 0.0% | -0.03% | -0.03% | OBS |
| Unclassified x  | 9 | 22.2% | -0.063% | 0.0% | HYP |
| Consumer Cyclical x ⚠ MARGINAL | 2 | 0.0% | -0.255% | -0.255% | OBS |
| Healthcare x ✓ OK | 2 | 0.0% | -0.595% | -0.595% | OBS |
| Energy x ⚠ MARGINAL | 1 | 0.0% | -1.36% | -1.36% | OBS |
| Consumer Cyclical x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| Financials x ⚠ MARGINAL | 1 | 0.0% | 0.0% | 0.0% | OBS |

## Winner profile (top 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R2 | LargeCap | Consumer Cyclical | 1 | 100.0% | 5.76% | OBS |
| 2 | R2 | MidCap | Technology | 1 | 100.0% | 5.45% | OBS |
| 3 | R2 | MidCap | Utilities | 1 | 100.0% | 3.9% | OBS |
| 4 | R2 | LargeCap | Technology | 3 | 66.7% | 2.64% | OBS |
| 5 | R2 | MidCap | Basic Materials | 2 | 100.0% | 2.22% | OBS |

## Failure profile (bottom 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R2 | MidCap | Energy | 1 | 0.0% | -1.36% | OBS |
| 2 | R2 | MidCap | Consumer Cyclical | 3 | 0.0% | -0.95% | OBS |
| 3 | R2 | MidCap | Healthcare | 2 | 0.0% | -0.6% | OBS |
| 4 | R2 | LargeCap | Unclassified | 9 | 22.2% | -0.06% | HYP |
| 5 | R2 | MidCap | Real Estate | 1 | 0.0% | -0.03% | OBS |

---
**Governance:** No R1/R2 changes above tier 'observation only'. No interaction claims below tier 'research signal' (n≥15). Winner/failure profiles are early observations · sample sizes noted.