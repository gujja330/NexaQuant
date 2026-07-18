# How to Run AEGIS

**AEGIS v2.0 · Production Baseline · Frozen 2026-07-18**

Two things: run the pipeline, and (optionally) wire up Telegram so the
Morning Report lands on your phone.

---

## 1. Run the daily pipeline

**One command. That's it.**

```powershell
cd C:\Users\GPraveenKumar\Downloads\prism
python scripts\aegis_daily_v2.py
```

This runs all 16 orchestrator steps in dependency order (~35 seconds
on baseline day). No individual step invocations. No manual sequencing.

The orchestrator refreshes:

- All engine outputs in `reports/*.json`
- The immutable daily archive at `data/archive/YYYY/MM/DD/bundle/`
- Today's Morning Research Report at `reports/morning_latest.{md,html}`
- The ops-check verdict at `reports/ops_check.json`
- Sends Telegram messages (if Telegram is configured — see §3)

**When to run:** every trading morning before market open. GitHub
Actions handles this automatically at ~06:00 IST if the repo is
pushed to a GitHub-Actions-enabled remote. Manual invocation is only
needed when you want a mid-session refresh.

---

## 2. View the dashboard

```powershell
python ux\dashboard\frontend\serve.py
```

Then open <http://localhost:8765/ux/dashboard/frontend/> in a browser.

The top nav has:

- **DASHBOARD** — investor-facing view: Decision Cards, Portfolio
  Health, Archive Maturation counter
- **VALIDATION LAB** — stock-first admin (search a ticker → its full
  history + accuracy + closed trades)
- **📄 MORNING** — today's Morning Research Report

Per-stock one-page sheet: `#/sheet/{TICKER}` (link from any card).

If you don't want to run the server, just double-click
`reports\morning_latest.html` — the report is a standalone HTML file
that opens in any browser.

---

## 3. Wire up Telegram (one-time, ~5 min)

The daily pipeline sends Telegram messages automatically **if** two
environment variables are configured. If they're missing, that step
silently skips — nothing breaks.

### 3a. Create a Telegram bot

1. Open Telegram, message **@BotFather**
2. Send `/newbot`, follow the prompts
   - Name: anything (e.g. `AEGIS Alerts`)
   - Username: must end in `bot` (e.g. `aegis_alerts_bot`)
3. BotFather replies with a token that looks like
   `7892345678:AAH_ABC123DEF456...` — copy it

### 3b. Get your chat ID

1. Search for the bot you just created in Telegram
2. Send it any message (e.g. `hi`) — this makes your chat visible to
   the bot
3. In a browser, open:
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
4. In the JSON response, find `"chat":{"id":<NUMBER>...}` — that
   number is your chat ID (usually 9–10 digits, no letters)

### 3c. Save the config locally

Create a file called `.env.telegram` in the repo root
(`C:\Users\GPraveenKumar\Downloads\prism\.env.telegram`). It's already
in `.gitignore` — the token stays local and never gets committed.

Contents:

```env
TELEGRAM_BOT_TOKEN=7892345678:AAH_ABC123DEF456...
TELEGRAM_CHAT_ID=1234567890
```

### 3d. Run the pipeline

```powershell
python scripts\aegis_daily_v2.py
```

Once the env vars are readable, the `telegram` step at the tail of the
pipeline sends 5 short messages to your chat:

1. Overnight summary
2. Top opportunities
3. Portfolio state
4. Alpha vs NIFTY + risk alerts
5. Action items

That's the whole setup.

---

## 4. What to expect after the run

At the tail of the output you'll see:

```
AEGIS OPS CHECK · artifact + schema + fingerprint + health
====================================================================

  ARTIFACTS   22/22 present · 0 invalid
  SCHEMAS     14/14 pass
  FINGERPRINT OK
  HEALTH      16/16 steps ok

  VERDICT     HEALTHY
```

**If VERDICT is anything other than HEALTHY**, read
`reports/ops_check.json` for details before you trade.

- **HEALTHY** — everything green, use the recommendations
- **DEGRADED** — non-critical warning (missing optional file, warming
  data), safe to proceed but investigate
- **CRITICAL** — production halt. `git status`, check what changed,
  don't trade until resolved

---

## 5. Automation options

**GitHub Actions (recommended, zero-effort):**  
`.github/workflows/aegis-daily.yml` runs the full pipeline every
weekday at ~06:00 IST from a hosted runner. Requires the repo to be
pushed to GitHub and `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` added
as GitHub repo secrets.

**Windows Task Scheduler (local):**  
`deploy/aegis-windows-task.ps1` installs a scheduled task that runs
the pipeline locally at 06:00 IST. Useful if you don't want cloud CI.

**Manual:**  
Just type the one command from §1 whenever you want a fresh set of
recommendations.

---

## Post-lock discipline

Per the [AEGIS Constitution](../AEGIS_CONSTITUTION.md), the daily
pipeline shape is now frozen. Individual step invocations are
supported for debugging but are not part of the operational flow. If
a step needs to be added or removed, that requires a Constitutional
amendment (≥90 days of live archive evidence + operator sign-off).

For everyday operation: **`python scripts\aegis_daily_v2.py`** — that's
the whole workflow.
