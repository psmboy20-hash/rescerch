@echo off
cd /d "%~dp0"
chcp 65001 > nul
echo ================================================
echo    Fashion Research Tool
echo ================================================
echo.

where python >/dev/null 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python from https://www.python.org
    pause
    exit /b 1
)

echo [1/4] Python OK
python --version
echo.

echo [2/4] Installing Python packages...
pip install requests beautifulsoup4 lxml playwright -q
echo Packages installed!
echo.

echo [3/4] Installing Chromium browser (first time only)...
python -m playwright install chromium
echo Chromium ready!
echo.

echo [4/4] Starting server...
echo ================================================
echo  Open browser: http://localhost:5000
echo  Close this window to stop the server.
echo ================================================
echo.

python app.py
pause
