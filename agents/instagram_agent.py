"""
agents/instagram_agent.py
Instagram 웹 에이전트 - Playwright 기반 해시태그/키워드 분석
스크린샷 포함, 로그인 없이 공개 데이터만 수집
"""
import asyncio
import re
import os
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger
import pandas as pd
from playwright.async_api import async_playwright
from PIL import Image
import io

from utils.browser import create_browser_context, safe_get, random_delay, scroll_to_bottom


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


class InstagramAgent:
    """Instagram 웹 에이전트 (로그인 없이 공개 데이터)"""

    BASE_URL = "https://www.instagram.com"
    SCREENSHOT_DIR = "./exports/screenshots"

    def __init__(self):
        os.makedirs(self.SCREENSHOT_DIR, exist_ok=True)

    async def search_hashtag(
        self,
        hashtag: str,
        max_posts: int = 30,
        take_screenshot: bool = True,
    ) -> list[InstagramPost]:
        """해시태그 페이지에서 최신 게시물 수집"""
        posts = []
        hashtag = hashtag.lstrip("#")
        url = f"{self.BASE_URL}/explore/tags/{hashtag}/"

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                ok = await safe_get(page, url, timeout=30000)
                if not ok:
                    logger.error(f"[Instagram] 해시태그 페이지 로드 실패: #{hashtag}")
                    return posts

                await asyncio.sleep(2)

                # 스크린샷 촬영
                if take_screenshot:
                    shot_path = os.path.join(
                        self.SCREENSHOT_DIR,
                        f"instagram_{hashtag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    )
                    await page.screenshot(path=shot_path, full_page=False)
                    logger.info(f"[Instagram] 스크린샷 저장: {shot_path}")

                # 게시물 썸네일 수집
                await scroll_to_bottom(page, step=600)
                post_links = await page.query_selector_all("a[href*='/p/']")

                post_urls = []
                for link in post_links:
                    href = await link.get_attribute("href")
                    if href and "/p/" in href:
                        full = href if href.startswith("http") else self.BASE_URL + href
                        if full not in post_urls:
                            post_urls.append(full)

                logger.info(f"[Instagram] #{hashtag} - {len(post_urls)}개 게시물 발견")

                # 각 게시물 상세 수집 (상위 N개)
                for idx, post_url in enumerate(post_urls[:max_posts]):
                    post = await self._get_post_detail(page, post_url, hashtag, idx + 1)
                    if post:
                        posts.append(post)
                    await random_delay(1.5, 3)

            except Exception as e:
                logger.error(f"[Instagram] 검색 오류: #{hashtag} - {e}")
            finally:
                await browser.close()

        return posts

    async def _get_post_detail(self, page, post_url: str, hashtag: str, rank: int) -> InstagramPost | None:
        """개별 게시물 상세 데이터 수집"""
        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1.5)

            # 포스트 ID
            post_id = re.search(r"/p/([^/]+)/", post_url)
            post_id = post_id.group(1) if post_id else ""

            # 이미지 URL
            img_el = await page.query_selector("article img, ._aagu img")
            image_url = await img_el.get_attribute("src") if img_el else ""

            # 캡션
            caption_el = await page.query_selector("div._a9zs, ._aacl._aaco._aacu._aacx._aad7._aade span")
            caption = (await caption_el.inner_text()).strip()[:500] if caption_el else ""

            # 좋아요 수 (공개된 경우)
            likes = 0
            like_el = await page.query_selector("section._aamu button span, span.x1lliihq")
            if like_el:
                like_text = await like_el.inner_text()
                likes = self._parse_count(like_text)

            # 댓글 수
            comments = 0
            comment_els = await page.query_selector_all("ul._a9z6 li")
            comments = max(0, len(comment_els) - 1)

            # 업로드 시간
            time_el = await page.query_selector("time[datetime]")
            posted_at = await time_el.get_attribute("datetime") if time_el else ""

            # 계정명
            account_el = await page.query_selector("header a.x1i10hfl, ._aaqt")
            account = (await account_el.inner_text()).strip() if account_el else ""

            # 동영상 여부
            is_video = await page.query_selector("video") is not None

            # 게시물 스크린샷
            shot_path = ""
            try:
                shot_path = os.path.join(
                    self.SCREENSHOT_DIR,
                    f"post_{post_id}.png"
                )
                await page.screenshot(path=shot_path, clip={"x": 0, "y": 0, "width": 800, "height": 600})
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
            logger.debug(f"[Instagram] 게시물 파싱 오류: {post_url} - {e}")
            return None

    async def get_hashtag_stats(self, hashtag: str) -> dict:
        """해시태그 기본 통계 (게시물 수 등)"""
        hashtag = hashtag.lstrip("#")
        url = f"{self.BASE_URL}/explore/tags/{hashtag}/"

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                await safe_get(page, url, timeout=30000)
                await asyncio.sleep(2)

                stats = {"hashtag": f"#{hashtag}", "url": url}

                # 게시물 수
                count_el = await page.query_selector("span.g47SY, header span")
                if count_el:
                    count_text = await count_el.inner_text()
                    stats["post_count"] = self._parse_count(count_text)

                # 스크린샷
                shot_path = os.path.join(
                    self.SCREENSHOT_DIR,
                    f"hashtag_{hashtag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                )
                await page.screenshot(path=shot_path)
                stats["screenshot"] = shot_path

                return stats
            finally:
                await browser.close()

    def _parse_count(self, text: str) -> int:
        """'1.2만' '12K' → 정수 변환"""
        text = text.strip().replace(",", "")
        multipliers = {"만": 10_000, "천": 1_000, "억": 100_000_000, "k": 1_000, "K": 1_000, "M": 1_000_000, "m": 1_000_000}
        for unit, mult in multipliers.items():
            if unit in text:
                num = re.search(r"[\d.]+", text)
                return int(float(num.group()) * mult) if num else 0
        num = re.sub(r"[^\d]", "", text)
        return int(num) if num else 0

    def to_dataframe(self, posts: list[InstagramPost]) -> pd.DataFrame:
        return pd.DataFrame([p.to_dict() for p in posts])

    def run_hashtag_search(self, hashtag: str, max_posts: int = 30) -> pd.DataFrame:
        """동기 방식 (Streamlit 호환)"""
        posts = asyncio.run(self.search_hashtag(hashtag, max_posts))
        return self.to_dataframe(posts)

    def extract_keywords_from_captions(self, posts_df: pd.DataFrame) -> list[tuple[str, int]]:
        """캡션에서 핵심 키워드 추출 (해시태그 포함)"""
        if posts_df.empty:
            return []
        all_text = " ".join(posts_df["caption"].fillna(""))
        # 해시태그 추출
        hashtags = re.findall(r"#(\w+)", all_text)
        hashtag_counts = {}
        for tag in hashtags:
            hashtag_counts[f"#{tag}"] = hashtag_counts.get(f"#{tag}", 0) + 1
        return sorted(hashtag_counts.items(), key=lambda x: x[1], reverse=True)[:30]
