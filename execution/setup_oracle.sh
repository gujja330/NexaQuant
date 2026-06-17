#!/usr/bin/env bash
# execution/setup_oracle.sh
# ONE-COMMAND setup for an Oracle Cloud "Always Free" Ubuntu (x86) VM:
# installs Wine + MT5 + Python deps, adds swap, writes a systemd service, and starts the
# bot. After this the bot is autonomous (auto-connects to MT5, trades, manages, alerts,
# restarts on boot/failure). Run ONCE:
#
#     export MT5_LOGIN=123456 MT5_PASSWORD='***' MT5_SERVER='YourBroker-Server'
#     # optional alerts:  export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
#     bash execution/setup_oracle.sh BTCUSDm H4 paper
#
# args:  SYMBOL (default BTCUSDm)   TF (default H4)   MODE (paper|live, default paper)
set -euo pipefail

SYMBOL="${1:-BTCUSDm}"; TF="${2:-H4}"; MODE="${3:-paper}"
SVC="nexabot-${SYMBOL}-${TF}"          # per-symbol service name -> run BTC + XAU side by side
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WINE_PY="$HOME/.wine/drive_c/users/$USER/python/python.exe"   # Wine Python (installed below)
MT5_EXE="$HOME/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"

: "${MT5_LOGIN:?set MT5_LOGIN}"; : "${MT5_PASSWORD:?set MT5_PASSWORD}"; : "${MT5_SERVER:?set MT5_SERVER}"

echo "==> [1/6] system packages + Wine + Xvfb"
sudo dpkg --add-architecture i386 || true
sudo apt-get update -y
sudo apt-get install -y wine64 wine32:i386 winbind xvfb wget python3 python3-pip git || \
  sudo apt-get install -y wine64 winbind xvfb wget python3 python3-pip git

echo "==> [2/6] 4G swap (1GB RAM VMs are tight for MT5+Wine)"
if ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

export WINEDEBUG=-all DISPLAY=:0
echo "==> [3/6] MT5 terminal under Wine (silent install)"
if [ ! -f "$MT5_EXE" ]; then
  wget -q https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe -O /tmp/mt5setup.exe
  xvfb-run -a wine /tmp/mt5setup.exe /auto || echo "  (if this stalls, run mt5setup.exe once interactively)"
fi

echo "==> [4/6] Python inside Wine + packages (MT5 pkg must share the Wine env)"
if [ ! -f "$WINE_PY" ]; then
  wget -q https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe -O /tmp/py.exe
  xvfb-run -a wine /tmp/py.exe /quiet InstallAllUsers=0 PrependPath=1 TargetDir='C:\\users\\'"$USER"'\\python'
fi
xvfb-run -a wine "$WINE_PY" -m pip install --upgrade pip
xvfb-run -a wine "$WINE_PY" -m pip install MetaTrader5 pandas numpy scikit-learn scipy hmmlearn pyyaml

echo "==> [5/6] credentials env file (root-only) + systemd service ($SVC)"
ENVF="$REPO_DIR/.env.${SVC}"
cat > "$ENVF" <<EOF
MT5_LOGIN=$MT5_LOGIN
MT5_PASSWORD=$MT5_PASSWORD
MT5_SERVER=$MT5_SERVER
MT5_PATH=Z:$(echo "$MT5_EXE" | sed 's#/#\\#g')
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}
EOF
chmod 600 "$ENVF"

LIVE_FLAG=""; [ "$MODE" = "live" ] && LIVE_FLAG="--live"
sudo tee /etc/systemd/system/${SVC}.service >/dev/null <<EOF
[Unit]
Description=NexaQuant bot ($SYMBOL $TF)
After=network-online.target
[Service]
User=$USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$ENVF
ExecStart=/usr/bin/xvfb-run -a wine "$WINE_PY" execution/live_trader.py --symbol $SYMBOL --tf $TF --mode $MODE $LIVE_FLAG --poll 60
Restart=always
RestartSec=30
[Install]
WantedBy=multi-user.target
EOF

echo "==> [6/7] enable + start ($SVC)"
sudo systemctl daemon-reload
sudo systemctl enable --now ${SVC}.service

echo "==> [7/7] WEEKLY self-learning loop (native Python; pulls fresh data, re-validates,"
echo "          updates the bot's trading license — runs OUTSIDE Wine, no MT5 needed)"
python3 -m pip install --user -q requests pandas numpy scikit-learn scipy hmmlearn pyyaml pyarrow || true
sudo tee /etc/systemd/system/nexa-update.service >/dev/null <<EOF
[Unit]
Description=NexaQuant weekly self-learning loop (pull + revalidate + license)
After=network-online.target
[Service]
Type=oneshot
User=$USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$ENVF
ExecStart=/usr/bin/python3 execution/auto_update.py
EOF
sudo tee /etc/systemd/system/nexa-update.timer >/dev/null <<EOF
[Unit]
Description=Run NexaQuant self-learning loop weekly (Mon 02:00) + on boot
[Timer]
OnCalendar=Mon *-*-* 02:00:00
OnBootSec=10min
Persistent=true
[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now nexa-update.timer

echo ""
echo "DONE. Service '$SVC' is running ($SYMBOL $TF, $MODE) and auto-restarts on boot/failure."
echo "  bot logs:      journalctl -u $SVC -f"
echo "  weekly loop:   journalctl -u nexa-update -f   (next run: systemctl list-timers nexa-update)"
echo "  stop bot:      sudo systemctl stop $SVC"
echo "  run the OTHER pair too:  bash execution/setup_oracle.sh XAUUSDm H4 paper   (separate service)"
echo "  go live: re-run with 'live' as the 3rd arg AFTER 30 days of profitable paper."
echo ""
echo "  The weekly loop re-validates the edge on fresh data and writes execution/health.json."
echo "  If the edge stops persisting, the bot AUTO-STANDS-DOWN (manage-only) — it never keeps"
echo "  trading a dead strategy. That is the self-learning + safety guarantee you asked for."
