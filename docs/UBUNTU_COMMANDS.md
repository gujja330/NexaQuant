# NexaQuant — Ubuntu VM Command Guide (Oracle Cloud)

All the commands to deploy, verify, operate, and troubleshoot the bot on the Oracle Cloud
Ubuntu VM. Copy-paste in order. **Note:** `systemctl` / `journalctl` end in the letter **L**
(not the number 1) — the terminal font makes them look alike.

VM: `nexabot` (Ubuntu 22.04) · user `ubuntu` · repo at `~/NexaQuant`
Account: Exness cent — symbols tagged **`c`** (BTCUSDc, XAUUSDc) · balance shown in cents.

---

## 0. One-time: set credentials (each new SSH session)
The password lives ONLY in these env vars on the VM — never in the repo.
```bash
export MT5_LOGIN=183286147
export MT5_PASSWORD='YOUR_NEW_PASSWORD'      # type your real (rotated) password
export MT5_SERVER='Exness-MT5Real25'
```

## 1. Get the latest code
```bash
cd ~/NexaQuant
git pull
```

## 2. Deploy / (re)start the bot — PAPER mode (start here, always)
```bash
bash execution/setup_oracle.sh BTCUSDc H4 paper
```
- Installs Wine + MT5 + Python (embeddable, headless-safe) + deps, writes a systemd
  service, starts the bot, and installs the weekly self-learning timer.
- Idempotent: safe to re-run; it skips steps already done.
- Wait for: `DONE. Service 'nexabot-BTCUSDc-H4' is running...`
- `X connection to :99 broken` and `Wine Gecko` messages are **harmless**.

Run the OTHER pair too (separate service):
```bash
bash execution/setup_oracle.sh XAUUSDc H4 paper
```

## 3. Verify it connected to your account
```bash
systemctl status nexabot-BTCUSDc-H4 --no-pager
journalctl -u nexabot-BTCUSDc-H4 -n 40 --no-pager
```
✅ Good: `active (running)` + `connected: balance=1196.00 USC server=Exness-MT5Real25`

## 4. Pre-flight sizing check (NO order placed)
Confirms the lot the bot would trade on your cent balance.
```bash
xvfb-run -a wine ~/.wine/drive_c/users/$USER/python/python.exe execution/live_trader.py \
  --symbol BTCUSDc --tf H4 --mode paper --check
```
- Tiny lot (e.g. `0.01`) = good. `SKIP ... too small for this symbol` = BTC min lot risks
  too much for $12 → use **gold (XAUUSDc)** instead (smaller contract).

---

## Daily operations
```bash
# live logs (follow)
journalctl -u nexabot-BTCUSDc-H4 -f

# weekly self-learning loop: when it next runs + its log
systemctl list-timers nexa-update --no-pager
journalctl -u nexa-update -n 30 --no-pager

# stop / start / restart the bot
sudo systemctl stop    nexabot-BTCUSDc-H4
sudo systemctl start   nexabot-BTCUSDc-H4
sudo systemctl restart nexabot-BTCUSDc-H4

# remove a service entirely (e.g. a wrong-symbol one)
sudo systemctl disable --now nexabot-BTCUSD-H4
```

## Update to the latest strategy/code
```bash
cd ~/NexaQuant
git pull
sudo systemctl restart nexabot-BTCUSDc-H4     # restart so the bot picks up changes
```

---

## Troubleshooting
```bash
# a Wine command hangs / "stopped on same screen": interrupt + kill lingering Wine
Ctrl + C
wineserver -k 2>/dev/null

# Wine-Python broken? force a clean reinstall of the embeddable Python, then re-run setup
rm -rf ~/.wine/drive_c/users/$USER/python
bash execution/setup_oracle.sh BTCUSDc H4 paper

# check the exact broker symbol name (must match what you pass the bot)
#   -> open the MT5 mobile app > Market Watch (cent account shows BTCUSDc / XAUUSDc)

# MT5 terminal didn't install in [3/7]? run it once interactively, then re-run setup
xvfb-run -a wine ~/.wine/drive_c/Program\ Files/MetaTrader\ 5/terminal64.exe &
sleep 30 && pkill -f terminal64

# confirm packages import inside Wine-Python
xvfb-run -a wine ~/.wine/drive_c/users/$USER/python/python.exe -c "import MetaTrader5, pandas, numpy, pyarrow; print('ok')"
```

---

## Going LIVE (only AFTER ~30 days of clean paper trading)
Real money. Stop the paper service first, then start live.
```bash
sudo systemctl disable --now nexabot-BTCUSDc-H4      # stop paper
export MT5_LOGIN=183286147 MT5_PASSWORD='YOUR_NEW_PASSWORD' MT5_SERVER='Exness-MT5Real25'
bash execution/setup_oracle.sh BTCUSDc H4 live       # 3rd arg = live
```

## Safety reminders
- **paper first**, ~30 days, before ever using `live`.
- The bot auto-stands-down (manage-only) if the weekly re-validation says the edge stopped
  persisting — it never keeps trading a dead strategy.
- Risk guards always on: ATR stop, daily-loss + drawdown kill switch, vol/news blackout,
  tiny-account feasibility skip.
- Never put the password in the repo — only in the env vars above.
