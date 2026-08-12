# AEGIS Attribution Report

**Generated:** 2026-08-12T03:12:51+00:00
**Source:** `reports/research/outcome_dataset.parquet`
**Positions:** 44 total · 15 closed · 29 open

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
| R2 | 15 | 53.3% | 1.207% | 0.45% | 4.34 | SIG |

### cap
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| LargeCap | 3 | 100.0% | 4.583% | 5.56% | None | OBS |
| MidCap | 12 | 41.7% | 0.363% | -0.07% | 1.8 | HYP |

### sector
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| Technology | 2 | 100.0% | 3.995% | 3.995% | None | OBS |
| Utilities | 1 | 100.0% | 3.9% | 3.9% | None | OBS |
| Basic Materials | 2 | 100.0% | 2.22% | 2.22% | None | OBS |
| Financial Services | 1 | 100.0% | 0.99% | 0.99% | None | OBS |
| Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | 2.03 | OBS |
| Industrials | 1 | 100.0% | 0.45% | 0.45% | None | OBS |
| Real Estate | 1 | 0.0% | -0.03% | -0.03% | 0.0 | OBS |
| Healthcare | 2 | 0.0% | -0.595% | -0.595% | 0.0 | OBS |
| Energy | 1 | 0.0% | -1.36% | -1.36% | 0.0 | OBS |

### initial_investability_verdict
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| ⚠ MARGINAL | 9 | 55.6% | 1.587% | 0.45% | 8.52 | HYP |
| ✓ OK | 4 | 50.0% | 1.39% | 0.44% | 5.67 | OBS |
| 🏆 QUALITY | 1 | 100.0% | 0.6% | 0.6% | None | OBS |
| ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | 0.0 | OBS |

## Interaction cross-tabs
### runner x cap
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap | 3 | 100.0% | 4.583% | 5.56% | OBS |
| R2 x MidCap | 12 | 41.7% | 0.363% | -0.07% | HYP |

### runner x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x Technology | 2 | 100.0% | 3.995% | 3.995% | OBS |
| R2 x Utilities | 1 | 100.0% | 3.9% | 3.9% | OBS |
| R2 x Basic Materials | 2 | 100.0% | 2.22% | 2.22% | OBS |
| R2 x Financial Services | 1 | 100.0% | 0.99% | 0.99% | OBS |
| R2 x Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | OBS |
| R2 x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| R2 x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| R2 x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |

### cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| LargeCap x Technology | 2 | 100.0% | 3.995% | 3.995% | OBS |
| MidCap x Utilities | 1 | 100.0% | 3.9% | 3.9% | OBS |
| MidCap x Basic Materials | 2 | 100.0% | 2.22% | 2.22% | OBS |
| MidCap x Financial Services | 1 | 100.0% | 0.99% | 0.99% | OBS |
| MidCap x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| MidCap x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |

### runner x cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| R2 x LargeCap x Technology | 2 | 100.0% | 3.995% | 3.995% | OBS |
| R2 x MidCap x Utilities | 1 | 100.0% | 3.9% | 3.9% | OBS |
| R2 x MidCap x Basic Materials | 2 | 100.0% | 2.22% | 2.22% | OBS |
| R2 x MidCap x Financial Services | 1 | 100.0% | 0.99% | 0.99% | OBS |
| R2 x MidCap x Industrials | 1 | 100.0% | 0.45% | 0.45% | OBS |
| R2 x MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x MidCap x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| R2 x MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| R2 x MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |

### runner x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x ⚠ MARGINAL | 9 | 55.6% | 1.587% | 0.45% | HYP |
| R2 x ✓ OK | 4 | 50.0% | 1.39% | 0.44% | OBS |
| R2 x 🏆 QUALITY | 1 | 100.0% | 0.6% | 0.6% | OBS |
| R2 x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |

### cap x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x ✓ OK | 1 | 100.0% | 5.76% | 5.76% | OBS |
| LargeCap x ⚠ MARGINAL | 2 | 100.0% | 3.995% | 3.995% | OBS |
| MidCap x ⚠ MARGINAL | 7 | 42.9% | 0.899% | -0.03% | HYP |
| MidCap x 🏆 QUALITY | 1 | 100.0% | 0.6% | 0.6% | OBS |
| MidCap x ✓ OK | 3 | 33.3% | -0.067% | -0.11% | OBS |
| MidCap x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |

### sector x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| Consumer Cyclical x ✓ OK | 1 | 100.0% | 5.76% | 5.76% | OBS |
| Technology x ⚠ MARGINAL | 2 | 100.0% | 3.995% | 3.995% | OBS |
| Utilities x ⚠ MARGINAL | 1 | 100.0% | 3.9% | 3.9% | OBS |
| Basic Materials x ⚠ MARGINAL | 1 | 100.0% | 3.84% | 3.84% | OBS |
| Financial Services x ✓ OK | 1 | 100.0% | 0.99% | 0.99% | OBS |
| Basic Materials x 🏆 QUALITY | 1 | 100.0% | 0.6% | 0.6% | OBS |
| Industrials x ⚠ MARGINAL | 1 | 100.0% | 0.45% | 0.45% | OBS |
| Real Estate x ⚠ MARGINAL | 1 | 0.0% | -0.03% | -0.03% | OBS |
| Consumer Cyclical x ⚠ MARGINAL | 2 | 0.0% | -0.255% | -0.255% | OBS |
| Healthcare x ✓ OK | 2 | 0.0% | -0.595% | -0.595% | OBS |
| Energy x ⚠ MARGINAL | 1 | 0.0% | -1.36% | -1.36% | OBS |
| Consumer Cyclical x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |

## Winner profile (top 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R2 | LargeCap | Consumer Cyclical | 1 | 100.0% | 5.76% | OBS |
| 2 | R2 | LargeCap | Technology | 2 | 100.0% | 4.0% | OBS |
| 3 | R2 | MidCap | Utilities | 1 | 100.0% | 3.9% | OBS |
| 4 | R2 | MidCap | Basic Materials | 2 | 100.0% | 2.22% | OBS |
| 5 | R2 | MidCap | Financial Services | 1 | 100.0% | 0.99% | OBS |

## Failure profile (bottom 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R2 | MidCap | Energy | 1 | 0.0% | -1.36% | OBS |
| 2 | R2 | MidCap | Consumer Cyclical | 3 | 0.0% | -0.95% | OBS |
| 3 | R2 | MidCap | Healthcare | 2 | 0.0% | -0.6% | OBS |
| 4 | R2 | MidCap | Real Estate | 1 | 0.0% | -0.03% | OBS |
| 5 | R2 | MidCap | Industrials | 1 | 100.0% | 0.45% | OBS |

---
**Governance:** No R1/R2 changes above tier 'observation only'. No interaction claims below tier 'research signal' (n≥15). Winner/failure profiles are early observations · sample sizes noted.