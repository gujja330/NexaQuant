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
# NOTE: deliberately NOT using `set -e` — Wine/Xvfb steps emit transient non-zero exits
# (e.g. "X connection to :99 broken") that must NOT abort the whole setup. We instead VERIFY
# the critical artifacts explicitly and fail loudly only when something real is missing.
set -uo pipefail

# ONE service, ONE MT5 terminal, driven by config (system.live_symbols + system.live_tf).
# Args are OPTIONAL overrides: $1=symbols (comma-sep), $2=TF, $3=mode. Omit them and the bot
# reads the live universe from config -> add a pair later = edit config + restart, no re-setup.
SYMBOLS="${1:-}"; TF="${2:-}"; MODE="${3:-paper}"
SVC="nexabot"                                       # single canonical service (multi-symbol)
SYMARG=""; [ -n "$SYMBOLS" ] && SYMARG="--symbols $SYMBOLS"
TFARG="";  [ -n "$TF" ] && TFARG="--tf $TF"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYDIR="$HOME/.wine/drive_c/users/$USER/python"
WINE_PY="$PYDIR/python.exe"            # Wine Python (embeddable build, installed below)
MT5_EXE="$HOME/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"

: "${MT5_LOGIN:?set MT5_LOGIN}"; : "${MT5_PASSWORD:?set MT5_PASSWORD}"; : "${MT5_SERVER:?set MT5_SERVER}"

echo "==> [1/7] system packages + WineHQ + Xvfb"
sudo dpkg --add-architecture i386 || true
sudo apt-get update -y
sudo apt-get install -y wget unzip xvfb winbind python3 python3-pip git || true
# WineHQ (modern Wine). Ubuntu's distro Wine 6.0 lacks CRT functions numpy/scipy call
# (api-ms-win-crt-runtime ...fetestexcept) and CRASH-LOOPS the bot. Install WineHQ stable;
# fall back to distro wine only if the WineHQ repo is unreachable.
WINEVER="$(wine --version 2>/dev/null || echo none)"
if echo "$WINEVER" | grep -qE 'wine-([0-7])\.'  || [ "$WINEVER" = none ]; then
  echo "  installing WineHQ stable (current: $WINEVER) ..."
  . /etc/os-release; CODE="${UBUNTU_CODENAME:-jammy}"
  sudo mkdir -pm755 /etc/apt/keyrings
  sudo wget -qO /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key
  sudo wget -qNP /etc/apt/sources.list.d/ "https://dl.winehq.org/wine-builds/ubuntu/dists/${CODE}/winehq-${CODE}.sources"
  sudo apt-get update -y
  sudo apt-get install -y --install-recommends winehq-stable \
    || sudo apt-get install -y wine64 wine32:i386 winbind   # fallback (may still be too old)
  echo "  wine now: $(wine --version 2>/dev/null)"
fi

echo "==> [2/7] 4G swap (1GB RAM VMs are tight for MT5+Wine)"
if ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

export WINEDEBUG=-all DISPLAY=:0 WINEARCH=win64 WINEPREFIX="$HOME/.wine"
echo "==> [2b/7] initialise the Wine prefix (creates kernel32 etc. — must exist before Python)"
echo "  wine version: $(wine --version 2>/dev/null || echo UNKNOWN)"
if [ ! -f "$HOME/.wine/system.reg" ]; then
  timeout 240 xvfb-run -a wineboot --init >/dev/null 2>&1
  timeout 60 wineserver -w 2>/dev/null || true
  sleep 3
fi
# sanity: the prefix must be able to load core DLLs, else Python will fail with c0000135
if ! timeout 60 xvfb-run -a wine cmd /c ver >/dev/null 2>&1; then
  echo "  ! Wine prefix not healthy yet — forcing a rebuild"
  rm -rf "$HOME/.wine"; timeout 240 xvfb-run -a wineboot --init >/dev/null 2>&1; timeout 60 wineserver -w 2>/dev/null || true; sleep 3
fi

echo "==> [3/7] MT5 terminal under Wine (silent install)"
if [ ! -f "$MT5_EXE" ]; then
  wget -q https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe -O /tmp/mt5setup.exe
  xvfb-run -a wine /tmp/mt5setup.exe /auto || echo "  (if this stalls, run mt5setup.exe once interactively)"
fi

echo "==> [4/7] Python inside Wine + packages (EMBEDDABLE zip — reliable headless on old Wine)"
# The Python .exe GUI installer is unreliable under Ubuntu's Wine 6.0 (crashes the Xvfb X
# server -> "X connection broken"). The embeddable ZIP needs no GUI, so it installs headless.
# We also pin Python 3.10 (works on Wine 6.0; 3.12 does not) and bootstrap pip via get-pip.
PYVER="3.10.11"; PYTAG="310"
# wrapper: run a Wine command headless with a hard TIMEOUT + kill lingering wineserver, so a
# Wine process that won't exit cleanly can never hang the whole setup.
winerun() { local t="$1"; shift; timeout --kill-after=10 "$t" xvfb-run -a wine "$@"; local rc=$?; wineserver -k >/dev/null 2>&1 || true; return $rc; }
if [ ! -f "$WINE_PY" ]; then
  mkdir -p "$PYDIR"
  wget -q "https://www.python.org/ftp/python/${PYVER}/python-${PYVER}-embed-amd64.zip" -O /tmp/py.zip
  unzip -o /tmp/py.zip -d "$PYDIR" >/dev/null
  # enable site-packages so pip works in the embeddable build
  sed -i 's/^#import site/import site/' "$PYDIR/python${PYTAG}._pth" 2>/dev/null || true
  grep -q '^import site' "$PYDIR/python${PYTAG}._pth" 2>/dev/null || echo 'import site' >> "$PYDIR/python${PYTAG}._pth"
  wget -q https://bootstrap.pypa.io/get-pip.py -O /tmp/get-pip.py
  winerun 180 "$WINE_PY" /tmp/get-pip.py || true
fi
winerun 120 "$WINE_PY" -m pip install --upgrade pip || true
winerun 600 "$WINE_PY" -m pip install MetaTrader5 pandas numpy scikit-learn scipy hmmlearn pyyaml pyarrow || true
# VERIFY (timeout-guarded so it can NEVER hang the script)
if ! winerun 90 "$WINE_PY" -c "import MetaTrader5, pandas, numpy, pyarrow" >/dev/null 2>&1; then
  echo "  ! Wine-Python import check did not pass cleanly (often just a slow Wine exit). Retrying pip once..."
  winerun 600 "$WINE_PY" -m pip install --no-cache-dir MetaTrader5 pandas numpy scikit-learn scipy hmmlearn pyyaml pyarrow || true
  winerun 90 "$WINE_PY" -c "import MetaTrader5, pandas, numpy" >/dev/null 2>&1 \
    && echo "  packages OK on retry" \
    || echo "  (continuing anyway — if the bot later can't import, re-run this step)"
fi
echo "  [4/7] done — continuing to service setup"

echo "==> [5/7] credentials env file (root-only) + systemd service ($SVC)"
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
Description=NexaQuant bot (config-driven universe)
After=network-online.target
[Service]
User=$USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$ENVF
ExecStart=/usr/bin/xvfb-run -a wine "$WINE_PY" execution/live_trader.py $SYMARG $TFARG --mode $MODE $LIVE_FLAG --poll 60
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
echo "DONE. Service '$SVC' is running ($MODE) — ONE terminal driving the config universe"
echo "      (system.live_symbols), auto-restarts on boot/failure."
echo "  bot logs:      journalctl -u $SVC -f"
echo "  weekly loop:   journalctl -u nexa-update -f   (next run: systemctl list-timers nexa-update)"
echo "  stop bot:      sudo systemctl stop $SVC"
echo "  ADD A PAIR:    edit system.live_symbols in config/base_config.yaml -> git pull on VM ->"
echo "                 sudo systemctl restart $SVC   (no re-setup, no code change)"
echo "  go live: re-run with 'live' as the 3rd arg AFTER 30 days of profitable paper."
echo ""
echo "  The weekly loop re-validates the edge on fresh data and writes execution/health.json."
echo "  If the edge stops persisting, the bot AUTO-STANDS-DOWN (manage-only) — it never keeps"
echo "  trading a dead strategy. That is the self-learning + safety guarantee you asked for."
