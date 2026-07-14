@echo off
REM AEGIS daily forward paper run (dev / manual fallback).
REM
REM PRIMARY SCHEDULER = GitHub Actions (.github/workflows/aegis-daily.yml).
REM This .bat is for local manual runs / laptop-only debugging. When both are active,
REM the .bat and Actions writes may fight over data/*.csv — pick one for a given day.

cd /d %~dp0
if not exist logs mkdir logs

set PYTHON="C:\Users\GPraveenKumar\AppData\Local\Programs\Python\Python312\python.exe"
set LOG=logs\arjuna_daily.log

echo. >> %LOG%
echo ============================================================ >> %LOG%
echo AEGIS run starting %date% %time% >> %LOG%
echo cwd: %cd% >> %LOG%
echo ============================================================ >> %LOG%

REM 1. Refresh data via yfinance (same path CI uses). Fast, no rate limits.
REM    Angel --pull is HEAVY (200 symbols, ~2s pacing, throttled under load).
REM    Set AEGIS_FORCE_ANGEL_PULL=1 to force the Angel path instead (weekly at most).
if defined AEGIS_FORCE_ANGEL_PULL (
    echo Forcing Angel --pull refresh (AEGIS_FORCE_ANGEL_PULL=1) >> %LOG%
    %PYTHON% india\daily_run.py --pull --capital 100000 >> %LOG% 2>&1
) else (
    %PYTHON% india\refresh_data.py >> %LOG% 2>&1
    if errorlevel 1 (
        echo WARN: refresh_data.py returned non-zero; freshness gate will decide >> %LOG%
    )
    %PYTHON% india\daily_run.py --capital 100000 >> %LOG% 2>&1
)
if errorlevel 1 (
    echo ERROR: daily_run.py failed with errorlevel %errorlevel% >> %LOG%
    echo AEGIS DAILY FAILED at data refresh - see %LOG%
    exit /b 1
)

REM 1b. Freshness gate — abort if the latest bar is older than the previous trading session.
REM      Prevents publishing recommendations from stale data on a broken pull.
%PYTHON% scripts\check_data_freshness.py >> %LOG% 2>&1
if errorlevel 1 (
    echo ERROR: freshness gate failed with errorlevel %errorlevel% >> %LOG%
    echo AEGIS DAILY ABORTED — data stale, see %LOG%
    exit /b 3
)

REM 2. Regenerate the canonical recommendation CSV that Telegram reads.
%PYTHON% india\recommendation_generator.py --capital 100000 >> %LOG% 2>&1
if errorlevel 1 (
    echo ERROR: recommendation_generator.py failed with errorlevel %errorlevel% >> %LOG%
    echo AEGIS DAILY FAILED at recommendation step — see %LOG%
    exit /b 2
)

REM 2b. Snapshot today into aegis_recommendation_db.csv so tomorrow's Telegram can
REM     compute daily_diff (entries/exits/rotation). Idempotent per recommended_date.
%PYTHON% india\recommendation_db.py >> %LOG% 2>&1

REM 3. Send the fresh recommendations to Telegram.
REM    Non-fatal on failure — recommendations are still written to disk.
%PYTHON% india\telegram_notify.py >> %LOG% 2>&1
if errorlevel 1 (
    echo WARNING: telegram_notify.py failed with errorlevel %errorlevel% >> %LOG%
)

echo AEGIS run completed %date% %time% >> %LOG%
echo ============================================================ >> %LOG%
