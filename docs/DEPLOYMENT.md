# NexaQuant — Deployment (run 24/7 without your PC on)

You do **not** keep your computer running. The bot lives on a small always-on machine
(VPS) next to MT5, trades on its own, and pushes alerts to your phone/email. You only
check in.

> Deploy ONLY a config that passed `run_nexaquant.py` (GATE-PASS) **and** 30-day paper.
> Until then, run in `paper` mode on a demo account.

---

> EVERYTHING here is FREE. The only money you ever put in is your trading-account balance.
> All software (Python, pandas, scikit-learn, hmmlearn, MetaTrader5) is open-source; all
> data sources (Binance dumps, Stooq, FRED, CFTC, yfinance) are key-free; alerts (Telegram,
> email, MT5 app) are free. No paid APIs, no paid hosting required.

## 1. Where it runs 24/7 — FREE options (pick one)

| Option | Cost | Notes |
|---|---|---|
| **Exness free VPS** | **FREE** for funded/active clients | best fit — you already fund Exness; ask support to enable (usually a small equity/volume threshold you meet anyway) |
| **Oracle Cloud "Always Free"** VM | **FREE forever** | a genuinely free 24/7 cloud VM; run MT5 via Wine on Linux + the Python bot (a bit more setup) |
| Google/AWS/Azure free tier | free 12 months | small Windows VM; fine to start |
| Your own PC | free, but must stay ON | only if you don't mind leaving it running |
| (paid) Forex/Windows VPS | ~$10–15/mo | optional convenience, NOT required |

Our bot is **Python**, so the host needs the **MT5 terminal + Python**. Exness free VPS is
the simplest free path; Oracle Always Free is the simplest *broker-independent* free path.
Latency is irrelevant for a swing / H1–M15 bot.

## 1b. Oracle Cloud "Always Free" (chosen) — the honest setup

Oracle Always-Free VMs are **Linux**, but MT5 + the `MetaTrader5` Python API are **Windows-only**,
so MT5 runs under **Wine**. Free and proven, just a bit more setup. One-time.

**Pick the shape:**
- **VM.Standard.E2.1.Micro (x86, Ubuntu 22.04)** — RECOMMENDED. MT5 is x86, so Wine works
  directly. Only 1 GB RAM → add a **4 GB swap file** (the setup script does this).
- Ampere A1 (ARM, 24 GB) is tempting but MT5 is x86 → needs slow emulation; avoid for MT5.

**One-time steps (run on the VM):**
```bash
sudo apt update && sudo apt -y install wine64 winbind xvfb python3-pip git
# 1) add swap (1GB RAM is tight for MT5+Wine)
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
# 2) install MT5 under Wine (downloads the broker-neutral MT5 setup)
wget https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe
WINEDLLOVERRIDES=mscoree=d wine mt5setup.exe   # click through; log into your broker
# 3) Python INSIDE Wine (the MetaTrader5 pkg must live in the same Wine env as the terminal)
wine python -m pip install MetaTrader5 pandas numpy scikit-learn scipy hmmlearn pyyaml
# 4) get the repo + run headless (Xvfb gives Wine a virtual display)
git clone <your repo>  &&  cd nexaquant
export MT5_LOGIN=... MT5_PASSWORD=... MT5_SERVER=...
xvfb-run wine python execution/live_trader.py --symbol BTCUSDm --tf H4 --mode paper --poll 60
```
A starter script that automates most of this: `execution/setup_oracle.sh`.

**Keep it alive across reboots:** a `systemd` unit (template in setup_oracle.sh) restarts the
bot on boot/failure — true set-and-forget.

> Broker note: the bot is broker-agnostic. If a broker restricts profitable/algo accounts,
> just change MT5_SERVER/LOGIN/PASSWORD to another MT5 broker — no code change.

## 2. One-time setup on the VPS
```
1. Install the MT5 terminal, log into your Exness account, keep it running.
2. Install Python 3.12 + this repo:  pip install -r requirements.txt
3. Set credentials & alerts as environment variables (NEVER in the repo):
     MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
     TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID   (optional push alerts)
     NEXA_SMTP_HOST/USER/PASS/EMAIL_TO       (optional email alerts)
4. Pull data:  python data/pull_mt5.py
```

## 3. Run the bot (it polls and trades only when a setup appears)
```
# paper (demo account) first — proves live wiring:
python execution/live_trader.py --symbol XAUUSDm --tf M15 --mode paper --poll 60

# live (real money) — ONLY after validation + paper:
python execution/live_trader.py --symbol XAUUSDm --tf M15 --mode live --live --poll 60
```
- `--poll 60` = check every 60s; it acts only when a fresh entry/exit triggers.
- Low frequency is fine — the bot waits patiently and fires only on high-confidence setups.
- Keep it alive across reboots with **Windows Task Scheduler** (run at logon, restart on
  failure) or **NSSM** (run the python command as a Windows service).

## 4. How you track it (no babysitting)
- **MT5 mobile app** — log into the same account; every position/SL/close shows live.
- **Telegram / email alerts** — the bot messages you on each BUY / CLOSE / KILL-SWITCH.
- **logs** — the bot prints every decision; redirect to a file for history.

## 5. Safety rails already built in
- Hard **ATR stop-loss** on every trade; **momentum-ride** exit; **scale-out** to breakeven.
- **Risk manager / kill switch**: halts on daily-loss limit and on max-drawdown breach.
- **Event/volatility guard**: no new entries during vol spikes or high-impact news windows.
- `--live` is refused unless you explicitly pass it (no accidental real-money trading).

## 6. Still pending before live (do not skip)
1. Pull M5/M15 (+ BTC, multi-regime) and re-run `run_nexaquant.py` → want PBO < 0.5, DSR > 0.95.
2. Validate intrabar SL on M5/M15.
3. 30-day paper trading with backtest≈live check.
4. Then live on a **micro/cent account** (a $10 balance can't place a 0.01 gold lot — use a
   cent account or lower-priced instrument), ramping size only as confidence grows.
