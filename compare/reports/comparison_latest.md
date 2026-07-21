# 🇮🇳 India vs 🇺🇸 USA · Cross-Market Comparison
_Generated 2026-07-20T07:50:18+00:00Z_

| Metric | 🇮🇳 India | 🇺🇸 USA |
|---|---|---|
| Currency | INR (₹) | USD ($) |
| Benchmark | NIFTY 50 | S&P 500 |
| Universe size | 208 | 30 |
| Strong-Buy | 7 | 6 |
| Buy | 44 | 3 |
| Accumulate | 0 | 3 |
| Hold | 0 | 4 |
| Reduce | 0 | 11 |
| Sell | 0 | 3 |
| Positions sized | — | 12 |
| Deployed % | 0.00% | 92.00% |
| Cash % | 0.00% | 8.00% |
| Portfolio vol % | 19.26% | 29.03% |
| Risk verdict | WARNING | PASS |
| Trades benchmarked | 1060 | 0 |
| Historical alpha vs benchmark | +1.31% | — |
| % beat benchmark | 52.17% | — |
| Benchmark verdict | at_par | insufficient_evidence |
| Archive days | 2/30 | 1/30 |
| Ops verdict | CRITICAL | HEALTHY |
| Artifacts present | 23/23 | 19/19 |

## Independence

India and USA are **fully independent deployments**. They share the repo but nothing else:

- Different currencies (INR ₹ vs USD $)
- Different universes (Nifty vs Dow 30)
- Different benchmarks (NIFTY vs S&P 500)
- Different archives (`data/archive/` vs `usa/data/archive/`)
- Different Constitutions (`AEGIS_CONSTITUTION.md` vs `usa/AEGIS_USA_CONSTITUTION.md`)
- Different CI workflows (`aegis-ci.yml` vs `aegis-usa.yml`)

Breaking one never affects the other.
