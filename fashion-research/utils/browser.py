"""
utils/browser.py
Playwright 브라우저 공통 유틸리티 - Stealth 모드 적용
"""
import asyncio
import random
import os
from loguru import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from dotenv import load_dotenv

load_dotenv()

HEADLESS = os.getenv("HEADLESS_MODE", "true").lower() == "true"
DELAY_MIN = float(os.getenv("SCRAPE_DELAY_MIN", "1.5"))
DELAY_MAX = float(os.getenv("SCRAPE_DELAY_MAX", "3.5"))

# ── Stealth 스크립트 (navigator.webdriver 우회) ──────────────
STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = { runtime: {} };
"""

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


async def random_delay(min_s: float = DELAY_MIN, max_s: float = DELAY_MAX):
    """봇 감지 방지용 랜덤 딜레이"""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def create_browser_context(playwright) -> tuple[Browser, BrowserContext]:
    """Stealth 브라우저 컨텍스트 생성"""
    browser = await playwright.chromium.launch(
        headless=HEADLESS,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1920,1080",
        ],
    )
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1920, "height": 1080},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        extra_http_headers={
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        },
    )
    # Stealth 스크립트 주입
    await context.add_init_script(STEALTH_SCRIPT)
    logger.info("🌐 Stealth 브라우저 컨텍스트 생성 완료")
    return browser, context


async def safe_get(page: Page, url: str, wait_selector: str = None, timeout: int = 30000):
    """안전한 페이지 로딩 (재시도 로직 포함)"""
    for attempt in range(3):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=timeout)
            await random_delay()
            return True
        except Exception as e:
            logger.warning(f"[{attempt+1}/3] 페이지 로드 실패: {url} - {e}")
            if attempt < 2:
                await asyncio.sleep(3)
    return False


async def scroll_to_bottom(page: Page, step: int = 800, delay: float = 0.5):
    """페이지 하단까지 스크롤 (레이지 로딩 트리거)"""
    prev_height = 0
    while True:
        curr_height = await page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        await page.evaluate(f"window.scrollBy(0, {step})")
        await asyncio.sleep(delay)
        prev_height = curr_height
