# AEGIS — System Architecture (High-Level, for External Review)

> A risk-managed Indian-equity recommendation system. This document describes the **concepts and
> architecture** at a level suitable for an independent expert to review and comment on. It deliberately
> omits proprietary selection rules, thresholds, weightings, and configuration values. The intent is to
> expose *how the system thinks*, not the exact recipe.

---

## 1. Design philosophy

AEGIS is built on one empirically-tested premise:

> **On public price data, future *returns* are close to unpredictable, but *risk* is predictable.**

So the system does **not** try to forecast which stock will rise most. It tries to (a) construct a
well-diversified, risk-controlled portfolio and (b) time overall market exposure. Every claim in the
system is required to survive out-of-sample testing before it is trusted; intuition alone never ships.

A second principle is **honesty over polish**: where the evidence is weak or absent, the output says so
("insufficient evidence", "not evaluated") rather than fabricating a number.

---

## 2. Architecture at a glance

```
            Market Data (daily OHLCV, index, volatility index)
                                  │
                                  ▼
                      Tradable Universe (liquidity / size)
                                  │
                                  ▼
        ┌─────────────── Recommendation Engine ───────────────┐
        │   Market regime  →  Sector diversification  →        │
        │   Company selection (risk-based)  →  Data Layers  →  │
        │   Portfolio construction  →  Risk Profile            │
        └──────────────────────────────────────────────────────┘
                                  │
                 ┌────────────────┼────────────────┐
                 ▼                ▼                ▼
          Recommendation     Evidence /       Delivery
            Database         Validation     (Excel · Sheets ·
          (lifecycle)         Framework       Telegram)
                 │                                 ▲
                 └──────── Daily Automation (CI scheduler) ─────┘
```

---

## 3. Components and concepts

### 3.1 Data layer
- Daily price/volume panels per stock, plus a market index and a market-volatility index.
- A **point-in-time (PIT) discipline**: any non-price information must be keyed by the date it became
  *publicly known*, never the period it describes — to prevent look-ahead bias.
- A pluggable adapter pattern so new datasets (fundamentals, earnings, flows, news) can be added without
  re-engineering the core.

### 3.2 Tradable universe
- Rather than hard-coding an index, the universe is conceived as a **filtered set** (liquidity, market
  cap, tradability). Index membership is one input, not the definition.
- (Current production uses a large-cap liquid set; a dynamic universe builder is on the roadmap.)

### 3.3 Risk-based portfolio construction
- **Selection** favors statistically lower-risk names rather than momentum/return chasing.
- **Diversification** is enforced structurally (per-sector caps), not bet on.
- **Weighting** uses **Hierarchical Risk Parity (HRP)** — a correlation-cluster-aware allocation that
  avoids the instability of naive mean-variance optimization.

### 3.4 Market-regime overlay
- A **regime engine** scales total market exposure up or down based on market state (e.g., a volatility
  gauge and trend filters, plus a global-risk input). This de-risking/re-risking overlay is treated as
  the single most important validated component.

### 3.5 Dynamic policy
- **Holding period** is chosen from a back-tested *horizon matrix* and is **regime-conditional** (shorter
  in weak markets, longer in strong) rather than a fixed number.
- **Basket size** adapts to market **breadth** and regime (wider when healthy, more concentrated + more
  cash when weak) — sized on a *risk-first* basis, not return-optimized.

### 3.6 Risk profiles
- One engine, three selectable **risk preferences** — Conservative (default), Balanced, and an
  Experimental higher-risk profile — defined by volatility tier. The default is the most conservative;
  the others are offered/flagged, and a profile is promoted only if live evidence supports it.

### 3.7 Evidence & validation framework
The acceptance gate for any idea or configuration:
- **Walk-forward / rolling out-of-sample** testing (no peeking).
- **Deflated Sharpe Ratio (DSR)** and **Probability of Backtest Overfitting (PBO/CSCV)** to discount for
  the number of trials — guarding against "found a good Sharpe by luck".
- A **recommendation-quality score** (average forward-return percentile of picks; 0.5 = random) used to
  measure whether *selection* adds skill (it largely does not on price alone — an honest finding).
- Explicit handling of **survivorship bias** and trading-cost caveats in interpretation.

### 3.8 Data-layer gate (pluggable information)
- A dataset-agnostic harness: any new information source is scored for **incremental** value
  (information coefficient, recommendation-quality lift, walk-forward, DSR) and **automatically kept or
  discarded**. Calibration signals (a planted "oracle" and pure noise) verify the gate has discriminating
  power before any real dataset is trusted.

### 3.9 AI Lab (disciplined model promotion)
- Production is **frozen** as a baseline. Machine-learning models (e.g., **learning-to-rank** rather than
  price prediction) are developed in a separate lab and may **replace production only if they beat the
  frozen baseline out-of-sample**, hold across folds, survive a trial penalty, and then pass forward
  paper. This separates "always learning" from "model drift".

### 3.10 Recommendation database & lifecycle
- Every run **snapshots** recommendations into a growing store (nothing deleted), giving each pick a
  lifecycle (Live → Review-due → Archived) and a **daily diff** (new / removed / increased / reduced).
- This is the substrate for **evidence learning**: performance statistics update continuously from
  realized outcomes.

### 3.11 Delivery & automation
- A single human-readable **workbook** (one clean table per sheet) is the authoritative report.
- The same data is mirrored to **Google Sheets** (shareable, mobile) and a concise **Telegram** push.
- A **CI scheduler** runs the whole pipeline daily (refresh data → generate → track → notify → commit),
  at zero hosting cost and with full version history.

---

## 4. Two feedback loops (deliberately separated)
1. **Evidence learning (automatic):** live outcomes continuously update *statistics* (win rate, returns,
   drawdown, calibration). This changes what we *know*, not the model.
2. **Model promotion (manual, gated):** only after enough new evidence accumulates and a candidate beats
   the frozen baseline does the *production model* change.

This gives continuous measurement without uncontrolled drift.

---

## 5. Engineering & reproducibility
- Deterministic, file-based pipeline; every claim is backed by a runnable script.
- Secrets are environment-based and never committed; data and config are versioned.
- The report, the database, and the notifications all derive from one canonical machine-readable snapshot.

---

## 6. Explicit limitations (stated up front)
- **Stock-level selection is not validated as alpha** — picks are risk-managed *constituents*, not proven
  winners. The validated edge is portfolio construction + regime timing.
- **Absolute backtest returns are survivorship-inflated**; the trustworthy signal is *relative* (vs the
  index) and *risk-adjusted* (Sharpe, drawdown).
- **No fundamentals / earnings / news / institutional-flow data yet** — these are "not evaluated", with a
  gate ready to test them when acquired.
- Backtests are gross of some real-world frictions; forward paper is treated as the real ongoing test.

---

## 7. Open questions for the reviewer
*(Please add your thoughts inline below — this section is for the external expert.)*

1. Is the **risk-predictable / return-unpredictable** premise a sound foundation, or are we leaving
   capturable return signal on the table?
2. Is the **regime overlay** the right primary edge, and are there better-established regime constructs?
3. On the **risk-tier finding** (a medium-volatility tier showed competitive risk-adjusted results), how
   much should we discount for survivorship bias and costs before acting?
4. Which **non-price datasets** would you prioritize for the data-layer gate (earnings surprise, flows,
   ownership, revisions), and why?
5. Are the **validation gates** (walk-forward, DSR, PBO) sufficient, or would you add others (e.g.,
   combinatorial purged CV, regime-stratified testing, capacity/turnover analysis)?
6. Is the **frozen-baseline + AI-Lab promotion** discipline the right way to introduce ML safely?
7. Any blind spots in the **architecture** itself (data integrity, leakage, overfitting surface area)?

---

### Reviewer comments
> _(space for the expert)_
