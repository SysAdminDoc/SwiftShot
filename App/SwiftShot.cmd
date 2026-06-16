@echo off
REM ============================================
REM  SwiftShot Launcher
REM ============================================
cd /d "%~dp0"
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py" %*
