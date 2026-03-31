"""
scrapers/bulk_scanner.py
벌크 스캐너 v2 - 병렬 처리로 속도 대폭 개선
- 제품 메타 수집: 동시 5개 병렬
- 리뷰 수집: httpx 비동기 + 배치 병렬
"""
import asyncio
import sys

# Windows 호환 설정
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from loguru import logger
import pandas as pd
from tqdm import tqdm

from scrapers.base_scraper import ProductMeta
from scrapers.scraper_29cm import Scraper29CM
from scrapers.scraper_wconcept import ScraperWConcept
from scrapers.scraper_musinsa import ScraperMusinsa
from utils.exporter import export_csv, export_excel


def get_scraper(platform: str):
    """플랫폼명으로 스크래퍼 인스턴스 반환"""
    scrapers = {
        "29cm": Scraper29CM,
        "wconcept": ScraperWConcept,
        "musinsa": ScraperMusinsa,
    }
    cls = scrapers.get(platform.lower())
    if not cls:
        raise ValueError(f"지원하지 않는 플랫폼: {platform}. 선택지: {list(scrapers.keys())}")
    return cls()


async def scrape_one(scraper, url: str, idx: int, total: int, semaphore: asyncio.Semaphore):
    """세마포어로 동시 실행 제한"""
    async with semaphore:
        try:
            logger.info(f"[{idx+1}/{total}] 분석: {url[-50:]}")
            meta, reviews_df = await scraper.scrape_full(url)
            return meta, reviews_df
        except Exception as e:
            logger.error(f"[{idx+1}/{total}] 오류: {url[-50:]} - {e}")
            return None, None


async def bulk_scan(
    category_url: str,
    platform: str,
    limit: int = 30,
    progress_callback=None,
    parallel: int = 3,  # 동시 처리 제품 수 (너무 높으면 차단됨)
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    카테고리 URL에서 상위 limit개 제품 일괄 분석
    parallel: 동시 처리 수 (기본 3 - 안전한 속도)
    """
    scraper = get_scraper(platform)
    logger.info(f"🔍 [{platform}] 카테고리 스캔: {category_url} (최대 {limit}개, 동시 {parallel}개)")

    # 1. 카테고리에서 제품 URL 수집
    product_urls = await scraper.get_category_products(category_url, limit=limit)
    logger.info(f"📋 수집된 제품 수: {len(product_urls)}")

    total = len(product_urls)
    meta_list = []
    all_reviews = []

    # 2. 세마포어로 병렬 처리
    semaphore = asyncio.Semaphore(parallel)
    tasks = [
        scrape_one(scraper, url, idx, total, semaphore)
        for idx, url in enumerate(product_urls)
    ]
    
    completed = 0
    for coro in asyncio.as_completed(tasks):
        meta, reviews_df = await coro
        completed += 1
        
        if progress_callback:
            progress_callback(completed, total, "처리 중...")
        
        if meta:
            meta_list.append(meta.to_dict())
        if reviews_df is not None and not reviews_df.empty:
            reviews_df["rank"] = completed
            all_reviews.append(reviews_df)

        logger.info(f"✅ 완료: {completed}/{total}")

    # 3. 통합 데이터프레임
    meta_df = pd.DataFrame(meta_list) if meta_list else pd.DataFrame()
    reviews_df = pd.concat(all_reviews, ignore_index=True) if all_reviews else pd.DataFrame()

    logger.success(f"✅ 벌크 완료: {len(meta_list)}개 제품, {len(reviews_df)}개 리뷰")
    return meta_df, reviews_df


def run_bulk_scan(category_url: str, platform: str, limit: int = 30, progress_callback=None):
    """동기 방식 (Streamlit)"""
    return asyncio.run(bulk_scan(category_url, platform, limit, progress_callback))


def run_single_scrape(url: str, platform: str):
    """단일 제품 동기 실행"""
    scraper = get_scraper(platform)
    return asyncio.run(scraper.scrape_full(url))
