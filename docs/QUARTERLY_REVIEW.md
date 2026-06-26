# AEGIS — Quarterly Review (governance template)

> Hold every 3 months. Copy this template into `docs/reviews/AEGIS_<YYYY-Qn>.md`, fill it in from the
> monthly reports + scorecard + research journal, and record an explicit decision. This is the
> disciplined alternative to ad-hoc changes: production moves only through a documented review.

**Quarter:** ____  ·  **Date:** ____  ·  **Reviewer:** ____

---

## 1. Production health (Operations)
- Was the system operationally reliable this quarter? (pipeline success %, green-board days)
- Any recurring failures? (Yahoo outages, missing tickers, Action failures)
- Were all changes this quarter strictly defect/dependency/data fixes — no features?

_Evidence: `docs/monthly/` reports · GitHub Actions history · `python india/ops_check.py`_

## 2. Recommendation quality (Evidence)
- Did live performance match historical expectations? (live win rate / median vs backtest)
- Is calibration improving or still over/under-confident?
- Decision-quality trend (MFE/MAE, quality-label mix)?

_Evidence: `python india/scorecard.py` · the monthly reports_

## 3. Research progress (Lab)
- How many datasets were investigated this quarter?
- How many experiments were run, and how many rejected?
- Did any experiment beat the frozen baseline OOS and enter forward paper?

_Evidence: `docs/RESEARCH_JOURNAL.md` · `python india/ai_lab/lab_status.py`_

## 4. Decision (one of)
- [ ] **Keep production unchanged** — no candidate met the bar.
- [ ] **Promote one improvement** — `LAB-___` cleared the gate + forward paper. Cut a new frozen tag.
- [ ] **Reject all candidates** — document why in the journal.

**Rationale:** ______________________________________________

**Actions for next quarter:** ______________________________________________

---

_Production changes ONLY via this review. Success this quarter is measured by operational reliability and
the quality of evidence accumulated — not by features added._
