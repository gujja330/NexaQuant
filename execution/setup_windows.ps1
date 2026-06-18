# execution/setup_windows.ps1
# END-TO-END automation for a home WINDOWS PC / laptop (no cloud, no card, no Wine).
# MT5 runs NATIVELY here — the reliable way to trade Exness (gold + BTC). Installs Python
# deps, auto-detects the MT5 terminal, writes a run wrapper, stops the PC from sleeping, and
# registers a Scheduled Task that auto-starts at logon + restarts on failure. Then it's
# autonomous; monitor from the MT5 phone app.
#
# The bot trades the CONFIG-DRIVEN multi-edge portfolio (system.live_symbols x live_edges):
# trend + breakout on BTCUSDc + XAUUSDc by default — edit config/base_config.yaml to change.
#
# RUN ONCE in PowerShell, from the repo folder:
#   $env:MT5_LOGIN="183286147"; $env:MT5_PASSWORD="***"; $env:MT5_SERVER="Exness-MT5Real25"
#   # optional alerts: $env:TELEGRAM_BOT_TOKEN="..."; $env:TELEGRAM_CHAT_ID="..."
#   powershell -ExecutionPolicy Bypass -File execution\setup_windows.ps1 -Mode paper
param(
  [string]$Symbols = "",                 # optional override, e.g. "BTCUSDc,XAUUSDc"; empty = use config
  [string]$TF      = "",                 # optional override; empty = use config system.live_tf
  [ValidateSet("paper","live")] [string]$Mode = "paper",
  [int]$Poll = 60
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $Repo

foreach ($v in "MT5_LOGIN","MT5_PASSWORD","MT5_SERVER") {
  if (-not (Get-Item "env:$v" -ErrorAction SilentlyContinue)) { throw "Set $v before running (\$env:$v='...')." }
}

Write-Host "==> [1/6] Python check + SLIM live dependencies (no heavy ML stack)"
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw "Python not found. Install Python 3.12 from python.org (tick 'Add to PATH'), then re-run." }
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements-live.txt    # slim: MetaTrader5 + pandas/numpy/... only

Write-Host "==> [2/6] locate MetaTrader 5 terminal"
$mt5 = Get-ChildItem "C:\Program Files","C:\Program Files (x86)","$env:APPDATA" -Recurse -Filter "terminal64.exe" -ErrorAction SilentlyContinue |
       Select-Object -First 1 -ExpandProperty FullName
if (-not $mt5) { Write-Host "  ! terminal64.exe not found — install MT5 from Exness and log in once, then re-run." }
else { Write-Host "  found MT5: $mt5" }

Write-Host "==> [3/6] keep the laptop AWAKE (so the bot keeps running on AC power)"
# the broker holds the hard stop-loss even if the PC sleeps, but scale-out/trailing only run
# while the bot is up — so prevent sleep on AC. (Closing the lid may still sleep; see notes.)
powercfg /change standby-timeout-ac 0 2>$null
powercfg /change hibernate-timeout-ac 0 2>$null
powercfg /change monitor-timeout-ac 0 2>$null

Write-Host "==> [4/6] write run wrapper (keeps creds out of the task definition)"
New-Item -ItemType Directory -Force -Path "$Repo\logs" | Out-Null
$bat = "$Repo\run_nexabot.bat"
$liveFlag = if ($Mode -eq "live") { "--live" } else { "" }
$symArg = if ($Symbols -ne "") { "--symbols $Symbols" } else { "" }   # empty = config-driven universe
$tfArg  = if ($TF -ne "") { "--tf $TF" } else { "" }
@"
@echo off
set MT5_LOGIN=$($env:MT5_LOGIN)
set MT5_PASSWORD=$($env:MT5_PASSWORD)
set MT5_SERVER=$($env:MT5_SERVER)
set MT5_PATH=$mt5
set TELEGRAM_BOT_TOKEN=$($env:TELEGRAM_BOT_TOKEN)
set TELEGRAM_CHAT_ID=$($env:TELEGRAM_CHAT_ID)
cd /d "$Repo"
"$py" execution\live_trader.py $symArg $tfArg --mode $Mode $liveFlag --poll $Poll >> "$Repo\logs\nexabot.log" 2>&1
"@ | Set-Content -Encoding ascii $bat
Write-Host "  wrote $bat  (keep private; it holds credentials)"

Write-Host "==> [5/6] pre-flight check (connects, prints lots it WOULD trade, NO order)"
$chkArgs = @("execution\live_trader.py")
if ($Symbols -ne "") { $chkArgs += @("--symbols", $Symbols) }
if ($TF -ne "")      { $chkArgs += @("--tf", $TF) }
$chkArgs += @("--mode", $Mode, "--check")
& $py @chkArgs

Write-Host "==> [6/6] register auto-start + auto-restart Scheduled Task 'NexaBot'"
$action  = New-ScheduledTaskAction -Execute $bat
$trigger = New-ScheduledTaskTrigger -AtLogOn
$set     = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
             -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Register-ScheduledTask -TaskName "NexaBot" -Action $action -Trigger $trigger -Settings $set -Force | Out-Null
Start-ScheduledTask -TaskName "NexaBot"

Write-Host ""
Write-Host "DONE. NexaBot is running ($Mode) on the CONFIG universe (system.live_symbols x live_edges)."
Write-Host "      Auto-starts at logon + restarts on failure. MT5 native — no Wine."
Write-Host "  watch log : Get-Content logs\nexabot.log -Wait"
Write-Host "  stop      : Stop-ScheduledTask -TaskName NexaBot ; Unregister-ScheduledTask -TaskName NexaBot -Confirm:`$false"
Write-Host "  monitor   : open the MetaTrader 5 phone app, log into the same account"
Write-Host "  NOTE      : keep the laptop plugged in and don't shut it down. The broker holds the"
Write-Host "              hard stop-loss even if it sleeps, but trailing/scale-out only run while on."
Write-Host "  go live   : re-run with -Mode live AFTER ~30 days of profitable paper"
