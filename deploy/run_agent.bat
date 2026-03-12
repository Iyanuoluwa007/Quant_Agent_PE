@echo off
REM Multi-Strategy AI Trading Agent - Task Scheduler Runner
cd /d E:\alpaca
call C:\ProgramData\anaconda3\Scripts\activate.bat base
python run.py --once
echo [%date% %time%] Cycle completed (exit code %ERRORLEVEL%) >> scheduler.log