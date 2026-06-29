# Dataset Scorecard — SEC EDGAR CompanyFacts

*Score a dataset BEFORE running experiments on it. A low-quality dataset produces low-quality verdicts no
matter how good the gate is. Re-score when coverage/quality materially changes.*

**Program:** A-Fundamentals · **Status:** ready · **Scored:** 2026-06-29

| Metric | Value | Note |
|---|---|---|
| Point-in-time | ✅ Yes | `filed` date used everywhere; no period-end look-ahead |
| Coverage | 74 / 259 (28%) | names with both price history AND SEC filings |
| Missing values | moderate | not all concepts present per filer; derived ratios drop NaNs |
| Reporting delay | ~0–2 days | `filed` is the public-availability date |
| History depth | ~2 yr usable | bounded by USA price history, not SEC (SEC goes back years) |
| Survivorship bias | present (mild) | universe is current-listed; delisted names absent |
| Refresh frequency | daily-able | CompanyFacts API; raw JSON regenerable (git-ignored) |
| Licensing | free / official | SEC, requires User-Agent header |
| **Overall quality** | **~70 / 100** | PIT and licensing excellent; coverage + history depth are the constraints |

## Verdict for research
Trustworthy for *direction* (sign of IC) but **underpowered for significance** — exactly what RC001 found
(74 names × 7 non-overlapping dates). The dataset is not the problem; *coverage + price-history depth* are.
**Action to raise the score:** widen SEC fetch to the full screened universe and extend price history; that
turns RC001's growth-tilt/ROE-inverse lead from "investigate" into a real promote/reject.

---
### Scorecard template (copy for new datasets)
`PIT · Coverage · Missing values · Reporting delay · History depth · Survivorship · Refresh · Licensing ·
Overall (/100) · Verdict for research · Action to raise score`
