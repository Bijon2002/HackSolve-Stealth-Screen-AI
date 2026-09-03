@echo off
cd /d "%~dp0"
title HackSolve — Stealth Screen AI
echo ========================================================
echo Starting HackSolve — Stealth Screen AI...
echo ========================================================
echo.

python main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application closed with an error.
    pause
)
