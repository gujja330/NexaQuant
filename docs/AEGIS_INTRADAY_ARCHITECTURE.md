# AEGIS Intraday Architecture · Ticket R004

**Status**: DEFERRED · specification-only · zero code today
**Owner**: AEGIS
**Author**: 2026-07-30 · under Article IX (Research Lifecycle)
**Markets**: India NSE 200 · USA S&P 500 + MidCap 400 (parallel · same architecture)
**Depends on**: none · greenfield build after delivery platform is validated

---

## 1 · Why a separate document

The current AEGIS product is a **swing / delivery** engine (17–60 day holds). An earlier "intraday shadow" experiment tried to reuse swing picks as an intraday measurement corpus — that was scientifically weak and operator-rejected on 2026-07-30 with the note:

> *"runner 1 daily stocks into intraday is useless. i dont agree this setup. we need real platform else no use."*

This document specifies the **real intraday engine** to be built when calendar allows. It is a **standalone parallel product** to delivery — different candidate universe, different signals, different exit rules, different execution profile, different risk model.

## 2 · What the intraday engine must be

Intraday means: **enter after open, exit before close, no overnight risk**. That constraint drives a different stack from delivery.

### 2.1 Product surface
- **Advisory only** (same constitutional constraint as delivery)
- **Paper trading only** during entire evaluation window
- **India first** (larger volume tail, session structure well-known)
- **USA second** (once India validates)
- **No user-facing recommendations until VALIDATED_90D** per Article IX

### 2.2 What we will NOT do
- Not touch the swing engine
- Not share ranking, scoring, or ensemble weights with delivery
- Not use daily OHLC bars as a proxy for intraday behavior
- Not run inside the main SSoT daily pipeline (belongs on its own cadence)
- Not promise sub-minute latency (institutional swing-flow speeds only)

## 3 · Data sources required (currently missing)

| Category | Source | Refresh | Cost |
|---|---|---|---|
| Minute bars (India) | Zerodha Kite / Alpha Vantage / TrueData | 1-min live during session · EOD backfill | Kite: ₹2000/mo · AV free tier limited |
| Minute bars (USA) | Polygon.io / Alpaca / IEX | 1-min live · EOD backfill | Polygon Starter $29/mo |
| Depth-of-book snapshot | Zerodha Kite WebSocket (India) · Polygon WebSocket (USA) | live | included with feed |
| Corporate actions today | NSE / NASDAQ end-of-day | daily | free (already have EOD) |
| Sector-ETF intraday flow | yfinance 1-min OHLCV on sector ETFs | 1-min | free |
| VIX intraday | yfinance ^INDIAVIX, ^VIX | 1-min | free |
| News intraday | Google News RSS + Reuters wire | 15-min polling | free basic |
| Earnings-window filter | existing earnings calendar | daily | already have |

**Cost estimate**: ₹2000/mo India feed + $29/mo USA feed ≈ **$50/mo running cost** for real intraday. Zero external cost until feeds turned on.

## 4 · Universe (each market · independent)

Intraday universe is **strictly a subset** of the delivery universe, filtered by intraday tradability rules:

### 4.1 India intraday universe filter (from NSE 200)
- Average daily volume ≥ 5,00,000 shares (last 20 days)
- Median bid-ask spread ≤ 0.10% (from level-1 snapshot)
- Not in delivery-only trade group (T2T)
- Not in F&O ban list today
- Not on earnings-today or ex-div-today filter
- Rolling 20-day realized vol between 1.0% and 4.0% (avoids dead + circuit-breaker names)

Expected cardinality: ~80–120 tickers per session.

### 4.2 USA intraday universe filter (from S&P 500 + MidCap 400)
- Average daily volume ≥ 2M shares (last 20 days)
- Median bid-ask spread ≤ 3 bps
- Not on Reg SHO threshold list
- Not on earnings-today filter
- Not halted today
- Price ≥ $10 (avoids penny drift)

Expected cardinality: ~250–400 tickers per session.

## 5 · Signal factories (five parallel models)

Each factory produces one intraday score per candidate. Ensembled at session-start (09:30 IST / 09:35 ET) after the opening auction settles.

### 5.1 Opening Range Breakout (ORB)
- **Idea**: momentum from opening 15-min range extension
- **Input**: 1-min bars from open to open+15min
- **Score**: +1 when price closes above open-range-high on volume ≥ 1.5× 15-min average, −1 when closes below open-range-low on same volume, 0 otherwise
- **Regime**: works best in trending sessions (session VIX flat)

### 5.2 Gap-and-Go
- **Idea**: overnight gap continuation
- **Input**: prev_close, today_open, opening 5-min volume
- **Score**: proportional to gap % × opening-5-min volume z-score
- **Filter**: gap must be > 0.5% and news-catalyst-verified (news feed cross-check)

### 5.3 VWAP-Reversion
- **Idea**: mean-revert when price deviates from VWAP with declining volume
- **Input**: 5-min bars, session VWAP
- **Score**: −(price − VWAP) / VWAP when 5-min volume is below session-average
- **Regime**: works in range-bound sessions (session VIX up)

### 5.4 Sector-Momentum Follow
- **Idea**: stock follows its sector-ETF's intraday move
- **Input**: 1-min intraday returns on the stock and its sector ETF
- **Score**: rolling 30-min correlation × current sector-ETF intraday return
- **Filter**: only fires when correlation > 0.4 (stock actually tracks its sector today)

### 5.5 News-Impact
- **Idea**: react to unscheduled news breaking during session
- **Input**: news feed timestamped, ticker-linked
- **Score**: signed by FinBERT sentiment × recency-decay weight (exp(-minutes_ago/30))
- **Filter**: only for headlines that are new AND ticker-specific

### 5.6 Ensemble
- Adaptive weights identical mechanism to delivery's ensemble (learning parquet feeds back per-model IC → next-session weights)
- Independent from delivery weights — different learning corpus
- Score → percentile classifier → INTRADAY_LONG / INTRADAY_SHORT / SKIP per candidate

## 6 · Entry / exit rules (session-scoped)

### 6.1 Entry
- Only between 09:30 IST + 15 min and 13:00 IST (India) · 09:35 ET + 15 min and 15:00 ET (USA)
- No entries in last 60 minutes of session
- Only enter if bid-ask spread ≤ 0.15% at signal time
- Order type: marketable limit at (mid + 0.05%) for longs

### 6.2 Position sizing
- Per-trade risk = 0.25% of session capital (much smaller than swing's 1%)
- Position size = (session_capital × risk_pct) / (entry − hard_stop)
- Session capital = 10% of total portfolio equity (rest stays in swing)
- Max 8 concurrent positions

### 6.3 Exit rules (hard, non-negotiable)
- **Time stop**: all positions exit no later than 15:15 IST / 15:55 ET (never held overnight, ever)
- **Hard stop**: −0.5% from entry (tighter than swing's −5%)
- **T1 profit-take**: +0.75% partial 50% off table
- **T2 stretch**: +1.5% remainder off
- **VWAP break**: exit if price crosses back through session VWAP against direction for 3 consecutive minutes
- **Trailing stop**: after T1 hit, trail at high-water − 0.5%

## 7 · Risk engine (session-level, independent from swing)

- **Session daily loss limit**: −1.0% of session capital → auto-pause new entries for the day
- **Consecutive-loss circuit breaker**: 3 losing trades in a row → pause 60 minutes
- **Correlation cap**: max 3 open positions in same sector
- **News-driven kill switch**: if VIX intraday +15% in 10 min, close all long positions, no new entries for 30 min
- **Slippage budget**: track realized vs modeled slippage; if slippage > 2× model for 2 sessions, halt engine for review

## 8 · Execution simulator (paper phase)

- Fill model: marketable limit fills at (quoted mid + configurable slippage). Slippage model: linear in bid-ask spread × sign(order size vs top-of-book).
- Commissions: India 0.03% + STT + exchange fees · USA $0 broker + SEC fees + finra
- Rejects: 5% base rate on entries + spike when spread > 0.20%
- Partial fills: modelled from top-of-book size
- **All fills timestamped to the minute** for accurate P&L attribution

## 9 · Metrics (per session, per week, per month)

Institutional intraday metric suite (NOT the same as swing):

| Metric | Note |
|---|---|
| Number of trades | per session, mean and std across window |
| Win rate | % of trades with realized P&L > 0 (post-slippage) |
| Profit factor | sum(wins) / sum(|losses|) |
| Avg winner / avg loser | in bps and in currency |
| Median holding time | in minutes (not days) |
| Sharpe ratio (intraday) | annualized from per-trade returns · scaled by 252 × avg trades/day |
| Max intra-session drawdown | worst session low from session peak |
| Max weekly drawdown | rolling 5-session |
| Slippage realized / modeled | health indicator |
| Fill rate | filled orders / attempted orders |
| Avg spread paid | in bps |
| Session capital utilization | avg deployed / max deployed |
| Best hour of day | conditional Sharpe by hour bucket |
| Best sector | conditional Sharpe by sector |
| Model attribution | Sharpe contribution per signal factory (ORB / Gap / VWAP / Sector / News) |

## 10 · Lifecycle (Article IX Research Lifecycle · no shortcuts)

R004 ticket lifecycle · same 7-state as R001-R003:

```
OPEN → HISTORICAL_BACKTEST → PAPER_PORTFOLIO → LIVE_60D
      → VALIDATED_90D → CEO_REVIEW → PRODUCTION | REJECTED | DEFERRED
```

Bar heights per state:

| State | Minimum evidence |
|---|---|
| OPEN | This document accepted by operator |
| HISTORICAL_BACKTEST | 12 months of 1-min-bar-backed backtest per market · Sharpe > 1.0 net of slippage · max drawdown < 5% |
| PAPER_PORTFOLIO | 10 sessions of live-feed paper trading matching backtest metrics within 20% |
| LIVE_60D | 60 sessions of live paper P&L with full audit trail · session-level metric panel green |
| VALIDATED_90D | 90 sessions · sustained Sharpe > 1.0 · win rate > 50% · avg slippage < 2× model |
| CEO_REVIEW | Written CEO note approving production with signed risk-limits |
| PRODUCTION | Live capital allocation ≤ 10% of portfolio · continues to log every trade |

## 11 · India + USA parallel implementation

Identical architecture, per-market instantiation. Nothing shared across markets except the abstract framework.

| Layer | India instance | USA instance |
|---|---|---|
| Universe | NSE 200 filtered per §4.1 | S&P 500 + MidCap 400 filtered per §4.2 |
| Data feed | Zerodha Kite (₹2000/mo) | Polygon.io Starter ($29/mo) |
| Sector ETF | Nifty sectoral indices via NSE | SPDR sector ETFs (XLK, XLF, XLE, …) |
| Session hours | 09:15 – 15:30 IST | 09:30 – 16:00 ET |
| Pre-market window | none (India has no premarket) | 04:00 – 09:30 ET (used for gap-and-go input only) |
| Auction close | 15:30 IST | 16:00 ET |
| Storage | `reports/research/runner{1,2}_intraday_india/` | `reports/research/runner{1,2}_intraday_usa/` |
| Ticket | R004 · India intraday | R005 · USA intraday |
| Currency | INR (Rs) | USD ($) |

## 12 · Telegram delivery (once VALIDATED_90D)

Standalone MSG 4 (parallel to Command Center / Delivery Research / Intraday Research once real):
```
━━━━━━━━━━━━━━━━━━━━━━
⚡ AEGIS INTRADAY LIVE
━━━━━━━━━━━━━━━━━━━━━━
📅 2026-XX-XX · session close IST
🎯 Signals executed: N  ·  Win %  ·  Session P&L +X.XX%
🟢 Winners: TICKER · +X.XX% · held Nm
🔴 Losers:  TICKER · −X.XX% · held Nm · reason
🛡 Session DD: −X.XX%  ·  Slippage realized/model: 1.Xx
📈 Model attribution: ORB +X · Gap +X · VWAP +X · Sector +X · News +X
```

Only enabled after Article X (Evidence-First Promotion) approves R004 into PRODUCTION.

## 13 · What does NOT change

- Delivery engine untouched
- Delivery Telegram messages unchanged
- Portfolio position store unchanged (intraday runs on separate 10% session-capital sub-account)
- Learning parquet for delivery unchanged (intraday gets its own parquet)
- Constitution unchanged (this doc is under existing Article IX)

## 14 · Timeline estimate (calendar effort · not committed)

| Phase | Effort | Depends on |
|---|---|---|
| Feed procurement (Kite + Polygon accounts, keys, first-fetch tests) | 1 week | operator budget approval |
| Signal factories §5 (5 models × 2 markets) | 2 weeks | feeds live |
| Ensemble + percentile classifier | 3 days | signals emit |
| Execution simulator + risk engine | 1 week | ensemble emits |
| Historical backtest 12 months | 4 days compute + review | simulator ready |
| Paper trading 10 sessions | 2 weeks calendar | backtest passes |
| LIVE_60D paper window | 60 sessions ≈ 3 months calendar | paper passes |
| VALIDATED_90D | additional 30 sessions | LIVE_60D green |
| CEO review + PRODUCTION promotion | as scheduled | VALIDATED_90D green |

Realistic first-live-session date: **2026-08 + 3 weeks build + 5 months evaluation ≈ 2027-02** at earliest, longer if any phase fails and re-runs.

## 15 · Explicit rejection of the "shadow-of-delivery" approach

The 2026-07-30 attempt to run intraday as "same picks as delivery, measured intraday" is rejected in this specification. Reasons:

1. **Selection bias**: swing picks are selected for multi-day expected return, not for intraday tradability. Reusing them measures a scenario nobody would trade.
2. **Metric contamination**: intraday P&L on swing candidates conflates intraday alpha with swing-selection alpha.
3. **Operational irrelevance**: no reasonable intraday trader would trade a portfolio picked for 60-day holds.
4. **False confidence**: any positive number from that experiment would not generalize to a real intraday product.

Correlation-lab evidence gathered from the shadow experiment (intraday↔swing pearson ≈ 0.004 · sector-scoped ORC pockets in PSU Bank + Financial Services) is kept as historical evidence in `reports/research/intraday_delivery_correlation.json` but is NOT authoritative for the R004 build.

## 16 · Acceptance criteria for this document

- Operator has read §1-§3 (why + product surface + feed cost)
- Operator has read §4 + §5 (universe + signals) — is this the right design?
- Operator has read §6 + §7 (exits + risk) — are these the right limits?
- Operator has read §14 (timeline) — is the calendar acceptable?

If all four are green, ticket R004 opens in state OPEN with this document as its evidence attachment. If any is red, this document is revised before R004 opens.

## 17 · Companion ticket update

`research/tickets/R003_intraday_shadow_india.json` will be updated to:
- lifecycle_state: `REJECTED`
- decisions: append `{"from_state": "LIVE_60D", "to_state": "REJECTED", "note": "shadow-of-delivery approach rejected · superseded by R004 real intraday engine (docs/AEGIS_INTRADAY_ARCHITECTURE.md)"}`

A new ticket file `research/tickets/R004_intraday_engine_india.json` is created in state `OPEN` pointing at this document.

---

## 18 · Execution Plan (no day counts · phase-gated)

Reads §1–§17 end-to-end. Every phase gates on the previous being green. No calendar in this plan — advancement is evidence-driven only.

### Phase 0 · Prerequisites (operator + infra)

- Operator sign-off on §16 acceptance criteria (§4 universe · §5 signals · §6 exits · §7 risk)
- Procure feeds: Zerodha Kite API key (India) + Polygon.io Starter (USA)
- Store keys in `.env.intraday`
- Add `configs/intraday_feeds.json` — feed URLs · symbols · rate limits · retry policy
- Advance ticket R004 → `HISTORICAL_BACKTEST`

### Phase 1 · Data layer (foundation)

- `backend/intraday/feed/` new module
  - `kite_adapter.py` — India 1-min bars via Kite WebSocket + REST backfill
  - `polygon_adapter.py` — USA 1-min bars
  - `feed_router.py` — market → adapter selection + degraded-fallback
- `data/raw/india_minute/{TICKER}_M1.parquet` + `data/raw/us_minute/{TICKER}_M1.parquet` (append-only cache · same pattern as daily bars)
- `backend/intraday/universe/` — daily universe filter per §4.1 (India) + §4.2 (USA) · emits `configs/intraday_universe_{market}_{YYYY-MM-DD}.json`
- Session-clock utility (India 09:15–15:30 IST · USA 09:30–16:00 ET · auction windows)
- Backfill 12 months of 1-min bars for both universes to seed backtest

### Phase 2 · Signal factories (five models × two markets)

Each factory lives at `backend/intraday/signals/{name}.py` · emits `{ticker: score}` per minute-tick:

- `orb.py` — Opening-Range Breakout (§5.1)
- `gap_go.py` — Gap-and-Go (§5.2)
- `vwap_reversion.py` — VWAP-Reversion (§5.3)
- `sector_momentum.py` — Sector-Momentum-Follow (§5.4 · needs sector-ETF minute feed)
- `news_impact.py` — News-Impact (§5.5 · reuses existing FinBERT + Google News RSS)
- Shared: `intraday_signal_registry.py` + per-signal unit tests with recorded fixtures

### Phase 3 · Ensemble + classifier

- `backend/intraday/ensemble/adaptive_weights.py` — same mechanism as delivery's adaptive weights but independent corpus (its own `reports/intraday_learning.parquet`)
- `backend/intraday/ensemble/percentile_classifier.py` — score → `INTRADAY_LONG / INTRADAY_SHORT / SKIP`
- Emits `reports/intraday/recommendations_intraday_{market}_{YYYY-MM-DD}.json` at session start + updates during session
- Ticket R004 → `PAPER_PORTFOLIO`

### Phase 4 · Risk engine + execution simulator

- `backend/intraday/risk/session_manager.py` — position sizing (§6.2) · daily loss cap · consecutive-loss circuit breaker · correlation cap · VIX kill switch (§7)
- `backend/intraday/exec/simulator.py` — marketable-limit fills · slippage model · commissions per market · partial-fills · rejects (§8)
- `backend/intraday/exec/session_state.py` — open positions · trailing stops · time-stop enforcement (never past 15:15 IST / 15:55 ET)
- Every fill/exit logged to `reports/intraday/fills_{market}_{YYYY-MM-DD}.jsonl` for full audit

### Phase 5 · Historical backtest

- `backend/intraday/backtest/runner.py` — replay 12 months of 1-min bars through the full stack (Phase 2 + 3 + 4)
- Metrics per §9 emitted to `reports/intraday/backtest_{market}.json`
- **Gate**: net-of-slippage Sharpe > 1.0 · max DD < 5% · win rate > 50%
- If any market fails, revise §5 signal weights or §6 exits · re-run · document in ticket decisions

### Phase 6 · Paper trading (short live window)

- `scripts/intraday_paper_run.py` — standalone parallel job (same pattern as previous `intraday_hourly_run.py`)
- Live feed → real-time signals → simulated fills → session P&L
- **Gate**: live paper metrics within 20% of backtest (§10 PAPER_PORTFOLIO row)
- Ticket R004 → `LIVE_60D` on green

### Phase 7 · LIVE_60D window

- Same script continues over 60 trading sessions
- Full metric panel green per §9 sustained
- No engine changes during this window (evidence is advisory · never autotunes production)
- Session-close Telegram MSG 4 rendered (per §12 format · still paper-only)

### Phase 8 · VALIDATED_90D window

- 90 sessions cumulative · sustained metrics
- Independent adversarial review of trade log + slippage realized/model ratio
- Ticket R004 → `VALIDATED_90D` on green

### Phase 9 · CEO_REVIEW + PRODUCTION

- Written CEO note approving:
  - Session-capital carve-out (default 10% of portfolio equity per §6.2)
  - Signed risk limits per §7
  - Kill-switch escalation path
- Constitutional amendment (Article X): ticket R004 cited in production diff
- Ticket R004 → `PRODUCTION`
- Continue logging every trade forever · quarterly review

### Parallel USA track

Everything above runs in parallel for USA on ticket R005 (opened as a companion when R004 clears Phase 1). Same code · per-market instantiation via §11 table. USA does not gate on India VALIDATED_90D — each market advances on its own evidence.

### What stays untouched throughout

- Delivery engine · code, config, corpus
- Delivery Telegram messages (MSG 1 + MSG 2)
- Position store for delivery
- Existing tests
- Existing Research Platform (`backend/research/`) — intraday gets its own module tree at `backend/intraday/`

### Kick-off signal

Ping operator with "start R004 Phase 0" to begin. Phase 1 starts the moment feed credentials land.

---

**End of specification** · 2026-07-30 · under operator authority
