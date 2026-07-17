# DEV026 — AI Investment Research Assistant (v0.1)

Deterministic, grounded, no-network Q&A over every DEV017-025 report.
Answers institutional questions by templating from the JSON corpus.

**Not an LLM.** Every answer is byte-reproducible from the same inputs.
Grounded per ARCH001A Article VIII clause 8.2 (explainability).

## Directory structure

```
research/research_assistant/
├── lib/
│   ├── loaders.py           AegisState — load all 25 reports/*.json into
│   │                          a single unified state
│   └── templates.py         6 query handlers:
│                              explain_stock, compare_stocks, explain_sector,
│                              portfolio_report, executive_summary, investment_memo
├── compute/
│   └── assistant.py         Query router with governance wrapper
├── publish/
│   └── bundle.py            JSON writer
├── tests/
│   └── test_smoke.py        23 tests, all pass
├── run.py                    CLI
└── README.md
```

## Supported queries

| CLI flag | Query type | Output |
|:--|:--|:--|
| `--executive-summary` | Portfolio-wide state summary | `executive_summary.json` |
| `--explain-stock TICKER` | Full breakdown of one company | `company_report.json` |
| `--compare A B` | Side-by-side two companies | `comparison_report.json` |
| `--sector-report SECTOR` | Sector deep-dive with constituents | `sector_report.json` |
| `--portfolio-report` | Live portfolio state (needs DEV024) | `portfolio_report.json` |
| `--memo TICKER` | Investment memo (thesis + risks + entry plan) | `investment_memo.json` |
| `--all` | Executive + portfolio + top-3 memos + IC report | multi-file |

## Execution

```bash
# Data coverage check
python research/research_assistant/run.py --executive-summary

# Single stock
python research/research_assistant/run.py --explain-stock IPCALAB

# Compare two
python research/research_assistant/run.py --compare HDFCBANK ICICIBANK

# Sector deep-dive
python research/research_assistant/run.py --sector-report Pharma

# Live portfolio
python research/research_assistant/run.py --portfolio-report

# Investment memo
python research/research_assistant/run.py --memo IPCALAB

# Full report suite
python research/research_assistant/run.py --all

# Smoke tests
python research/research_assistant/tests/test_smoke.py    # 23 tests, all pass
```

## Sample output (2026-07-17)

```
Global posture:     Neutral (risk score 47.12, conf 1.00)
Sectors computed:   12 · class dist {'Strong-Bullish': 2, 'Bullish': 4, 'Neutral': 3, 'Weak': 3}
Companies scored:   208 · class dist {'Strong-Bullish': 8, 'Bullish': 43, 'Neutral': 48, 'Weak': 62, 'Bearish': 47}
Recommendations:    {'Strong-Buy': 7, 'Buy': 44, 'Watchlist': 30, 'Avoid': 127}
Portfolio snapshot: demo_top_10_ew_2026-07-17 · P&L −0.09% · health 100/100
Learning:           1060 trades · WR 58.3% · Brier 0.33

Highlights:
  - 7 Strong-Buy recommendation(s) — top pick IPCALAB (score 83.5)
  - 2 HIGH-severity improvement suggestion(s) from DEV025

IPCALAB   score 83.5   Strong-Bullish
  Recommendation: Strong-Buy · confidence 1.00
  Sector:   Pharma (Strong-Bullish) score 80.51
  Industry: Pharma (Mid Cap) (Strong-Bullish)
  Rank:     overall 1 · sector 1/16 · industry 1/9
  Entry:    latest INR 1863.4 · target INR 2070.19 · stop INR 1697.96

  "IPCALAB carries an AEGIS composite score of 83.5 with confidence 1.00,
   classified as Strong-Bullish. Its parent sector (Pharma) is Strong-Bullish
   with score 80.5; industry (Pharma (Mid Cap)) is Strong-Bullish with
   score 84.3. DEV023 recommends Strong-Buy with entry near INR 1863.40,
   target INR 2070.19 (+11.1%), stop INR 1697.96 (−8.9%)."

Verdict on HDFCBANK vs ICICIBANK: "ICICIBANK scores materially higher"
```

## Governance

- **Deterministic** — same reports → same output (`test_determinism` verifies).
- **Grounded** — every claim traceable to a source JSON field.
- **Explainable** — every answer includes the reasoning chain from DEV020's `positive_drivers` / `reasons_for` etc.
- **No LLM. No network.** Templates only.
- Sealed core untouched.
- Structurally isolated under `research/research_assistant/`.

## v0.2 follow-ups

- Natural-language question parsing (map free-form → structured query)
- Bull-case / bear-case generation from `reasons_for` / `reasons_against`
- Historical outcome commentary ("What actually happened after last N recommendations of this type?")
- Multi-ticker comparison (>2)
- Time-series narrative ("How has INFY's score evolved over the last 30 days?")
- LLM adapter (optional — grounded LLM that reads the JSON reports as authoritative context)
