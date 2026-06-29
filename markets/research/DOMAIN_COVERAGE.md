# Research Domain Coverage — India vs USA

Tracks Phase 1 (complete India R&D) and Phase 2 (complete USA R&D) toward "no major research area left
unexplored," under the IDENTICAL gate. Update as each domain gets a logged verdict in the Leaderboard.

**Legend:** ✅ done (verdict logged) · 🟡 partial / running · ⬜ pending · ▫️ data-limited (no clean free
source for that market) · — n/a

| Domain | India | USA | Notes |
|---|:--:|:--:|---|
| Price action / trend | 🟡 | 🟡 | trend embedded in regime (200-DMA); not gated as a standalone factor |
| Momentum | ✅ | 🟡 | India pure-momentum rejected (loses to index); USA t_mom production-used, not gated as alpha |
| Volatility (low-vol) | ✅ | ✅ | low-vol selection is the shared production base (both markets) |
| Regime timing | ✅ | ✅ | **cross-market defensive overlay (Global)** — RC010/.1 |
| Quality (ROE/margin) | ⬜ | ✅ | USA rejected (flat on 14y); India pending |
| Value (P/E, P/B, FCF) | ⬜ | ⬜ | not yet tested either market |
| Growth (rev/earnings) | ⬜ | ✅ | USA revenue-growth rejected (flat 14y); India pending |
| Earnings / PEAD | ⬜ | ✅ | USA naive-YoY surprise rejected; India pending |
| Seasonality | ⬜ | ⬜ | pending both |
| Volume / liquidity | ⬜ | ⬜ | pending both |
| Breadth | 🟡 | 🟡 | used in sector intelligence, not gated as a factor |
| Insider (Form 4) | ▫️ | 🟡 | USA deep ingest running (RC005); India lacks a clean free source |
| Macro (rates/FX/credit) | ⬜ | ⬜ | pending both (FRED free for USA; India macro thinner) |
| ETF / fund flows | ▫️ | ⬜ | USA free; India limited |
| 13F / institutional | ▫️ | ⬜ | USA free; India n/a |
| News / sentiment | ⬜ | ⬜ | India has a news_sentiment feed (ungated); USA via RSS |
| Analyst revisions | ▫️ | ⬜ | needs a source (no free analyst estimates) |
| ML / learned blend | ⬜ | ✅ | USA learned blend rejected (no edge over equal-weight); India pending |
| Ensemble | ⬜ | ⬜ | only after multiple validated single-factor domains exist |
| Risk models | ✅ | ✅ | regime overlay (risk) cross-market; HRP tested India (neutral) |

## Reading it
- **Done with a verdict:** volatility ✅, regime ✅ (both markets), plus USA quality/growth/earnings/ML (all
  rejected) and India momentum (rejected). The validated survivors are **low-vol selection** and the
  **regime overlay** — both market-agnostic.
- **Biggest gaps:** value, seasonality, volume, macro, news — untested in BOTH markets; the bulk of India's
  factor R&D is still pending (India was built as production first, research second).
- **Data-limited (▫️) for India:** insider, ETF, 13F, analyst — no clean free source. This itself is
  evidence for Phase 5 (USA is the richer research market) but is NOT yet a decision.
- **Phase gate:** do not start Phase 3 (cross-validation) or Phase 4 (portfolio simulation) until the ⬜
  rows are closed (tested or explicitly data-limited) under the same gate in both markets.
