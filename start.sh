#!/bin/bash
# ─── ARÊTE Intelligence Dashboard - 시작 스크립트 ───────────────
echo "🏛️  ARÊTE Fashion Intelligence Dashboard 시작..."

# 1. 가상환경 확인/생성
if [ ! -d "venv" ]; then
  echo "📦 가상환경 생성 중..."
  python3 -m venv venv
fi

source venv/bin/activate

# 2. 의존성 설치
echo "📥 패키지 설치 중..."
pip install -r requirements.txt -q

# 3. Playwright 브라우저 설치
echo "🌐 Playwright 브라우저 설치 중..."
playwright install chromium

# 4. .env 파일 확인
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "⚠️  .env 파일이 생성되었습니다. OPENAI_API_KEY를 입력하세요."
fi

# 5. Streamlit 실행
echo "🚀 대시보드 시작: http://localhost:8501"
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
