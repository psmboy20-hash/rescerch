@echo off
chcp 65001 > nul
title ARÊTE Dashboard

echo  ARÊTE 대시보드 시작 중...
echo  브라우저: http://localhost:8501
echo  종료: 이 창을 닫으세요
echo.

py -3.11 -m streamlit run app.py

pause
