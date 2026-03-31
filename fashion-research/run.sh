#!/bin/bash
# 패션 리서치 툴 실행 스크립트

echo "================================================"
echo "🛍️  패션 리서치 툴 설치 & 실행"
echo "================================================"

# Python 확인
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3가 설치되어 있지 않습니다."
    echo "   https://www.python.org 에서 설치해 주세요."
    exit 1
fi

# pip 패키지 설치
echo "📦 필요한 패키지를 설치합니다..."
pip3 install -r requirements.txt --quiet

echo ""
echo "✅ 설치 완료!"
echo "🌐 브라우저에서 http://localhost:5000 을 열어주세요."
echo ""

# 서버 실행
python3 app.py
