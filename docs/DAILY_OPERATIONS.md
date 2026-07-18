# AEGIS · Daily Operations HOWTO

**How the platform runs day-to-day and how you consume its outputs.**

---

## The one-command daily flow

Every weekday morning, one of two things happens:

### 1. Fully automated (default · GitHub Actions)

The `.github/workflows/aegis-daily.yml` workflow fires **~06:00 IST**
(with backups at 06:30 / 07:00 / 08:00 IST) and:

1. Refreshes market data via yfinance.
2. Runs the base engine (`india/recommendation_generator.py`) —
   the sealed OPS001 pipeline.
3. Runs **`scripts/aegis_daily_v2.py`** — the Phase 2 v2 orchestrator
   (Adaptive v2.0 → Validation v2.0 → Risk & Capital v2.0 →
   DNA feedback v1.5 → Knowledge Graph v1.6 → Fusion v2.1).
4. Runs the sealed Telegram delivery (`telegram_send_with_retry.py`).
5. Commits every fresh report + v2 artifact back to `main` with
   `[skip ci]`.

Result: by ~06:15 IST, `reports/*.json` contains today's numbers +
Telegram has fired. **You do nothing.**

### 2. Manually (if you're running locally or the workflow didn't fire)

```
# Base engine (produces reports/recommendations.json, portfolio.json, etc.)
python india/recommendation_generator.py

# Phase 2 v2 pipeline (produces intelligence_*.json, validation_v2_*, etc.)
python scripts/aegis_daily_v2.py

# Optional: local Telegram send (only if .env.telegram has real creds)
python scripts/telegram_send_ux030.py
```

Total local runtime today: ~40 seconds for the v2 orchestrator.

---

## How to see the dashboard

```
# Terminal 1 · start the dashboard server (from repo root)
python ux/dashboard/frontend/serve.py

#   AEGIS Executive Dashboard
#   serving from: C:\...\prism
#   open:         http://127.0.0.1:8765/ux/dashboard/frontend/index.html

# Terminal 2 (or browser) · open the URL above
```

**Realtime — do you need to hit refresh?** No.

- **Auto-refresh checkbox** is ON by default (sidebar). Every 60s
  the dashboard reloads `reports/*.json` and rebuilds every widget.
- **↻ NOW button** for immediate reload.
- **Last-refresh timestamp** shown so you know the age of what
  you're looking at.
- **Auto-refresh pauses** when the tab is hidden (browser API).

Leave the tab open all day. When the daily pipeline finishes writing
new files, the dashboard picks them up within 60s.

---

## The 11 dashboard routes

Sidebar navigation:

| Route | What it shows | Reads |
|---|---|---|
| `/` (Overview) | Regime · Champion · Calibration · Portfolio · v2.0 · Risk · Validation · Top Buys · Exits | 8 files |
| `/portfolio` | Portfolio + Holdings table + Sizing decisions | 3 files |
| `/recommendations` | Top buys · Exits · v2.0 signal · Feature importance | 3 files |
| `/risk` | Risk budget · Sizing · Alerts | 3 files |
| `/validation` | Paper harness · Opportunity cost · Rolling edge sparklines | 2 files |
| `/intelligence` (v2.1) | Fusion score · Conflicts · Top-10 · Weights · Why-panel · Stress scenarios | 5 files |
| `/champion` | Champion + Challenger board + Regime champions | 3 files |
| `/knowledge` | Graph stats + Communities + Influencers + Entity/Relation breakdown | 3 files |
| `/dna` | Pattern leaderboard + Losing patterns + High-prior recs (v1.5) | 1 file |
| `/learning` | Calibration + v2.0 rebuild + Doctor + Drift + Feature importance | 5 files |
| `/timeline` | Daily run ledger + Champion events + Top-10 reasoning | 4 files |

---

## The daily v2 orchestrator (`scripts/aegis_daily_v2.py`)

Runs the six Phase 2 v2 engines in dependency order.

```
python scripts/aegis_daily_v2.py                # normal fail-fast run
python scripts/aegis_daily_v2.py --continue     # keep going on failure
python scripts/aegis_daily_v2.py --only fusion  # run just the fusion step
python scripts/aegis_daily_v2.py --list         # print the plan and exit
python scripts/aegis_daily_v2.py --dry-run      # show commands, don't execute
```

Every run appends to `reports/aegis_daily_v2_history.jsonl` with:

- per-step verdict (SUCCESS / SUCCESS_NO_REFRESH / FAILURE /
  MISSING_INPUTS / MISSING_ENV / SKIPPED_OPTIONAL / MISSING_SCRIPT / DRY_RUN)
- elapsed seconds
- returncode
- stdout tail
- artifact-refresh check (did the declared output files change mtime?)

The **/timeline** dashboard route surfaces this ledger — you see the
last 10 runs with success/failure counts and total elapsed.

Step dependency chain:

```
adaptive_rec_v2      (needs learning.parquet)
     ↓
validation_v2        (needs recommendations.json + raw prices)
     ↓
risk_capital_v2      (needs recommendations.json + global_context.json)
     ↓
dna_feedback         (needs recommendation_dna.parquet + learning + recs)
     ↓
knowledge_graph      (needs recommendations + portfolio + backtest)
     ↓
fusion               (needs everything above)
     ↓
telegram             (opt-in · needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)
```

The telegram step **skips gracefully** if env vars aren't set —
verdict is `SKIPPED_OPTIONAL`, not a failure.

---

## Telegram wiring

The GitHub Actions workflow **still uses the sealed Telegram sender**
(`scripts/telegram_send_with_retry.py` calling
`india/telegram_notify.py`) for production reliability — that's the
retry-wrapped, OPS001-hardened path.

The **UX030 renderer** (`scripts/telegram_send_ux030.py`) is the new
richer message format. It's wired into the daily orchestrator's last
step, but the workflow **deliberately strips its env vars** so it
skips there — production delivery stays on the sealed path until an
explicit cutover.

If you want to test the UX030 sender locally with your `.env.telegram`:

```
python scripts/telegram_send_ux030.py
```

5 messages fire: morning brief · new buys · champion update ·
portfolio health · executive summary. ~1.2 KB total across all
messages. Every send emits `sent (N chars)` on success — matches
the retry-wrapper's SUCCESS marker so a parallel-run wrapper would
classify correctly.

---

## Verifying a good run

Fast checks after a daily run:

```
# Latest v2 fingerprint
python -c "
import json
s = json.load(open('reports/intelligence_summary.json', encoding='utf-8'))
print(f\"as_of={s.get('as_of', '—')} · avg_intelligence={s['avg_intelligence']} · \"
      f\"decisions={s['by_decision']} · CRITICAL={s['conflict_summary']['n_critical']}\")
"

# Last 3 orchestrator runs
tail -3 reports/aegis_daily_v2_history.jsonl 2>/dev/null || echo "no history yet"

# Any freshness issues in the workflow
cat data/.published                     # today's IST date if last run succeeded
```

Dashboard also shows this in the `/timeline` route's "Daily Run
Ledger" widget — no shell required.

---

## What to do if a daily run fails

The orchestrator writes every failure into
`reports/aegis_daily_v2_history.jsonl`. To re-run only what failed:

```
# Re-run one specific step
python scripts/aegis_daily_v2.py --only fusion

# Re-run the last N steps (comma-separated)
python scripts/aegis_daily_v2.py --only risk_capital_v2,dna_feedback,knowledge_graph,fusion
```

The base pipeline (`recommendation_generator.py`) is separate — if
IT failed, the GitHub Actions workflow's freshness gate blocks the
day and nothing downstream runs. See `docs/OPS001-I_CHANGELOG.md`.

---

## Governance summary

- Every engine writes to `reports/*.json`; the dashboard reads them.
- No dashboard route calls engine code.
- No engine calls another engine — everything flows through disk.
- Auto-refresh doesn't push data; it just re-reads.
- Advisory-only (ADR-002). Nothing auto-executes.
- Deterministic (ADR-006). Same inputs → same outputs across every
  route and every widget.
