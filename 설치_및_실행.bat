@echo off
chcp 65001 > nul
title ARÊTE Fashion Intelligence Dashboard

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   ARÊTE Fashion Intelligence         ║
echo  ║   설치 및 실행 스크립트              ║
echo  ╚══════════════════════════════════════╝
echo.

:: Python 3.11 확인
py -3.11 --version > nul 2>&1
if errorlevel 1 (
    echo [오류] Python 3.11이 설치되어 있지 않습니다.
    echo 아래 주소에서 다운로드 후 다시 실행하세요:
    echo https://www.python.org/downloads/release/python-3119/
    echo.
    pause
    exit /b
)

echo [1/4] Python 3.11 확인 완료
py -3.11 --version

echo.
echo [2/4] 패키지 설치 중... (처음 한 번만, 수분 소요)
py -3.11 -m pip install --upgrade pip > nul 2>&1
py -3.11 -m pip install streamlit pandas plotly openai python-dotenv loguru tqdm Pillow httpx playwright tenacity openpyxl aiohttp

echo.
echo [3/4] Playwright 브라우저 설치 중... (처음 한 번만)
py -3.11 -m playwright install chromium

echo.
echo [4/4] 대시보드 실행 중...
echo.
echo  브라우저에서 자동으로 열립니다: http://localhost:8501
echo  종료하려면 이 창을 닫으세요.
echo.

py -3.11 -m streamlit run app.py

pause
