"""
scrapers/scraper_musinsa.py
무신사 스크래퍼 v2 - httpx API 우선 + Playwright fallback
- 리뷰: 내부 API 직접 호출 (Playwright 없이 → 빠름)
- 제품명/브랜드: 상품 API 또는 웹페이지 파싱
"""
import asyncio
import re
import json
import httpx
from loguru import logger
from playwright.async_api import async_playwright

from scrapers.base_scraper import BaseScraper, ProductMeta, Review
from utils.browser import create_browser_context, safe_get, random_delay, scroll_to_bottom

# 무신사 API 엔드포인트 후보
REVIEW_API_TEMPLATES = [
    "https://goods-detail.musinsa.com/api2/goods/{pid}/reviews?page={page}&size=20&sort=new",
    "https://api.musinsa.com/api/goods/{pid}/reviews?page={page}&size=20",
    "https://www.musinsa.com/api2/goods/{pid}/reviews?page={page}&limit=20",
]

PRODUCT_API_TEMPLATES = [
    "https://goods-detail.musinsa.com/api2/goods/{pid}",
    "https://api.musinsa.com/api/goods/{pid}",
    "https://www.musinsa.com/api/goods/{pid}",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.musinsa.com/",
    "Origin": "https://www.musinsa.com",
}


class ScraperMusinsa(BaseScraper):

    def __init__(self):
        super().__init__()
        self.platform = "musinsa"
        self.base_url = "https://www.musinsa.com"

    # ── 제품 메타데이터 ─────────────────────────────────────────
    async def get_product_meta(self, url: str) -> ProductMeta:
        product_id = self._extract_product_id(url)
        meta = ProductMeta(platform=self.platform, product_id=product_id, url=url)

        # 1. API 직접 시도
        await self._fetch_meta_api(meta)
        
        # 2. API 실패 시 httpx 웹 파싱
        if not meta.name:
            await self._fetch_meta_web(meta)

        # 3. 마지막 수단: Playwright
        if not meta.name:
            await self._fetch_meta_playwright(meta)

        logger.info(f"[무신사] {meta.name or '(미확인)'} | 브랜드: {meta.brand} | 제조년월: {meta.manufacture_date}")
        return meta

    async def _fetch_meta_api(self, meta: ProductMeta) -> bool:
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            for tmpl in PRODUCT_API_TEMPLATES:
                try:
                    resp = await client.get(tmpl.format(pid=meta.product_id))
                    if resp.status_code == 200:
                        data = resp.json()
                        item = data.get("data") or data.get("item") or data.get("product") or data
                        if isinstance(item, dict):
                            meta.name = (item.get("goodsName") or item.get("name") or item.get("goods_name") or "").strip()
                            meta.brand = (item.get("brandName") or item.get("brand") or item.get("brand_name") or "").strip()
                            try:
                                meta.price = int(str(item.get("salePrice") or item.get("price") or 0).replace(",", ""))
                            except Exception:
                                pass
                            if meta.name:
                                return True
                except Exception as e:
                    logger.debug(f"[무신사 API] {tmpl}: {e}")
        return False

    async def _fetch_meta_web(self, meta: ProductMeta) -> bool:
        url = f"{self.base_url}/app/goods/{meta.product_id}"
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return False
                html = resp.text
                
                # JSON-LD
                ld_match = re.search(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
                if ld_match:
                    try:
                        ld = json.loads(ld_match.group(1))
                        meta.name = ld.get("name", "").strip()
                        brand_info = ld.get("brand", {})
                        if isinstance(brand_info, dict):
                            meta.brand = brand_info.get("name", "").strip()
                        if meta.name:
                            meta.manufacture_date = self._extract_mfg_from_text(html)
                            return True
                    except Exception:
                        pass
                
                # og:title
                m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
                if m:
                    meta.name = m.group(1).strip()
                meta.manufacture_date = self._extract_mfg_from_text(html)
                return bool(meta.name)
        except Exception as e:
            logger.debug(f"[무신사 Web] {e}")
        return False

    async def _fetch_meta_playwright(self, meta: ProductMeta):
        url = f"{self.base_url}/app/goods/{meta.product_id}"
        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # 제품명
                for sel in ['.product_article_contents h1', '.product-title', 'h1', 'h2']:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            txt = (await el.inner_text()).strip()
                            if txt and len(txt) > 3:
                                meta.name = txt
                                break
                    except Exception:
                        continue

                # 브랜드
                for sel in ['.brand_info strong', '.product-brand', 'a[href*="brand"]']:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            meta.brand = (await el.inner_text()).strip()
                            break
                    except Exception:
                        continue

                # 제조년월
                body_text = await page.inner_text("body")
                meta.manufacture_date = self._extract_mfg_from_text(body_text)

            except Exception as e:
                logger.error(f"[무신사 Playwright] {e}")
            finally:
                await browser.close()

    def _extract_mfg_from_text(self, text: str) -> str | None:
        patterns = [
            r'제조년월[^\d]*(\d{4})[-./년\s]*(\d{1,2})',
            r'제조일자[^\d]*(\d{4})[-./년\s]*(\d{1,2})',
            r'제조\s*:\s*(\d{4})[-./년\s]*(\d{1,2})',
            r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(?:제조|생산)',
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return f"{m.group(1)}-{m.group(2).zfill(2)}"
        return None

    # ── 전체 리뷰 수집 (API 우선) ──────────────────────────────
    async def get_all_reviews(self, product_meta: ProductMeta) -> list[Review]:
        # 작동하는 API 탐색
        working_tmpl, first_data = await self._find_review_api(product_meta.product_id)

        if working_tmpl and first_data:
            return await self._collect_reviews_api(working_tmpl, first_data, product_meta)
        
        logger.warning(f"[무신사] API 없음 → Playwright fallback")
        return await self._collect_reviews_playwright(product_meta)

    async def _find_review_api(self, product_id: str) -> tuple[str | None, dict | None]:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            for tmpl in REVIEW_API_TEMPLATES:
                try:
                    url = tmpl.format(pid=product_id, page=1)
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        items = self._extract_items(data)
                        if items is not None:
                            return tmpl, data
                except Exception as e:
                    logger.debug(f"[무신사 API] {tmpl}: {e}")
        return None, None

    async def _collect_reviews_api(self, tmpl: str, first_data: dict, meta: ProductMeta) -> list[Review]:
        reviews = self._parse_reviews(first_data, meta)
        total = (
            first_data.get('totalCount') or first_data.get('total_count') or
            (first_data.get('data') or {}).get('totalCount') or 0
        )
        total_pages = min((int(total) // 20) + 2, 300)

        logger.info(f"[무신사] 총 {total}건 → {total_pages}페이지 수집")

        batch_size = 10
        for start in range(2, total_pages + 1, batch_size):
            batch = range(start, min(start + batch_size, total_pages + 1))
            tasks = [self._fetch_page(tmpl, meta.product_id, p) for p in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            before = len(reviews)
            for result in results:
                if isinstance(result, dict):
                    reviews += self._parse_reviews(result, meta)
            
            if len(reviews) == before:
                break
            logger.info(f"[무신사] 누적 {len(reviews)}건")
            await asyncio.sleep(0.2)

        return reviews

    async def _fetch_page(self, tmpl: str, product_id: str, page: int) -> dict | None:
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
                url = tmpl.format(pid=product_id, page=page)
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return None

    def _extract_items(self, data: dict) -> list | None:
        if not isinstance(data, dict):
            return None
        for key in ['list', 'reviews', 'items', 'data']:
            v = data.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for subkey in ['list', 'reviews', 'items']:
                    sv = v.get(subkey)
                    if isinstance(sv, list):
                        return sv
        return None

    def _parse_reviews(self, data: dict, meta: ProductMeta) -> list[Review]:
        reviews = []
        items = self._extract_items(data) or []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                date_raw = (
                    item.get('regDate') or item.get('created_at') or
                    item.get('writeDate') or item.get('reg_date') or ''
                )
                date = self._normalize_date(str(date_raw))
                if not date:
                    continue
                rating = float(item.get('starPoint') or item.get('rating') or item.get('star') or 0)
                option = str(item.get('goodsOption') or item.get('option') or item.get('goods_option') or '')
                text = str(item.get('contents') or item.get('content') or item.get('review') or '').strip()
                if not text:
                    continue
                review_id = str(item.get('id') or item.get('reviewId') or item.get('review_id') or f"{meta.product_id}_{hash(text) % 99999}")
                reviews.append(Review(
                    product_id=meta.product_id, platform=self.platform,
                    review_id=review_id, date=date, rating=rating,
                    option=option, text=text,
                    has_photo=bool(item.get('imageList') or item.get('photos')),
                    helpful=int(item.get('likeCount') or item.get('helpful') or 0),
                ))
            except Exception as e:
                logger.debug(f"[무신사] 리뷰 파싱: {e}")
        return reviews

    async def _collect_reviews_playwright(self, product_meta: ProductMeta) -> list[Review]:
        reviews = []
        found_api = []

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()

            async def intercept(response):
                try:
                    if 'review' in response.url.lower() and response.status == 200:
                        if 'json' in response.headers.get('content-type', ''):
                            data = await response.json()
                            items = self._extract_items(data)
                            if items:
                                found_api.append((response.url, data))
                except Exception:
                    pass
            page.on("response", intercept)

            try:
                url = f"{self.base_url}/app/goods/{product_meta.product_id}"
                await safe_get(page, url, timeout=30000)
                await asyncio.sleep(2)

                # 리뷰 탭 클릭
                for sel in ['li:has-text("리뷰")', '.tab_btn:has-text("리뷰")', 'a:has-text("리뷰 (")']:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            await el.click()
                            await asyncio.sleep(2)
                            break
                    except Exception:
                        continue

                # 인터셉트된 API 활용
                if found_api:
                    api_url, first_data = found_api[0]
                    reviews += self._parse_reviews(first_data, product_meta)
                    tmpl = re.sub(r'page=\d+', 'page={page}', api_url)
                    for page_num in range(2, 200):
                        data = await self._fetch_page(tmpl, product_meta.product_id, page_num)
                        if not data:
                            break
                        new = self._parse_reviews(data, product_meta)
                        if not new:
                            break
                        reviews += new
                        logger.info(f"[무신사] 페이지 {page_num}: 누적 {len(reviews)}건")
                        await asyncio.sleep(0.2)
                    return reviews

                # DOM 직접 파싱
                items = await page.query_selector_all('.review-list-item, .review_item, [class*="review_list"] li')
                for item in items:
                    review = await self._parse_dom_review(item, product_meta)
                    if review:
                        reviews.append(review)

            except Exception as e:
                logger.error(f"[무신사 Playwright] {e}")
            finally:
                await browser.close()
        return reviews

    async def _parse_dom_review(self, item, meta: ProductMeta) -> Review | None:
        try:
            txt = (await item.inner_text()).strip()
            date_match = re.search(r'(20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2})', txt)
            if not date_match:
                return None
            return Review(
                product_id=meta.product_id, platform=self.platform,
                review_id=f"{meta.product_id}_{hash(txt) % 99999}",
                date=self._normalize_date(date_match.group(1)),
                rating=5.0, option='', text=txt[:500], has_photo=False,
            )
        except Exception:
            return None

    def _normalize_date(self, raw: str) -> str:
        raw = raw.strip()
        match = re.search(r'(\d{4})[.\-/T](\d{2})[.\-/](\d{2})', raw)
        if match:
            y, m, d = match.groups()
            return f"{y}-{m}-{d}"
        match = re.search(r'(\d{2,4})[.\-/](\d{1,2})[.\-/](\d{1,2})', raw)
        if match:
            y, m, d = match.groups()
            if len(y) == 2:
                y = "20" + y
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        return ''

    def _extract_product_id(self, url: str) -> str:
        for pattern in [r'/goods/(\d+)', r'/app/goods/(\d+)', r'goodsNo=(\d+)', r'goods_no=(\d+)']:
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return url.split("/")[-1].split("?")[0]

    # ── 카테고리 벌크 스캔 ─────────────────────────────────────
    async def get_category_products(self, category_url: str, limit: int = 100) -> list[str]:
        product_urls = []
        
        # httpx 먼저 시도
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
                for page_num in range(1, 15):
                    sep = "&" if "?" in category_url else "?"
                    url = f"{category_url}{sep}page={page_num}"
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        break
                    found = re.findall(r'href="([^"]*?/goods/\d+[^"]*?)"', resp.text)
                    for href in found:
                        full = href if href.startswith("http") else self.base_url + href
                        full = full.split("?")[0]
                        if full not in product_urls:
                            product_urls.append(full)
                    if not found or len(product_urls) >= limit:
                        break
                    await asyncio.sleep(0.5)
            if product_urls:
                return product_urls[:limit]
        except Exception:
            pass

        # Playwright fallback
        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                page_num = 1
                while len(product_urls) < limit:
                    sep = "&" if "?" in category_url else "?"
                    paged_url = f"{category_url}{sep}page={page_num}"
                    ok = await safe_get(page, paged_url, timeout=30000)
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
