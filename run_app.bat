@echo off
title HostelPocket - PRISM by Block Convey Hackathon Prototype
echo ========================================================
echo   HostelPocket: AI Expense Manager & UPI Engine
echo   Powered by PRISM by Block Convey & PostgreSQL
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/2] Checking Python Virtual Environment...
if exist "venv\Scripts\python.exe" (
    echo Virtual environment detected.
) else (
    echo Error: venv not found. Please ensure venv is present.
    pause
    exit /b 1
)

echo.
echo [2/2] Launching HostelPocket Streamlit Application...
echo The app will open in your default browser at http://localhost:8501
echo Press Ctrl+C in this terminal to stop the server.
echo.

.\venv\Scripts\streamlit.exe run hostelpocket_app.py --server.port 8501 --server.headless false

pause
