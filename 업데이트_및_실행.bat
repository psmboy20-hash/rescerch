@echo off
chcp 65001 > nul
title ARÊTE - 업데이트 및 실행

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   ARÊTE - 업데이트 및 실행           ║
echo  ╚══════════════════════════════════════╝
echo.

:: 현재 배치 파일 위치로 이동
cd /d "%~dp0"

echo [1/3] 최신 코드 다운로드 중...
git pull
if errorlevel 1 (
    echo [경고] git pull 실패. 인터넷 연결을 확인하세요.
    echo 그냥 계속 실행합니다...
)

echo.
echo [2/3] 새 패키지 설치 확인 중...
py -3.11 -m pip install streamlit pandas plotly openai python-dotenv loguru tqdm Pillow httpx playwright tenacity openpyxl aiohttp -q

echo.
echo [3/3] 대시보드 실행 중...
echo  브라우저: http://localhost:8501
echo  종료: 이 창을 닫으세요
echo.

py -3.11 -m streamlit run app.py

pause
