# AEGIS Research Journal

_Production baseline: **AEGIS Production 1.3** · selection RQS **0.5** (the bar every experiment must beat out-of-sample). Production is frozen; nothing here reaches it without passing the full pipeline._

## Research Leaderboard

| LAB | Dataset | Status | IC | Lift | Walk-Fwd | Forward | Decision |
|-----|---------|--------|----|------|----------|---------|----------|
| LAB-001 | Earnings Intelligence | planned | — | — | — | — | pending |
| LAB-002 | Point-in-Time Fundamentals | planned | — | — | — | — | pending |
| LAB-003 | Corporate Actions / Events | planned | — | — | — | — | pending |
| LAB-004 | Institutional Money | planned | — | — | — | — | pending |
| LAB-005 | Learning-to-Rank | harness-built | — | -0.006 | FAIL | — | reject |

**Promoted to production:** none yet  ·  **Tested:** 1  ·  **Total experiments:** 5

_Success is measured by how many weak ideas were rejected before they could contaminate production — not by how many shipped._

---

## LAB-001 — Earnings Intelligence

**Question:** Do quarterly earnings surprises / guidance / revisions improve cross-sectional ranking?

**Dataset:** NSE quarterly earnings surprise, guidance, estimate revisions (point-in-time)

| Field | Value |
|-------|-------|
| Status | planned |
| Coverage | — |
| Missing % | — |
| IC | — |
| Incremental lift (RQS) | — |
| Walk-forward | — |
| Forward paper | — |
| **Decision** | **pending** |

**Notes:** Highest-ROI first dataset. Blocked only on data acquisition.

_Gate: drop the dataset in `data/layers/earnings.parquet` and run `python india/data_layer_gate.py`; record IC / lift here._

---

## LAB-002 — Point-in-Time Fundamentals

**Question:** Do as-reported fundamentals and their acceleration rank winners better than price?

**Dataset:** PIT ROE / margins / debt / growth + acceleration (as-reported dates)

| Field | Value |
|-------|-------|
| Status | planned |
| Coverage | — |
| Missing % | — |
| IC | — |
| Incremental lift (RQS) | — |
| Walk-forward | — |
| Forward paper | — |
| **Decision** | **pending** |

**Notes:** Must be strictly point-in-time or the verdict is a lie.

_Gate: drop the dataset in `data/layers/fundamentals.parquet` and run `python india/data_layer_gate.py`; record IC / lift here._

---

## LAB-003 — Corporate Actions / Events

**Question:** Do discrete events (orders, approvals, M&A, buybacks) carry rankable information?

**Dataset:** corporate-action / event feed with public announcement dates

| Field | Value |
|-------|-------|
| Status | planned |
| Coverage | — |
| Missing % | — |
| IC | — |
| Incremental lift (RQS) | — |
| Walk-forward | — |
| Forward paper | — |
| **Decision** | **pending** |

**Notes:** Prone to look-ahead/survivorship — be strict on announcement dates.

_Gate: drop the dataset in `data/layers/events.parquet` and run `python india/data_layer_gate.py`; record IC / lift here._

---

## LAB-004 — Institutional Money

**Question:** Do FII / DII / MF / ETF flows and holdings changes lead or confirm moves?

**Dataset:** FII / DII net flows + fund holdings changes (disclosure-dated)

| Field | Value |
|-------|-------|
| Status | planned |
| Coverage | — |
| Missing % | — |
| IC | — |
| Incremental lift (RQS) | — |
| Walk-forward | — |
| Forward paper | — |
| **Decision** | **pending** |

**Notes:** Aggregate flows may help the regime overlay; stock-level holdings are the per-name signal.

_Gate: drop the dataset in `data/layers/flows.parquet` and run `python india/data_layer_gate.py`; record IC / lift here._

---

## LAB-005 — Learning-to-Rank

**Question:** Does an ML ranker over richer features beat the hand-weighted suitability score?

**Dataset:** technicals + sector + KEPT LAB datasets -> relative ranking (never price)

| Field | Value |
|-------|-------|
| Status | harness-built |
| Coverage | 100% |
| Missing % | 0 |
| IC | — |
| Incremental lift (RQS) | -0.006 |
| Walk-forward | FAIL |
| Forward paper | — |
| **Decision** | **reject** |

**Notes:** Runs LAST. Rejected on price alone (expected). Harness = india/ai_lab/rank_model.py (ai-lab branch).

_Gate: drop the dataset in `data/layers/ltr.parquet` and run `python india/data_layer_gate.py`; record IC / lift here._

---
