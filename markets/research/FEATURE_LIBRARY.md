# AEGIS Feature Library & Cross-Market Promotion Matrix

Everything AEGIS has learned, by concept and market. Auto-generated from `LEADERBOARD.csv` (`python tools/feature_library.py`). Cross-market lift (✅ in BOTH) is the strongest evidence and the path to production.

| Concept | Domain | USA | India | Scope | Confidence |
|---|---|---|---|---|--:|
| Low-volatility selection | Risk | ✅ production | ✅ production | 🌐 Global | 90 |
| Regime overlay (defensive) | Risk/Timing | ✅ promoted | ✅ promoted | 🌐 Global | 85 |
| HRP weighting | Risk | — | ❌ rejected | Rejected | 80 |
| Stock selection | Portfolio | — | ❌ rejected | Rejected | 80 |
| Momentum | Technical | ✅ production | ❌ rejected | USA-only | 80 |
| Relative strength | Technical | ✅ production | — | USA-only | 90 |
| Universe sizing | Portfolio | — | ❌ rejected | Rejected | 80 |
| Fundamental ratios (ROE/margin/growth/debt) | Fundamental | ❌ rejected | — | Rejected | 83 |
| Fundamental learned blend | Fundamental/ML | ❌ rejected | — | Rejected | 60 |
| PEAD (earnings surprise) | Event | ❌ rejected | — | Rejected | 57 |
| Insider buying (Form 4) | Alternative | — | — | Untested | — |

**Legend:** ✅ production (live engine) / promoted · 🟡 research lead · ❌ rejected (tested, no edge) · — untested · 🌐 Global (works in both markets).

## Reading it today
- **Cross-market validated:** the **regime overlay** now works in BOTH markets — as a **DEFENSIVE risk overlay**, not unconditional alpha (RC010/RC010.1: USA portfolio MaxDD −55%→−38%, Sortino 1.52→1.97, ~2.5pt CAGR cost; de-risks correctly — Weak regime −118%/yr). This is AEGIS's first 🌐 Global concept earned by research, and the closest thing to portable edge.
- **Validated alpha (return):** still essentially none — even the regime overlay is risk management, not return generation. Low-vol selection is the shared production base.
- **USA factors:** every tested *return* concept (fundamental ratios, learned blend, PEAD) is **rejected** on expanded data; insider (Form 4) in research (deep ingest running).
- **Planned domains (⏳):** analyst revisions, 13F, ETF flows, options, macro, news.
- **Next:** characterize the overlay by regime (RC010.2/.3/.4 — done in RC010.1's breakdown) and adopt it as the standard risk layer above the USA paper engine; forward-track live.
