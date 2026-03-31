"""
agents/instagram_agent.py
Instagram 웹 에이전트 v2 - 로그인 기반 Playwright 자동화
- 로그인 세션 쿠키 저장/재사용으로 속도 개선
- 최신 Instagram DOM 구조 셀렉터 (2024년 기준)
- 스크린샷 자동 캡처
- 게시물 상세 데이터 수집
"""
import asyncio
import re
import os
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from loguru import logger
import pandas as pd
from playwright.async_api import async_playwright, BrowserContext, Page
from PIL import Image

from utils.browser import create_browser_context, random_delay, scroll_to_bottom


@dataclass
class InstagramPost:
    hashtag: str
    post_id: str
    post_url: str
    image_url: str
    caption: str
    likes: int
    comments: int
    posted_at: str
    account: str
    is_video: bool = False
    screenshot_path: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


# 환경변수 또는 하드코딩 (실행 시 .env로 오버라이드 가능)
IG_USERNAME = os.getenv("INSTAGRAM_USERNAME", "jellygogo1")
IG_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "tjdan1020123!!")
# 쿠키 경로: 환경변수 INSTAGRAM_COOKIE_FILE → 기본값 ./exports/instagram_cookies.json
_cookie_env = os.getenv("INSTAGRAM_COOKIE_FILE", "")
COOKIE_FILE = Path(_cookie_env) if _cookie_env else Path("./exports/instagram_cookies.json")
SCREENSHOT_DIR = Path("./exports/screenshots")


class InstagramAgent:
    """Instagram 웹 에이전트 (로그인 세션 기반)"""

    BASE_URL = "https://www.instagram.com"

    def __init__(self, username: str = None, password: str = None):
        self.username = username or IG_USERNAME
        self.password = password or IG_PASSWORD
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ── 로그인 / 세션 관리 ─────────────────────────────────────

    async def _login(self, page: Page) -> bool:
        """Instagram 로그인 (저장된 쿠키 우선, 없으면 실제 로그인)"""
        # 1. 저장된 쿠키로 복원 시도
        if COOKIE_FILE.exists():
            try:
                cookies = json.loads(COOKIE_FILE.read_text())
                await page.context.add_cookies(cookies)
                await page.goto(f"{self.BASE_URL}/", wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                
                # 로그인 상태 확인 (프로필 아이콘 또는 홈 피드)
                if await self._is_logged_in(page):
                    logger.info("[Instagram] 저장된 쿠키로 로그인 성공")
                    return True
                else:
                    logger.warning("[Instagram] 쿠키 만료 → 재로그인")
                    COOKIE_FILE.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"[Instagram] 쿠키 복원 실패: {e}")

        # 2. 실제 로그인
        return await self._do_login(page)

    async def _do_login(self, page: Page) -> bool:
        """실제 ID/PW 로그인"""
        try:
            logger.info(f"[Instagram] 로그인 시도: {self.username}")
            await page.goto(f"{self.BASE_URL}/accounts/login/", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)

            # 쿠키 팝업 닫기
            await self._dismiss_popups(page)

            # ID 입력
            username_input = await page.wait_for_selector(
                'input[name="username"], input[type="text"]',
                timeout=10000
            )
            await username_input.click()
            await username_input.fill("")
            await asyncio.sleep(0.3)
            await username_input.type(self.username, delay=80)

            # PW 입력
            password_input = await page.wait_for_selector(
                'input[name="password"], input[type="password"]',
                timeout=5000
            )
            await password_input.click()
            await password_input.fill("")
            await asyncio.sleep(0.3)
            await password_input.type(self.password, delay=80)

            # 로그인 버튼 클릭
            await asyncio.sleep(0.5)
            login_btn = await page.query_selector(
                'button[type="submit"], button:has-text("로그인"), button:has-text("Log in")'
            )
            if login_btn:
                await login_btn.click()
            else:
                await page.keyboard.press("Enter")

            # 로그인 완료 대기
            await asyncio.sleep(5)
            
            # "나중에" 팝업 처리 (알림, 앱 등)
            for _ in range(3):
                await self._dismiss_popups(page)
                await asyncio.sleep(1)

            # 로그인 성공 확인
            if await self._is_logged_in(page):
                # 쿠키 저장
                cookies = await page.context.cookies()
                COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
                logger.info(f"[Instagram] 로그인 성공! 쿠키 저장: {COOKIE_FILE}")
                return True
            else:
                # 스크린샷으로 상태 확인
                shot = str(SCREENSHOT_DIR / f"login_fail_{datetime.now().strftime('%H%M%S')}.png")
                await page.screenshot(path=shot)
                logger.error(f"[Instagram] 로그인 실패 (스크린샷: {shot})")
                return False

        except Exception as e:
            logger.error(f"[Instagram] 로그인 오류: {e}")
            return False

    async def _is_logged_in(self, page: Page) -> bool:
        """로그인 상태 확인"""
        try:
            # URL 확인
            current_url = page.url
            if "login" in current_url or "accounts/login" in current_url:
                return False
            
            # 홈 피드 또는 프로필 아이콘 확인
            indicators = [
                'nav a[href="/"]',           # 홈 링크
                'a[href*="/direct/"]',        # DM 링크
                'svg[aria-label="홈"]',
                'svg[aria-label="Home"]',
                '[data-testid="user-avatar"]',
                'a[href*="/p/"]',             # 게시물 링크 (피드)
            ]
            for sel in indicators:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        return True
                except Exception:
                    pass
            return False
        except Exception:
            return False

    async def _dismiss_popups(self, page: Page):
        """각종 팝업 닫기"""
        popup_selectors = [
            # 쿠키 동의
            'button:has-text("허용")',
            'button:has-text("Allow")',
            'button:has-text("Accept")',
            'button:has-text("모두 허용")',
            # 알림 팝업
            'button:has-text("나중에")',
            'button:has-text("Not Now")',
            'button:has-text("지금 아님")',
            # 앱 설치 팝업
            'button:has-text("Not Now")',
            'button[class*="close"]',
            # 대화 상자
            '[role="dialog"] button:has-text("아님")',
            '[role="dialog"] button:has-text("취소")',
        ]
        for sel in popup_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass

    # ── 해시태그 검색 ──────────────────────────────────────────

    async def search_hashtag(
        self,
        hashtag: str,
        max_posts: int = 30,
        take_screenshot: bool = True,
    ) -> list[InstagramPost]:
        """해시태그 페이지에서 최신 게시물 수집"""
        posts = []
        hashtag = hashtag.lstrip("#")

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                # 로그인
                logged_in = await self._login(page)
                if not logged_in:
                    logger.warning("[Instagram] 로그인 없이 진행 (공개 게시물만)")

                # 해시태그 페이지 이동
                url = f"{self.BASE_URL}/explore/tags/{hashtag}/"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
                await self._dismiss_popups(page)

                # 스크린샷 (해시태그 페이지 전체)
                if take_screenshot:
                    shot_path = str(SCREENSHOT_DIR / f"instagram_{hashtag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                    await page.screenshot(path=shot_path, full_page=False)
                    logger.info(f"[Instagram] 해시태그 페이지 스크린샷: {shot_path}")

                # 게시물 수집
                await scroll_to_bottom(page, step=500)
                await asyncio.sleep(2)

                # 게시물 링크 수집 (여러 셀렉터 시도)
                post_urls = await self._collect_post_urls(page, max_posts * 2)
                logger.info(f"[Instagram] #{hashtag} - {len(post_urls)}개 게시물 URL 발견")

                if not post_urls:
                    # 디버그 스크린샷
                    shot = str(SCREENSHOT_DIR / f"debug_{hashtag}_{datetime.now().strftime('%H%M%S')}.png")
                    await page.screenshot(path=shot, full_page=True)
                    logger.warning(f"[Instagram] 게시물 없음 (디버그: {shot})")
                    return posts

                # 각 게시물 상세 수집
                for idx, post_url in enumerate(post_urls[:max_posts]):
                    post = await self._get_post_detail(page, post_url, hashtag, idx + 1)
                    if post:
                        posts.append(post)
                    logger.info(f"[Instagram] [{idx+1}/{min(max_posts, len(post_urls))}] {post_url[-30:]}")
                    await random_delay(1.5, 3.0)

                logger.info(f"[Instagram] #{hashtag} 수집 완료: {len(posts)}개")

            except Exception as e:
                logger.error(f"[Instagram] 검색 오류: #{hashtag} - {e}")
            finally:
                await browser.close()

        return posts

    async def _collect_post_urls(self, page: Page, limit: int) -> list[str]:
        """게시물 URL 수집 - 다양한 셀렉터 시도"""
        post_urls = []
        
        # 셀렉터 후보들 (Instagram DOM 구조 변화 대응)
        selectors = [
            'a[href*="/p/"]',
            'a[href*="/reel/"]',
            'article a[href]',
            'div[class*="x1lliihq"] a[href]',
            'div._aagw a',
            'div._ac7v a',
        ]
        
        for sel in selectors:
            try:
                links = await page.query_selector_all(sel)
                for link in links:
                    href = await link.get_attribute("href")
                    if href and ("/p/" in href or "/reel/" in href):
                        full = href if href.startswith("http") else self.BASE_URL + href
                        # 쿼리 스트링 제거
                        full = full.split("?")[0].rstrip("/") + "/"
                        if full not in post_urls:
                            post_urls.append(full)
            except Exception:
                continue
        
        # 중복 제거 후 반환
        return list(dict.fromkeys(post_urls))[:limit]

    async def _get_post_detail(self, page: Page, post_url: str, hashtag: str, rank: int) -> InstagramPost | None:
        """개별 게시물 상세 데이터 수집 (최신 셀렉터)"""
        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)
            await self._dismiss_popups(page)

            post_id = re.search(r"/(?:p|reel)/([^/]+)/", post_url)
            post_id = post_id.group(1) if post_id else f"rank_{rank}"

            # ── 이미지 URL ──────────────────────────────────────
            image_url = ""
            img_selectors = [
                'article img[src*="cdninstagram"]',
                'article img[src*="instagram"]',
                'div[role="presentation"] img',
                'img[class*="x5yr21d"]',
                'img[class*="_aagt"]',
            ]
            for sel in img_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        image_url = await el.get_attribute("src") or ""
                        if image_url:
                            break
                except Exception:
                    continue

            # ── 캡션 ────────────────────────────────────────────
            caption = ""
            caption_selectors = [
                'h1._aacl',
                'div._a9zs span',
                'div[class*="_aacl"] span',
                'article h1',
                'span._aacl._aaco._aacu._aacx._aad7._aade',
                # 새 DOM 구조 (2024)
                'div[class*="x193iq5w"] span',
                'div._a9zs',
            ]
            for sel in caption_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        caption = (await el.inner_text()).strip()[:500]
                        if caption:
                            break
                except Exception:
                    continue

            # ── 좋아요 수 ────────────────────────────────────────
            likes = 0
            like_selectors = [
                'section span span',
                'div._aacl span',
                'button span[class*="html-span"]',
                'span[class*="_aacl"]',
                # 새 구조
                'div[class*="x1i10hfl"] span span',
                'a[href*="liked_by"] span',
            ]
            for sel in like_selectors:
                try:
                    els = await page.query_selector_all(sel)
                    for el in els[:10]:
                        txt = (await el.inner_text()).strip()
                        if re.search(r'\d', txt) and len(txt) < 20:
                            parsed = self._parse_count(txt)
                            if parsed > 0:
                                likes = parsed
                                break
                    if likes > 0:
                        break
                except Exception:
                    continue

            # ── 댓글 수 ──────────────────────────────────────────
            comments = 0
            comment_selectors = [
                'ul._a9z6 > li',
                'div._a9z7 > ul > li',
                'div[class*="comment"] > ul > li',
            ]
            for sel in comment_selectors:
                try:
                    els = await page.query_selector_all(sel)
                    if els:
                        comments = max(0, len(els) - 1)
                        break
                except Exception:
                    continue

            # ── 업로드 시간 ──────────────────────────────────────
            posted_at = ""
            time_selectors = [
                'time[datetime]',
                'time._aaqe',
                'div._a9ze time',
            ]
            for sel in time_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        posted_at = await el.get_attribute("datetime") or await el.inner_text()
                        if posted_at:
                            break
                except Exception:
                    continue

            # ── 계정명 ───────────────────────────────────────────
            account = ""
            account_selectors = [
                'header a._aaqt',
                'header div._aaqt',
                'article header a',
                'span._aap6',
                # 새 구조
                'a[role="link"] span[class*="x1lliihq"]',
                'header span[class*="_aap6"]',
            ]
            for sel in account_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        account = (await el.inner_text()).strip()
                        if account and "@" not in account or len(account) < 50:
                            break
                except Exception:
                    continue

            # ── 동영상 여부 ──────────────────────────────────────
            is_video = await page.query_selector("video") is not None

            # ── 게시물 스크린샷 ──────────────────────────────────
            shot_path = ""
            try:
                shot_path = str(SCREENSHOT_DIR / f"post_{post_id}.png")
                # article 영역만 캡처
                article = await page.query_selector("article, div[role='dialog']")
                if article:
                    await article.screenshot(path=shot_path)
                else:
                    await page.screenshot(path=shot_path, clip={"x": 0, "y": 0, "width": 900, "height": 700})
            except Exception:
                pass

            return InstagramPost(
                hashtag=hashtag,
                post_id=post_id,
                post_url=post_url,
                image_url=image_url,
                caption=caption,
                likes=likes,
                comments=comments,
                posted_at=posted_at,
                account=account,
                is_video=is_video,
                screenshot_path=shot_path,
            )
        except Exception as e:
            logger.debug(f"[Instagram] 게시물 파싱 오류: {post_url[-30:]} - {e}")
            return None

    # ── 해시태그 통계 ──────────────────────────────────────────

    async def get_hashtag_stats(self, hashtag: str) -> dict:
        """해시태그 기본 통계"""
        hashtag = hashtag.lstrip("#")
        url = f"{self.BASE_URL}/explore/tags/{hashtag}/"

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                await self._login(page)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                stats = {"hashtag": f"#{hashtag}", "url": url, "post_count": 0}

                # 게시물 수 (다양한 셀렉터)
                count_selectors = [
                    'span.g47SY',
                    'header span[title]',
                    'div._aacl span',
                    'h2 ~ span',
                ]
                for sel in count_selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            txt = await el.inner_text()
                            count = self._parse_count(txt)
                            if count > 0:
                                stats["post_count"] = count
                                break
                    except Exception:
                        pass

                # 스크린샷
                shot_path = str(SCREENSHOT_DIR / f"hashtag_{hashtag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                await page.screenshot(path=shot_path)
                stats["screenshot"] = shot_path
                logger.info(f"[Instagram] #{hashtag} 통계: {stats}")

                return stats
            finally:
                await browser.close()

    # ── 유틸리티 ───────────────────────────────────────────────

    def _parse_count(self, text: str) -> int:
        """'1.2만' '12K' '12,345' → 정수 변환"""
        text = text.strip().replace(",", "").replace(" ", "")
        multipliers = {
            "만": 10_000, "천": 1_000, "억": 100_000_000,
            "k": 1_000, "K": 1_000, "M": 1_000_000, "m": 1_000_000
        }
        for unit, mult in multipliers.items():
            if unit in text:
                num = re.search(r"[\d.]+", text)
                return int(float(num.group()) * mult) if num else 0
        num = re.sub(r"[^\d]", "", text)
        return int(num) if num and len(num) < 12 else 0

    def to_dataframe(self, posts: list[InstagramPost]) -> pd.DataFrame:
        if not posts:
            # 빈 DataFrame도 필요한 컬럼은 포함
            return pd.DataFrame(columns=[
                "hashtag", "post_id", "post_url", "image_url",
                "caption", "likes", "comments", "posted_at",
                "account", "is_video", "screenshot_path"
            ])
        return pd.DataFrame([p.to_dict() for p in posts])

    def run_hashtag_search(self, hashtag: str, max_posts: int = 30) -> pd.DataFrame:
        """동기 방식 (Streamlit 호환)"""
        posts = asyncio.run(self.search_hashtag(hashtag, max_posts))
        return self.to_dataframe(posts)

    def extract_keywords_from_captions(self, posts_df: pd.DataFrame) -> list[tuple[str, int]]:
        """캡션에서 핵심 키워드 추출"""
        if posts_df.empty or "caption" not in posts_df.columns:
            return []
        all_text = " ".join(posts_df["caption"].fillna(""))
        hashtags = re.findall(r"#(\w+)", all_text)
        counts: dict[str, int] = {}
        for tag in hashtags:
            key = f"#{tag}"
            counts[key] = counts.get(key, 0) + 1
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:30]

    def clear_cookies(self):
        """저장된 쿠키 삭제 (재로그인 강제)"""
        if COOKIE_FILE.exists():
            COOKIE_FILE.unlink()
            logger.info("[Instagram] 쿠키 삭제 완료")
