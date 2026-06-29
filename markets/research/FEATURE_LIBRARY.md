# AEGIS Feature Library & Cross-Market Promotion Matrix

Everything AEGIS has learned, by concept and market. Auto-generated from `LEADERBOARD.csv` (`python tools/feature_library.py`). Cross-market lift (✅ in BOTH) is the strongest evidence and the path to production.

| Concept | Domain | USA | India | Scope |
|---|---|---|---|---|
| Low-volatility selection | Risk | ✅ production | ✅ production | 🌐 Global |
| Regime timing overlay | Timing | — | ✅ production | India-only |
| HRP weighting | Risk | — | ❌ rejected | Rejected |
| Stock selection | Portfolio | — | ❌ rejected | Rejected |
| Momentum | Technical | ✅ production | ❌ rejected | USA-only |
| Relative strength | Technical | ✅ production | — | USA-only |
| Universe sizing | Portfolio | — | ❌ rejected | Rejected |
| Fundamental ratios (ROE/margin/growth/debt) | Fundamental | ❌ rejected | — | Rejected |
| Fundamental learned blend | Fundamental/ML | ❌ rejected | — | Rejected |
| PEAD (earnings surprise) | Event | ❌ rejected | — | Rejected |
| Insider buying (Form 4) | Alternative | — | — | Untested |

**Legend:** ✅ production (live engine) / promoted · 🟡 research lead · ❌ rejected (tested, no edge) · — untested · 🌐 Global (works in both markets).

## Reading it today
- **Validated alpha:** only the **regime timing overlay (India)** — the rest of India's stack (HRP, selection, momentum) adds ~nothing over equal-weight; low-vol selection is the shared production base in both markets.
- **USA:** every tested concept (fundamental ratios, learned blend, PEAD) is **rejected** on expanded data; insider (Form 4) is in research (deep ingest running).
- **Cross-market gap:** no concept is yet ✅ in BOTH markets by *research evidence* (low-vol is production-shared but not separately gated as alpha). Closing this — e.g. testing the India regime overlay on USA — is the highest-value cross-market experiment.
- **Planned domains (⏳):** analyst revisions, 13F, ETF flows, options, macro, news — each enters as its own concept once acquired.
