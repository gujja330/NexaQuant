#!/usr/bin/env bash
# execution/setup_oracle_arm.sh
# EXPERIMENTAL — run MT5 on an Oracle Ampere ARM (VM.Standard.A1.Flex, free up to 24GB) box.
# ARM cannot run x86 Windows natively, so we use box64 (x86_64->ARM translation) + an amd64
# WineHQ build, then install MT5 + an embeddable Python under it. 24GB RAM gives the headroom
# the 1GB x86 box lacked. HONEST: this stack is fiddly; logs are verbose on purpose so any
# failure is diagnosable. Same multi-edge bot + config-driven universe as the x86 path.
#
# RUN ONCE on a fresh Ubuntu 22.04 ARM instance:
#   export MT5_LOGIN=... MT5_PASSWORD='...' MT5_SERVER='Exness-...'
#   bash execution/setup_oracle_arm.sh
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WINEDIR="/opt/wine-stable"                       # extracted amd64 WineHQ
WINE_PY="$HOME/.wine/drive_c/users/$USER/python/python.exe"
MT5_EXE="$HOME/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"
WINEVER="11.0.0.0~jammy-1"                        # WineHQ amd64 build to translate via box64
export BOX64_LOG=0 BOX86_LOG=0
export WINEDEBUG=-all DISPLAY=:0 WINEARCH=win64 WINEPREFIX="$HOME/.wine" WINEDLLOVERRIDES="mscoree=;mshtml="

: "${MT5_LOGIN:?set MT5_LOGIN}"; : "${MT5_PASSWORD:?set MT5_PASSWORD}"; : "${MT5_SERVER:?set MT5_SERVER}"

# wine via box64 (x86_64 wine binary translated to ARM at runtime)
wine64() { box64 "$WINEDIR/bin/wine64" "$@"; }
xwine()  { timeout --kill-after=20 "${1}" xvfb-run -a box64 "$WINEDIR/bin/wine64" "${@:2}"; wineserver -k >/dev/null 2>&1 || true; }

echo "==> [1/8] base packages + armhf"
sudo dpkg --add-architecture armhf || true
sudo apt-get update -y
sudo apt-get install -y wget unzip xvfb python3 python3-pip git curl gnupg ca-certificates || true

echo "==> [2/8] box86 + box64 (x86/x86_64 -> ARM translators)"
sudo mkdir -pm755 /etc/apt/keyrings
if ! command -v box64 >/dev/null; then
  sudo wget -qO /etc/apt/sources.list.d/box86.list https://ryanfortner.github.io/box86-debs/box86.list
  sudo wget -qO /etc/apt/sources.list.d/box64.list https://ryanfortner.github.io/box64-debs/box64.list
  wget -qO- https://ryanfortner.github.io/box86-debs/KEY.gpg | sudo gpg --yes --dearmor -o /etc/apt/keyrings/box86-debs-archive-keyring.gpg
  wget -qO- https://ryanfortner.github.io/box64-debs/KEY.gpg | sudo gpg --yes --dearmor -o /etc/apt/keyrings/box64-debs-archive-keyring.gpg
  sudo apt-get update -y
  sudo apt-get install -y box86 box64 || sudo apt-get install -y box64
fi
echo "  box64: $(box64 --version 2>/dev/null | head -1 || echo MISSING)"

echo "==> [3/8] amd64 WineHQ (extracted; run via box64 — no native install on ARM)"
if [ ! -x "$WINEDIR/bin/wine64" ]; then
  cd /tmp
  base="https://dl.winehq.org/wine-builds/ubuntu/dists/jammy/main/binary-amd64"
  for pkg in "wine-stable-amd64_${WINEVER}_amd64.deb"; do
    wget -q "$base/$pkg" -O "$pkg" && dpkg-deb -x "$pkg" /tmp/wineroot
  done
  if [ -d /tmp/wineroot/opt/wine-stable ]; then
    sudo cp -r /tmp/wineroot/opt/wine-stable /opt/
    echo "  extracted Wine to $WINEDIR"
  else
    echo "  ! could not extract Wine amd64 deb — check the WINEVER / URL";
  fi
fi
echo "  wine: $(wine64 --version 2>/dev/null || echo MISSING)"

echo "==> [4/8] initialise the Wine prefix (box64)"
if [ ! -f "$HOME/.wine/system.reg" ]; then
  xwine 300 wineboot --init >/dev/null 2>&1; sleep 5
fi
xwine 60 cmd /c ver >/dev/null 2>&1 && echo "  prefix OK" || echo "  ! prefix health check failed"

echo "==> [5/8] MT5 terminal (silent; mono/gecko disabled so it can't hang)"
if [ ! -f "$MT5_EXE" ]; then
  wget -q https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe -O /tmp/mt5setup.exe
  xwine 900 /tmp/mt5setup.exe /auto
fi
[ -f "$MT5_EXE" ] && echo "  MT5 installed OK" || echo "  ! MT5 not found after install (see logs above)"

echo "==> [6/8] embeddable Python + packages (under box64 Wine)"
PYDIR="$HOME/.wine/drive_c/users/$USER/python"
if [ ! -f "$WINE_PY" ]; then
  mkdir -p "$PYDIR"
  wget -q https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip -O /tmp/py.zip
  unzip -o /tmp/py.zip -d "$PYDIR" >/dev/null
  sed -i 's/^#import site/import site/' "$PYDIR/python310._pth" 2>/dev/null || true
  grep -q '^import site' "$PYDIR/python310._pth" 2>/dev/null || echo 'import site' >> "$PYDIR/python310._pth"
  wget -q https://bootstrap.pypa.io/get-pip.py -O /tmp/get-pip.py
  xwine 300 "$WINE_PY" /tmp/get-pip.py || true
fi
xwine 600 "$WINE_PY" -m pip install MetaTrader5 pandas numpy scikit-learn scipy hmmlearn pyyaml pyarrow || true
xwine 90 "$WINE_PY" -c "import MetaTrader5, pandas, numpy" >/dev/null 2>&1 \
  && echo "  Wine-Python OK" || echo "  ! Wine-Python import failed"

echo "==> [7/8] credentials env file + systemd service (nexabot)"
ENVF="$REPO_DIR/.env.nexabot"
cat > "$ENVF" <<EOF
MT5_LOGIN=$MT5_LOGIN
MT5_PASSWORD=$MT5_PASSWORD
MT5_SERVER=$MT5_SERVER
MT5_PATH=Z:$(echo "$MT5_EXE" | sed 's#/#\\#g')
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}
EOF
chmod 600 "$ENVF"
sudo tee /etc/systemd/system/nexabot.service >/dev/null <<EOF
[Unit]
Description=NexaQuant bot (ARM/box64 Wine, config universe)
After=network-online.target
[Service]
User=$USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$ENVF
Environment=WINEDEBUG=-all DISPLAY=:0 WINEARCH=win64 WINEPREFIX=$HOME/.wine WINEDLLOVERRIDES=mscoree=;mshtml=
ExecStart=/usr/bin/xvfb-run -a /usr/local/bin/box64 $WINEDIR/bin/wine64 "$WINE_PY" execution/live_trader.py --mode paper --poll 60
Restart=always
RestartSec=30
[Install]
WantedBy=multi-user.target
EOF

echo "==> [8/8] enable + start"
sudo systemctl daemon-reload
sudo systemctl enable --now nexabot.service || true
echo ""
echo "DONE (experimental ARM path). Check: journalctl -u nexabot -n 40 --no-pager"
echo "  If MT5 / Wine-Python failed above, paste those lines — ARM+box64 often needs a tweak."
