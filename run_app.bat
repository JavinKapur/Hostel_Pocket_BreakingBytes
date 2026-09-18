@echo off
title HostelPocket - Student Expense Tracker
echo ========================================================
echo   HostelPocket: AI Expense Manager for Students
echo   PostgreSQL + Streamlit + PRISM by Block Convey
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/3] Checking Python Virtual Environment...
if exist "venv\Scripts\python.exe" (
    echo [OK] Virtual environment found.
) else (
    echo [ERROR] Virtual environment not found. Please ensure venv is set up.
    pause
    exit /b 1
)

echo [2/3] Checking for lingering processes on port 8501...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [3/3] Launching HostelPocket Streamlit Application...
echo The app will open in your browser automatically.
echo (Press Ctrl+C in this window to stop the server)
echo.

.\venv\Scripts\streamlit.exe run hostelpocket_app.py

pause
