@echo off
setlocal

cd /d "%~dp0"

echo ==========================================
echo Toss Portfolio Radar
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo.
        echo Failed to create .venv with py launcher. Trying python...
        python -m venv .venv
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Python virtual environment could not be created.
    echo Please install Python 3.11 or newer, then run this file again.
    echo.
    pause
    exit /b 1
)

echo Installing required packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Package installation failed.
    echo Check your internet connection, then run this file again.
    echo.
    pause
    exit /b 1
)

if not exist ".env" (
    echo Creating .env from .env.example...
    copy ".env.example" ".env" >nul
    echo.
    echo IMPORTANT:
    echo .env was created. Add your TOSS_CLIENT_ID and TOSS_CLIENT_SECRET later.
    echo The app will still open and show setup guidance without API keys.
    echo.
)

echo Starting Streamlit...
echo Browser URL: http://localhost:8501
echo.
".venv\Scripts\python.exe" -m streamlit run app.py

echo.
echo Streamlit stopped.
pause
