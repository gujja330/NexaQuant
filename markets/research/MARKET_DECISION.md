# Program X — Market Comparison & Decision (MARKET_DECISION.md)

Evidence-based decision on each market's long-term role. MC002 is computed from the Leaderboard; other sections are evidence-grounded assessment (J = judgment, F = factual).

## MC001 — Data Quality & Availability
| Dimension | India | USA |
|---|---|---|
| Price history (F) | ~5y usable panels | **decades** (SPX 1927; stocks up to 64y) |
| Liquid universe (F) | few hundred (NSE) | **5,000+ screened → 227 liquid, expandable** |
| PIT fundamentals (F) | limited/costly | **SEC EDGAR — free, official, filed-date** |
| Insider data (F) | sparse/unclean | **SEC Form 4 — free, ~2-day PIT** |
| 13F / ETF / macro (F) | mostly unavailable free | **all free (SEC 13F, issuers, FRED)** |
| Survivorship-free source (F) | hard | hard (both need CRSP/Norgate eventually) |
| Free availability / API (F) | broker-gated | **fully free + stable (SEC/Yahoo/FRED)** |
| → MC001 winner | | **USA (decisively)** |

## MC002 — Research Success (computed from the Leaderboard)
| Metric | India | USA |
|---|---|---|
| Experiments (ex-superseded) | 5 | 11 |
| Promoted | 1 | 1 |
| Rejected / closed | 4 | 9 |
| Investigating | 0 | 1 |
| Avg confidence | 81 | 53 |
| → MC002 read | concentrated: 1 validated edge | high throughput, mostly rejections |

**Key finding:** neither market has demonstrated stock-**selection** alpha. The ONLY validated edge — the regime overlay — is **cross-market** (works in both). So 'which market discovers edges' is largely the wrong question: the edge we found is market-agnostic.

## MC003 — Production Comparison (J/F)
- **India:** LIVE production engine — daily automation (GitHub Actions), Telegram + Google Sheets, recommendation DB, frozen v1.x baseline. Real operational track record. (F)
- **USA:** paper-only; no live track record yet. (F)
- Both engines are the SAME core via adapters; India is simply further along operationally.
- → **Production winner: India** (maturity/operations), not because of better alpha.

## MC004 — Research Cost (J)
- **USA:** richer data but heavier pipelines (deep ingest, shards, large universes → more compute/storage/maintenance). **India:** smaller, simpler, cheaper to run, but expensive/hard to *expand* (little free alt-data). → Cost-per-experiment favors India today; cost-to-scale favors USA.

## MC005 — Expandability (F/J)
- **USA wins decisively:** insider, 13F, ETF, options, macro (FRED), news — all free and PIT. India has few comparable free alternative datasets. → **USA**.

## MC006 — Commercial Opportunity (J)
- Larger addressable market, deeper liquidity, more data vendors and customers in **USA/Global**; India is a strong secondary. (Business judgment, not a research result.) → **USA/Global**.

## Scorecard (ratings are judgment, 1–5)
| Category | India | USA | Winner |
|---|--:|--:|---|
| Data quality/depth | 2 | 5 | USA |
| Research success (edges found) | 3 | 3 | Tie (edge is cross-market) |
| Production maturity | 5 | 2 | India |
| Research cost (cheap to run) | 4 | 3 | India |
| Expandability | 2 | 5 | USA |
| Commercial/scale | 3 | 5 | USA |
| AI potential (data diversity) | 2 | 5 | USA |

## Decision — DEFERRED (do not optimize early)
The earlier draft froze a USA-research / India-production split. That is **premature**: with ~17 experiments (mostly rejections) and neither market's R&D close to complete, choosing a market now would be preference, not evidence. The role-split above is a **hypothesis to test**, not a commitment. **Only one thing is locked now — the market-AGNOSTIC core** (the `MarketAdapter` seam), because that is architecture, not a market bet, and the one validated edge (regime overlay) is already cross-market.

**The capital-allocation / product decision is postponed until BOTH research libraries are complete and portfolio simulations have run.** Phased plan:
1. **Complete India R&D** — every domain through the gate (price/trend/momentum/vol/regime/quality/value/growth/seasonality/volume/breadth/insider/macro/ETF/news/ML/ensemble/risk). Goal: no major area left unexplored. (tracker: `DOMAIN_COVERAGE.md`)
2. **Complete USA R&D** — the IDENTICAL pipeline/methodology, same gate.
3. **Cross-market validation** — which factors are universal vs India-only vs USA-only.
4. **Portfolio simulation** — India-only / USA-only / 50-50 / 70-30 / dynamic-allocation, identical assumptions, long history.
5. **Capital-allocation & product decision** — where *our money* goes and what AEGIS *recommends* — from the completed evidence, not a predefined preference.

_Pending: RC005 (insider) deep ingest still running. Next per plan: finish RC005 → complete India R&D → complete USA R&D → freeze libraries → portfolio sims → final decision._
