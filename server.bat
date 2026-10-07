@echo off
cd /d "%~dp0"
python remote.py %*
if errorlevel 1 pause
