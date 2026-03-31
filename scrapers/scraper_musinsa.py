"""
scrapers/scraper_musinsa.py
무신사 전용 스크래퍼 - 전체 리뷰 수집 + 제조년월 추출
"""
import asyncio
import re
import json
from loguru import logger
from playwright.async_api import async_playwright

from scrapers.base_scraper import BaseScraper, ProductMeta, Review
from utils.browser import create_browser_context, safe_get, random_delay, scroll_to_bottom


class ScraperMusinsa(BaseScraper):

    def __init__(self):
        super().__init__()
        self.platform = "musinsa"
        self.base_url = "https://www.musinsa.com"
        self.review_api = "https://goods-detail.musinsa.com/api2/goods/{product_id}/reviews"

    # ── 제품 메타데이터 ─────────────────────────────────────────
    async def get_product_meta(self, url: str) -> ProductMeta:
        product_id = self._extract_product_id(url)
        meta = ProductMeta(platform=self.platform, product_id=product_id, url=url)

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                ok = await safe_get(page, url, wait_selector=".product_article, #product_order_info", timeout=30000)
                if not ok:
                    return meta

                # 제품명
                try:
                    meta.name = await page.inner_text(".product_article_contents h1, .product-title", timeout=5000)
                    meta.name = meta.name.strip()
                except Exception:
                    pass

                # 브랜드명
                try:
                    meta.brand = await page.inner_text(".brand_info strong, .product-brand", timeout=5000)
                    meta.brand = meta.brand.strip()
                except Exception:
                    pass

                # 가격
                try:
                    price_text = await page.inner_text(".price-info .sale, .discount-price", timeout=5000)
                    meta.price = int(re.sub(r"[^\d]", "", price_text))
                except Exception:
                    pass

                # 제조년월 추출
                meta.manufacture_date = await self._extract_manufacture_date(page)
                logger.info(f"[무신사] 제품명: {meta.name} | 제조년월: {meta.manufacture_date}")

            finally:
                await browser.close()

        return meta

    async def _extract_manufacture_date(self, page) -> str | None:
        """무신사 상품 정보 및 상세페이지에서 제조년월 추출"""
        patterns = [
            r'제조년월[^\d]*(\d{4}[-./년]\s*\d{1,2})',
            r'제조일자[^\d]*(\d{4}[-./년]\s*\d{1,2})',
            r'제조\s*:\s*(\d{4}[-./년]\s*\d{1,2})',
            r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(제조|생산)',
            r'manufactured[^\d]*(\d{4}[-./]\d{1,2})',
        ]
        try:
            # 기본정보 탭 클릭
            try:
                info_tab = await page.query_selector("li:has-text('기본정보'), .tab_btn:has-text('기본정보')")
                if info_tab:
                    await info_tab.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            full_text = await page.inner_text("body")
            for pattern in patterns:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    raw = match.group(1) if len(match.groups()) == 1 else f"{match.group(1)}-{match.group(2)}"
                    normalized = re.sub(r'[년./\s]+', '-', raw).strip('-')
                    parts = normalized.split('-')
                    if len(parts) >= 2:
                        return f"{parts[0]}-{parts[1].zfill(2)}"
        except Exception as e:
            logger.warning(f"[무신사] 제조년월 추출 오류: {e}")
        return None

    # ── 전체 리뷰 수집 ─────────────────────────────────────────
    async def get_all_reviews(self, product_meta: ProductMeta) -> list[Review]:
        """
        무신사 리뷰 수집 - 웹 스크래핑 + API 하이브리드 방식
        """
        reviews = []
        page_num = 1
        page_size = 20

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                while True:
                    # 무신사는 리뷰 탭 URL 파라미터 방식 사용
                    review_url = (
                        f"{self.base_url}/app/goods/{product_meta.product_id}"
                        f"?section=review&page={page_num}&_isTab=true"
                    )
                    ok = await safe_get(page, review_url, timeout=20000)
                    if not ok:
                        break

                    items = await page.query_selector_all(
                        ".review-list-item, .review_item, [class*='review_list'] li"
                    )
                    if not items:
                        logger.info(f"[무신사] 리뷰 수집 완료 - 총 {len(reviews)}건 (페이지 {page_num-1})")
                        break

                    for item in items:
                        review = await self._parse_review_item(item, product_meta)
                        if review and not any(r.review_id == review.review_id for r in reviews):
                            reviews.append(review)

                    logger.info(f"[무신사] 페이지 {page_num} - 누적 {len(reviews)}건")
                    page_num += 1
                    await random_delay()

                    if page_num > int(__import__('os').getenv("MAX_PAGES", "999")):
                        break

            finally:
                await browser.close()

        return reviews

    async def _parse_review_item(self, item, meta: ProductMeta) -> Review | None:
        try:
            date_el = await item.query_selector(".review-info-date, .date, time")
            date_text = (await date_el.inner_text()).strip() if date_el else ""
            if not date_text:
                date_attr = await item.query_selector("time")
                if date_attr:
                    date_text = await date_attr.get_attribute("datetime") or ""
            date = self._normalize_date(date_text)

            # 별점
            rating_el = await item.query_selector("[class*='rating'], .star_score, .review-grade")
            rating = 0.0
            if rating_el:
                rating_text = await rating_el.get_attribute("data-score") or await rating_el.inner_text()
                try:
                    rating = float(re.search(r'\d+\.?\d*', rating_text).group())
                except Exception:
                    filled = await item.query_selector_all(".ico-star-filled, .review-star-on")
                    rating = float(len(filled))

            # 옵션
            option_el = await item.query_selector(".review-info-goods-option, .goods_option")
            option = (await option_el.inner_text()).strip() if option_el else ""

            # 텍스트
            text_el = await item.query_selector(".review-content p, .review_txt, .review-text-area")
            text = (await text_el.inner_text()).strip() if text_el else ""

            # ID
            review_id = await item.get_attribute("data-review-id") or f"{meta.product_id}_{date}_{hash(text) % 99999}"

            # 사진
            photo_el = await item.query_selector("img.review-photo-img, .review_imgs img")
            has_photo = photo_el is not None

            # 도움됐어요
            helpful_el = await item.query_selector(".review-like-count, .helpful_count")
            helpful = 0
            if helpful_el:
                try:
                    helpful = int(re.sub(r"[^\d]", "", await helpful_el.inner_text()))
                except Exception:
                    pass

            return Review(
                product_id=meta.product_id,
                platform=self.platform,
                review_id=str(review_id),
                date=date,
                rating=rating,
                option=option,
                text=text,
                has_photo=has_photo,
                helpful=helpful,
            )
        except Exception as e:
            logger.debug(f"[무신사] 리뷰 파싱 오류: {e}")
            return None

    def _normalize_date(self, raw: str) -> str:
        raw = raw.strip()
        match = re.search(r'(\d{2,4})[.\-/](\d{1,2})[.\-/](\d{1,2})', raw)
        if match:
            y, m, d = match.groups()
            if len(y) == 2:
                y = "20" + y
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        return raw

    def _extract_product_id(self, url: str) -> str:
        match = re.search(r'/goods/(\d+)', url)
        if match:
            return match.group(1)
        match = re.search(r'/app/goods/(\d+)', url)
        return match.group(1) if match else url.split("/")[-1].split("?")[0]

    # ── 카테고리 벌크 스캔 ─────────────────────────────────────
    async def get_category_products(self, category_url: str, limit: int = 100) -> list[str]:
        product_urls = []

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                page_num = 1
                while len(product_urls) < limit:
                    paginated_url = f"{category_url}&page={page_num}" if "?" in category_url else f"{category_url}?page={page_num}"
                    ok = await safe_get(page, paginated_url, timeout=30000)
                    if not ok:
                        break

                    await scroll_to_bottom(page)
                    links = await page.query_selector_all("a[href*='/goods/']")
                    if not links:
                        break

                    for link in links:
                        href = await link.get_attribute("href")
                        if href and "/goods/" in href and "review" not in href:
                            full = href if href.startswith("http") else self.base_url + href
                            if full not in product_urls:
                                product_urls.append(full)
                    product_urls = product_urls[:limit]
                    page_num += 1
                    await random_delay()

                logger.info(f"[무신사] 카테고리 수집: {len(product_urls)}개")
            finally:
                await browser.close()

        return product_urls
