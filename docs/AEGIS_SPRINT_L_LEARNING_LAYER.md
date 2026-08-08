# AEGIS · Sprint L · Learning Layer + Capital Preservation

**Locked 2026-08-08 · execution 2026-12-01 to 2027-01-31 (~60 days)**
**Depends on: Sprint K+ complete (attribution data + walk-forward validated)**

Sprint L is the "AEGIS learns from itself and protects downside" sprint.
Two engines that fundamentally change how the system evolves:

1. **Distillation Engine** · nightly learning · reads outcomes · extracts
   which signal combinations reliably win/lose · continuously improves
   weights without changing model architecture
2. **Capital Preservation Engine** · dedicated downside-focused decision
   layer · answers "should we enter/reduce/trail/exit" with the SOLE
   objective of not losing big

Operator context (2026-08-08 CEO-level review):
> "Add one final engine · Capital Preservation Engine · its only objective:
> never lose big. Institutional funds spend as much effort on preservation
> as on idea generation."
>
> "Distillation Engine · read history nightly · ask which combination
> created rank 10 that beat rank 1 · after 5000 recs you'll know which
> factors actually matter · not which should matter. Huge difference."

---

## Part L1 · Distillation Engine

### L1.1 · Purpose

Continuously learn WHICH signal combinations actually produce winners vs
losers. Update Investability Engine weights + Recommendation ensemble
weights nightly based on accumulated evidence.

### L1.2 · Input data (all exist by Sprint K completion)

- `reports/rec_attribution/{market}/*.json` (Sprint K Part 25 · per-position snapshots)
- `reports/telegram/aegis_history_{market}.xlsx` (full trade history)
- `reports/investability_{market}.json` (Sprint K Part 26 · per-ticker scores)
- `reports/research/rotation_outcomes.jsonl` (Rotation Outcome Tracker)
- `reports/research/monthly/loss_category_review.json` (Sprint K Part 25 rollup)

### L1.3 · The core question · reframed

Not: "Which stock made money?"
Instead: "Which COMBINATION created the outcome?"

Example distillation query:
```
GIVEN a rec that was:
    Fundamental: 91
    Governance: 88
    Sector momentum: quartile 1 (top)
    Regime: bull
    Runner: R2
    Confidence: 0.72
WHAT was the average P&L across all matching historical recs?
```

Answer after n≥100 matching recs:
> "Combinations with Fund>85, Gov>85, Sector Q1, Bull regime → avg P&L
> +4.2% (n=127, win rate 71%). Reliable pattern. Increase weight."

Contrast:
> "Combinations with High PE + Weak Sector + Negative News → avg P&L
> -6.8% (n=43, win rate 12%). Reliable failure. Decrease weight or
> reject."

### L1.4 · Weight optimizer

**Objective function:** maximize risk-adjusted return (Sharpe · not raw P&L)
of the FULL portfolio produced by the recommendation pipeline.

**Constraint:** weights change slowly · max ±5% per week · prevents whipsaw
from noise-driven micro-optimizations.

**Method:** Bayesian weighted-average update on historical evidence · with
prior toward equal weights (regularizes against overfitting).

**Human-in-loop:** proposed weight changes accumulate for 5 trading days ·
operator promotes them via `python -m backend.learning.apply_weights` ·
never auto-applies (Constitutional invariant · "never auto-rewrites
production").

### L1.5 · Deliverables

1. `backend/learning/distillation.py` · nightly pattern extractor
2. `backend/learning/weight_optimizer.py` · Bayesian weight update
3. `backend/learning/apply_weights.py` · operator-invoked promotion CLI
4. `reports/research/distillation_report_{week}.json` · weekly rollup
5. `reports/research/weight_proposals_{week}.json` · staged weight changes
6. Regression test · same input → same distilled output (deterministic)

### L1.6 · Success metric

By end of Sprint L: at least 3 weight adjustments promoted by operator ·
each backed by n≥100 evidence · walk-forward validated on held-out data ·
demonstrable Sharpe improvement vs baseline weights.

---

## Part L2 · Capital Preservation Engine

### L2.1 · Purpose

Dedicated downside-focused decision layer. Sits AFTER Portfolio Engine
but BEFORE Telegram delivery. Its ONE objective: **never lose big.**

Doesn't care about maximizing upside. Cares about limiting downside.

### L2.2 · Decision questions answered per position

For every currently-held position, every trading day:

| Question | Trigger criteria | Recommendation |
|---|---|---|
| **Should we enter?** | Even for STRONG BUY · check gap-risk + earnings-window + sector-vol | Suppress entry if downside > 8% likely in next 5 days |
| **Should we reduce?** | Position >2x avg size · sector concentration >30% · vol regime shifted | Reduce to target size |
| **Should we trail?** | Position +8% · momentum weakening | Raise trailing stop to protect gains |
| **Should we book profit?** | Position +15% · target hit · overvalued vs 5yr median | Book 50% · let 50% run |
| **Should we exit?** | Stop-loss hit · deep-loss triggered · earnings miss · governance flag · regime shift | Hard exit |

### L2.3 · The 5 hard exits (non-negotiable)

Independent of Runner recommendations. If ANY fires, Capital Preservation
overrides:

1. **Stop-loss hit** (position ≤ -5%)
2. **Deep loss** (position ≤ -8%) · guard-failed scenario · exit + investigate
3. **Governance flag** (auditor change · SEBI notice · promoter pledge spike)
4. **Fundamental break** (earnings miss > 30% · guidance cut · going-concern qualification)
5. **Position-size violation** (single position > 8% of portfolio · sector > 30%)

### L2.4 · The soft signals (weighted recommendation)

- Trailing stop breach (momentum weakening while position profitable)
- Sector rotation out (position's sector in bottom quartile 2+ weeks)
- Vol regime shift (VIX/India VIX up > 30% · reduce beta exposure)
- News impact "Very Negative" (event-driven exit)
- Time-decay (position held > 60 days · momentum thesis expired)

Each soft signal contributes to a "Preservation Score" · when it exceeds
threshold, action is suggested (never forced).

### L2.5 · Deliverables

1. `backend/preservation/__init__.py`
2. `backend/preservation/hard_exits.py` · 5 non-negotiable triggers
3. `backend/preservation/soft_signals.py` · weighted recommendation
4. `backend/preservation/decisioner.py` · per-position action output
5. `reports/preservation_actions_{market}.json` · daily output
6. Portfolio sheet gains "Preservation Action" column
7. Telegram Command Center prepends preservation alerts (highest severity first)

### L2.6 · Pipeline integration

```
Universe
  ↓
Investability Engine (Part 26)
  ↓
Runner 1 · Runner 2
  ↓
Context Engine
  ↓
Portfolio Engine
  ↓
Recommendation Continuity
  ↓
Capital Preservation Engine  ← NEW (Part L2)
  ↓
Telegram / History.xlsx / Portfolio.xlsx
  ↓
Distillation Engine (Part L1 · nightly)
  ↓
Weight proposals (operator promotes)
  ↓
Next day's model
```

### L2.7 · Success metric

By end of Sprint L: zero deep-loss events (positions worse than -8%) that
were NOT flagged by Capital Preservation Engine at least 1 day before ·
demonstrates guard is faster than damage.

---

## Execution timeline (60 days)

| Window | Focus | Deliverable |
|---|---|---|
| 2026-12-01 to 2026-12-14 | Part L1 phase 1 · Distillation core | Pattern extractor · Bayesian weight update · dry-run only |
| 2026-12-15 to 2026-12-24 | Part L1 phase 2 · Weight optimizer + promotion CLI | Operator promotes first weight change · WF-validated |
| 2026-12-25 to 2027-01-07 | Part L2 phase 1 · Capital Preservation hard exits | 5 non-negotiable triggers wired · Portfolio column live |
| 2027-01-08 to 2027-01-17 | Part L2 phase 2 · Soft signals + decisioner | Weighted recommendation output · Telegram integration |
| 2027-01-18 to 2027-01-25 | Regression suite · both L1 + L2 | All tests green · walk-forward validated |
| 2027-01-26 to 2027-01-31 | Production acceptance · 90-day paper-trading gate | Sprint L complete · move to canonical operation |

---

## Governance rules (Sprint L specific)

1. **Distillation must be Constitutional** · never auto-rewrites production
   · always proposes · operator promotes
2. **Capital Preservation trumps runners** · hard-exit triggers override
   Runner recommendations · full audit trail
3. **Weight changes need n≥100 evidence** · below threshold = suggestion only
4. **Weekly walk-forward validation** on held-out data · propose vs
   validate must be separated in time
5. **No new engines beyond L1+L2** · Sprint L is learning + protection ·
   not new alpha generation

---

## Why Sprint L is separate from Sprint K

- L1 (Distillation) NEEDS Sprint K's Part 25 attribution data as input
- L2 (Capital Preservation) NEEDS Sprint K's Part 26 Investability +
  Part 15 profit-protection as substrate
- Sprint K ends Nov 30 · Sprint L starts Dec 1 · natural handoff
- 60-day paper-trading window (per Sprint K post-lock rule) becomes
  Sprint L's implementation window · zero wasted time

## Signed 2026-08-08

Sprint L is CONSTITUTIONALLY LOCKED. Any deviation requires operator
explicit amendment. No new engines beyond L1 + L2. Focus is entirely on
learning and protection.
