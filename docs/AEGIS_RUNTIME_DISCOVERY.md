# AEGIS Runtime Discovery · Intelligence + Recommendation Lineage
**Stage 0.5 deliverable · Top-down runtime traversal, per stock**

---

## A. Intelligence lineage (designed 4-tier, ACTUAL 1-tier)

### Design (per `docs/ARCH017_GLOBAL_INTELLIGENCE_ENGINE.md` and DEV017-020)

```
Global Intelligence (macro, regime, breadth, VIX, currency)
      │
      ▼
Sector Intelligence (relative strength, momentum, breadth per sector)
      │
      ▼
Industry Intelligence (per-industry aggregate, inheritance from sector)
      │
      ▼
Company Intelligence (11-dim composite per ticker, full inheritance chain)
      │
      ▼
Fusion → Risk → Recommendation
```

### Reality (per this audit)

All four engines ran **exactly once on 2026-07-17** and produced JSON outputs. Since then, the daily pipeline reads those frozen files as if they were current.

```
[FROZEN 2026-07-17 14:37] global_context.json
       │
       ▼  (15+ readers, treated as live)
[FROZEN 2026-07-17 14:48] sector_context.json
       │
       ▼  (inherited by industry + company)
[FROZEN 2026-07-17 15:04] industry_context.json
       │
       ▼
[FROZEN 2026-07-17 15:47] company_context.json  ← terminal, no live consumer
```

The **actual live regime signal** used by `india/recommendation_generator.py` is NOT this 4-tier hierarchy — it is `india/confidence_engine.current_regime()` producing a simple "global" state (Nifty 200-DMA + India VIX + Global-Risk gate). See `india/config.py:56` (`regime: str = "global"`) and `india/recommendation_generator.py:44` (`CONFIG = dict(method="hrp", regime="global", ...)`).

**So the runtime picture is:**
- Live: 1-tier regime engine (`confidence_engine.current_regime()`) → HRP portfolio construction (`arjuna_strategy`) → basket → v2 chain
- Frozen: the 4-tier engine chain, still consumed by many downstream steps but with stale inputs

## B. Recommendation lineage (per stock, e.g. IPCALAB)

### India — actual runtime path

```
1. yfinance daily bar for IPCALAB.NS
        ▼
2. india/refresh_data.py writes data/raw/india/IPCALAB_D1.parquet
        ▼
3. india/feature_engine.py + india/technical_factors.py compute technicals
   (momentum, trend, RSI, volatility, drawdown, 52-week position, ADX, etc.)
        ▼
4. india/confidence_engine.current_regime() → "risk-on" / "de-risked"
   (based on Nifty 200-DMA + India VIX + global_risk from india/global_risk.py)
        ▼
5. india/arjuna_strategy.screen() → passes quality filter?
        ▼
6. india/arjuna_v2.py + india/recommendation_generator.py:
   - HRP weighting across selected universe
   - regime-gated exposure sizing
   - global-risk multiplier applied
        ▼
7. Write data/aegis_today.csv + AEGIS_LATEST.xlsx (LIVE)
        ▼
8. scripts/aegis_daily_v2.py --continue kicks in
        ▼
9. research/adaptive_rec_v2/run.py rebuilds recommendations.json
   using learning.parquet (STALE 2026-07-17) — HistGradientBoosting +
   permutation_importance
        ▼
10. research/adaptive_rec_v2/run_fusion.py combines:
    - technicals (from feature_engine)
    - dna feedback (from run_feedback.py step 4)
    - knowledge graph signals (from step 5)
    - IF ii_r has values, computes intelligence_score (0-100)
        ▼
11. reports/investment_intelligence.json IPCALAB row now has:
    intelligence_score, fusion_decision, dimensions[], why_this,
    why_not_stronger, top_contributors, conflicts
        ▼
12. research/risk_capital_v2 sizes IPCALAB position
    (reads global_context.json — STALE 2026-07-17)
        ▼
13. research/decision_center diffs vs yesterday's archive
        ▼
14. research/institutional_memory archives + updates lifecycle
        ▼
15. research/winner_genome mines learning.parquet (STALE) for signature
        ▼
16. research/decision_attribution computes per-subsystem contribution
        ▼
17. research/benchmark compares to NIFTY 50 over historical trades
        ▼
18. research/morning_report renders IPCALAB into the top-10 table
        ▼
19. SPA (ux/dashboard/frontend/index.html) reads all the above,
    renders IPCALAB Decision Card
        ▼
20. Telegram UX030 (scripts/telegram_send_ux030.py) renders IPCALAB
    into the "Top Opportunities" message
```

**Stale-input distortion points:** steps 9, 12, 15 (learning.parquet + global_context.json). Steps 10-11 (fusion) blend live technicals with stale intelligence layers, so the composite score is a hybrid of fresh + stale.

### USA — actual runtime path (structural mirror, single-tier)

```
1. yfinance daily bar for AAPL
        ▼
2. usa/scripts/refresh_market_data.py writes usa/data/raw/us/AAPL_D1.parquet
        ▼
3. usa/research/recommendations/run.py:
   - compute 6 technical dimensions (momentum, trend, RS vs SPX,
     volatility, drawdown, 52W position)
   - blend into composite_decision_score (0-100)
   - map score → action (Strong-Buy / Buy / Accumulate / Hold / Reduce / Sell)
   - compute entry/target/stop from ATR
        ▼
4. usa/research/validation/run.py (baseline stub — no closed trades yet)
        ▼
5. usa/research/risk/run.py — position sizing + sector caps
        ▼
6. usa/research/fusion/run.py — 6-dim aggregate + conflicts
        ▼
7. usa/research/price_context/run.py — CMP + 52W bounds
        ▼
8. usa/research/institutional_memory/run.py — archive + lifecycle
        ▼
9. usa/research/winner_genome/run.py — INSUFFICIENT_DATA (no corpus)
        ▼
10. usa/research/decision_attribution/run.py — per-rec only,
    no subsystem accuracy (no historical outcomes)
        ▼
11. usa/research/benchmark/run.py — INSUFFICIENT_EVIDENCE
        ▼
12. usa/research/morning_report/run.py — HTML + MD
        ▼
13. usa/scripts/usa_ops_check.py — HEALTHY verdict
        ▼
14. usa/scripts/telegram_send.py (optional)
        ▼
15. compare/build_comparison.py — India vs USA side-by-side
```

**USA is 100% technicals-only, with no historical-outcome layers active.** Winner Genome, Decision Attribution accuracy, and Benchmark all emit "insufficient data" placeholders until USA accumulates closed trades.

## C. Where each score actually comes from

For an India Strong-Buy signal on a given ticker, the composite Investment Decision Score is currently a blend of:

| Component | Weight (per SPA `computeInvestmentDecisionScore`) | Freshness of underlying |
|---|---|---|
| `intelligence_score` (from `investment_intelligence.json`) | 55% | LIVE (recomputed daily, but blends stale intelligence layers) |
| Historical win_rate × 100 (from `stock_validation.json`, if n_trades ≥ 3) | 20% | STALE (backed by `learning.parquet` frozen since 2026-07-17) |
| Confidence × 100 (from `recommendations.json`) | 15% | LIVE (from adaptive_rec_v2) |
| Reliability_stars × 20 (from `stock_validation.json`) | 10% | STALE (same as above) |

**30% of the composite score by weight is derived from data frozen since 2026-07-17.** The remaining 70% is live but recycled through fusion steps that also read frozen `global_context.json`.

## D. Backend validation lineage

### India

- `scripts/aegis_ops_check.py` (step 15 of v2) — checks 22 required artifacts exist + parse as JSON. **No recency check.** No content validation beyond top-level key presence in a small schemas dict (line 121-160).
- `india/ops_check.py` (step in `aegis-daily.yml`) — legacy ops check, ran non-critically (masked).
- `research/validation_v2/run.py` (step 2) — paper harness, drift over closed trades, expected-vs-actual. Its own artifact `validation_v2_latest.json` reports drift verdicts, but consumes stale `learning.parquet`.
- `nexaquant/tests/` — CI-only, code-level regression on lib + ops modules.

### USA

- `usa/scripts/usa_ops_check.py` — mirror of India's, 18 artifacts + 9 schemas. Same no-recency-check limitation.

**Neither market's ops check would catch FINDING 1 or FINDING 2** (stale corpus, stale intelligence tiles). The freshness gap is invisible to current monitoring.

## E. Explainability chain (per stock)

- SPA Decision Card displays `reasons_for` + `reasons_against` (from `recommendations.json`) humanized via `humanizeReason()` map
- SPA Stock Detail displays the Fusion "Decision Breakdown" — 10 dimensions per stock from `investment_intelligence.json`'s `reports[i].dimensions[]`
- Winner Genome displays plain-language "Looks similar to N historical winners" (from `winner_genome.json` matches)
- Decision Attribution displays per-subsystem contribution % (from `decision_attribution.json.per_recommendation[ticker].contributions`)
- Morning Report renders top-10 with score / target / stop / hold / α vs NIFTY

**All of this uses live 2026-07-20 data at the top layers, but the historical / winner / attribution content is grounded in the frozen `learning.parquet` corpus.**
