"""
analyzers/ai_analyzer.py
GPT-4o 기반 리뷰 분석 및 제품 개발 제안
"""
import os
import json
from openai import OpenAI
from loguru import logger
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def summarize_reviews(reviews_df: pd.DataFrame, product_name: str = "", max_reviews: int = 200) -> dict:
    """
    전체 리뷰를 GPT-4o로 분석하여 인사이트 추출
    Returns: {
        "summary": str,         # 전체 요약
        "positives": list[str], # 긍정 포인트
        "negatives": list[str], # 부정 포인트
        "size_feedback": str,   # 사이즈/핏 피드백
        "quality_feedback": str,# 품질 피드백
        "keywords": list[str],  # 핵심 키워드
        "dev_suggestions": list[str], # 제품 개발 제안
    }
    """
    if reviews_df.empty:
        return {"error": "리뷰 데이터 없음"}

    # 리뷰 샘플링 (너무 많으면 비용 증가)
    sample = reviews_df.sample(min(max_reviews, len(reviews_df)), random_state=42)
    review_texts = []
    for _, row in sample.iterrows():
        text = row.get("text", "")
        rating = row.get("rating", "")
        option = row.get("option", "")
        if text:
            review_texts.append(f"[{rating}점/{option}] {text}")

    combined_text = "\n".join(review_texts[:100])

    prompt = f"""
당신은 패션 브랜드 ARÊTE의 수석 MD 어시스턴트입니다.
아래는 '{product_name}' 제품의 실제 고객 리뷰입니다.

[리뷰 데이터 ({len(review_texts)}건 샘플)]
{combined_text}

다음 항목을 JSON 형식으로 분석해주세요:

1. summary: 전체 리뷰 핵심 요약 (3-4문장)
2. positives: 고객이 좋아하는 점 (최대 5가지)
3. negatives: 고객 불만 사항 (최대 5가지)
4. size_feedback: 사이즈/핏 관련 종합 피드백
5. quality_feedback: 원단/품질 관련 종합 피드백
6. keywords: 자주 등장하는 핵심 키워드 (최대 10개)
7. dev_suggestions: 다음 시즌 제품 개선 제안 (최대 5가지)
8. target_profile: 주요 구매 고객 프로필 추정

JSON만 반환하세요. 한국어로 작성하세요.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2000,
        )
        result = json.loads(response.choices[0].message.content)
        logger.success(f"[GPT-4o] 리뷰 분석 완료: {product_name}")
        return result
    except Exception as e:
        logger.error(f"[GPT-4o] 분석 오류: {e}")
        return {"error": str(e)}


def generate_product_brief(
    meta_dict: dict,
    review_analysis: dict,
    director_notes: str = "",
    season: str = "",
) -> str:
    """
    MD 브리핑 문서 자동 생성
    """
    prompt = f"""
당신은 패션 브랜드 ARÊTE의 브랜드 디렉터 어시스턴트입니다.
아래 데이터를 바탕으로 다음 시즌 제품 기획 브리핑 문서를 작성해주세요.

[제품 메타데이터]
{json.dumps(meta_dict, ensure_ascii=False, indent=2)}

[리뷰 분석 결과]
{json.dumps(review_analysis, ensure_ascii=False, indent=2)}

[디렉터 추가 메모]
{director_notes or "없음"}

[대상 시즌]
{season or "다음 시즌"}

다음 구조로 마크다운 형식의 브리핑을 작성해주세요:

# 제품 기획 브리핑: [제품명]

## 1. 시장 반응 분석
## 2. 고객 인사이트 요약
## 3. 개선 방향 (원단/핏/컬러/디테일)
## 4. 생산 시점 제안
## 5. 타겟 고객 재정의
## 6. 예상 판매 시나리오

한국어로 작성하고, 구체적이고 실행 가능한 내용으로 채워주세요.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=3000,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"[GPT-4o] 브리핑 생성 오류: {e}")
        return f"❌ 생성 오류: {e}"


def filter_reviews_by_profile(
    reviews_df: pd.DataFrame,
    filter_instruction: str,
) -> pd.DataFrame:
    """
    디렉터가 지정한 조건으로 리뷰 필터링 (Script Wrapping 플러그인)
    예: "키가 170 이상이고 불만을 남긴 리뷰만"
    """
    if reviews_df.empty:
        return reviews_df

    sample_texts = reviews_df["text"].head(20).tolist()
    prompt = f"""
다음은 패션 제품 리뷰 목록입니다.
디렉터의 필터 조건: "{filter_instruction}"

각 리뷰가 이 조건에 해당하는지 True/False 배열로 반환하세요.
배열 길이는 리뷰 개수({len(sample_texts)})와 동일해야 합니다.
JSON: {{"matches": [true, false, ...]}}

리뷰들:
{chr(10).join([f'{i+1}. {t[:200]}' for i, t in enumerate(sample_texts)])}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        result = json.loads(response.choices[0].message.content)
        matches = result.get("matches", [True] * len(sample_texts))
        filtered = reviews_df.head(len(matches)).copy()
        filtered = filtered[[bool(m) for m in matches]]
        return filtered
    except Exception as e:
        logger.error(f"[GPT-4o] 필터링 오류: {e}")
        return reviews_df
