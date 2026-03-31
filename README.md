# 🏛️ ARÊTE Fashion Intelligence Dashboard (Python/Streamlit 버전)

## 📋 개요
패션 브랜드 ARÊTE를 위한 내부용 데이터 인텔리전스 도구입니다.
무신사/W컨셉/29CM 리뷰 전수 수집 + SNS 트렌드 분석 + GPT-4o 제품 개발 브리핑을 지원합니다.

---

## 🏗️ 프로젝트 구조

```
arête-python/
├── app.py                  ← Streamlit 메인 앱 (진입점)
├── requirements.txt
├── .env.example            ← API 키 설정 예시
├── start.sh                ← 원클릭 시작 스크립트
│
├── scrapers/               ← 이커머스 스크래퍼
│   ├── base_scraper.py     ← 기반 클래스 (ProductMeta, Review)
│   ├── scraper_29cm.py     ← 29CM 전용 스크래퍼
│   ├── scraper_wconcept.py ← W컨셉 전용 스크래퍼
│   ├── scraper_musinsa.py  ← 무신사 전용 스크래퍼
│   └── bulk_scanner.py     ← 카테고리 벌크 스캔
│
├── analyzers/              ← 데이터 분석 엔진
│   ├── sales_analyzer.py   ← Pandas + Plotly 판매 추이 분석
│   └── ai_analyzer.py      ← GPT-4o 리뷰 요약 + 제품 브리핑
│
├── agents/                 ← SNS 웹 에이전트
│   ├── youtube_agent.py    ← YouTube 웹 자동화 (Playwright)
│   └── instagram_agent.py  ← Instagram 해시태그 분석 + 스크린샷
│
├── plugins/                ← 디렉터 커스텀 로직
│   └── director_plugins.py ← Script Wrapping 플러그인 시스템
│
├── utils/                  ← 공통 유틸리티
│   ├── browser.py          ← Playwright Stealth 브라우저
│   └── exporter.py         ← CSV/Excel/JSON 내보내기
│
├── data/                   ← 수집된 원본 데이터
└── exports/                ← 분석 결과 내보내기
```

---

## 🚀 시작 방법

### 1. 환경 설정
```bash
# 의존성 설치
pip install -r requirements.txt

# Playwright 브라우저 설치 (필수!)
playwright install chromium

# API 키 설정
cp .env.example .env
# .env 파일에서 OPENAI_API_KEY 입력
```

### 2. 실행
```bash
# 원클릭 시작
bash start.sh

# 또는 직접 실행
streamlit run app.py
# → http://localhost:8501 접속
```

---

## 📊 주요 기능

### 🔍 이커머스 분석
| 기능 | 설명 |
|---|---|
| 리뷰 전수 수집 | 페이지네이션 끝까지 모든 리뷰 수집 |
| 제조년월 추출 | 상세페이지에서 자동 파싱 |
| 시장 반응 속도 | 제조년월 → 첫 리뷰일 일수 계산 |
| 월별/주별 추이 | 리뷰 날짜 기반 판매 트렌드 시각화 |
| 벌크 스캐너 | 카테고리 상위 100개 일괄 분석 |

### 📺 SNS 에이전트
| 플랫폼 | 수집 데이터 |
|---|---|
| YouTube | 제목, 조회수, 업로드일, 댓글 |
| Instagram | 해시태그 추이, 게시물, 스크린샷 |

### 🔧 디렉터 플러그인
| 플러그인 | 기능 |
|---|---|
| 체형_불만_필터 | 특정 체형(키/몸무게) 불만 추출 |
| 생산월_원단분석 | 특정 생산월 이후 소재 피드백 |
| 사이즈_정확도_분석 | 옵션별 핏 일치 통계 |
| 시즌_트렌드_감지 | 계절별 키워드 분석 |
| **커스텀 플러그인** | UI에서 Python 코드 직접 입력 |

---

## ⚙️ 환경 변수 (.env)

```env
OPENAI_API_KEY=sk-xxx          # GPT-4o 사용 (필수)
YOUTUBE_API_KEY=AIza-xxx       # YouTube API (선택)
HEADLESS_MODE=true             # 브라우저 숨김 여부
SCRAPE_DELAY_MIN=1.5           # 최소 딜레이(초)
SCRAPE_DELAY_MAX=3.5           # 최대 딜레이(초)
MAX_PAGES=999                  # 전수 수집 (999=무제한)
```

---

## 📝 데이터 모델

### ProductMeta (제품 메타)
- `platform`: 플랫폼명 (29cm/wconcept/musinsa)
- `name`, `brand`, `price`: 기본 정보
- `manufacture_date`: 제조년월 (YYYY-MM)
- `first_review_date`: 첫 리뷰일
- `market_response_days`: 시장 반응 속도 (일수)

### Review (리뷰)
- `date`: 리뷰 작성일 (YYYY-MM-DD)
- `rating`: 별점 (1-5)
- `option`: 선택 옵션 (사이즈/컬러)
- `text`: 리뷰 내용
- `has_photo`: 포토 리뷰 여부

---

## ⚠️ 주의사항
- 이 도구는 내부 의사결정 보조용입니다
- 플랫폼 정책 변경 시 셀렉터 업데이트 필요
- 과도한 스크래핑은 IP 차단 위험 → 딜레이 설정 준수

---
*ARÊTE © 2024 | Internal Use Only*
