@echo off
REM Arjuna daily forward paper run (news + news-filtered basket + paper log).
REM Registered as a Windows scheduled task to run each weekday after market close.
cd /d C:\Users\GPraveenKumar\Downloads\marl
if not exist logs mkdir logs
"C:\Users\GPraveenKumar\AppData\Local\Programs\Python\Python312\python.exe" india\daily_run.py --pull --capital 100000 >> logs\arjuna_daily.log 2>&1
