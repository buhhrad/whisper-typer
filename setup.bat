@echo off
echo ============================================
echo   Whisper Typer — Setup
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

echo Installing dependencies...
pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies.
    echo Make sure you have pip installed and try running as administrator.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Setup complete!
echo.
echo   Run WhisperTyper.bat to start.
echo   Or: python whisper_typer.py
echo ============================================
pause
