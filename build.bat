@echo off
setlocal
title HackSolve — Stealth Screen AI Build Script

echo ========================================================
echo   HackSolve — Stealth Screen AI Single-File EXE Builder
echo ========================================================
echo.

REM 1. Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH!
    echo Please install Python 3.10+ from python.org and check "Add to PATH".
    pause
    exit /b 1
)

REM 2. Check / Install dependencies
echo [*] Checking Python dependencies...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARNING] Some dependencies could not be installed automatically.
)

REM 3. Compile EXE with PyInstaller
echo.
echo [*] Compiling standalone executable with PyInstaller...
echo     Target: dist\HackSolve.exe
echo.

pyinstaller --onefile --noconsole --name HackSolve --clean ^
    --hidden-import "PIL" ^
    --hidden-import "pytesseract" ^
    --hidden-import "keyboard" ^
    --hidden-import "mss" ^
    --hidden-import "requests" ^
    --hidden-import "winocr" ^
    main.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo  [SUCCESS] HackSolve.exe built successfully!
    echo  Location: dist\HackSolve.exe
    echo ========================================================
    echo.
    echo NOTE: Always run HackSolve.exe as Administrator so the
    echo       global hotkey (F9) works across all windows.
    echo.
) else (
    echo.
    echo [ERROR] PyInstaller failed to compile HackSolve.
    echo Please review the errors printed above.
)

pause
