# NexaQuant on Oracle Cloud "Always Free" — step by step

Goal: a free, always-on VM running MT5 + the bot, monitored from your phone. One-time setup.
(Oracle asks for a card for IDENTITY VERIFICATION only — Always-Free resources are never charged.)

---

## A. Open the free account (~10 min)
1. cloud.oracle.com → **Start for free**.
2. Email + verify → country → **Account type: Individual**.
3. Add card (verification only; tiny refundable hold). A **debit/prepaid Visa** usually works.
4. **Home Region:** pick the one closest to you — it CANNOT be changed later.
5. Land in the **Oracle Cloud Console**.

## B. Create the VM (~5 min)
1. ☰ → **Compute → Instances → Create instance**. Name: `nexabot`.
2. **Image & shape → Edit:**
   - Image: **Canonical Ubuntu 22.04**
   - Shape: **VM.Standard.E2.1.Micro** (x86, tagged **Always Free**). *Pick x86 — MT5 is x86; the
     ARM "Ampere" shape would need slow emulation.*
3. **Add SSH keys:** "Generate a key pair for me" → **download the private key** (keep it safe).
4. **Create** → wait ~1 min → copy the **Public IP**.

## C. Connect (browser or phone — no PC needed)
- Easiest: Oracle Console → your instance → **Cloud Shell**, or the **"Launch terminal"** option.
- Or a phone SSH app (**Termius**): host = Public IP, user = `ubuntu`, key = the file you downloaded.

## D. One-command setup (the automation)
First get the code on the VM (after your day-end GitHub push):
```bash
git clone https://github.com/praveen330/NexaQuant.git && cd NexaQuant
```
Then run the installer with your Exness credentials (use your **Standard Cent** account):
```bash
export MT5_LOGIN=<login> MT5_PASSWORD='<password>' MT5_SERVER='<Exness server name>'
# optional phone alerts:
# export TELEGRAM_BOT_TOKEN='...' TELEGRAM_CHAT_ID='...'
bash execution/setup_oracle.sh BTCUSDm H4 paper
```
This installs Wine + MT5 + Python, adds swap, registers an **auto-restarting systemd service**,
and starts the bot in **paper** mode. (Find your exact `MT5_SERVER` in the MT5 app: Settings → your account.)

## E. Verify before it trades (no order placed)
```bash
xvfb-run wine ~/.wine/drive_c/users/$USER/python/python.exe \
  execution/live_trader.py --symbol BTCUSDm --tf H4 --mode paper --check
```
Prints balance (e.g. `1196 USC`), the exact lots it would trade, and the risk.

## F. Monitor + control
- **Phone:** MetaTrader 5 app → log into the same account → see every trade live.
- Logs:   `journalctl -u nexabot -f`
- Stop:   `sudo systemctl stop nexabot`
- Go live: re-run step D with `live` as the 3rd arg — **only after ~30 days of profitable paper.**

---

### Gotchas
- Pick the **x86 micro** shape (not ARM) for MT5.
- 1 GB RAM is tight → the script adds a 4 GB swap file automatically.
- If `mt5setup.exe /auto` stalls under Xvfb, run it once interactively (or the bot's
  `mt5.initialize(path, login, password, server)` will auto-launch the terminal on first connect).
- Bot is broker-agnostic: change `MT5_SERVER/LOGIN/PASSWORD` to use any MT5 broker later.
