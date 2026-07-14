# MON001 · Windows Task Scheduler launcher
#
# Register in Task Scheduler once:
#   $act = New-ScheduledTaskAction -Execute 'powershell.exe' `
#            -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\GPraveenKumar\Downloads\prism\india\monitoring\MON001_Forward_Validation\launchers\run_mon001_windows.ps1"'
#   $trg = New-ScheduledTaskTrigger -Daily -At 6:15am
#   Register-ScheduledTask -TaskName "MON001-daily" -Action $act -Trigger $trg -RunLevel Highest
#
# Run manually (dry test) from PowerShell:
#   .\run_mon001_windows.ps1

param(
    [switch]$SealInit
)

$ErrorActionPreference = "Continue"

$repo = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)))
Set-Location $repo

$python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$logDir = Join-Path $repo "logs\mon001"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("mon001_" + (Get-Date -Format "yyyy-MM-dd") + ".log")

Add-Content -Path $log -Value ""
Add-Content -Path $log -Value "============================================================"
Add-Content -Path $log -Value ("MON001 daily runner starting " + (Get-Date -Format "o"))
Add-Content -Path $log -Value ("cwd: " + $repo)
Add-Content -Path $log -Value "============================================================"

$args = @("-m", "india.monitoring.MON001_Forward_Validation.ops.daily_runner")
if ($SealInit) { $args += "--seal-init" }

& $python @args *>> $log
$exit = $LASTEXITCODE

Add-Content -Path $log -Value ("MON001 daily runner exit=" + $exit + " at " + (Get-Date -Format "o"))
exit $exit
