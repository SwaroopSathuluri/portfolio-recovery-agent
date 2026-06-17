@echo off
cd /d "%~dp0"
python -B run_market_monitor.py --send --loop --interval-minutes 5
