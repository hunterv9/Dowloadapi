"""Headless browser scraper for TikTok & Douyin profiles.

Uses Playwright to render JavaScript and bypass WAF/anti-bot protection.
Falls back gracefully when Playwright is not installed.
"""

import re
import logging
from pathlib import Path
from typing import List, Optional

_log = logging.getLogger(__name__)

__all__ = ["BrowserScraper"]

# Persist browser session (cookies, localStorage) between runs
_BROWSER_DATA_DIR = Path(__file__).parent.parent / ".browser_data"


class BrowserScraper:
    """Scrape profile pages using a headless browser to bypass anti-bot."""

    @staticmethod
    def is_available() -> bool:
        """Check if Playwright is installed and usable."""
        try:
            import playwright.sync_api  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def scrape_profile(
        profile_url: str,
        max_videos: int = 50,
        timeout_ms: int = 30000,
        headless: bool = True,
    ) -> List[str]:
        """Open profile in Chromium, scroll, extract video URLs.

        When *headless* is True, runs invisibly. When False, shows the browser
        so the user can solve CAPTCHAs manually on first run.

        Returns a list of video URLs (e.g. ``https://www.tiktok.com/@user/video/123``).
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            _log.warning("Playwright not installed")
            return []

        video_ids: List[str] = []
        seen: set = set()

        try:
            with sync_playwright() as p:
                _BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

                # Use persistent context to keep cookies between runs
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(_BROWSER_DATA_DIR),
                    headless=headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--no-sandbox",
                    ],
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    java_script_enabled=True,
                )
                # Remove webdriver flag
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                """)
                page = context.new_page()

                # Block heavy resources to speed up
                page.route(
                    re.compile(r"\.(png|jpg|jpeg|gif|svg|mp4|webm|woff2?)$"),
                    lambda route: route.abort(),
                )

                page.goto(profile_url, wait_until="domcontentloaded", timeout=timeout_ms)

                # Detect CAPTCHA and wait for user to solve it (headed mode only)
                if not headless:
                    captcha_selectors = [
                        'text="Drag the slider"',
                        'text="Log in"',
                        '[class*="captcha"]',
                        '[class*="verify"]',
                        '#captcha-verify-image',
                    ]
                    for sel in captcha_selectors:
                        try:
                            if page.query_selector(sel):
                                _log.info("CAPTCHA detected — solve it in the browser window")
                                # Wait up to 60s for CAPTCHA to disappear
                                page.wait_for_timeout(60000)
                                break
                        except Exception:
                            pass

                # Wait for video elements to appear
                try:
                    page.wait_for_selector(
                        'a[href*="/video/"], [data-e2e="user-post-item"]',
                        timeout=15000,
                    )
                except Exception:
                    _log.warning("No video elements found after page load")

                # Scroll to load more videos
                prev_count = 0
                scroll_attempts = 0
                max_scrolls = max(3, max_videos // 6)

                while len(video_ids) < max_videos and scroll_attempts < max_scrolls:
                    scroll_attempts += 1

                    # Extract video IDs from current page
                    links = page.query_selector_all('a[href*="/video/"]')
                    for link in links:
                        href = link.get_attribute("href") or ""
                        match = re.search(r"/video/(\d+)", href)
                        if match:
                            vid = match.group(1)
                            if vid not in seen:
                                seen.add(vid)
                                video_ids.append(vid)
                            if len(video_ids) >= max_videos:
                                break

                    if len(video_ids) >= max_videos:
                        break

                    # Check if new videos loaded
                    if len(video_ids) == prev_count and scroll_attempts > 2:
                        break
                    prev_count = len(video_ids)

                    # Scroll down
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1500)

                context.close()

        except Exception as e:
            _log.warning("Browser scraping failed: %s", e)

        # Build URLs
        username_match = re.search(r"@([a-zA-Z0-9_.\-]+)", profile_url)
        username = username_match.group(1) if username_match else ""

        # Detect platform
        if "douyin.com" in profile_url:
            base = "https://www.douyin.com"
        else:
            base = "https://www.tiktok.com"

        return [
            f"{base}/@{username}/video/{vid}"
            for vid in video_ids[:max_videos]
        ]
