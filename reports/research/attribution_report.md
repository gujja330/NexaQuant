# AEGIS Attribution Report

**Generated:** 2026-09-02T01:02:57+00:00
**Source:** `reports/research/outcome_dataset.parquet`
**Positions:** 50 total · 32 closed · 18 open

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
| R2 | 29 | 44.8% | 0.265% | -0.03% | 1.27 | SIG |
| R1 | 3 | 0.0% | -5.293% | -5.21% | 0.0 | OBS |

### cap
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| LargeCap | 10 | 40.0% | -0.226% | -0.035% | 0.88 | HYP |
| MidCap | 22 | 40.9% | -0.27% | -0.18% | 0.78 | SIG |

### sector
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| Technology | 4 | 75.0% | 3.343% | 3.94% | 192.0 | OBS |
| Basic Materials | 4 | 75.0% | 1.295% | 0.805% | 20.19 | OBS |
| Industrials | 3 | 66.7% | 1.26% | 0.45% | None | OBS |
| Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | 2.03 | OBS |
| Real Estate | 1 | 0.0% | -0.03% | -0.03% | 0.0 | OBS |
| Communication Services | 1 | 0.0% | -0.8% | -0.8% | 0.0 | OBS |
| Financial Services | 5 | 60.0% | -0.882% | 0.99% | 0.49 | HYP |
| Energy | 2 | 0.0% | -1.745% | -1.745% | 0.0 | OBS |
| Utilities | 4 | 25.0% | -1.95% | -3.065% | 0.33 | OBS |
| Healthcare | 4 | 0.0% | -4.227% | -3.09% | 0.0 | OBS |

### initial_investability_verdict
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | 5.6 | HYP |
| ✓ OK | 8 | 50.0% | 0.419% | 0.44% | 1.34 | HYP |
|  | 5 | 40.0% | 0.32% | 0.0% | 1.57 | HYP |
| 🏆 QUALITY | 5 | 40.0% | -2.664% | -0.27% | 0.17 | HYP |
| ✗ AVOID | 3 | 0.0% | -4.37% | -5.21% | 0.0 | OBS |

## Interaction cross-tabs
### runner x cap
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap | 7 | 57.1% | 1.946% | 2.07% | HYP |
| R2 x MidCap | 22 | 40.9% | -0.27% | -0.18% | SIG |
| R1 x LargeCap | 3 | 0.0% | -5.293% | -5.21% | OBS |

### runner x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x Technology | 4 | 75.0% | 3.343% | 3.94% | OBS |
| R2 x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x Industrials | 3 | 66.7% | 1.26% | 0.45% | OBS |
| R2 x Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | OBS |
| R2 x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x Communication Services | 1 | 0.0% | -0.8% | -0.8% | OBS |
| R2 x Financial Services | 5 | 60.0% | -0.882% | 0.99% | HYP |
| R2 x Energy | 2 | 0.0% | -1.745% | -1.745% | OBS |
| R2 x Healthcare | 3 | 0.0% | -3.937% | -1.08% | OBS |
| R1 x Healthcare | 1 | 0.0% | -5.1% | -5.1% | OBS |
| R1 x Utilities | 2 | 0.0% | -5.39% | -5.39% | OBS |

### cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| LargeCap x Financial Services | 1 | 100.0% | 2.07% | 2.07% | OBS |
| MidCap x Industrials | 2 | 100.0% | 1.89% | 1.89% | OBS |
| MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| MidCap x Communication Services | 1 | 0.0% | -0.8% | -0.8% | OBS |
| MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| MidCap x Financial Services | 4 | 50.0% | -1.62% | -0.52% | OBS |
| LargeCap x Energy | 1 | 0.0% | -2.13% | -2.13% | OBS |
| MidCap x Healthcare | 3 | 0.0% | -3.937% | -1.08% | OBS |
| LargeCap x Healthcare | 1 | 0.0% | -5.1% | -5.1% | OBS |
| LargeCap x Utilities | 2 | 0.0% | -5.39% | -5.39% | OBS |
| LargeCap x Industrials | 1 | 0.0% | 0.0% | 0.0% | OBS |

### runner x cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| R2 x MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| R2 x LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| R2 x LargeCap x Financial Services | 1 | 100.0% | 2.07% | 2.07% | OBS |
| R2 x MidCap x Industrials | 2 | 100.0% | 1.89% | 1.89% | OBS |
| R2 x MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x MidCap x Communication Services | 1 | 0.0% | -0.8% | -0.8% | OBS |
| R2 x MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| R2 x MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| R2 x MidCap x Financial Services | 4 | 50.0% | -1.62% | -0.52% | OBS |
| R2 x LargeCap x Energy | 1 | 0.0% | -2.13% | -2.13% | OBS |
| R2 x MidCap x Healthcare | 3 | 0.0% | -3.937% | -1.08% | OBS |
| R1 x LargeCap x Healthcare | 1 | 0.0% | -5.1% | -5.1% | OBS |
| R1 x LargeCap x Utilities | 2 | 0.0% | -5.39% | -5.39% | OBS |
| R2 x LargeCap x Industrials | 1 | 0.0% | 0.0% | 0.0% | OBS |

### runner x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | HYP |
| R2 x ✓ OK | 8 | 50.0% | 0.419% | 0.44% | HYP |
| R2 x  | 5 | 40.0% | 0.32% | 0.0% | HYP |
| R2 x 🏆 QUALITY | 4 | 50.0% | -2.055% | 0.165% | OBS |
| R2 x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| R1 x 🏆 QUALITY | 1 | 0.0% | -5.1% | -5.1% | OBS |
| R1 x ✗ AVOID | 2 | 0.0% | -5.39% | -5.39% | OBS |

### cap x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x ⚠ MARGINAL | 3 | 66.7% | 2.64% | 2.43% | OBS |
| LargeCap x ✓ OK | 2 | 50.0% | 1.815% | 1.815% | OBS |
| MidCap x ⚠ MARGINAL | 8 | 37.5% | 0.671% | -0.14% | HYP |
| MidCap x  | 4 | 50.0% | 0.4% | 0.15% | OBS |
| MidCap x ✓ OK | 6 | 50.0% | -0.047% | 0.44% | HYP |
| LargeCap x 🏆 QUALITY | 2 | 50.0% | -1.515% | -1.515% | OBS |
| MidCap x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| MidCap x 🏆 QUALITY | 3 | 33.3% | -3.43% | -0.27% | OBS |
| LargeCap x ✗ AVOID | 2 | 0.0% | -5.39% | -5.39% | OBS |
| LargeCap x  | 1 | 0.0% | 0.0% | 0.0% | OBS |

### sector x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| Consumer Cyclical x ✓ OK | 1 | 100.0% | 5.76% | 5.76% | OBS |
| Technology x ✓ OK | 1 | 100.0% | 5.45% | 5.45% | OBS |
| Basic Materials x ⚠ MARGINAL | 1 | 100.0% | 3.84% | 3.84% | OBS |
| Technology x ⚠ MARGINAL | 3 | 66.7% | 2.64% | 2.43% | OBS |
| Financial Services x 🏆 QUALITY | 1 | 100.0% | 2.07% | 2.07% | OBS |
| Industrials x  | 2 | 50.0% | 1.665% | 1.665% | OBS |
| Utilities x ⚠ MARGINAL | 2 | 50.0% | 1.49% | 1.49% | OBS |
| Basic Materials x ✓ OK | 1 | 100.0% | 1.01% | 1.01% | OBS |
| Industrials x ⚠ MARGINAL | 1 | 100.0% | 0.45% | 0.45% | OBS |
| Basic Materials x 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | OBS |
| Real Estate x ⚠ MARGINAL | 1 | 0.0% | -0.03% | -0.03% | OBS |
| Consumer Cyclical x ⚠ MARGINAL | 2 | 0.0% | -0.255% | -0.255% | OBS |
| Financial Services x  | 2 | 50.0% | -0.465% | -0.465% | OBS |
| Healthcare x ✓ OK | 2 | 0.0% | -0.595% | -0.595% | OBS |
| Communication Services x  | 1 | 0.0% | -0.8% | -0.8% | OBS |
| Energy x ⚠ MARGINAL | 1 | 0.0% | -1.36% | -1.36% | OBS |
| Energy x ✓ OK | 1 | 0.0% | -2.13% | -2.13% | OBS |
| Consumer Cyclical x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| Financial Services x ✓ OK | 2 | 50.0% | -2.775% | -2.775% | OBS |
| Utilities x ✗ AVOID | 2 | 0.0% | -5.39% | -5.39% | OBS |
| Healthcare x 🏆 QUALITY | 2 | 0.0% | -7.86% | -7.86% | OBS |

## Winner profile (top 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R2 | LargeCap | Consumer Cyclical | 1 | 100.0% | 5.76% | OBS |
| 2 | R2 | MidCap | Technology | 1 | 100.0% | 5.45% | OBS |
| 3 | R2 | LargeCap | Technology | 3 | 66.7% | 2.64% | OBS |
| 4 | R2 | LargeCap | Financial Services | 1 | 100.0% | 2.07% | OBS |
| 5 | R2 | MidCap | Industrials | 2 | 100.0% | 1.89% | OBS |

## Failure profile (bottom 5 · Runner × Cap × Sector)
| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |
|---|---|---|---|---|---|---|---|
| 1 | R1 | LargeCap | Utilities | 2 | 0.0% | -5.39% | OBS |
| 2 | R1 | LargeCap | Healthcare | 1 | 0.0% | -5.1% | OBS |
| 3 | R2 | MidCap | Healthcare | 3 | 0.0% | -3.94% | OBS |
| 4 | R2 | LargeCap | Energy | 1 | 0.0% | -2.13% | OBS |
| 5 | R2 | MidCap | Financial Services | 4 | 50.0% | -1.62% | OBS |

---
**Governance:** No R1/R2 changes above tier 'observation only'. No interaction claims below tier 'research signal' (n≥15). Winner/failure profiles are early observations · sample sizes noted.