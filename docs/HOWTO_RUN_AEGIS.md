# HOWTO · Run AEGIS

Three steps. That's the whole daily workflow.

Windows PowerShell / Bash · `pwd` = repo root (the folder that contains `research/`, `docs/`, `ux/`).

---

## STEP 1 · Run the full pipeline

One command runs every engine (base + Phase 2 v2) in dependency order:

```
python scripts/aegis_daily_v2.py
```

**What it does** (in ~30-40 seconds):

1. **Adaptive Rec Engine v2.0** — confidence signal rebuild + Precision@K
2. **Validation Engine v2.0** — paper-trading harness + drift + opportunity cost
3. **Risk & Capital Engine v2.0** — position sizing + risk budget + counterfactuals
4. **DNA Feedback v1.5** — pattern priors from historical DNA records
5. **Knowledge Graph v1.6** — communities + propagation + stress scenarios
6. **Fusion v2.1** — 10-dimension Investment Intelligence Score per rec
7. **Decision Center v1.0** — overnight diff + exit center + watchlist
8. **Telegram v2** (optional, see Step 2)

Each step's verdict + elapsed time prints as it runs. Final summary shows
`N/M steps succeeded`. Full history logged to `reports/aegis_daily_v2_history.jsonl`.

**Flags:**

```
python scripts/aegis_daily_v2.py --list          # print plan and exit
python scripts/aegis_daily_v2.py --dry-run       # show commands, don't run
python scripts/aegis_daily_v2.py --continue      # keep going on step failure
python scripts/aegis_daily_v2.py --only fusion   # run one step (comma-separated for many)
```

**When to run manually:** if the GitHub Actions workflow didn't fire, or if
you want to refresh reports after tweaking `reports/fusion_weights.json` etc.

**When it runs automatically:** GitHub Actions fires it every weekday at
~06:00 IST (backup slots at 06:30 · 07:00 · 08:00 IST).

---

## STEP 2 · Send the Telegram notification

Two options. Pick one.

### Option A · The sealed production sender (recommended)

The existing OPS001-hardened path, with retry + freshness guard + delivery ledger:

```
python scripts/telegram_send_with_retry.py --attempts 4
```

**Prereqs:** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` set in
environment or in `.env.telegram` at the repo root. GitHub Actions
already has these as secrets.

### Option B · The new UX030 rich sender (opt-in)

Sends 5 messages (morning brief · new buys · champion · portfolio
health · executive summary) built from the UX030 renderer:

```
python scripts/telegram_send_ux030.py
```

Uses the same `.env.telegram`. Writes a parallel delivery ledger at
`reports/telegram_delivery_ux030_<date>.jsonl`.

**Testing without sending:** print the messages locally instead of
posting them:

```
python -c "
import sys; sys.path.insert(0, '.')
from ux.telegram.lib.aggregator import load_context
from ux.telegram.lib import renderer
ctx = load_context()
for fn in ['render_morning_brief','render_executive_summary',
           'render_new_buys_summary','render_champion_update',
           'render_portfolio_health']:
    print('=' * 60)
    print(getattr(renderer, fn)(ctx))
"
```

---

## STEP 3 · View the dashboard

```
python ux/dashboard/frontend/serve.py
```

Then open in your browser:

```
http://127.0.0.1:8765/ux/dashboard/frontend/index.html
```

**What you'll see:**

- **Daily Decision Center** (top of page) — overnight paragraph +
  today's action counts + What Changed table + Exit Center + Watchlist +
  priority-tiered notifications
- **Market Summary** — regime · champion · cash · risk · intelligence
- **Today's Investment Opportunities** — one canonical ranked table with
  CMP · Buy Below · Target · Stop · Upside · Risk:Reward · Hold days ·
  Intelligence score · Confidence · Action
- **Current Portfolio** — held positions with P/L · target · stop
- **Portfolio Health** — Win Rate · Sharpe · Max DD · CAGR · VaR
- **Today's Alerts** — proximity + risk alerts

**Click any ticker row** → jumps to the Stock Detail page with the full
10-dimension Why-Buy breakdown, sizing counterfactuals (why not 4%?
why not 12%?), historical pattern performance, conflict list.

**Realtime:** the dashboard auto-refreshes every 60 seconds (pauses when
the tab is hidden). Manual reload with the `↻` button. Top bar shows
`Updated HH:MM:SS` and the pipeline's last run status.

**Search:** type any ticker or sector in the top-bar search box, press
Enter → jumps to that stock's detail page.

**Theme:** `◐` button toggles light/dark. Choice persists in localStorage.

**Stop the server:** `Ctrl+C` in the terminal where `serve.py` is running.

---

## Putting it all together

Every morning, from the repo root:

```
# One-shot workflow:
python scripts/aegis_daily_v2.py       # 30-40s · runs all engines
python scripts/telegram_send_with_retry.py --attempts 4    # optional · sends daily brief
python ux/dashboard/frontend/serve.py  # background · leaves dashboard live
```

Open `http://127.0.0.1:8765/ux/dashboard/frontend/index.html` and leave
the tab open. The Decision Center at the top tells you exactly what
changed overnight and what needs attention today.

## Prereqs

- Python 3.12 (with pandas, numpy, scikit-learn, reportlab installed)
- Repo cloned and on branch `main`
- `.env.telegram` present at repo root if you want Telegram sends
- `reports/` and `data/raw/india/*.parquet` exist (the base pipeline
  runs `python india/recommendation_generator.py` upstream; the daily
  workflow does that automatically)

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python scripts/aegis_daily_v2.py` reports `MISSING_INPUTS` | Run the base pipeline first: `python india/recommendation_generator.py` |
| Dashboard shows "loading…" forever | Confirm `serve.py` is running and reports/*.json files exist |
| Telegram send says `cannot send: missing TELEGRAM_BOT_TOKEN` | Add to `.env.telegram` or shell environment |
| Decision Center shows "first day of tracking" every run | Snapshots live under `data/market_intelligence/derived/decisions/` — check that directory exists and is writeable |

## What to read next

- [DAILY_OPERATIONS.md](DAILY_OPERATIONS.md) — deeper operational
  reference (verdict codes, ledger format, recovery procedures)
- [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) — engine
  architecture and version history
- [PHASE2_MASTER_ROADMAP.md](PHASE2_MASTER_ROADMAP.md) — where Phase 2
  stands and what's left before completion gate
