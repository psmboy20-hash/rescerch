"""
scrapers/base_scraper.py
모든 스크래퍼의 기반 클래스 - 공통 인터페이스 정의
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pandas as pd


@dataclass
class ProductMeta:
    """제품 메타데이터"""
    platform: str                        # 플랫폼 (29cm / wconcept / musinsa)
    product_id: str                      # 플랫폼 내 제품 ID
    url: str                             # 상품 URL
    name: str = ""                       # 제품명
    brand: str = ""                      # 브랜드명
    category: str = ""                   # 카테고리
    price: int = 0                       # 판매가 (원)
    manufacture_date: Optional[str] = None   # 제조년월 (YYYY-MM)
    first_review_date: Optional[str] = None  # 첫 리뷰 날짜
    review_count: int = 0                # 총 리뷰 수
    avg_rating: float = 0.0             # 평균 별점
    scraped_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    @property
    def market_response_days(self) -> Optional[int]:
        """제조년월 → 첫 리뷰까지 걸린 일수 (시장 반응 속도)"""
        if not self.manufacture_date or not self.first_review_date:
            return None
        try:
            mfg = datetime.strptime(self.manufacture_date + "-01", "%Y-%m-%d")
            rev = datetime.strptime(self.first_review_date, "%Y-%m-%d")
            return (rev - mfg).days
        except Exception:
            return None

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["market_response_days"] = self.market_response_days
        return d


@dataclass
class Review:
    """리뷰 단건 데이터"""
    product_id: str
    platform: str
    review_id: str
    date: str          # YYYY-MM-DD
    rating: float
    option: str        # 선택한 옵션 (사이즈/컬러 등)
    text: str
    helpful: int = 0   # 도움이 됐어요 수
    has_photo: bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class BaseScraper(ABC):
    """모든 플랫폼 스크래퍼의 추상 기반 클래스"""

    def __init__(self):
        self.platform = "unknown"

    @abstractmethod
    async def get_product_meta(self, url: str) -> ProductMeta:
        """상품 URL에서 메타데이터(제품명, 제조년월 등) 추출"""
        pass

    @abstractmethod
    async def get_all_reviews(self, product_meta: ProductMeta) -> list[Review]:
        """해당 제품의 전체 리뷰 수집 (페이지네이션 끝까지)"""
        pass

    @abstractmethod
    async def get_category_products(self, category_url: str, limit: int = 100) -> list[str]:
        """카테고리 URL에서 상위 N개 제품 URL 목록 반환"""
        pass

    async def scrape_full(self, url: str) -> tuple[ProductMeta, pd.DataFrame]:
        """제품 URL 하나로 메타 + 전체 리뷰를 한 번에 수집"""
        meta = await self.get_product_meta(url)
        reviews = await self.get_all_reviews(meta)
        df = pd.DataFrame([r.to_dict() for r in reviews])
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.sort_values("date")
            meta.first_review_date = df["date"].min().strftime("%Y-%m-%d") if not df.empty else None
        meta.review_count = len(reviews)
        if reviews:
            meta.avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 2)
        return meta, df
