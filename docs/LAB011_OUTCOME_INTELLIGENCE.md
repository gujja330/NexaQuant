# LAB011 · Recommendation Outcome Intelligence — Design Specification

**Spec ID:** `LAB011-OI-DESIGN-2026-07-17`
**Role:** Chief Investment Officer · Head of Quant Research · Principal Portfolio Architect · Independent Validation Lead
**Deliverable type:** DESIGN SPECIFICATION ONLY. Zero code changes. Zero implementation.
**Constraint:** No production logic, no recommendation scoring, no parameter tuning, no strategy search, no portfolio construction change.

> **Critical nomenclature note (§2):** LAB011 despite the "LAB" prefix is
> an **observation / measurement layer**, NOT an alpha research lab. It
> observes existing recommendations. It does **NOT** increment
> `cumulative_strategy_search`. It does **NOT** add PBO risk. It sits in
> the same architectural family as MON001 (monitoring) rather than
> LAB001–LAB010 (alpha research).

---

## Table of contents

- [0. Executive summary + priority verdict](#0-executive-summary--priority-verdict)
- [1. The gap this fills](#1-the-gap-this-fills)
- [2. Positioning + nomenclature](#2-positioning--nomenclature)
- [3. Architecture](#3-architecture)
- [4. Recommendation lifecycle](#4-recommendation-lifecycle)
- [5. Outcome database schemas](#5-outcome-database-schemas)
- [6. KPI catalogue (institutional metrics)](#6-kpi-catalogue-institutional-metrics)
- [7. Learning opportunity detection](#7-learning-opportunity-detection)
- [8. Dashboards](#8-dashboards)
- [9. Alerts](#9-alerts)
- [10. Workflow + cadence](#10-workflow--cadence)
- [11. Research roadmap](#11-research-roadmap)
- [12. Implementation roadmap](#12-implementation-roadmap)
- [13. Dependencies](#13-dependencies)
- [14. Risk assessment](#14-risk-assessment)
- [15. Expected value (business, alpha, operational, research)](#15-expected-value-business-alpha-operational-research)
- [16. Complexity assessment](#16-complexity-assessment)
- [17. Priority verdict — should LAB011 come first?](#17-priority-verdict--should-lab011-come-first)

---

## 0. Executive summary + priority verdict

### 0.1 What LAB011 is

A read-only **outcome-observation system** that continuously answers:

- What did we recommend?
- What happened to each recommendation?
- Was it a win, a loss, an early exit, a late exit, a false Strong Buy, a missed winner?
- How well-calibrated was our confidence?
- Which biases (sector / regime / horizon / confidence) systematically distort outcomes?
- Is our track record improving or decaying?

### 0.2 What LAB011 is NOT

- Not an alpha research lab
- Not a new strategy
- Not a hyperparameter tune
- Not a portfolio-construction change
- Not a scoring change
- Not a recommendation-engine modification
- Does not increment `cumulative_strategy_search`
- Does not touch MON001 sealed core
- Does not touch LAB001–LAB010 artefacts

### 0.3 Priority verdict — headline

# ✅ Yes — LAB011 (Outcome Intelligence) should be the next major initiative

**But** with a critical clarification: LAB011 is **not** the "quant
research LAB011" from the earlier meta-audit's Phase 4 roadmap. It's
an **observation layer** — closer in family to MON001 than to
LAB001–LAB010. Under this framing, it becomes the **highest-value
non-alpha initiative** available:

- Closes the biggest identified portfolio gap (§F in the meta-audit
  identified "Portfolio Intelligence" as the single most under-developed
  dimension — no actual holdings tracking, no attribution, no
  outcome loop).
- Adds ZERO PBO risk (no new hypothesis tested).
- Preserves the operator's stated goal of *"stop adding alpha research
  until forward evidence proves the sealed baseline"*.
- Produces the evidence base needed to make *any* future alpha
  decision honestly (LAB012+, MON002).
- Publishable track record → business value.

### 0.4 Sequencing recommendation

```
NOW (already in flight or pending):
  1. Verify OPS001-F at 16:15 IST today               [PENDING PROOF]
  2. OPS001-H spec → OPS001-I implementation           [PENDING AUTH]

NEXT (proposed order):
  3. LAB011-OI foundation (Phase 1: ingestion + outcome DB)   ~5 days
  4. LAB011-OI Phase 2: KPIs + calibration                     ~5 days
  5. LAB011-OI Phase 3: dashboards + alerts                    ~5 days
  6. MON002 (drift-detection on the LAB011 evidence base)      later

DEFER (until LAB011 has 30+ days of accumulated evidence):
  7. Any new alpha lab (LAB012+)
```

Rationale: MON002 depends on LAB011 evidence. Any new LAB depends on
LAB011 evidence to be honest. Therefore LAB011 sits on the critical
path.

---

## 1. The gap this fills

### 1.1 What the system knows today

- **What was recommended** — `data/aegis_registry.csv` has every REC-YYYYMMDD-NNNN row with ticker, weight, entry date, score.
- **What MON001 sees at portfolio level** — envelope divergence, ledger integrity, fingerprint stability.
- **Ad-hoc backtest scorecards** — `data/aegis_scorecard.csv` computes historical win rate on completed LAB backtests.

### 1.2 What the system does NOT know today

| Question | Currently unknown |
|---|---|
| For each specific rec, what was its **Maximum Favourable Excursion** (best price reached during holding period)? | ❌ Not tracked |
| For each specific rec, what was its **Maximum Adverse Excursion** (worst dip during holding)? | ❌ Not tracked |
| What % of Strong Buys turned out to be false positives? | ❌ Not tracked |
| What % of recs we didn't hold went on to outperform (missed winners)? | ❌ Not tracked |
| Did we exit too early on winners? Too late on losers? | ❌ Not tracked |
| Is our confidence calibrated (85% confidence → 85% actual win rate)? | ❌ Only crudely, via scorecard |
| Which sectors do we systematically fail on? | ❌ Not exposed to operator |
| Which market regimes have highest alpha? Which decay fastest? | ❌ Not tracked longitudinally |
| Has the win rate degraded over time (alpha decay)? | ❌ Only manually |
| Are we consistent: does the same rec pattern get similar outcomes? | ❌ Not measured |

The scorecard exists but it is a **static backtest artefact**, not a
live outcome-intelligence pipeline. It does not track individual
recommendation lifecycles from generation to resolution.

### 1.3 What LAB011 delivers

An **evidence-first, per-recommendation outcome database** that the
operator (and any future research initiative) can query for hard
answers to every question above.

---

## 2. Positioning + nomenclature

### 2.1 The name problem

The operator's prompt uses "LAB011". Historically:
- **LAB001–LAB010**: alpha research labs, each testing a hypothesis, each incrementing `cumulative_strategy_search`, each contributing to PBO risk.
- **MON001**: monitoring, explicitly declared "NOT an alpha lab" in `preregistration.md`. Does not increment trial count.

**LAB011 Outcome Intelligence follows MON001's family, not the LAB family.**

### 2.2 Recommended nomenclature

Two options:

- **Option A (recommended):** Keep the name **LAB011** for continuity
  with the operator's naming, but explicitly document in
  `preregistration.md` that LAB011-OI "does not test alpha hypotheses,
  does not increment cumulative_strategy_search, does not affect PBO".
- **Option B:** Rename to **MON002-OI** or **OI001** to align with the
  monitoring/observability family.

I recommend Option A for operator continuity. But whichever name is
chosen, the preregistration must explicitly state that this is not an
alpha-testing lab.

### 2.3 What "not testing hypotheses" means concretely

LAB011 does NOT:
- Compute new features
- Score stocks in any way that differs from `recommendation_generator.py`
- Rank candidates
- Backtest alternative strategies
- Fit any model
- Cross-validate anything
- Sweep hyperparameters

LAB011 DOES:
- Read what production output
- Compute what happened AFTER (using existing price data)
- Aggregate outcomes into KPIs
- Compare KPIs to thresholds and emit alerts
- Present dashboards

This is measurement of an existing signal, not generation of a new one.
By the trial-registry definition in `docs/RELEASE_CHECKLIST.md`, this
does not count as a research trial.

---

## 3. Architecture

### 3.1 Three-tier layered design

```
┌──────────────────────────────────────────────────────────────────┐
│  TIER 1 · INGESTION                                              │
│  ────────────────────────────────────────────────────────────    │
│  Read-only pulls from existing artefacts.                        │
│  Never writes back to production.                                │
│                                                                  │
│  Inputs:                                                         │
│    ├─ data/aegis_registry.csv                                    │
│    ├─ data/aegis_recommendation_db.csv                           │
│    ├─ india/monitoring/MON001_Forward_Validation/                │
│    │     ledger/forward_ledger.jsonl                             │
│    ├─ india/monitoring/MON001_Forward_Validation/                │
│    │     reports/mon001_diagnostics_*.json                       │
│    ├─ data/raw/india/*_D1.parquet   (price series)               │
│    └─ reports/telegram_delivery_*.jsonl                          │
│                                                                  │
│  Output: normalized in-memory frames per REC row                 │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  TIER 2 · STORAGE (append-only)                                  │
│  ────────────────────────────────────────────────────────────    │
│  ├─ oi/recommendation_outcomes.jsonl                             │
│  │     One row per rec transition (state-machine log)            │
│  ├─ oi/recommendation_states.parquet                             │
│  │     Latest state per rec (materialized view)                  │
│  ├─ oi/kpi_snapshots.jsonl                                       │
│  │     Daily / weekly / monthly / quarterly / yearly rollups     │
│  ├─ oi/calibration.jsonl                                         │
│  │     Confidence bucket → actual win rate mappings              │
│  └─ oi/alert_log.jsonl                                           │
│        Fired alerts + severity + rationale                       │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  TIER 3 · INTELLIGENCE                                           │
│  ────────────────────────────────────────────────────────────    │
│  ├─ Dashboards (Markdown + optional HTML/Excel)                  │
│  │     - Daily summary                                           │
│  │     - Weekly review                                           │
│  │     - Monthly attribution                                     │
│  │     - Quarterly performance                                   │
│  │     - Annual scorecard                                        │
│  ├─ Alerts (WARN / ERROR / CRITICAL — reuses OPS001-C bus)       │
│  ├─ KPI query API (Python function-level)                        │
│  └─ Learning-opportunity reports (bias detection)                │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Operator + future research
```

### 3.2 Location in repository

Proposed:

```
india/
└── outcome_intelligence/
    ├── __init__.py
    ├── preregistration.md          # non-alpha lab declaration
    ├── ingest.py                   # Tier 1 readers (read-only)
    ├── lifecycle.py                # State machine
    ├── outcomes.py                 # Per-rec computation
    ├── kpi.py                      # KPI computations
    ├── calibration.py              # Confidence calibration
    ├── alerts.py                   # Alert rules + thresholds
    ├── dashboards/
    │   ├── daily.py
    │   ├── weekly.py
    │   ├── monthly.py
    │   ├── quarterly.py
    │   └── yearly.py
    ├── schemas/
    │   └── outcomes_schema.yaml
    ├── reports/                    # generated artefacts
    │   ├── oi_dashboard_YYYY-MM-DD.md
    │   ├── oi_weekly_YYYY-WW.md
    │   ├── oi_monthly_YYYY-MM.md
    │   └── oi_annual_YYYY.md
    ├── data/
    │   ├── recommendation_outcomes.jsonl
    │   ├── recommendation_states.parquet
    │   ├── kpi_snapshots.jsonl
    │   ├── calibration.jsonl
    │   └── alert_log.jsonl
    └── test_lab011_framework.py    # unit + integration tests
```

**Sealed?** NO. LAB011 is not in the MON001 fingerprint set. It's an
observation module on top of MON001, analogous to a Grafana dashboard
built on top of a database.

### 3.3 Isolation guarantees

- Never writes to `data/aegis_*.csv`
- Never writes to `india/monitoring/MON001_Forward_Validation/` (sealed)
- Never writes to `data/raw/india/` (read-only market data)
- Never modifies any production module
- Never invoked from `recommendation_generator.py` (one-way dependency: OI reads production, production does not read OI)
- All LAB011 output lives under `india/outcome_intelligence/data/` and `india/outcome_intelligence/reports/`

---

## 4. Recommendation lifecycle

### 4.1 State machine

```
┌───────────────┐
│   GENERATED   │  ← recommendation_generator wrote this rec_id
│               │      into aegis_registry.csv
└───────┬───────┘
        │
        │  (Telegram send succeeds)
        ▼
┌───────────────┐
│   DELIVERED   │  ← Telegram delivery ledger confirms send
│               │
└───────┬───────┘
        │
        │  (optional operator marks execution — future)
        ▼
┌───────────────┐
│    ENTERED    │  ← operator opens the position (opt-in)
│               │      falls through if unmarked
└───────┬───────┘
        │
        │  (T+1 close observed on Nifty parquet)
        ▼
┌───────────────┐
│    ACTIVE     │  ← daily price observations updating MFE/MAE
│               │
└───────┬───────┘
        │
        │  (mature or exit trigger)
        ▼
     ┌──┴──┐
     │     │
     ▼     ▼    (exactly one of the five below)
┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
│ TARGET │  │  STOP  │  │TRAILING│  │EXPIRED │  │REPLACED│
│  HIT   │  │  HIT   │  │  HIT   │  │        │  │        │
└────┬───┘  └────┬───┘  └────┬───┘  └────┬───┘  └────┬───┘
     │           │           │           │           │
     └─────┬─────┴─────┬─────┴─────┬─────┴─────┬─────┘
                       │
                       │  (final grade assigned)
                       ▼
                ┌───────────────┐
                │    RESOLVED   │  ← outcome quantified, KPIs updated
                │               │
                └───────┬───────┘
                        │
                        │  (30 days after resolution)
                        ▼
                ┌───────────────┐
                │   ARCHIVED    │  ← immutable historical record
                │               │
                └───────────────┘
```

### 4.2 State transitions and timers

| From → To | Trigger | Timer / Timeout |
|---|---|---|
| — → GENERATED | New row in aegis_registry.csv | Instant |
| GENERATED → DELIVERED | Telegram delivery ledger success | Must occur within 6h; else `DELIVERY_FAILED` |
| DELIVERED → ENTERED | Operator marks executed OR default T+1 open | 1 trading day |
| ENTERED → ACTIVE | First post-entry close | 1 trading day |
| ACTIVE → TARGET_HIT | Close ≥ target price | Per-day check |
| ACTIVE → STOP_HIT | Close ≤ stop level | Per-day check |
| ACTIVE → TRAILING_HIT | Close ≤ (peak_since_entry × (1 − trail%)) | Per-day check |
| ACTIVE → EXPIRED | Days held ≥ expiry_cal_days (default 7) | Days-based |
| ACTIVE → REPLACED | Ticker rank-out during rotation | Per-run check |
| Any-terminal → RESOLVED | Outcome fields all populated | Instant on terminal state |
| RESOLVED → ARCHIVED | 30 days after RESOLVED | 30-day timer |

### 4.3 Exit-reason taxonomy (11 canonical codes)

Same codes as proposed in OPS001-H Telegram spec — reusable across the platform:

```
TARGET_HIT              — price crossed target
STOP_LOSS_HIT           — price ≤ stop
TRAILING_STOP_HIT       — peak-drawdown > trail%
BETTER_OPPORTUNITY      — rotation replacement
PORTFOLIO_REBALANCE     — HRP re-opt removed name
SECTOR_EXPOSURE         — sector-cap exit
RISK_REDUCTION          — VaR-driven trim
CONFIDENCE_DETERIORATION — signal weakened
ALPHA_DECAY             — historic edge no longer present
EVIDENCE_DETERIORATION  — case count dropped below threshold
EXPIRY                  — age > expiry_cal_days
```

Every RESOLVED recommendation has exactly one exit reason code.

### 4.4 Special outcome categories

Beyond the state machine, LAB011 classifies each RESOLVED rec into
one of several **quality categories** for aggregate analysis:

- **True Positive:** Strong Buy → outperformed benchmark by >X%
- **False Strong Buy:** Strong Buy → underperformed benchmark
- **True Hold:** Hold → benchmark-tracking outcome
- **False Hold (Missed Winner):** Not held → subsequently outperformed
- **Early Exit:** Exited before target; price continued to run
- **Late Exit:** Exited after peak; MFE not captured
- **Round-Trip Loss:** Bought, price rose, gave back all gains, exited flat/red
- **Fast Winner:** Target hit in < half of expected holding period
- **Slow Winner:** Target hit near / beyond expected holding period
- **Grinding Loss:** MAE breach then partial recovery, exited red

---

## 5. Outcome database schemas

### 5.1 Primary table: `recommendation_outcomes.jsonl`

**Append-only.** One row per rec, updated in-place as state transitions
by rewriting the row (JSONL loses no history because a re-emit is a new
line — same rec_id → latest state).

Schema (per row):

```yaml
# --- identity ---
rec_id:                   str    # e.g., "REC-20260714-0357"
ticker:                   str
sector:                   str
strategy_version:         str    # e.g., "AEGIS_v2.2"

# --- generation ---
generated_at_utc:         iso8601-str
generation_date:          date   # asof
strong_buy:               bool
grade:                    str    # A / B / C
score:                    int    # 0-100
confidence_pct:           int    # 0-100
evidence_level:           str    # strong / medium / low / none
recommended_weight_pct:   float  # 0-100
buy_range_lo:             float  # ₹
buy_range_hi:             float  # ₹
target_price:             float  # ₹
stop_price:               float  # ₹
trail_pct:                float  # e.g., 0.03 for 3%
expiry_date:              date
review_date:              date
horizon_days:             int    # e.g., 63

# --- delivery ---
delivery_status:          str    # DELIVERED / DELIVERY_FAILED / DELIVERY_PENDING
delivery_channel:         str    # telegram / file / etc.
delivered_at_utc:         iso8601-str

# --- execution (optional) ---
entered:                  bool
entered_at_utc:           iso8601-str  # nullable
entry_price:              float         # nullable (default = close of asof+1)

# --- lifecycle ---
current_state:            str    # GENERATED/DELIVERED/ENTERED/ACTIVE/RESOLVED/ARCHIVED
state_history:            list   # [{state, entered_at_utc, reason}]
days_held:                int    # nullable, integer

# --- price observations ---
current_price:            float
peak_price_since_entry:   float  # MFE tracker
trough_price_since_entry: float  # MAE tracker
peak_pct:                 float  # MFE %  (peak/entry − 1)
trough_pct:               float  # MAE %  (trough/entry − 1)
current_pct:              float  # (current/entry − 1)

# --- exit (nullable until RESOLVED) ---
exit_price:               float    # nullable
exit_date:                date     # nullable
exit_reason:              str      # one of the 11 codes; nullable
final_return_pct:         float    # nullable

# --- benchmark comparison ---
nifty_return_since_entry:  float   # cumulative
sector_return_since_entry: float
alpha_vs_nifty:           float   # final_return_pct − nifty_return_pct
alpha_vs_sector:          float

# --- flags ---
target_achieved:          bool
stop_triggered:            bool
trailing_stop_triggered:   bool
false_strong_buy:          bool    # StrongBuy AND alpha_vs_nifty < 0
missed_winner:             bool    # (not held) AND subsequent alpha > +X%
early_exit:                bool    # exit reason ∈ {ROT, REBAL, etc.} AND MFE > final_return + Y%
late_exit:                 bool    # peak_pct significantly above exit return

# --- quality ---
quality_category:         str      # TRUE_POSITIVE, FALSE_STRONG_BUY, EARLY_EXIT, etc.
calibration_delta:        float    # actual − confidence  (per confidence bucket)
final_grade:              str      # A / B / C / F (post-hoc, LAB011-assigned)

# --- provenance ---
mon001_fingerprint:       str      # fingerprint at generation
report_sha:               str      # Telegram-message SHA256 that delivered this rec
run_utc:                  iso8601  # when generator wrote it
updated_at_utc:           iso8601  # last time this outcome row was recomputed
```

### 5.2 State materialized view: `recommendation_states.parquet`

For query performance. One row per rec_id, always latest state. Rebuilt
nightly from `recommendation_outcomes.jsonl`.

### 5.3 KPI snapshot: `kpi_snapshots.jsonl`

```yaml
snapshot_id:              str    # "kpi_YYYY-MM-DD_daily" / "kpi_YYYY-WW_weekly" / etc.
snapshot_type:            str    # daily / weekly / monthly / quarterly / yearly
period_start:             date
period_end:               date
computed_at_utc:          iso8601

# --- headline metrics ---
active_positions:         int
recommendations_generated: int
recommendations_resolved:  int
win_rate_pct:             float
profit_factor:            float
sharpe:                   float
sortino:                  float
max_drawdown_pct:         float
alpha_vs_nifty:           float
alpha_vs_sector:          float

# --- quality metrics ---
false_strong_buy_pct:     float
true_positive_pct:        float
missed_winners_count:     int
early_exit_pct:           float
late_exit_pct:            float

# --- distribution ---
avg_winner_pct:           float
avg_loser_pct:            float
avg_holding_days:         float
median_holding_days:      int
recommendation_half_life_days: float

# --- calibration ---
calibration_error:        float  # Brier-like score
confidence_buckets:       list   # per-bucket predicted vs actual

# --- drift indicators ---
recommendation_stability: float  # 1.0 = every rec appears in prior run
turnover_pct:             float  # daily
alpha_decay_slope:        float  # rolling 60D alpha regression slope

# --- provenance ---
mon001_fingerprint:       str    # fingerprint at snapshot time
cycle_version:            str    # e.g., "AEGIS_v2.2"
cumulative_strategy_search: int  # 38 (verified unchanged)
```

### 5.4 Calibration table: `calibration.jsonl`

```yaml
period_id:                str
confidence_bucket:        str    # e.g., "0-20", "20-40", "40-60", "60-80", "80-100"
predicted_win_rate:       float  # midpoint of bucket
recs_in_bucket:           int
actual_win_rate:          float
calibration_delta:        float  # actual − predicted
calibration_severity:     str    # OK / MISCALIBRATED / SEVERELY_MISCALIBRATED
```

### 5.5 Alert log: `alert_log.jsonl`

Same schema as OPS001-C `Notification` (dict form) with LAB011-specific fields:

```yaml
timestamp_utc:            iso8601
severity:                 str    # INFO / WARN / ERROR / CRITICAL
source:                   str    # e.g., "oi.calibration"
alert_code:               str    # e.g., "OI-C-01"
title:                    str
body:                     str
threshold:                float
observed_value:           float
context:                  dict
```

---

## 6. KPI catalogue (institutional metrics)

Grouped into 6 institutional families.

### 6.1 Hit-quality KPIs (per rec)

| KPI | Definition | Institutional benchmark |
|---|---|---|
| **Hit Rate** | Fraction of resolved recs with `final_return > 0` | 55%+ = good |
| **False Strong Buy %** | StrongBuys with `alpha_vs_nifty < 0` | < 30% |
| **False Buy %** | Buys with `final_return < 0` | < 40% |
| **True Positive %** | StrongBuys with `alpha_vs_nifty > 2%` | > 40% |
| **Missed Winners** | Non-held tickers that outperformed by >5% during equivalent horizon | Count + names |

### 6.2 Return-quality KPIs

| KPI | Definition | Benchmark |
|---|---|---|
| **Profit Factor** | Sum(winners) / abs(Sum(losers)) | > 1.5 |
| **Sharpe** (30D rolling) | 252 × mean/std of daily returns | > 1.0 |
| **Sortino** (30D) | Same but only downside vol | > 1.2 |
| **Max Drawdown %** | Worst peak-to-trough on active portfolio | Track over time |
| **Avg Winner %** | Mean return of winners | Track |
| **Avg Loser %** | Mean return of losers | Track |
| **Win/Loss Ratio** | Avg Winner / Avg Loser | > 1.5 |

### 6.3 Alpha KPIs

| KPI | Definition | Institutional |
|---|---|---|
| **Alpha vs Nifty** | Portfolio return − Nifty return over same period | > 0 |
| **Alpha vs Sector** | Rec return − sector return | > 0 |
| **Beat Expected Return %** | Frequency `final_return > target × 0.5` (partial credit) | > 60% |

### 6.4 Timing KPIs

| KPI | Definition |
|---|---|
| **Avg Holding Days** | Mean of `days_held` over resolved recs |
| **Median Holding Days** | Median (robust to outliers) |
| **Recommendation Half-Life** | Days until 50% of a cohort has exited |
| **Early Exit %** | Exits where MFE exceeds final return by >5% |
| **Late Exit %** | Exits where MFE > final return by >5% AND exit came after MFE |
| **Time to Target %** | For target-hits, fraction of horizon consumed |

### 6.5 Recommendation-quality KPIs

| KPI | Definition |
|---|---|
| **Recommendation Stability** | Cosine similarity of today's ranked list vs yesterday's |
| **Turnover %** | Fraction of positions changed per rebalance |
| **Confidence Calibration Error** | Mean absolute (predicted − actual) across confidence buckets |
| **Rank-in Duration** | For a rec present today, how many prior days it was in the top-N |

### 6.6 Longitudinal KPIs

| KPI | Definition |
|---|---|
| **Alpha Decay Slope** | Regression slope of alpha over rolling 60-day window (negative = alpha decaying) |
| **Recommendation Survival Curve** | Kaplan-Meier-style curve of active-rec attrition by day-of-life |
| **Win-rate trend** | Rolling 30-day win rate; alert on 3σ deterioration |
| **Sector-level attribution over time** | Which sectors contributed most / least alpha per quarter |

---

## 7. Learning opportunity detection

LAB011 is **evidence-producing**, not experiment-running. It IDENTIFIES
research opportunities. It does NOT run experiments — that stays with
future explicit alpha labs (LAB012+ if authorised).

### 7.1 Detection dimensions

| Dimension | What LAB011 measures | What it reveals for future research |
|---|---|---|
| **Sector bias** | Alpha per sector | If Pharma consistently outperforms while Metals underperforms, future research could weight sectors |
| **Regime bias** | Alpha per market regime (Weak/Neutral/Strong) | Regime-conditional exposure sizing (extends LAB007) |
| **Holding-period bias** | Alpha per days-held bucket | Optimal holding period may not be 63d |
| **Confidence bias** | Actual vs predicted per confidence bucket | If 80% confidence gives 50% actual, calibration is broken |
| **Position-size bias** | Alpha per weight bucket (5-10%, 10-15%, etc.) | Does putting more weight on higher-grade recs actually help? |
| **Exit-timing bias** | MFE minus final return distribution | Persistent gap = exit rule is too slow / too fast |
| **Rotation bias** | Alpha lost by rotating out vs holding through | Is our rotation aggressive or lazy? |
| **Stop-loss bias** | Frequency of stop-then-recover | Are stops set too tight? |
| **False-signal bias** | Systematic patterns in false Strong Buys | Feature engineering targets |
| **Volatility bias** | Alpha per volatility bucket | High-vol vs low-vol candidate performance |

### 7.2 Bias reports

Monthly, LAB011 generates a `bias_report_YYYY-MM.md` with:

- Per-dimension KPIs
- Statistical significance (>N recs per bucket required)
- Recommendations for future research phrased as HYPOTHESES (not implemented):

Example excerpt:

```
Sector bias detected (2026 Q3):
- Pharma alpha: +4.2% vs Nifty (n=18, p=0.03)
- Metals alpha: -3.1% vs Nifty (n=12, p=0.11)
Suggested future hypothesis (LAB012 candidate):
  "Weight sectors by their trailing 60-day alpha distribution."
Status: HYPOTHESIS. Not tested. Not implemented.
```

**Constraint:** these hypotheses are logged, not acted on. Any future
LAB that acts on them counts as a research trial and must go through
the preregistration ceremony.

---

## 8. Dashboards

### 8.1 Daily dashboard (`oi_dashboard_YYYY-MM-DD.md`)

Generated every trading day after MON001 daily runner. ≤ 1 page.

Contents:
- Headline: today's win rate delta vs 30D average
- Portfolio state: active positions, cash, deployment
- Today's outcomes: any RESOLVED recs today (target hit / stop / expired)
- Newly-active: RECs entering ACTIVE state today
- MFE/MAE alerts: recs approaching stop or target
- Confidence calibration snapshot: today's confidence-bucket vs actual comparison

### 8.2 Weekly review (`oi_weekly_YYYY-WW.md`)

Generated Friday post-close. ≤ 2 pages.

Contents:
- Week P&L attribution: which recs made / lost money
- Sector attribution: which sectors contributed
- Newcomers vs veterans: alpha by holding period bucket
- Exits this week: reasons + outcomes
- Missed winners: 5 stocks that outperformed without being held
- Confidence calibration weekly delta
- Alert digest

### 8.3 Monthly attribution (`oi_monthly_YYYY-MM.md`)

Generated 1st of each month. ≤ 4 pages.

Contents:
- Full attribution: rec-by-rec P&L waterfall
- Sector/regime/horizon breakdowns
- Bias detection report (§7.2)
- Top 10 contributors, top 10 detractors
- Calibration curve (predicted vs actual by bucket)
- Portfolio Sharpe / Sortino / max DD
- Rolling 90-day trend charts

### 8.4 Quarterly performance (`oi_quarterly_YYYY-QN.md`)

Generated end of Q1/Q2/Q3/Q4. ≤ 6 pages.

Contents:
- Quarterly performance vs Nifty, sector benchmarks
- Alpha decay analysis
- Recommendation survival curve
- Trial-count status (cumulative_strategy_search)
- Certification lineage
- Research opportunities catalog
- Executive summary for potential external audit

### 8.5 Annual scorecard (`oi_annual_YYYY.md`)

Publishable form. ≤ 10 pages.

Contents:
- Executive summary
- Full-year performance tables
- Attribution
- Calibration curves
- Chronological timeline of certifications + amendments
- Learning opportunity catalog for next year
- Recommendation database summary statistics

---

## 9. Alerts

Every alert has: **code · severity · trigger · action**.

### 9.1 Alert catalog

| Code | Severity | Trigger | Suggested action |
|---|:-:|---|---|
| OI-C-01 | CRITICAL | Confidence calibration error > 30% for 3 consecutive weeks | Halt Strong-Buy weighting; investigate signal decay |
| OI-C-02 | CRITICAL | Win rate < 40% over 30-day rolling window | Halt live recommendations; investigate |
| OI-C-03 | CRITICAL | Model drift detected: rec set vs 7-day-ago has cosine similarity < 0.3 | Investigate — likely bug in refresh or data |
| OI-E-01 | ERROR | Strong Buy failure rate > 50% in a calendar month | Review Strong-Buy criteria (research hypothesis, not immediate fix) |
| OI-E-02 | ERROR | Sector consistently negative alpha for 30D + statistically significant | Log as research candidate |
| OI-E-03 | ERROR | Average holding period doubled vs 90D baseline | Investigate rotation logic |
| OI-W-01 | WARN | 5 recs approaching stop-loss (< 2% from stop) | Operator review before market open |
| OI-W-02 | WARN | 2 or more consecutive false Strong Buys | Watchlist candidate; not blocking |
| OI-W-03 | WARN | Weekly win rate ≥ 1σ below rolling 90D average | Contextual — check regime |
| OI-W-04 | WARN | New alpha-decay slope crosses zero (from positive to negative) | Track for 4 weeks; escalate if persists |
| OI-W-05 | WARN | Recommendation half-life > horizon_days × 1.5 | Rotations getting slower — investigate |
| OI-I-01 | INFO | Daily summary line for monitoring |  Track only |
| OI-I-02 | INFO | Weekly summary line | Track only |

### 9.2 Alert routing (reuses OPS001-C)

`OI-C-*` → `RoutingPolicy.CRITICAL` → all channels (Telegram + Email + Slack + Discord + Webhook + File)
`OI-E-*` → `RoutingPolicy.ERROR` → Telegram + Email + File
`OI-W-*` → `RoutingPolicy.WARN` → Telegram + File
`OI-I-*` → `RoutingPolicy.INFO` → File only

Alert templates should extend the existing `nexaquant/ops/notify/templates.py`.

---

## 10. Workflow + cadence

### 10.1 Daily cadence

```
Post-close IST (after 16:30 IST MON001 daily runner):

1. Ingest today's outputs
   - Read new rows from data/aegis_registry.csv
   - Read Telegram delivery ledger
   - Read latest mon001_diagnostics_*.json

2. Update lifecycle states
   - New GENERATED → check delivery → DELIVERED / DELIVERY_FAILED
   - ACTIVE recs: update MFE/MAE with today's close
   - Check terminal conditions: TARGET_HIT / STOP_HIT / TRAILING_HIT / EXPIRED / REPLACED

3. Compute outcome deltas
   - Recompute all ACTIVE recs' current_pct
   - Recompute alpha_vs_nifty / alpha_vs_sector for active recs
   - Flag any newly resolved outcomes

4. Aggregate KPIs
   - Update daily KPI snapshot
   - Update rolling 30D / 90D / 1Y windows

5. Evaluate alert rules
   - Compare KPIs to thresholds
   - Fire alerts via OPS001-C notification bus

6. Generate daily dashboard
   - Write india/outcome_intelligence/reports/oi_dashboard_YYYY-MM-DD.md

Cost budget: < 60 seconds per daily run.
```

### 10.2 Weekly cadence

- Every Friday post-close: weekly review + calibration update
- Every Sunday: rolling-7-day rebuild of KPI snapshots

### 10.3 Monthly cadence

- 1st of each month: monthly attribution + bias report

### 10.4 Quarterly + yearly cadences

- End of March / June / September / December: quarterly performance
- End of December: annual scorecard

### 10.5 Deployment options

Two paths:

**Option A: GitHub Actions cron.** Add `.github/workflows/lab011-daily.yml`
that fires at 16:45 IST Mon-Fri (after MON001 daily), same 3-slot
redundancy pattern. Advantage: proven infrastructure. Disadvantage:
adds another workflow.

**Option B: Extend OPS001-B daemon.** Add a new pipeline stage
`lab011_outcome_intelligence` after `mon001_daily` in
`nexaquant/ops/pipelines/aegis_daily.yaml`. Runs when daemon is deployed.
Advantage: consolidated. Disadvantage: daemon not yet deployed.

**Recommendation:** Option A initially (GitHub Actions), migrate to
Option B when daemon is live.

---

## 11. Research roadmap

### 11.1 What LAB011 unlocks for future research

None of the below is done by LAB011 itself — LAB011 produces the evidence base.

| Future initiative | Evidence LAB011 provides |
|---|---|
| **MON002 drift-forecasting** | 60+ days of calibration data + alpha-decay slopes |
| **LAB012 sector-tilted allocation** (hypothesis) | Sector-level alpha attribution over 90+ days |
| **LAB013 regime-conditional exposure** (hypothesis) | Regime-level alpha attribution |
| **LAB014 confidence recalibration** (hypothesis) | Bucket-wise calibration curves |
| **Publishable annual track record** | Full audited outcome database |
| **External-audit certification** | Reproducible outcome computations |

Each "LABxxx hypothesis" would require its own preregistration and
would count as a research trial. LAB011 makes those trials CHEAP to
conduct (data is ready) and HONEST (evidence is authoritative).

### 11.2 Recommended research phasing (post-LAB011)

```
Phase A — LAB011 delivery (weeks 1-3)
Phase B — Observation window (weeks 4-16)
  Accumulate 60-90 days of outcomes
  Let bias reports produce hypotheses
Phase C — Evidence review (week 17)
  Independent review of bias reports
  Decide which hypotheses are worth trials
Phase D — LAB012 (or MON002) trial (week 18+)
  Only after Phase C conclusions
```

No new research trial should be authorised before Phase C. This
preserves the operator's "stop adding alpha research" directive
until forward evidence is meaningful.

---

## 12. Implementation roadmap

### 12.1 Phase 1 — Foundation (5 elapsed days)

- `india/outcome_intelligence/ingest.py` — read-only pulls
- `india/outcome_intelligence/lifecycle.py` — state machine
- `india/outcome_intelligence/outcomes.py` — per-rec MFE/MAE + terminal detection
- `india/outcome_intelligence/schemas/outcomes_schema.yaml`
- Test suite: `test_lab011_framework.py` — 30-40 tests
- Register in `nexaquant/tests/test_regression.py`

### 12.2 Phase 2 — KPIs + calibration (5 days)

- `india/outcome_intelligence/kpi.py` — all 6 KPI families
- `india/outcome_intelligence/calibration.py` — bucket-wise
- Historical backfill: recompute outcomes for all 285 recs in scorecard
- Materialize `recommendation_states.parquet`

### 12.3 Phase 3 — Dashboards + alerts (5 days)

- `india/outcome_intelligence/dashboards/*.py`
- `india/outcome_intelligence/alerts.py`
- Wire alerts to OPS001-C notification bus (uses existing routing)
- Add `.github/workflows/lab011-daily.yml` (or daemon-side stage)

### 12.4 Phase 4 — Bias reports + monthly cadence (2 days)

- Bias detection module
- Monthly report generator
- First monthly bias report (once 30 days of data present)

**Total: ~17 elapsed days = ~1 focused month. Each phase produces a
publishable artefact. Phases 1-2 unlock daily value; Phase 4 unlocks
research-roadmap value.**

### 12.5 What NOT to build in LAB011

Explicitly out of scope:

- Auto-recalibration of confidence scores (that's a strategy change; would need preregistration)
- Auto-adjustment of sector caps based on bias (strategy change)
- Auto-generation of new recommendations (production change)
- ML models that predict outcomes (research trial)
- Retraining any existing scorer (research trial)
- Modifying `recommendation_generator.py` in ANY way (sealed file)

---

## 13. Dependencies

### 13.1 Hard prerequisites (must be present before LAB011 starts)

- ✅ MON001 sealed and certified (present)
- ✅ Forward ledger with 100+ rows (present: 150 rows)
- ✅ Recommendation registry (present: 359+ rec_ids)
- ✅ Historical parquet data spanning inception to today (present)
- ✅ OPS001-C notification bus for alert routing (present)
- ⏳ OPS001-F production fix landed and verified live (verify 16:15 IST today)
- ⏳ Cleanup of docs/ (optional but recommended before starting)

### 13.2 Soft prerequisites (nice to have)

- Actual-holdings tracking (`portfolio_state.yaml` — not present, would enrich `entered` flag)
- Second data source for benchmark verification (not present)
- OPS001-B daemon deployed (not required; GitHub Actions is fine)

### 13.3 Dependencies on future work

**None.** LAB011 does not require any future initiative to be complete.

### 13.4 What LAB011 unblocks (dependency direction)

- MON002 (drift forecasting) depends on LAB011 calibration data
- Any LAB012+ (post-LAB011) benefits from LAB011 evidence
- Publishable track record depends on LAB011 outputs
- External audit certification would require LAB011 KPIs

---

## 14. Risk assessment

### 14.1 Risk register

| Risk | Prob | Impact | Mitigation |
|---|:-:|:-:|---|
| **LAB011 accidentally modifies production files** | LOW | HIGH | Read-only enforced by test guards (analogous to test_no_sealed_files_modified_by_eng001). All writes go under `india/outcome_intelligence/data/`. |
| **Outcome computation has bugs (wrong MFE/MAE)** | MED | MED | Golden-file tests on 5-10 hand-verified recs. Include unit tests for edge cases (weekend gaps, holidays, split adjustments). |
| **KPI thresholds mis-set → alert fatigue** | HIGH | LOW | Initial WARN thresholds set at 2σ, tightened after 30 days of live data. |
| **LAB011 wrongly classified as alpha research → PBO risk** | LOW | HIGH | Preregistration explicitly declares non-lab status. Regression test asserts `cumulative_strategy_search` unchanged after LAB011 lands. |
| **Bias reports produce spurious signals** | HIGH | MED | Statistical significance floor (n ≥ 10 per bucket, p ≤ 0.05). Multi-testing correction (Bonferroni). Reports include "n" and "p" per finding. |
| **LAB011 adds dependency footgun** | LOW | MED | Uses ONLY existing deps (pandas, numpy, pyarrow, scipy). No new pip packages. |
| **Ingestion breaks when production schema changes** | MED | MED | Schema-validation test on read. Alerts if schema drift detected. |
| **Calibration curves misinterpreted** | MED | LOW | Documented in `docs/OPS001_5_OPERATOR_RUNBOOK.md` extension: "how to read a calibration curve". |
| **Alert bus overwhelmed by high-frequency LAB011 alerts** | LOW | LOW | INFO-level alerts route only to file; WARN and higher throttled to 1 per calendar day per code. |
| **Storage growth unbounded** | LOW | LOW | JSONL files rotate monthly via existing log rotation infrastructure. |

### 14.2 Governance risks

- **MON001 certification impact:** ZERO. LAB011 does not touch sealed files. Fingerprint unchanged.
- **`cumulative_strategy_search` impact:** ZERO. Preregistration declares non-lab. Regression test guards.
- **PBO impact:** ZERO. No hypothesis tested; no experiments run.

### 14.3 What can go wrong that is NOT easily mitigated

- **Operator misinterprets LAB011 alerts as directives.** LAB011 detects
  patterns; it does not prescribe actions. Operator training required —
  reflect in `docs/OPS001_5_OPERATOR_RUNBOOK.md`.
- **Adverse effect of measuring:** Goodhart's law risk. Once we measure
  "false Strong Buy %", there's pressure to reduce it — even at cost of
  overall alpha. Mitigation: KPI dashboard shows every metric; no single
  KPI is a governance target.
- **Bias reports become read as strategy prescriptions.** They must be
  labelled HYPOTHESES not RECOMMENDATIONS.

---

## 15. Expected value (business, alpha, operational, research)

### 15.1 Business value

**HIGH.**

- Publishable track record after 90 days — enables external
  demonstration.
- Turns MON001's "the system is running" story into "the system is
  running AND here is proof of what it produces".
- Foundation for external audit certification (institutional prerequisite).
- Operator can answer "how has the system done?" with data, not narrative.

### 15.2 Expected alpha improvement

**INDIRECT ONLY.**

LAB011 itself contributes **zero direct alpha**. It cannot — by
construction, it modifies no strategy.

However, LAB011 REVEALS opportunities that (if authorised as future
LAB experiments) could contribute:

- **Sector-tilted allocation** (candidate hypothesis) — potential
  +0.5% to +1.5% CAGR IF LAB012 confirms sector-level alpha is
  actionable and not survivorship.
- **Regime-conditional exposure** — potential +0.3% to +1.0% CAGR IF
  LAB013 confirms regime bias is exploitable.
- **Confidence recalibration** — potential improvement in Sharpe
  through better position sizing.

**Estimated indirect alpha through post-LAB011 initiatives: +1% to +2.5% CAGR over 12 months**
IF the follow-on labs prove out. HIGHLY conditional on evidence.

### 15.3 Operational improvement

**HIGH.**

- Automated daily/weekly/monthly reports replace manual attribution work.
- Operator time saved: ~30-60 min per week.
- Alerts catch degradation early (calibration drift, alpha decay).
- Publishable artefacts (annual scorecard) reduce ad-hoc reporting requests.

### 15.4 Research value

**VERY HIGH.**

- Every future research trial gets:
  - Empirical baseline (what current strategy actually produces)
  - Bias catalog (where opportunities exist)
  - Reproducible outcome verification (post-trial)
- Reduces PBO risk of future trials: hypotheses derived from LAB011 data
  are less likely to be data-burn candidates.
- Enables **honest** decisions about whether to add more strategy trials.

---

## 16. Complexity assessment

### 16.1 Implementation complexity: **MEDIUM**

- Est. 1500-2500 LOC across ~15 files
- ~30-40 unit tests
- ~5-10 integration tests
- ~15 days total elapsed effort (matches Phase 1-3 in §12)
- Zero new dependencies
- Zero fitting, ML, optimization — mostly deterministic pandas + numpy

### 16.2 Cognitive complexity: **MEDIUM-HIGH**

- 6 KPI families × ~5-10 metrics each = ~40 institutional metrics
- 11 exit reasons × ~5 quality categories = ~55 outcome types
- Calibration statistics require care (confidence intervals, multi-test correction)
- Dashboard design must balance detail vs mobile readability

### 16.3 Maintenance burden: **LOW**

- Additive to existing infrastructure
- No coupling with sealed files
- Test suite guards against schema drift
- Failure modes are visible (unlike the OPS001-E defect that hid for 17 days)

### 16.4 Operational overhead: **LOW**

- Daily job < 60 seconds
- Storage growth ~5-10 MB/year
- No new secrets required

---

## 17. Priority verdict — should LAB011 come first?

### 17.1 Alternatives considered

Ranked by ROI as of 2026-07-17:

| # | Initiative | ROI signal | Time to value |
|:-:|---|:-:|:-:|
| 1 | **LAB011 Outcome Intelligence** | ⭐⭐⭐⭐⭐ | 3-4 weeks |
| 2 | OPS001-I (Telegram redesign implementation from H) | ⭐⭐⭐⭐ | 1 focused session |
| 3 | MON002 drift forecasting | ⭐⭐⭐⭐ (but depends on #1 data) | Deferred until LAB011 delivers |
| 4 | LAB012+ (new alpha lab) | ⭐⭐ (compounds PBO risk without LAB011 data) | Should not start until LAB011 |
| 5 | OPS001-B daemon deployment on VPS | ⭐⭐⭐ | Half day + observation |
| 6 | Docs cleanup (56 → 15 files) | ⭐⭐ | Half day |
| 7 | Off-repo backup of forward_ledger | ⭐⭐⭐ | 15 minutes |

### 17.2 Why LAB011 wins

**LAB011 sits on the critical path for every other high-ROI initiative:**

- MON002 needs LAB011 data → LAB011 first
- Any new alpha lab needs LAB011 data to be honest → LAB011 first
- Annual audit requires LAB011 outputs → LAB011 first
- Publishable track record requires LAB011 → LAB011 first

**LAB011 also has the highest evidence-per-day accrual:**
Every trading day adds ~5-8 recommendations that flow into the outcome
DB. After 90 days = 500+ resolutions × 40 metrics = 20,000+ data points
supporting future decisions.

### 17.3 What competes with LAB011 for the #1 slot

**OPS001-I (Telegram redesign implementation)** competes on user-visible
value. The operator reads Telegram daily; LAB011 outputs are consumed by
the operator less frequently (weekly/monthly reports). BUT: OPS001-I is
smaller (1 session) and doesn't preclude LAB011.

**Recommendation:** OPS001-I first (small, immediate user value), then
LAB011 in parallel with the 30-day observation window that OPS001-G
prescribed.

### 17.4 What should NOT come before LAB011

**Any alpha research (LAB012+).** Explicit rejection. Adding more
strategy trials before LAB011 provides outcome intelligence would:
- Increment `cumulative_strategy_search` towards PBO cliff
- Add hypotheses that cannot be validated with existing evidence
- Contradict the operator's stated "stop adding alpha research" directive

### 17.5 Final ranked sequence

```
IMMEDIATE (today - week 1):
  ✅ Verify OPS001-F live at 16:15 IST (completed if all-green)
  ⏳ OPS001-I Telegram implementation (~1 session)
  ⏳ Off-repo backup (~15 minutes)
  ⏳ Docs cleanup approval (~operator decision)

NEAR-TERM (weeks 2-4):
  → LAB011 Phase 1 (foundation)
  → LAB011 Phase 2 (KPIs + calibration)

MEDIUM-TERM (weeks 5-8):
  → LAB011 Phase 3 (dashboards + alerts)
  → LAB011 Phase 4 (bias reports + monthly cadence)

LONG-TERM (weeks 9+):
  → 60-90 days observation window with LAB011 collecting evidence
  → MON002 (drift-detection using LAB011 base) — proposal only, not authorized
  → Evidence review committee (operator + independent)
  → Only THEN: consider LAB012+ alpha initiatives
```

### 17.6 Answer to the exact question

**Should LAB011 become the highest priority research initiative?**

If "research initiative" means "new alpha lab" — **NO**. LAB011 is not
an alpha lab. Framing it as one would confuse the trial registry.

If "research initiative" means "the next major work stream" — **YES**,
after OPS001-I lands. LAB011 is the highest-value non-production-code
initiative available AND it unblocks every subsequent research decision.

**Recommended framing for LAB011:**

> LAB011 is a **research-enabling observability layer**, not a research
> experiment. Its purpose is to ensure that when the operator authorises
> LAB012 (or MON002), the decision is made on 90 days of evidence rather
> than on intuition. It reduces the marginal cost and PBO risk of every
> future research decision.

---

## 18. What LAB011 does NOT do

- ❌ Does not modify any production code
- ❌ Does not touch MON001 sealed files
- ❌ Does not touch LAB001–LAB010 artefacts
- ❌ Does not modify `recommendation_generator.py`, `arjuna_v2.py`, or any strategy code
- ❌ Does not increment `cumulative_strategy_search`
- ❌ Does not run any strategy search
- ❌ Does not tune parameters
- ❌ Does not fit any model
- ❌ Does not backtest alternative strategies
- ❌ Does not modify HOLD, rebal, HRP, sector caps, name caps, method
- ❌ Does not change portfolio construction
- ❌ Does not change recommendation delivery
- ❌ Does not create commits (this spec is design-only)
- ❌ Does not push anything

---

## 19. Awaiting operator authorization

Three orthogonal decisions:

1. **Approve LAB011 as the next major work stream** (following OPS001-I).
   → Yes / No / Modify scope

2. **Approve LAB011's "not a research lab" classification.**
   → Yes / No / Rename to MON002-OI / Rename to OI001

3. **Approve Phase 1 start date.**
   → After OPS001-I lands / After 30-day OPS001-F observation / Immediately in parallel

No implementation is authorized by this spec. No commits will be made
without explicit further authorization.

---

**End of LAB011 Outcome Intelligence design specification.**

**Verdict: recommended as the next major initiative — as an observability
layer, not an alpha lab. Sequenced after OPS001-I; runs during the 30-day
OPS001-F observation window; unblocks every future research decision.**
