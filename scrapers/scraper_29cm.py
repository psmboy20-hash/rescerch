"""
scrapers/scraper_29cm.py
29CM 전용 스크래퍼 - 전체 리뷰 수집 + 제조년월 추출
"""
import asyncio
import re
from loguru import logger
from playwright.async_api import async_playwright

from scrapers.base_scraper import BaseScraper, ProductMeta, Review
from utils.browser import create_browser_context, safe_get, random_delay, scroll_to_bottom


class Scraper29CM(BaseScraper):

    def __init__(self):
        super().__init__()
        self.platform = "29cm"
        self.base_url = "https://www.29cm.co.kr"

    # ── 제품 메타데이터 ─────────────────────────────────────────
    async def get_product_meta(self, url: str) -> ProductMeta:
        product_id = self._extract_product_id(url)
        meta = ProductMeta(platform=self.platform, product_id=product_id, url=url)

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                ok = await safe_get(page, url, wait_selector=".product_detail_info", timeout=30000)
                if not ok:
                    logger.error(f"[29CM] 페이지 로드 실패: {url}")
                    return meta

                # 제품명
                try:
                    meta.name = await page.inner_text("h1.product_name, .pdp_title", timeout=5000)
                    meta.name = meta.name.strip()
                except Exception:
                    pass

                # 브랜드명
                try:
                    meta.brand = await page.inner_text(".brand_name a, .pdp_brand", timeout=5000)
                    meta.brand = meta.brand.strip()
                except Exception:
                    pass

                # 가격
                try:
                    price_text = await page.inner_text(".final_price, .price_sale", timeout=5000)
                    meta.price = int(re.sub(r"[^\d]", "", price_text))
                except Exception:
                    pass

                # 제조년월 추출 (상세페이지 텍스트 전수 탐색)
                meta.manufacture_date = await self._extract_manufacture_date(page)
                logger.info(f"[29CM] 제품명: {meta.name} | 제조년월: {meta.manufacture_date}")

            finally:
                await browser.close()

        return meta

    async def _extract_manufacture_date(self, page) -> str | None:
        """
        상세페이지 내 제조년월 추출
        패턴: '제조년월', '제조일자', '생산일', 'Made in', 날짜 형식 등
        """
        patterns = [
            r'제조년월[^\d]*(\d{4}[-./년]\s*\d{1,2})',
            r'제조일자[^\d]*(\d{4}[-./년]\s*\d{1,2})',
            r'생산일[^\d]*(\d{4}[-./년]\s*\d{1,2})',
            r'제조\s*:\s*(\d{4}[-./년]\s*\d{1,2})',
            r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(제조|생산)',
        ]
        try:
            # 상세 정보 영역 텍스트 전체 추출
            full_text = await page.inner_text("body")
            for pattern in patterns:
                match = re.search(pattern, full_text)
                if match:
                    raw = match.group(1) if len(match.groups()) == 1 else f"{match.group(1)}-{match.group(2)}"
                    # 정규화: YYYY-MM 형식으로
                    normalized = re.sub(r'[년./\s]+', '-', raw).strip('-')
                    parts = normalized.split('-')
                    if len(parts) >= 2:
                        return f"{parts[0]}-{parts[1].zfill(2)}"
        except Exception as e:
            logger.warning(f"[29CM] 제조년월 추출 오류: {e}")
        return None

    # ── 전체 리뷰 수집 ─────────────────────────────────────────
    async def get_all_reviews(self, product_meta: ProductMeta) -> list[Review]:
        reviews = []
        page_num = 1

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                while True:
                    review_url = (
                        f"{self.base_url}/product/detail/{product_meta.product_id}"
                        f"?tab=review&page={page_num}&sort=latest"
                    )
                    ok = await safe_get(page, review_url, timeout=20000)
                    if not ok:
                        break

                    items = await page.query_selector_all(".review_item, .pdp_review_item")
                    if not items:
                        logger.info(f"[29CM] 리뷰 수집 완료 - 총 {len(reviews)}건 (페이지 {page_num-1})")
                        break

                    for item in items:
                        review = await self._parse_review_item(item, product_meta)
                        if review:
                            reviews.append(review)

                    logger.info(f"[29CM] 페이지 {page_num} - 누적 {len(reviews)}건")
                    page_num += 1
                    await random_delay()

                    # 최대 페이지 초과 방지
                    if page_num > int(__import__('os').getenv("MAX_PAGES", "999")):
                        break

            finally:
                await browser.close()

        return reviews

    async def _parse_review_item(self, item, meta: ProductMeta) -> Review | None:
        try:
            # 날짜
            date_el = await item.query_selector(".review_date, .date")
            date_text = (await date_el.inner_text()).strip() if date_el else ""
            date = self._normalize_date(date_text)

            # 별점
            rating_el = await item.query_selector(".review_star, [class*='star']")
            rating_text = await rating_el.get_attribute("data-score") if rating_el else "0"
            try:
                rating = float(rating_text or "0")
            except Exception:
                rating = 0.0

            # 옵션
            option_el = await item.query_selector(".review_option, .option_info")
            option = (await option_el.inner_text()).strip() if option_el else ""

            # 텍스트
            text_el = await item.query_selector(".review_content, .review_text")
            text = (await text_el.inner_text()).strip() if text_el else ""

            # 리뷰 ID (URL 또는 data-id)
            review_id = await item.get_attribute("data-review-id") or f"{meta.product_id}_{date}_{hash(text) % 99999}"

            # 포토 여부
            photo_el = await item.query_selector(".review_photo, img.review_img")
            has_photo = photo_el is not None

            return Review(
                product_id=meta.product_id,
                platform=self.platform,
                review_id=str(review_id),
                date=date,
                rating=rating,
                option=option,
                text=text,
                has_photo=has_photo,
            )
        except Exception as e:
            logger.debug(f"[29CM] 리뷰 파싱 오류: {e}")
            return None

    def _normalize_date(self, raw: str) -> str:
        """날짜 문자열을 YYYY-MM-DD 형식으로 정규화"""
        raw = raw.strip()
        # 2024.05.12 / 2024-05-12 / 24.05.12
        match = re.search(r'(\d{2,4})[.\-/](\d{1,2})[.\-/](\d{1,2})', raw)
        if match:
            y, m, d = match.groups()
            if len(y) == 2:
                y = "20" + y
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        return raw

    def _extract_product_id(self, url: str) -> str:
        match = re.search(r'/product/(?:detail/)?(\d+)', url)
        return match.group(1) if match else url.split("/")[-1].split("?")[0]

    # ── 카테고리 벌크 스캔 ─────────────────────────────────────
    async def get_category_products(self, category_url: str, limit: int = 100) -> list[str]:
        product_urls = []

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                await safe_get(page, category_url, wait_selector=".product_list", timeout=30000)

                # 무한 스크롤 처리
                loaded = 0
                while loaded < limit:
                    await scroll_to_bottom(page)
                    links = await page.query_selector_all("a[href*='/product/']")
                    urls = []
                    for link in links:
                        href = await link.get_attribute("href")
                        if href and "/product/" in href:
                            full = href if href.startswith("http") else self.base_url + href
                            if full not in urls:
                                urls.append(full)
                    product_urls = list(dict.fromkeys(urls))[:limit]
                    if len(product_urls) >= limit:
                        break
                    loaded = len(product_urls)
                    await random_delay()

                logger.info(f"[29CM] 카테고리 수집 완료: {len(product_urls)}개 제품")
            finally:
                await browser.close()

        return product_urls
