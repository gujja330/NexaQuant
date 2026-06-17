# execution/setup_windows.ps1
# END-TO-END automation for a home WINDOWS PC (no cloud, no card, no Wine).
# Installs Python deps, auto-detects the MT5 terminal, writes a run wrapper, registers a
# Scheduled Task that auto-starts at logon AND restarts on failure, then launches the bot.
# After this the bot is autonomous; monitor from the MT5 phone app.
#
# RUN ONCE in PowerShell (from the repo folder):
#   $env:MT5_LOGIN="123456"; $env:MT5_PASSWORD="***"; $env:MT5_SERVER="Exness-..."
#   # optional alerts: $env:TELEGRAM_BOT_TOKEN="..."; $env:TELEGRAM_CHAT_ID="..."
#   powershell -ExecutionPolicy Bypass -File execution\setup_windows.ps1 -Symbol BTCUSDm -TF H4 -Mode paper
param(
  [string]$Symbol = "BTCUSDm",
  [string]$TF     = "H4",
  [ValidateSet("paper","live")] [string]$Mode = "paper",
  [int]$Poll = 60
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $Repo

foreach ($v in "MT5_LOGIN","MT5_PASSWORD","MT5_SERVER") {
  if (-not (Get-Item "env:$v" -ErrorAction SilentlyContinue)) { throw "Set $v before running (\$env:$v='...')." }
}

Write-Host "==> [1/5] Python check + dependencies"
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw "Python not found. Install Python 3.12 from python.org (tick 'Add to PATH'), then re-run." }
& $py -m pip install --quiet -r requirements.txt
& $py -m pip install --quiet MetaTrader5

Write-Host "==> [2/5] locate MetaTrader 5 terminal"
$mt5 = Get-ChildItem "C:\Program Files","C:\Program Files (x86)" -Recurse -Filter "terminal64.exe" -ErrorAction SilentlyContinue |
       Select-Object -First 1 -ExpandProperty FullName
if (-not $mt5) { Write-Host "  ! terminal64.exe not found — install MT5 from your broker and log in, then re-run." }
else { Write-Host "  found MT5: $mt5" }

Write-Host "==> [3/5] write run wrapper (keeps creds out of the task definition)"
New-Item -ItemType Directory -Force -Path "$Repo\logs" | Out-Null
$bat = "$Repo\run_nexabot.bat"
$liveFlag = if ($Mode -eq "live") { "--live" } else { "" }
@"
@echo off
set MT5_LOGIN=$($env:MT5_LOGIN)
set MT5_PASSWORD=$($env:MT5_PASSWORD)
set MT5_SERVER=$($env:MT5_SERVER)
set MT5_PATH=$mt5
set TELEGRAM_BOT_TOKEN=$($env:TELEGRAM_BOT_TOKEN)
set TELEGRAM_CHAT_ID=$($env:TELEGRAM_CHAT_ID)
cd /d "$Repo"
"$py" execution\live_trader.py --symbol $Symbol --tf $TF --mode $Mode $liveFlag --poll $Poll >> "$Repo\logs\nexabot.log" 2>&1
"@ | Set-Content -Encoding ascii $bat
Write-Host "  wrote $bat  (keep private; it holds credentials)"

Write-Host "==> [4/5] pre-flight check (no order placed)"
& $py execution\live_trader.py --symbol $Symbol --tf $TF --mode $Mode --check

Write-Host "==> [5/5] register auto-start + auto-restart Scheduled Task 'NexaBot'"
$action  = New-ScheduledTaskAction -Execute $bat
$trigger = New-ScheduledTaskTrigger -AtLogOn
$set     = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
             -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Register-ScheduledTask -TaskName "NexaBot" -Action $action -Trigger $trigger -Settings $set -Force | Out-Null
Start-ScheduledTask -TaskName "NexaBot"

Write-Host ""
Write-Host "DONE. NexaBot is running ($Symbol $TF, $Mode) and will auto-start at logon + restart on failure."
Write-Host "  watch log : Get-Content logs\nexabot.log -Wait"
Write-Host "  stop      : Stop-ScheduledTask -TaskName NexaBot ; Unregister-ScheduledTask -TaskName NexaBot -Confirm:`$false"
Write-Host "  monitor   : open the MetaTrader 5 phone app, log into the same account"
Write-Host "  go live   : re-run with -Mode live AFTER ~30 days of profitable paper"
