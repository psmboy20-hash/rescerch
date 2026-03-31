"""
scrapers/scraper_29cm.py
29CM 스크래퍼 v3 - httpx API 직접 호출 (Playwright 최소화)
- 제품명/브랜드: 29CM 상품 API 직접 호출
- 리뷰: 내부 REST API 병렬 수집 (Playwright 불필요 → 10-30배 빠름)
- 제조년월: httpx로 페이지 소스 파싱
"""
import asyncio
import re
import httpx
import json
from loguru import logger
from playwright.async_api import async_playwright

from scrapers.base_scraper import BaseScraper, ProductMeta, Review
from utils.browser import create_browser_context, random_delay, scroll_to_bottom

# 29CM API 엔드포인트 후보들 (실제 API 구조에 맞게 폴백)
REVIEW_API_TEMPLATES = [
    "https://api.29cm.co.kr/product/v2/review/list?item_id={pid}&page={page}&per_page=20&sort=latest",
    "https://api.29cm.co.kr/product/v2/reviews?item_no={pid}&page={page}&size=20",
    "https://api.29cm.co.kr/product/reviews?item_id={pid}&page={page}&limit=20",
]

PRODUCT_API_TEMPLATES = [
    "https://api.29cm.co.kr/product/v2/item/{pid}",
    "https://api.29cm.co.kr/product/items/{pid}",
]

HEADERS_API = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Referer": "https://www.29cm.co.kr/",
    "Origin": "https://www.29cm.co.kr",
    "x-requested-with": "XMLHttpRequest",
}

HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


class Scraper29CM(BaseScraper):

    def __init__(self):
        super().__init__()
        self.platform = "29cm"
        self.base_url = "https://www.29cm.co.kr"

    # ── 제품 메타데이터 ─────────────────────────────────────────
    async def get_product_meta(self, url: str) -> ProductMeta:
        product_id = self._extract_product_id(url)
        meta = ProductMeta(platform=self.platform, product_id=product_id, url=url)

        # 1. httpx로 API 먼저 시도 (빠름)
        api_success = await self._fetch_product_meta_api(meta)
        
        # 2. API 실패 시 httpx로 웹페이지 파싱 (중간)
        if not meta.name:
            web_success = await self._fetch_product_meta_web(meta)
        
        # 3. 두 방법 다 실패 시 Playwright (최후 수단, 느림)
        if not meta.name:
            await self._fetch_product_meta_playwright(meta)

        logger.info(f"[29CM] {meta.name or '(제품명 미확인)'} | 브랜드: {meta.brand} | 제조년월: {meta.manufacture_date}")
        return meta

    async def _fetch_product_meta_api(self, meta: ProductMeta) -> bool:
        """29CM 상품 API 직접 호출"""
        async with httpx.AsyncClient(headers=HEADERS_API, timeout=10, follow_redirects=True) as client:
            for tmpl in PRODUCT_API_TEMPLATES:
                try:
                    url = tmpl.format(pid=meta.product_id)
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        # 다양한 API 응답 구조 대응
                        item = (
                            data.get("data") or data.get("item") or 
                            data.get("product") or data.get("result") or data
                        )
                        if isinstance(item, dict):
                            meta.name = (
                                item.get("item_name") or item.get("name") or 
                                item.get("product_name") or item.get("title") or ""
                            ).strip()
                            meta.brand = (
                                item.get("brand_name") or item.get("brand") or
                                item.get("brand_nm") or ""
                            ).strip()
                            price_raw = item.get("sale_price") or item.get("price") or item.get("sell_price") or 0
                            try:
                                meta.price = int(str(price_raw).replace(",", ""))
                            except Exception:
                                pass
                            if meta.name:
                                return True
                except Exception as e:
                    logger.debug(f"[29CM API] {tmpl}: {e}")
        return False

    async def _fetch_product_meta_web(self, meta: ProductMeta) -> bool:
        """httpx로 웹페이지 HTML 파싱 (JS 렌더링 없음 - 정적 HTML만)"""
        url = f"{self.base_url}/products/{meta.product_id}"
        try:
            async with httpx.AsyncClient(headers=HEADERS_WEB, timeout=10, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return False
                html = resp.text
                
                # JSON-LD 구조화 데이터 파싱 (가장 정확)
                ld_match = re.search(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
                if ld_match:
                    try:
                        ld_data = json.loads(ld_match.group(1))
                        meta.name = ld_data.get("name", "").strip()
                        brand_info = ld_data.get("brand", {})
                        if isinstance(brand_info, dict):
                            meta.brand = brand_info.get("name", "").strip()
                        price_info = ld_data.get("offers", {})
                        if isinstance(price_info, dict):
                            try:
                                meta.price = int(float(price_info.get("price", 0)))
                            except Exception:
                                pass
                        if meta.name:
                            return True
                    except Exception:
                        pass
                
                # meta og:title 파싱
                og_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
                if og_match:
                    meta.name = og_match.group(1).strip()
                
                # 제조년월 파싱 (정적 HTML에서 가능한 경우)
                meta.manufacture_date = self._extract_manufacture_date_from_text(html)
                return bool(meta.name)
        except Exception as e:
            logger.debug(f"[29CM Web] httpx 파싱 실패: {e}")
        return False

    async def _fetch_product_meta_playwright(self, meta: ProductMeta):
        """Playwright fallback - 최후 수단"""
        url = f"{self.base_url}/products/{meta.product_id}"
        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # 제품명: 여러 셀렉터 시도
                name_selectors = [
                    'h2[class*="text-l"]',
                    'h2[class*="product"]',
                    'h1[class*="product"]',
                    '[class*="product-name"]',
                    '[class*="productName"]',
                    '[data-testid="product-name"]',
                    'h2', 'h1',
                ]
                for sel in name_selectors:
                    try:
                        els = await page.query_selector_all(sel)
                        for el in els[:3]:
                            txt = (await el.inner_text()).strip()
                            if txt and 3 < len(txt) < 200 and not txt.isdigit():
                                meta.name = txt
                                break
                        if meta.name:
                            break
                    except Exception:
                        continue

                # 브랜드: 여러 셀렉터 시도
                brand_selectors = [
                    'h3[class*="title"]',
                    '[class*="brand-name"]',
                    '[class*="brandName"]',
                    'a[href*="/brands/"]',
                    'a[href*="/brand/"]',
                ]
                for sel in brand_selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            txt = (await el.inner_text()).strip()
                            if txt and len(txt) < 50:
                                meta.brand = txt
                                break
                    except Exception:
                        continue

                # 제조년월
                try:
                    full_text = await page.inner_text("body")
                    meta.manufacture_date = self._extract_manufacture_date_from_text(full_text)
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"[29CM Playwright] 메타 수집 오류: {e}")
            finally:
                await browser.close()

    def _extract_manufacture_date_from_text(self, text: str) -> str | None:
        patterns = [
            r'제조년월[^\d]*(\d{4})[-./년\s]*(\d{1,2})',
            r'제조일자[^\d]*(\d{4})[-./년\s]*(\d{1,2})',
            r'생산일[^\d]*(\d{4})[-./년\s]*(\d{1,2})',
            r'제조\s*:\s*(\d{4})[-./년\s]*(\d{1,2})',
            r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(?:제조|생산)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                year, month = match.group(1), match.group(2)
                return f"{year}-{month.zfill(2)}"
        return None

    # ── 전체 리뷰 수집 (httpx 병렬 - 최고속) ──────────────────
    async def get_all_reviews(self, product_meta: ProductMeta) -> list[Review]:
        """
        httpx 병렬 배치로 전체 리뷰 수집 (Playwright 없음)
        실패 시 Playwright fallback
        """
        reviews = []

        # 1단계: 작동하는 API 엔드포인트 탐색
        working_tmpl, first_data = await self._find_working_review_api(product_meta.product_id)
        
        if not working_tmpl or not first_data:
            logger.warning(f"[29CM] API 미발견 → Playwright fallback")
            return await self._get_reviews_playwright(product_meta)

        # 총 리뷰 수 파악
        total = (
            first_data.get('total_count') or first_data.get('totalCount') or
            first_data.get('total') or first_data.get('count') or
            (first_data.get('data') or {}).get('total_count') or 0
        )
        page_size = 20
        total_pages = min((int(total) // page_size) + 2, 500)

        logger.info(f"[29CM] 총 {total}건 → {total_pages}페이지 병렬 수집 (엔드포인트: 발견)")

        # 1페이지 파싱
        reviews += self._parse_api_reviews(first_data, product_meta)

        # 2~N 페이지: 10개씩 병렬 수집
        batch_size = 10
        for batch_start in range(2, total_pages + 1, batch_size):
            batch = range(batch_start, min(batch_start + batch_size, total_pages + 1))
            tasks = [self._fetch_one_page(working_tmpl, product_meta.product_id, p) for p in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            before = len(reviews)
            for result in results:
                if isinstance(result, dict):
                    reviews += self._parse_api_reviews(result, product_meta)
            
            after = len(reviews)
            if after == before:
                logger.info(f"[29CM] 새 리뷰 없음 → 수집 완료 ({len(reviews)}건)")
                break

            logger.info(f"[29CM] 누적 {len(reviews)}건")
            await asyncio.sleep(0.2)  # 최소 딜레이

        return reviews

    async def _find_working_review_api(self, product_id: str) -> tuple[str | None, dict | None]:
        """작동하는 리뷰 API 엔드포인트 탐색"""
        async with httpx.AsyncClient(headers=HEADERS_API, timeout=15, follow_redirects=True) as client:
            for tmpl in REVIEW_API_TEMPLATES:
                try:
                    url = tmpl.format(pid=product_id, page=1)
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        items = self._extract_review_items(data)
                        if items is not None:  # 빈 리스트도 유효 (마지막 페이지)
                            logger.debug(f"[29CM] 작동하는 API 발견: {tmpl}")
                            return tmpl, data
                except Exception as e:
                    logger.debug(f"[29CM] API 시도: {tmpl} → {e}")
        return None, None

    async def _fetch_one_page(self, tmpl: str, product_id: str, page: int) -> dict | None:
        """단일 페이지 리뷰 API 호출"""
        try:
            async with httpx.AsyncClient(headers=HEADERS_API, timeout=10, follow_redirects=True) as client:
                url = tmpl.format(pid=product_id, page=page)
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return None

    def _extract_review_items(self, data: dict) -> list | None:
        """API 응답에서 리뷰 항목 리스트 추출"""
        if not isinstance(data, dict):
            return None
        # 다양한 API 응답 구조 대응
        candidates = [
            data.get('data', {}).get('reviews') if isinstance(data.get('data'), dict) else None,
            data.get('data', {}).get('list') if isinstance(data.get('data'), dict) else None,
            data.get('reviews'),
            data.get('list'),
            data.get('items'),
            data.get('data') if isinstance(data.get('data'), list) else None,
        ]
        for c in candidates:
            if c is not None:
                return c if isinstance(c, list) else []
        return None

    def _parse_api_reviews(self, data: dict, meta: ProductMeta) -> list[Review]:
        reviews = []
        items = self._extract_review_items(data) or []

        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                date_raw = (
                    item.get('created_at') or item.get('createdAt') or
                    item.get('write_date') or item.get('writeDate') or
                    item.get('reg_date') or item.get('regDt') or ''
                )
                date = self._normalize_date(str(date_raw))
                if not date:
                    continue

                rating = float(
                    item.get('rating') or item.get('score') or
                    item.get('star') or item.get('star_point') or 0
                )
                option = str(
                    item.get('option') or item.get('order_option') or
                    item.get('itemOption') or item.get('goods_option') or ''
                )
                text = str(
                    item.get('contents') or item.get('content') or
                    item.get('review') or item.get('body') or
                    item.get('review_contents') or ''
                ).strip()
                if not text:
                    continue

                review_id = str(
                    item.get('id') or item.get('review_id') or item.get('reviewId') or
                    item.get('no') or f"{meta.product_id}_{date}_{hash(text) % 99999}"
                )
                reviews.append(Review(
                    product_id=meta.product_id,
                    platform=self.platform,
                    review_id=review_id,
                    date=date,
                    rating=rating,
                    option=option,
                    text=text,
                    has_photo=bool(item.get('photos') or item.get('images') or item.get('photo_count')),
                    helpful=int(item.get('helpful') or item.get('like_count') or item.get('good_count') or 0),
                ))
            except Exception as e:
                logger.debug(f"[29CM] 리뷰 파싱: {e}")
        return reviews

    # ── Playwright Fallback ────────────────────────────────────
    async def _get_reviews_playwright(self, product_meta: ProductMeta) -> list[Review]:
        """
        Playwright로 리뷰 수집 (API 실패 시)
        네트워크 요청 인터셉트로 내부 API URL 자동 탐지
        """
        reviews = []
        found_api_data = []

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()

            # 네트워크 요청 인터셉트 - 리뷰 API 자동 탐지
            async def intercept_response(response):
                try:
                    url = response.url
                    if ('review' in url.lower() or 'comment' in url.lower()) and response.status == 200:
                        ct = response.headers.get('content-type', '')
                        if 'json' in ct:
                            data = await response.json()
                            items = self._extract_review_items(data)
                            if items and len(items) > 0:
                                found_api_data.append((url, data))
                                logger.info(f"[29CM Intercept] 리뷰 API 탐지: {url} ({len(items)}건)")
                except Exception:
                    pass

            page.on("response", intercept_response)

            try:
                product_url = f"{self.base_url}/products/{product_meta.product_id}"
                await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                # 리뷰 탭 클릭
                review_tab_selectors = [
                    'button:has-text("리뷰")',
                    '[role="tab"]:has-text("리뷰")',
                    'a:has-text("리뷰")',
                    'li:has-text("리뷰")',
                    '[class*="review"][class*="tab"]',
                ]
                for sel in review_tab_selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            await el.click()
                            await asyncio.sleep(2)
                            break
                    except Exception:
                        continue

                # 인터셉트된 API 데이터 활용
                if found_api_data:
                    api_url_tmpl, first_data = found_api_data[0]
                    reviews += self._parse_api_reviews(first_data, product_meta)
                    
                    # API URL 패턴화
                    tmpl = re.sub(r'page=\d+', 'page={page}', api_url_tmpl)
                    tmpl = re.sub(r'(item_id|item_no|itemId)=\d+', f'\\1={product_meta.product_id}', tmpl)
                    
                    logger.info(f"[29CM] 인터셉트 API로 추가 페이지 수집 중...")
                    for page_num in range(2, 200):
                        page_url = tmpl.replace('{page}', str(page_num))
                        data = await self._fetch_one_page(page_url, product_meta.product_id, page_num)
                        if not data:
                            break
                        new_reviews = self._parse_api_reviews(data, product_meta)
                        if not new_reviews:
                            break
                        reviews += new_reviews
                        logger.info(f"[29CM] 페이지 {page_num}: 누적 {len(reviews)}건")
                        await asyncio.sleep(0.2)
                    
                    return reviews

                # DOM 직접 파싱 (마지막 수단)
                await asyncio.sleep(3)
                review_items = await page.query_selector_all(
                    '[class*="review"]:not([class*="tab"]):not([class*="count"]):not([class*="header"]):not([class*="button"])'
                )
                for item in review_items:
                    try:
                        txt = (await item.inner_text()).strip()
                        if len(txt) < 10:
                            continue
                        date_match = re.search(r'(20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2})', txt)
                        if not date_match:
                            continue
                        date = self._normalize_date(date_match.group(1))
                        reviews.append(Review(
                            product_id=product_meta.product_id,
                            platform=self.platform,
                            review_id=f"{product_meta.product_id}_{hash(txt) % 99999}",
                            date=date, rating=5.0,
                            option='', text=txt[:500], has_photo=False,
                        ))
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"[29CM Playwright] 오류: {e}")
            finally:
                await browser.close()

        return reviews

    def _normalize_date(self, raw: str) -> str:
        raw = raw.strip()
        # ISO 형식 (2024-03-15T10:00:00)
        match = re.search(r'(\d{4})[.\-/T](\d{2})[.\-/](\d{2})', raw)
        if match:
            y, m, d = match.groups()
            return f"{y}-{m}-{d}"
        # 짧은 형식 (24.03.15)
        match = re.search(r'(\d{2,4})[.\-/](\d{1,2})[.\-/](\d{1,2})', raw)
        if match:
            y, m, d = match.groups()
            if len(y) == 2:
                y = "20" + y
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        return ''

    def _extract_product_id(self, url: str) -> str:
        match = re.search(r'/products?/(\d+)', url)
        if match:
            return match.group(1)
        match = re.search(r'[?&]item_?id=(\d+)', url)
        return match.group(1) if match else url.split("/")[-1].split("?")[0]

    # ── 카테고리 벌크 스캔 ─────────────────────────────────────
    async def get_category_products(self, category_url: str, limit: int = 100) -> list[str]:
        """
        카테고리 페이지에서 httpx로 제품 URL 수집 (빠름)
        실패 시 Playwright fallback
        """
        # httpx로 먼저 시도
        product_urls = await self._get_category_httpx(category_url, limit)
        if product_urls:
            return product_urls

        # Playwright fallback
        return await self._get_category_playwright(category_url, limit)

    async def _get_category_httpx(self, category_url: str, limit: int) -> list[str]:
        """httpx로 카테고리 페이지 크롤링"""
        product_urls = []
        try:
            async with httpx.AsyncClient(headers=HEADERS_WEB, timeout=15, follow_redirects=True) as client:
                for page_num in range(1, 20):
                    # 페이지네이션 파라미터 추가
                    sep = "&" if "?" in category_url else "?"
                    url = f"{category_url}{sep}page={page_num}"
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        break
                    html = resp.text
                    # /products/숫자 패턴 추출
                    found = re.findall(r'href="(/products/\d+)"', html)
                    for href in found:
                        full = self.base_url + href
                        if full not in product_urls:
                            product_urls.append(full)
                    if not found or len(product_urls) >= limit:
                        break
                    await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"[29CM] httpx 카테고리: {e}")
        return product_urls[:limit]

    async def _get_category_playwright(self, category_url: str, limit: int) -> list[str]:
        product_urls = []
        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                await page.goto(category_url, wait_until="domcontentloaded", timeout=25000)
                await asyncio.sleep(3)

                while len(product_urls) < limit:
                    await scroll_to_bottom(page, step=1000)
                    links = await page.query_selector_all('a[href*="/products/"]')
                    for link in links:
                        href = await link.get_attribute("href")
                        if href and re.search(r'/products/\d+$', href):
                            full = href if href.startswith("http") else self.base_url + href
                            if full not in product_urls:
                                product_urls.append(full)
                    product_urls = list(dict.fromkeys(product_urls))[:limit]
                    if len(product_urls) >= limit:
                        break
                    await random_delay(1, 2)

                logger.info(f"[29CM] 카테고리 {len(product_urls)}개 수집")
            finally:
                await browser.close()
        return product_urls
