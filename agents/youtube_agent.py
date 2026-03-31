"""
agents/youtube_agent.py
YouTube 웹 에이전트 - API 없이 Playwright로 데이터 수집
검색 → 영상 목록 → 제목/조회수/업로드일/댓글 수집
"""
import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
import pandas as pd
from playwright.async_api import async_playwright

from utils.browser import create_browser_context, safe_get, random_delay, scroll_to_bottom


@dataclass
class YouTubeVideo:
    keyword: str
    rank: int
    video_id: str
    title: str
    channel: str
    views: int
    upload_date: str
    duration: str
    thumbnail_url: str
    video_url: str
    like_count: int = 0
    comment_count: int = 0
    top_comments: list = None

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["top_comments"] = "\n---\n".join(self.top_comments or [])
        return d


class YouTubeAgent:
    """YouTube 웹 에이전트"""

    BASE_URL = "https://www.youtube.com"

    async def search_videos(
        self,
        keyword: str,
        max_results: int = 20,
        sort: str = "relevance",  # relevance / date / viewCount / rating
    ) -> list[YouTubeVideo]:
        """키워드로 YouTube 검색 후 영상 목록 수집"""
        videos = []
        search_url = (
            f"{self.BASE_URL}/results?search_query="
            f"{keyword.replace(' ', '+')}&sp="
            + ("CAISAhAB" if sort == "date" else "CAMSAhAB" if sort == "viewCount" else "")
        )

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                await safe_get(page, search_url, wait_selector="ytd-video-renderer", timeout=30000)

                # 스크롤로 더 많은 결과 로드
                for _ in range(3):
                    await scroll_to_bottom(page, step=1000)
                    await random_delay(1, 2)

                items = await page.query_selector_all("ytd-video-renderer")
                logger.info(f"[YouTube] '{keyword}' 검색 결과: {len(items)}개")

                for rank, item in enumerate(items[:max_results], 1):
                    video = await self._parse_video_item(item, keyword, rank)
                    if video:
                        videos.append(video)

            finally:
                await browser.close()

        return videos

    async def _parse_video_item(self, item, keyword: str, rank: int) -> YouTubeVideo | None:
        try:
            # 제목
            title_el = await item.query_selector("#video-title, h3 a")
            title = (await title_el.inner_text()).strip() if title_el else ""
            video_url = await title_el.get_attribute("href") if title_el else ""
            if video_url and not video_url.startswith("http"):
                video_url = self.BASE_URL + video_url

            # 비디오 ID
            vid_match = re.search(r"v=([a-zA-Z0-9_-]{11})", video_url or "")
            video_id = vid_match.group(1) if vid_match else ""

            # 채널명
            channel_el = await item.query_selector("#channel-name yt-formatted-string, .ytd-channel-name")
            channel = (await channel_el.inner_text()).strip() if channel_el else ""

            # 조회수
            meta_el = await item.query_selector_all("#metadata-line span")
            views = 0
            upload_date = ""
            for el in meta_el:
                text = (await el.inner_text()).strip()
                if "조회수" in text or "views" in text.lower():
                    views = self._parse_views(text)
                elif any(kw in text for kw in ["전", "ago", "일", "주", "개월", "년"]):
                    upload_date = text

            # 썸네일
            img_el = await item.query_selector("img#img, thumbnail img")
            thumbnail_url = await img_el.get_attribute("src") if img_el else ""

            # 재생시간
            duration_el = await item.query_selector("span#text.ytd-thumbnail-overlay-time-status-renderer")
            duration = (await duration_el.inner_text()).strip() if duration_el else ""

            return YouTubeVideo(
                keyword=keyword,
                rank=rank,
                video_id=video_id,
                title=title,
                channel=channel,
                views=views,
                upload_date=upload_date,
                duration=duration,
                thumbnail_url=thumbnail_url,
                video_url=video_url,
                top_comments=[],
            )
        except Exception as e:
            logger.debug(f"[YouTube] 영상 파싱 오류 rank={rank}: {e}")
            return None

    async def get_video_comments(self, video_url: str, max_comments: int = 20) -> list[str]:
        """영상 댓글 수집"""
        comments = []

        async with async_playwright() as pw:
            browser, ctx = await create_browser_context(pw)
            page = await ctx.new_page()
            try:
                await safe_get(page, video_url, timeout=30000)
                await asyncio.sleep(3)

                # 댓글 섹션으로 스크롤
                await page.evaluate("window.scrollTo(0, 700)")
                await asyncio.sleep(2)
                await page.evaluate("window.scrollTo(0, 1500)")
                await asyncio.sleep(3)

                comment_els = await page.query_selector_all("#content-text")
                for el in comment_els[:max_comments]:
                    text = (await el.inner_text()).strip()
                    if text:
                        comments.append(text)

                logger.info(f"[YouTube] 댓글 수집: {len(comments)}개")
            except Exception as e:
                logger.error(f"[YouTube] 댓글 수집 오류: {e}")
            finally:
                await browser.close()

        return comments

    def _parse_views(self, text: str) -> int:
        """'1.2만 조회수' → 12000"""
        text = re.sub(r"[조회수\s]", "", text)
        multipliers = {"천": 1_000, "만": 10_000, "억": 100_000_000, "k": 1_000, "m": 1_000_000}
        for unit, mult in multipliers.items():
            if unit in text.lower():
                num = re.search(r"[\d.]+", text)
                return int(float(num.group()) * mult) if num else 0
        num = re.sub(r"[^\d]", "", text)
        return int(num) if num else 0

    def to_dataframe(self, videos: list[YouTubeVideo]) -> pd.DataFrame:
        return pd.DataFrame([v.to_dict() for v in videos])

    def run_search(self, keyword: str, max_results: int = 20) -> pd.DataFrame:
        """동기 방식 (Streamlit 호환)"""
        videos = asyncio.run(self.search_videos(keyword, max_results))
        return self.to_dataframe(videos)
