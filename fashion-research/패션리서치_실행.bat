@echo off
chcp 65001 > nul
title 패션 리서치 툴 v3 (통합)

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   패션 리서치 툴 v3 (통합 버전)             ║
echo  ║   랭킹 + 벌크스캔 + 시장반응속도 + 원단    ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: 현재 파일 위치로 이동
cd /d "%~dp0"

:: Python 확인
py -3.11 --version > nul 2>&1
if errorlevel 1 (
    echo [오류] Python 3.11이 없습니다.
    echo https://www.python.org/downloads/release/python-3119/
    pause
    exit /b
)

:: 패키지 설치
echo [1/3] 패키지 설치 확인 중...
py -3.11 -m pip install requests beautifulsoup4 playwright httpx loguru pandas tqdm aiohttp python-dotenv fake-useragent -q

:: Playwright 브라우저
echo [2/3] Playwright 브라우저 확인 중...
py -3.11 -m playwright install chromium --quiet 2>nul

:: 서버 실행
echo [3/3] 서버 시작 중...
echo.
echo  브라우저에서 열기: http://localhost:5000
echo  종료: 이 창을 닫으세요
echo.

start "" http://localhost:5000
py -3.11 app.py

pause
