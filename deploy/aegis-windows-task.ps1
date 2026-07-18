# AEGIS · Windows Task Scheduler setup
#
# One-shot setup script. Registers two scheduled tasks on the current user:
#   AEGIS-Pipeline  — runs scripts/aegis_daily_v2.py at 06:00 IST weekdays
#   AEGIS-Telegram  — runs scripts/telegram_send_with_retry.py after pipeline
#
# Run PowerShell as Administrator, then:
#   .\deploy\aegis-windows-task.ps1

param(
  [string]$RepoRoot   = (Get-Location).Path,
  [string]$PythonExe  = "python",
  [string]$IstTime    = "06:00"
)

Write-Host "AEGIS Windows Task Scheduler setup"
Write-Host "  RepoRoot:  $RepoRoot"
Write-Host "  PythonExe: $PythonExe"
Write-Host "  Trigger:   $IstTime IST (weekdays)"

# --- Pipeline task ---
$pipelineAction = New-ScheduledTaskAction `
  -Execute $PythonExe `
  -Argument "scripts\aegis_daily_v2.py --continue" `
  -WorkingDirectory $RepoRoot

$pipelineTrigger = New-ScheduledTaskTrigger `
  -Weekly `
  -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
  -At $IstTime

$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
  -TaskName "AEGIS-Pipeline" `
  -Description "AEGIS Phase 2 daily orchestrator (v2.1.0-RC1)" `
  -Action $pipelineAction `
  -Trigger $pipelineTrigger `
  -Settings $settings `
  -Force

Write-Host "  registered task: AEGIS-Pipeline"

# --- Telegram task (fires 5 min after pipeline) ---
$telegramAction = New-ScheduledTaskAction `
  -Execute $PythonExe `
  -Argument "scripts\telegram_send_with_retry.py --attempts 4" `
  -WorkingDirectory $RepoRoot

# Compute trigger time = pipeline time + 5 min
$time = [datetime]::ParseExact($IstTime, "HH:mm", $null)
$telegramTime = $time.AddMinutes(5).ToString("HH:mm")

$telegramTrigger = New-ScheduledTaskTrigger `
  -Weekly `
  -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
  -At $telegramTime

Register-ScheduledTask `
  -TaskName "AEGIS-Telegram" `
  -Description "AEGIS Telegram delivery (sealed retry wrapper)" `
  -Action $telegramAction `
  -Trigger $telegramTrigger `
  -Settings $settings `
  -Force

Write-Host "  registered task: AEGIS-Telegram (fires at $telegramTime IST)"

Write-Host ""
Write-Host "Done. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName AEGIS-*"
Write-Host "Manually trigger:"
Write-Host "  Start-ScheduledTask -TaskName AEGIS-Pipeline"
