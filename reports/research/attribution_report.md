# AEGIS Attribution Report

**Generated:** 2026-08-31T01:20:04+00:00
**Source:** `reports/research/outcome_dataset.parquet`
**Positions:** 47 total · 27 closed · 20 open

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
| R2 | 25 | 48.0% | 0.606% | -0.03% | 1.85 | SIG |
| R1 | 2 | 0.0% | -5.155% | -5.155% | 0.0 | OBS |

### cap
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| LargeCap | 8 | 50.0% | 0.414% | 1.0% | 1.26 | HYP |
| MidCap | 19 | 42.1% | 0.081% | -0.11% | 1.1 | SIG |

### sector
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| Technology | 4 | 75.0% | 3.343% | 3.94% | 192.0 | OBS |
| Basic Materials | 4 | 75.0% | 1.295% | 0.805% | 20.19 | OBS |
| Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | 2.03 | OBS |
| Industrials | 2 | 100.0% | 0.665% | 0.665% | None | OBS |
| Real Estate | 1 | 0.0% | -0.03% | -0.03% | 0.0 | OBS |
| Utilities | 3 | 33.3% | -0.743% | -0.92% | 0.64 | OBS |
| Financial Services | 4 | 50.0% | -1.478% | -0.72% | 0.34 | OBS |
| Energy | 2 | 0.0% | -1.745% | -1.745% | 0.0 | OBS |
| Healthcare | 3 | 0.0% | -2.097% | -1.08% | 0.0 | OBS |

### initial_investability_verdict
| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |
|---|---|---|---|---|---|---|
| ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | 5.6 | HYP |
| ✓ OK | 8 | 50.0% | 0.419% | 0.44% | 1.34 | HYP |
| 🏆 QUALITY | 4 | 50.0% | -0.675% | 0.165% | 0.5 | OBS |
|  | 2 | 50.0% | -0.775% | -0.775% | 0.36 | OBS |
| ✗ AVOID | 2 | 0.0% | -3.77% | -3.77% | 0.0 | OBS |

## Interaction cross-tabs
### runner x cap
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap | 6 | 66.7% | 2.27% | 2.25% | HYP |
| R2 x MidCap | 19 | 42.1% | 0.081% | -0.11% | SIG |
| R1 x LargeCap | 2 | 0.0% | -5.155% | -5.155% | OBS |

### runner x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x Technology | 4 | 75.0% | 3.343% | 3.94% | OBS |
| R2 x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x Consumer Cyclical | 4 | 25.0% | 0.73% | -0.255% | OBS |
| R2 x Industrials | 2 | 100.0% | 0.665% | 0.665% | OBS |
| R2 x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| R2 x Financial Services | 4 | 50.0% | -1.478% | -0.72% | OBS |
| R2 x Energy | 2 | 0.0% | -1.745% | -1.745% | OBS |
| R1 x Healthcare | 1 | 0.0% | -5.1% | -5.1% | OBS |
| R1 x Utilities | 1 | 0.0% | -5.21% | -5.21% | OBS |

### cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| LargeCap x Financial Services | 1 | 100.0% | 2.07% | 2.07% | OBS |
| MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| MidCap x Industrials | 2 | 100.0% | 0.665% | 0.665% | OBS |
| MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| MidCap x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| LargeCap x Energy | 1 | 0.0% | -2.13% | -2.13% | OBS |
| MidCap x Financial Services | 3 | 33.3% | -2.66% | -2.43% | OBS |
| LargeCap x Healthcare | 1 | 0.0% | -5.1% | -5.1% | OBS |
| LargeCap x Utilities | 1 | 0.0% | -5.21% | -5.21% | OBS |

### runner x cap x sector
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x LargeCap x Consumer Cyclical | 1 | 100.0% | 5.76% | 5.76% | OBS |
| R2 x MidCap x Technology | 1 | 100.0% | 5.45% | 5.45% | OBS |
| R2 x LargeCap x Technology | 3 | 66.7% | 2.64% | 2.43% | OBS |
| R2 x LargeCap x Financial Services | 1 | 100.0% | 2.07% | 2.07% | OBS |
| R2 x MidCap x Utilities | 2 | 50.0% | 1.49% | 1.49% | OBS |
| R2 x MidCap x Basic Materials | 4 | 75.0% | 1.295% | 0.805% | OBS |
| R2 x MidCap x Industrials | 2 | 100.0% | 0.665% | 0.665% | OBS |
| R2 x MidCap x Real Estate | 1 | 0.0% | -0.03% | -0.03% | OBS |
| R2 x MidCap x Healthcare | 2 | 0.0% | -0.595% | -0.595% | OBS |
| R2 x MidCap x Consumer Cyclical | 3 | 0.0% | -0.947% | -0.26% | OBS |
| R2 x MidCap x Energy | 1 | 0.0% | -1.36% | -1.36% | OBS |
| R2 x LargeCap x Energy | 1 | 0.0% | -2.13% | -2.13% | OBS |
| R2 x MidCap x Financial Services | 3 | 33.3% | -2.66% | -2.43% | OBS |
| R1 x LargeCap x Healthcare | 1 | 0.0% | -5.1% | -5.1% | OBS |
| R1 x LargeCap x Utilities | 1 | 0.0% | -5.21% | -5.21% | OBS |

### runner x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| R2 x ⚠ MARGINAL | 11 | 45.5% | 1.208% | -0.03% | HYP |
| R2 x 🏆 QUALITY | 3 | 66.7% | 0.8% | 0.6% | OBS |
| R2 x ✓ OK | 8 | 50.0% | 0.419% | 0.44% | HYP |
| R2 x  | 2 | 50.0% | -0.775% | -0.775% | OBS |
| R2 x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| R1 x 🏆 QUALITY | 1 | 0.0% | -5.1% | -5.1% | OBS |
| R1 x ✗ AVOID | 1 | 0.0% | -5.21% | -5.21% | OBS |

### cap x initial_investability_verdict
| Combination | N | Win% | Avg P&L | Median | Tier |
|---|---|---|---|---|---|
| LargeCap x ⚠ MARGINAL | 3 | 66.7% | 2.64% | 2.43% | OBS |
| LargeCap x ✓ OK | 2 | 50.0% | 1.815% | 1.815% | OBS |
| MidCap x ⚠ MARGINAL | 8 | 37.5% | 0.671% | -0.14% | HYP |
| MidCap x 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | OBS |
| MidCap x ✓ OK | 6 | 50.0% | -0.047% | 0.44% | HYP |
| MidCap x  | 2 | 50.0% | -0.775% | -0.775% | OBS |
| LargeCap x 🏆 QUALITY | 2 | 50.0% | -1.515% | -1.515% | OBS |
| MidCap x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| LargeCap x ✗ AVOID | 1 | 0.0% | -5.21% | -5.21% | OBS |

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
| Industrials x  | 1 | 100.0% | 0.88% | 0.88% | OBS |
| Industrials x ⚠ MARGINAL | 1 | 100.0% | 0.45% | 0.45% | OBS |
| Basic Materials x 🏆 QUALITY | 2 | 50.0% | 0.165% | 0.165% | OBS |
| Real Estate x ⚠ MARGINAL | 1 | 0.0% | -0.03% | -0.03% | OBS |
| Consumer Cyclical x ⚠ MARGINAL | 2 | 0.0% | -0.255% | -0.255% | OBS |
| Healthcare x ✓ OK | 2 | 0.0% | -0.595% | -0.595% | OBS |
| Energy x ⚠ MARGINAL | 1 | 0.0% | -1.36% | -1.36% | OBS |
| Energy x ✓ OK | 1 | 0.0% | -2.13% | -2.13% | OBS |
| Consumer Cyclical x ✗ AVOID | 1 | 0.0% | -2.33% | -2.33% | OBS |
| Financial Services x  | 1 | 0.0% | -2.43% | -2.43% | OBS |
| Financial Services x ✓ OK | 2 | 50.0% | -2.775% | -2.775% | OBS |
| Healthcare x 🏆 QUALITY | 1 | 0.0% | -5.1% | -5.1% | OBS |
| Utilities x ✗ AVOID | 1 | 0.0% | -5.21% | -5.21% | OBS |

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
| 1 | R1 | LargeCap | Utilities | 1 | 0.0% | -5.21% | OBS |
| 2 | R1 | LargeCap | Healthcare | 1 | 0.0% | -5.1% | OBS |
| 3 | R2 | MidCap | Financial Services | 3 | 33.3% | -2.66% | OBS |
| 4 | R2 | LargeCap | Energy | 1 | 0.0% | -2.13% | OBS |
| 5 | R2 | MidCap | Energy | 1 | 0.0% | -1.36% | OBS |

---
**Governance:** No R1/R2 changes above tier 'observation only'. No interaction claims below tier 'research signal' (n≥15). Winner/failure profiles are early observations · sample sizes noted.