# AEGIS · Sprint K · 25-Issue Portfolio State Machine Refactor

**Signed:** 2026-08-06 · execute post-lock (Runner 3 Day-30 gate = 2026-09-09)
**Trigger:** Operator 25-issue audit 2026-08-06 · "AEGIS currently has NO
concept of Position State · every day it is creating a snapshot · instead
it should maintain Discovery → Recommendation → Active Position →
Monitoring → Exit."

---

## Executive summary

Operator identified 25 issues across the recommendation lifecycle. **8 shipped
tonight** as quick wins. **17 deferred to Sprint K** because they need
engine changes that would confound Runner 3's Day-30 shadow window.

### Shipped tonight (Sprint J-final)
| # | Issue | Fix |
|---|---|---|
| 1 | Date vs Recommended Date | Recommended is immutable via position_store first_seen_date |
| 2 | Entry Price frozen | Uses position_store first_seen_price · never re-anchors |
| 7 | Prev Close + Today Move | New `Prev Close` column · Today Move already computed |
| 8 | Current Perf auto-compute | `(current - entry) / entry × 100` derived in row builder |
| 12 | Trading vs Calendar Days | New `Trading Days` column (excludes weekends) |
| 14 | R1_NEW / R2_NEW tag | Auto-decay via rank_history lookup |
| 15 | Position Stage lifecycle | New `Position Stage` column (NEW/ACTIVE/MATURE/WATCH/EXIT) |
| 21 | Position ID | New `Position ID` column · {TKR}_{MKT}_{YYYYMMDD} |

XLSX: 50 → 54 columns · single sheet · Sheet name "AEGIS Daily".

### Deferred to Sprint K (17 items · 5-7 days engineering)

#### Group A · Dynamic risk fields (need ATR engine)
- **Issue 3** · Initial Buy Zone vs Dynamic Buy Zone (ATR-based expand/contract)
- **Issue 4** · Trailing Stop Loss (ATR + volatility + regime)
- **Issue 5** · Dynamic Risk % (recomputed daily from stop distance + vol)
- **Issue 6** · Initial Target vs Current Target (trail once T1 hit)

Implementation: new `backend/portfolio/dynamic_risk.py` · reads ATR from
bar data (add to feature store) · recomputes stop/targets daily · writes
Initial + Dynamic columns to XLSX.

#### Group B · Better rankings (need engine changes)
- **Issue 13** · Yesterday Rank + Weekly Rank columns
- **Issue 14** · Universe scan (full NSE 200 + S&P 500 · not top-15)
- **Issue 25** · Discovery Rank vs Portfolio Rank (dual concept · one display)

Implementation: R2 ensemble runs across full universe daily · then splits
output into 3 pools: current holdings · new discoveries · watch list.
Rank column derives from Run_Type context.

#### Group C · Explanations
- **Issue 16** · Health breakdown (Trend/Momentum/Breadth/Macro/Liquidity subscores)
- **Issue 17** · Confidence Raw + Adjusted + Final columns
- **Issue 18** · AI-generated narrative Story (LLM · not raw driver list)
- **Issue 24** · Opportunity Freshness age tag (1 day · 2 days · 7 days · Expired)

Implementation: extend health_score to emit subscores · add LLM call to
generate 1-sentence Story per rec · freshness derived from days since
first_seen.

#### Group D · Behavioral
- **Issue 19** · Expected Alpha decay (18% → 9% → 3% over horizon)
- **Issue 20** · Portfolio Weight = f(confidence) (12% at 90% · 4% at 40%)
- **Issue 22** · Status vocabulary (NEW/BUY/ADD/HOLD/REDUCE/EXIT · 6-state)
- **Issue 23** · Exit Reason auto-classification (Target/Stop/Time/Macro/AI/Risk)

Implementation: add `backend/portfolio/lifecycle_actions.py` · reads current
state + triggers · emits action per rec. Update _rec_to_row Status derivation.

#### Group E · Meta
- **Issue 9** · Max Gain daily update (already exists · verify)
- **Issue 10** · Max Drawdown daily update (already exists · verify)
- **Issue 11** · Days Left = Horizon − Elapsed (columns already exist · verify)

Currently these ARE updated daily by mark-to-market · but display may be
stale in some edge cases. Sprint K verifies + adds MTM freshness guard.

---

## Sprint K architecture · Position State Machine

The core refactor moves AEGIS from "daily snapshot" to "persistent position":

```
┌──────────────────────────────────────────────┐
│  Position (persistent · immutable fields)      │
│  · Position ID · Discovery Date                 │
│  · Recommendation Date · Entry Date · Entry Px │
│  · Initial Buy Zone · Initial Stop · Init Tgt  │
│  · Initial Confidence · Initial Alpha           │
└──────────┬───────────────────────────────────┘
           │
           ▼ (daily append)
┌──────────────────────────────────────────────┐
│  Snapshot Row (dynamic fields · daily update)  │
│  · Snapshot Date · Current Price · Current Perf │
│  · Dynamic Buy Zone · Trailing Stop · Cur Target│
│  · Current Rank · Current Confidence · Cur Alpha│
│  · Position Stage · Max Gain · Max DD · Risk %  │
│  · Status Action (NEW/BUY/ADD/HOLD/REDUCE/EXIT) │
└──────────────────────────────────────────────┘
```

Storage:
- `reports/positions/{market}/{position_id}.json` · immutable header + snapshot history
- XLSX joins position header + latest snapshot per row

---

## Execution timeline

- **2026-08-06 tonight**: 8 quick-win issues shipped (this commit)
- **2026-09-09**: Runner 3 Day-30 gate fires
- **2026-09-10 to 2026-09-25**: Sprint K Group A (Dynamic risk fields)
- **2026-09-26 to 2026-10-05**: Sprint K Group B (Ranking refactor)
- **2026-10-06 to 2026-10-15**: Sprint K Group C (Explanations)
- **2026-10-16 to 2026-10-25**: Sprint K Group D (Behavioral)
- **2026-10-26 to 2026-11-03**: Sprint K Group E + integration + regression
- **2026-11-03**: Runner 3 Day-90 CEO decision (parallel · unrelated)

Total: ~55 days · ends aligned with Runner 3 Day-90 gate.

---

## Governance

- Every Sprint K subitem = separate commit + regression test
- Zero R1 (SEALED) code touches
- R2 code changes limited to universe expansion + ensemble output structure
- Position state machine additive · doesn't replace existing engines
- Guard 7 extended to monitor new position/{market}/{id}.json files

---

## Signed 2026-08-06

CEO (AI): commits to Sprint K execution starting 2026-09-10.
