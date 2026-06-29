# USA Research Roadmap — pre-registered experiments (RC002–RC006)

Pre-registration discipline: the question, data, PIT method, factor candidates, and **promote thresholds**
are fixed BEFORE the data is collected, so a cycle can't be retrofitted to a result. Every cycle reuses the
RC001 harness pattern (`core/usa_research.py`): build a cached PIT panel, then IC / IC-IR / lift / learned
blend off it.

## Standing methodology rules (learned from RC001.x — non-negotiable)
- **Point-in-time only.** Use the public/`filed`/report timestamp, never the period it describes.
- **Overlap embargo.** If a forward-return window (H days) is longer than the rebalance cadence (C days),
  adjacent dates' labels overlap → IC-IR is inflated. ALWAYS (a) embargo train rows whose label window
  overlaps the test date, and (b) measure IC-IR on **non-overlapping dates only** (stride = ceil(H/C)).
  RC001.2 showed this turns a fake IC +0.287 into an honest +0.083.
- **Power first.** Report effective N (non-overlapping dates × cross-section). A null on thin data is
  "no evidence," not "proven useless." Widen coverage before concluding.
- **Promote bar:** mean IC > 0.03 AND IC-IR > 2.0 (non-overlap) AND positive lift over price-only.
  Promotion = paper-forward tracking, never straight into a live baseline.

## Pre-registered cycles

### RC002 — Earnings surprise / revisions
- **Question:** does post-earnings drift (SUE / surprise %, estimate revisions) predict forward returns?
- **Data (free):** SEC 8-K/10-Q `filed` dates for actuals; surprise vs a naive expectation (YoY or
  trailing-trend) since free analyst estimates are scarce. Optional: Nasdaq earnings calendar.
- **Factors:** `e_surprise_yoy`, `e_surprise_vs_trend`, `e_days_since_report`, drift window 1–60d.
- **Hypothesis:** positive surprises drift up over ~20–60d (PEAD); strongest in smaller names.
- **Pitfalls:** announcement-date accuracy (must be `filed`, not period end); event-study windows are
  short → cadence/embargo care; survivorship in the universe.

### RC003 — Insider buying (Form 4)
- **Question:** do net open-market insider purchases predict forward returns?
- **Data (free):** SEC Form 4 (transaction code P = open-market buy), `filed` within 2 business days.
- **Factors:** `i_net_buy_value_90d`, `i_num_buyers_90d`, `i_buy_sell_ratio`, cluster-buy flag.
- **Hypothesis:** cluster buying (multiple insiders) > single; signal decays over 1–3 months.
- **Pitfalls:** 10b5-1 planned sales noise; size-normalise by market cap; sparse events → pooled IC.

### RC004 — ETF / fund flows
- **Question:** do sector/thematic ETF flows or short interest predict member-stock returns?
- **Data (free):** ETF holdings + daily shares-outstanding (proxy for creation/redemption flow);
  FINRA/exchange short interest (bi-monthly).
- **Factors:** `f_sector_etf_flow_20d`, `f_short_interest_pct`, `f_days_to_cover`.
- **Hypothesis:** persistent inflows → momentum; extreme short interest → squeeze or decline (test sign).
- **Pitfalls:** flow attribution to single stocks is indirect; short-interest is lagged/low-frequency.

### RC005 — Macro factors (FRED)
- **Question:** do macro regimes (rates, curve, credit spreads, USD) condition cross-sectional returns?
- **Data (free):** FRED — 10Y/2Y, term spread, HY OAS, DXY, CPI surprises, claims.
- **Factors:** regime states + per-stock macro betas (rate-sensitivity, cyclicality).
- **Hypothesis:** macro is a **conditioner** (when to tilt growth vs defensives), not a stock-level alpha.
  Likely best applied as a regime overlay (cf. India: the whole edge was the regime overlay).
- **Pitfalls:** few independent macro regimes in short history → severe overlap/power problem; resist
  fitting regime boundaries to returns.

### RC006 — News / sentiment
- **Question:** does headline/news sentiment predict short-horizon returns?
- **Data (free):** RSS / company news feeds; lightweight sentiment (lexicon or small model).
- **Factors:** `n_sentiment_5d`, `n_volume_zscore`, `n_dispersion`.
- **Hypothesis:** sentiment is short-lived (days); decays fast; mostly noise after costs.
- **Pitfalls:** look-ahead via publish timestamps; spurious correlation; transaction costs likely kill it.

## Sequencing note
RC001 left a concrete blocker (statistical power) and a concrete lead (growth-tilt / ROE-inverse). The
highest-ROI move before RC002+ is **widening SEC coverage + price history** so RC001's lead — and every
later cycle — has enough independent observations to clear the gate honestly.
