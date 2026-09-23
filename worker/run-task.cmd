@echo off
rem Shopping Helper worker runner for Windows Task Scheduler (ASCII only: cmd reads this file in the console codepage)
rem usage: run-task.cmd collect | digest | report
cd /d "%~dp0"
if not exist data mkdir data
set PYTHONIOENCODING=utf-8
echo ==== %date% %time% %1 >> data\scheduler.log
if "%1"=="collect" (
  python -m worker run >> data\scheduler.log 2>&1
  python -m worker deals >> data\scheduler.log 2>&1
) else (
  python -m worker %1 >> data\scheduler.log 2>&1
)
