"""
plugins/director_plugins.py
디렉터 커스텀 로직 플러그인 - Script Wrapping 시스템
언제든 새 플러그인을 추가/수정할 수 있는 모듈화 구조
"""
import pandas as pd
import re
from typing import Callable
from loguru import logger


# ════════════════════════════════════════════════════════════════
# 플러그인 레지스트리 - 여기에 새 플러그인을 등록하세요
# ════════════════════════════════════════════════════════════════
PLUGIN_REGISTRY: dict[str, dict] = {}


def register_plugin(name: str, description: str):
    """플러그인 등록 데코레이터"""
    def decorator(func: Callable):
        PLUGIN_REGISTRY[name] = {
            "func": func,
            "description": description,
            "name": name,
        }
        return func
    return decorator


# ════════════════════════════════════════════════════════════════
# 기본 내장 플러그인들
# ════════════════════════════════════════════════════════════════

@register_plugin(
    name="체형_불만_필터",
    description="특정 체형(키/몸무게/사이즈) 관련 불만 리뷰만 추출"
)
def filter_body_complaints(reviews_df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    체형 관련 불만 리뷰 필터
    kwargs: height_range=(160, 170), weight_range=(50, 60), size="M"
    """
    if reviews_df.empty:
        return reviews_df

    df = reviews_df.copy()
    # 부정적 키워드
    complaint_kw = ["크다", "작다", "길다", "짧다", "넓다", "좁다", "불편", "안맞", "빠진", "틀어"]
    # 체형 키워드
    body_kw = ["키", "cm", "몸무게", "kg", "어깨", "허리", "가슴", "힙", "허벅지"]

    mask_complaint = df["text"].str.contains("|".join(complaint_kw), case=False, na=False)
    mask_body = df["text"].str.contains("|".join(body_kw), case=False, na=False)

    # 키 범위 필터 (선택)
    height_range = kwargs.get("height_range")
    if height_range:
        h_pattern = "|".join([f"{h}cm|{h}CM" for h in range(*height_range)])
        mask_height = df["text"].str.contains(h_pattern, na=False)
        result = df[mask_complaint & (mask_body | mask_height)]
    else:
        result = df[mask_complaint & mask_body]

    logger.info(f"[체형_불만_필터] {len(result)}건 추출 / 전체 {len(df)}건")
    return result


@register_plugin(
    name="생산월_원단분석",
    description="특정 생산월의 원단/소재 관련 리뷰만 추출 및 분석"
)
def filter_by_production_month(reviews_df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    생산월 기준 이후 리뷰의 소재/원단 관련 피드백 추출
    kwargs: production_month="2024-03", fabric_change="컬러"
    """
    if reviews_df.empty:
        return reviews_df

    df = reviews_df.copy()
    production_month = kwargs.get("production_month", "")

    if production_month:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        cutoff = pd.to_datetime(production_month + "-01")
        df = df[df["date"] >= cutoff]

    # 소재/원단 키워드
    fabric_kw = ["원단", "소재", "패브릭", "느낌", "촉감", "두께", "비침", "늘어", "수축", "구김", "세탁", "컬러", "색상", "염색"]
    mask = df["text"].str.contains("|".join(fabric_kw), case=False, na=False)
    result = df[mask]

    logger.info(f"[생산월_원단분석] {production_month} 이후 원단 관련 {len(result)}건")
    return result


@register_plugin(
    name="사이즈_정확도_분석",
    description="사이즈 선택과 실제 핏의 일치 여부 통계 분석"
)
def analyze_size_accuracy(reviews_df: pd.DataFrame, **kwargs) -> dict:
    """
    사이즈 옵션별 핏 평가 분석
    Returns: {"accuracy_rate": float, "by_size": dict, "recommendations": list}
    """
    if reviews_df.empty:
        return {}

    df = reviews_df.copy()
    result = {"by_size": {}, "recommendations": []}

    # 사이즈 옵션 파싱
    size_pattern = r'\b(XS|S|M|L|XL|XXL|FREE|\d+)'
    df["parsed_size"] = df["option"].str.extract(size_pattern, expand=False)

    # 사이즈 일치 키워드
    correct_kw = ["딱맞", "잘맞", "사이즈대로", "정사이즈", "평소대로"]
    big_kw = ["크다", "커요", "크네요", "빅", "여유"]
    small_kw = ["작다", "작아요", "작네요", "끼다", "타이트"]

    for size in df["parsed_size"].dropna().unique():
        sub = df[df["parsed_size"] == size]
        correct = sub["text"].str.contains("|".join(correct_kw), na=False).sum()
        big = sub["text"].str.contains("|".join(big_kw), na=False).sum()
        small = sub["text"].str.contains("|".join(small_kw), na=False).sum()
        total = len(sub)

        result["by_size"][size] = {
            "total": total,
            "correct_fit": int(correct),
            "runs_big": int(big),
            "runs_small": int(small),
            "accuracy_pct": round(correct / total * 100, 1) if total > 0 else 0,
        }

    # 추천사항 생성
    for size, stats in result["by_size"].items():
        if stats["runs_big"] > stats["runs_small"] and stats["runs_big"] > stats["total"] * 0.3:
            result["recommendations"].append(f"사이즈 {size}: 크게 나오는 편 → 한 사이즈 아래 권장")
        elif stats["runs_small"] > stats["runs_big"] and stats["runs_small"] > stats["total"] * 0.3:
            result["recommendations"].append(f"사이즈 {size}: 작게 나오는 편 → 한 사이즈 위 권장")

    return result


@register_plugin(
    name="시즌_트렌드_감지",
    description="월별 리뷰에서 시즌별 키워드 트렌드를 감지"
)
def detect_seasonal_trends(reviews_df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    계절별 언급 키워드 분석
    """
    if reviews_df.empty:
        return pd.DataFrame()

    season_keywords = {
        "봄": ["봄", "봄날", "데이트", "나들이", "화사", "파스텔"],
        "여름": ["여름", "시원", "더위", "민소매", "린넨", "비치"],
        "가을": ["가을", "데일리", "레이어드", "니트", "캐시미어"],
        "겨울": ["겨울", "따뜻", "보온", "패딩", "울", "기모"],
    }

    df = reviews_df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = df["date"].dt.month

    records = []
    for season, kws in season_keywords.items():
        mask = df["text"].str.contains("|".join(kws), case=False, na=False)
        monthly = df[mask].groupby("month").size().reset_index(name="count")
        monthly["season"] = season
        records.append(monthly)

    result = pd.concat(records) if records else pd.DataFrame()
    return result


# ════════════════════════════════════════════════════════════════
# 플러그인 실행기
# ════════════════════════════════════════════════════════════════

def run_plugin(plugin_name: str, reviews_df: pd.DataFrame, **kwargs):
    """플러그인 이름으로 실행"""
    if plugin_name not in PLUGIN_REGISTRY:
        raise ValueError(f"플러그인 없음: {plugin_name}. 사용 가능: {list(PLUGIN_REGISTRY.keys())}")
    plugin = PLUGIN_REGISTRY[plugin_name]
    logger.info(f"▶ 플러그인 실행: {plugin_name}")
    return plugin["func"](reviews_df, **kwargs)


def list_plugins() -> list[dict]:
    """등록된 플러그인 목록 반환"""
    return [{"name": v["name"], "description": v["description"]} for v in PLUGIN_REGISTRY.values()]


# ════════════════════════════════════════════════════════════════
# 커스텀 플러그인 동적 추가 (디렉터가 런타임에 코드 입력)
# ════════════════════════════════════════════════════════════════

def add_custom_plugin(name: str, description: str, code: str) -> bool:
    """
    Streamlit UI에서 디렉터가 직접 Python 코드를 입력하여 플러그인 추가
    code: 'def run(reviews_df, **kwargs): ...' 형식의 함수 코드
    """
    try:
        namespace = {}
        exec(code, namespace)
        if "run" not in namespace:
            raise ValueError("함수명은 반드시 'run'이어야 합니다")
        PLUGIN_REGISTRY[name] = {
            "func": namespace["run"],
            "description": description,
            "name": name,
        }
        logger.success(f"✅ 커스텀 플러그인 등록: {name}")
        return True
    except Exception as e:
        logger.error(f"❌ 플러그인 등록 실패: {e}")
        return False
