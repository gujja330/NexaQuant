# NexaQuant — Windows Setup (laptop / PC, native MT5, NO Wine)

Run the bot on a **Windows laptop** where MetaTrader 5 runs **natively** — the simplest,
most reliable, **$0** way to trade your Exness account. No cloud, no Wine, no capacity limits.

It trades the validated **multi-edge portfolio** (trend + breakout on the config universe),
with dynamic risk sizing and the account-wide kill switch. You monitor from the **MT5 phone
app**. Total cost: nothing.

> Note on "always-on": for the **30-day paper test**, the laptop just needs to be on while you
> use it (it's an H4 bot — it acts every ~4 hours). For true 24/7 later, leave it plugged in,
> or move to the free **Exness VPS** once the account reaches ~$500. The broker holds the hard
> stop-loss even if the laptop sleeps; only trailing/scale-out pause while it's off.

---

## 0. One-time prerequisites (install these once)

1. **MetaTrader 5 (Exness)** — download from Exness, install, and **log into your cent account**
   (login `183286147`, server `Exness-MT5Real25`). Open **Market Watch** and confirm you see
   `BTCUSDc` and `XAUUSDc`. Leave MT5 running.
   - In MT5: **Tools → Options → Expert Advisors → tick "Allow algorithmic trading"**.
2. **Python 3.12** — https://www.python.org/downloads/ → run installer → **TICK "Add python.exe
   to PATH"** → Install. (Verify: open PowerShell, type `python --version`.)
3. **Git** — https://git-scm.com/download/win → install with defaults.
   *(Or skip Git and download the repo as a ZIP from GitHub → Extract.)*

---

## 1. Get the code
Open **PowerShell** and run:
```powershell
cd $HOME\Downloads
git clone https://github.com/praveen330/NexaQuant.git
cd NexaQuant
```
*(If you downloaded the ZIP instead: extract it, then `cd` into the extracted folder.)*

## 2. Set your credentials (this PowerShell window only)
```powershell
$env:MT5_LOGIN   = "183286147"
$env:MT5_PASSWORD= "YOUR_PASSWORD"
$env:MT5_SERVER  = "Exness-MT5Real25"
# optional phone alerts:
# $env:TELEGRAM_BOT_TOKEN="..."; $env:TELEGRAM_CHAT_ID="..."
```

## 3. Run the one-command setup (PAPER mode)
```powershell
powershell -ExecutionPolicy Bypass -File execution\setup_windows.ps1 -Mode paper
```
This will:
- `[1/6]` install the slim Python deps (MetaTrader5 + pandas/numpy/… — fast, no torch)
- `[2/6]` auto-find your MT5 `terminal64.exe`
- `[3/6]` stop the laptop sleeping on AC power
- `[4/6]` write `run_nexabot.bat` (holds creds; keep private — it's git-ignored)
- `[5/6]` **pre-flight check** — connects and prints the lots it *would* trade (NO order placed)
- `[6/6]` register a **Scheduled Task** that auto-starts the bot at logon + restarts on failure

✅ Success ends with: `DONE. NexaBot is running (paper) ...`

## 4. Confirm it's working
```powershell
Get-Content logs\nexabot.log -Wait
```
Look for: `connected: balance=1196.00 USC ... symbols=BTCUSDc,XAUUSDc edges=trend,breakout (... sleeves)`
Then watch trades appear here AND in the **MT5 phone app** (log into the same account).

---

## Daily controls
```powershell
# watch the live log
Get-Content logs\nexabot.log -Wait

# stop / start the bot
Stop-ScheduledTask  -TaskName NexaBot
Start-ScheduledTask -TaskName NexaBot

# remove it entirely
Stop-ScheduledTask -TaskName NexaBot; Unregister-ScheduledTask -TaskName NexaBot -Confirm:$false

# pre-flight only (no order) — see balance + lot it would trade
python execution\live_trader.py --mode paper --check
```

## Update to the latest code
```powershell
cd $HOME\Downloads\NexaQuant
git pull
Stop-ScheduledTask -TaskName NexaBot; Start-ScheduledTask -TaskName NexaBot
```

## Change which pairs it trades (config-driven, no code edit)
Edit `config\base_config.yaml` → `system.live_symbols` (e.g. add/remove a symbol) → `git pull`
isn't needed if you edited locally → restart the task. The bot reads the universe from config.

---

## Going LIVE (only after ~30 days of clean paper)
```powershell
Stop-ScheduledTask -TaskName NexaBot; Unregister-ScheduledTask -TaskName NexaBot -Confirm:$false
$env:MT5_LOGIN="183286147"; $env:MT5_PASSWORD="YOUR_PASSWORD"; $env:MT5_SERVER="Exness-MT5Real25"
powershell -ExecutionPolicy Bypass -File execution\setup_windows.ps1 -Mode live
```

## Troubleshooting
| Symptom | Fix |
|---|---|
| `Python not found` | Reinstall Python 3.12 with **"Add to PATH"** ticked; reopen PowerShell |
| `terminal64.exe not found` | Install MT5 from Exness + log in once, then re-run the script |
| `MT5 connect failed` | Check creds; ensure MT5 is open + "Allow algorithmic trading" is on |
| `SKIP ... too small for this symbol` | BTC min lot too big for $12 → it trades gold; normal on a tiny account |
| Laptop sleeps / bot stops | Keep plugged in; don't close the lid (or set lid-close = Do nothing in Power Options) |

## Safety
- **Paper first**, ~30 days, before `-Mode live`.
- Risk guards always on: ATR stop, 6% portfolio cap, 3% daily-loss + 20% drawdown kill switch,
  tiny-account feasibility skip. The weekly self-learning loop stands the bot down if the edge
  stops persisting.
- `run_nexabot.bat` holds your password — it's git-ignored; never share it.
