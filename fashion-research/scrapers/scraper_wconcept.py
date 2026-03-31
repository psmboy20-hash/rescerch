"""
scrapers/scraper_wconcept.py
W컨셉 전용 스크래퍼 - 전체 리뷰 수집 + 제조년월 추출
"""
import asyncio
import re
import json
from loguru import logger
from playwright.async_api import async_playwright

from scrapers.base_scraper import BaseScraper, ProductMeta, Review
from utils.browser import create_browser_context, safe_get, random_delay, scroll_to_bottom


class ScraperWConcept(BaseScraper):

    def __init__(self):
        super().__init__()
        self.platform = "wconcept"
        self.base_url = "https://www.wconcept.co.kr"

    # ── 제품 메타데이터 ─────────────────────────────────────────
    async def get_product_meta(self, url: str) -> ProductMeta:
        product_id = self._extract_product_id(url)
        meta = ProductMeta(platform=self.platform, product_id=product_id, url=url)

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                ok = await safe_get(page, url, wait_selector=".product-info, .pdp-info", timeout=30000)
                if not ok:
                    return meta

                # 제품명
                try:
                    meta.name = await page.inner_text(".product-name, h1.pdp-name", timeout=5000)
                    meta.name = meta.name.strip()
                except Exception:
                    pass

                # 브랜드명
                try:
                    meta.brand = await page.inner_text(".brand-name a, .designer-name", timeout=5000)
                    meta.brand = meta.brand.strip()
                except Exception:
                    pass

                # 가격
                try:
                    price_text = await page.inner_text(".sale-price, .price-sale", timeout=5000)
                    meta.price = int(re.sub(r"[^\d]", "", price_text))
                except Exception:
                    pass

                # 제조년월 - 상세 정보 탭 클릭 후 추출
                meta.manufacture_date = await self._extract_manufacture_date(page)
                logger.info(f"[W컨셉] 제품명: {meta.name} | 제조년월: {meta.manufacture_date}")

            finally:
                await browser.close()

        return meta

    async def _extract_manufacture_date(self, page) -> str | None:
        """W컨셉 상세 정보 탭에서 제조년월 추출"""
        # 상세 정보 탭 클릭 시도
        try:
            detail_tab = await page.query_selector("[data-tab='detail'], .tab-detail, button:has-text('상세정보')")
            if detail_tab:
                await detail_tab.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        patterns = [
            r'제조년월[^\d]*(\d{4}[-./년]\s*\d{1,2})',
            r'제조일자[^\d]*(\d{4}[-./년]\s*\d{1,2})',
            r'Manufacture[^\d]*(\d{4}[-./]\d{1,2})',
            r'(\d{4})\s*년\s*(\d{1,2})\s*월',
            r'(\d{4})[./](\d{2})\s*(제조|생산|만든)',
        ]
        try:
            full_text = await page.inner_text("body")
            for pattern in patterns:
                match = re.search(pattern, full_text)
                if match:
                    raw = match.group(1) if len(match.groups()) == 1 else f"{match.group(1)}-{match.group(2)}"
                    normalized = re.sub(r'[년./\s]+', '-', raw).strip('-')
                    parts = normalized.split('-')
                    if len(parts) >= 2:
                        return f"{parts[0]}-{parts[1].zfill(2)}"
        except Exception as e:
            logger.warning(f"[W컨셉] 제조년월 추출 오류: {e}")
        return None

    # ── 전체 리뷰 수집 ─────────────────────────────────────────
    async def get_all_reviews(self, product_meta: ProductMeta) -> list[Review]:
        reviews = []

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                # W컨셉 리뷰 탭 이동
                review_url = f"{product_meta.url}#review"
                await safe_get(page, review_url, timeout=30000)

                # 리뷰 탭 클릭
                try:
                    review_tab = await page.query_selector("button:has-text('리뷰'), [data-tab='review']")
                    if review_tab:
                        await review_tab.click()
                        await asyncio.sleep(1.5)
                except Exception:
                    pass

                page_num = 1
                while True:
                    # 리뷰 아이템 수집
                    items = await page.query_selector_all(".review-item, .product-review-item, li.review_list")
                    if not items:
                        logger.info(f"[W컨셉] 리뷰 수집 완료 - 총 {len(reviews)}건")
                        break

                    for item in items:
                        review = await self._parse_review_item(item, product_meta)
                        if review and not any(r.review_id == review.review_id for r in reviews):
                            reviews.append(review)

                    logger.info(f"[W컨셉] 페이지 {page_num} - 누적 {len(reviews)}건")

                    # 다음 페이지 버튼
                    next_btn = await page.query_selector(".next-page:not(.disabled), button.btn-next:not([disabled])")
                    if not next_btn:
                        break
                    await next_btn.click()
                    page_num += 1
                    await random_delay()

                    if page_num > int(__import__('os').getenv("MAX_PAGES", "999")):
                        break

            finally:
                await browser.close()

        return reviews

    async def _parse_review_item(self, item, meta: ProductMeta) -> Review | None:
        try:
            date_el = await item.query_selector(".review-date, .date, .write-date")
            date_text = (await date_el.inner_text()).strip() if date_el else ""
            date = self._normalize_date(date_text)

            rating_el = await item.query_selector(".star-rating, [class*='rating']")
            rating_text = await rating_el.get_attribute("data-score") if rating_el else ""
            if not rating_text:
                # 별 아이콘 카운트로 별점 계산
                filled = await item.query_selector_all(".star-fill, .ico-star-on")
                rating_text = str(len(filled))
            try:
                rating = float(rating_text)
            except Exception:
                rating = 0.0

            option_el = await item.query_selector(".review-option, .option-label, .size-info")
            option = (await option_el.inner_text()).strip() if option_el else ""

            text_el = await item.query_selector(".review-text, .review-content, .review-body")
            text = (await text_el.inner_text()).strip() if text_el else ""

            review_id = await item.get_attribute("data-id") or f"{meta.product_id}_{date}_{hash(text) % 99999}"

            photo_el = await item.query_selector("img.review-photo, .review-img-wrap img")
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
            logger.debug(f"[W컨셉] 리뷰 파싱 오류: {e}")
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
        match = re.search(r'/product/(\d+)', url)
        if match:
            return match.group(1)
        match = re.search(r'goodsNo=(\d+)', url)
        return match.group(1) if match else url.split("/")[-1].split("?")[0]

    # ── 카테고리 벌크 스캔 ─────────────────────────────────────
    async def get_category_products(self, category_url: str, limit: int = 100) -> list[str]:
        product_urls = []

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                await safe_get(page, category_url, timeout=30000)

                while len(product_urls) < limit:
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

                    # 더 보기 버튼
                    more_btn = await page.query_selector(".btn-more, button:has-text('더보기')")
                    if not more_btn or len(product_urls) >= limit:
                        break
                    await more_btn.click()
                    await random_delay()

                logger.info(f"[W컨셉] 카테고리 수집: {len(product_urls)}개")
            finally:
                await browser.close()

        return product_urls
