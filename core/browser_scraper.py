"""Headless browser scraper for TikTok & Douyin profiles.

Uses Playwright to render JavaScript and bypass WAF/anti-bot protection.
Falls back gracefully when Playwright is not installed.
"""

import os
import re
import sys
import time
import random
import logging
from typing import List, Optional

from . import stealth as _stealth
from .env_utils import BROWSER_DATA_DIR as _BROWSER_DATA_DIR

_log = logging.getLogger(__name__)

__all__ = ["BrowserScraper"]


# UA pool single source: stealth.pick_user_agent() (Chrome 126).

# Stealth JS to inject before page load — defeats common bot-detection signals
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'language', {get: () => 'en-US'});
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
            {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''},
        ];
        plugins.length = 3;
        return plugins;
    }
});
window.chrome = window.chrome || {};
window.chrome.runtime = window.chrome.runtime || {};
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.apply(this, arguments);
};
delete navigator.__proto__.webdriver;
if (navigator.connection) {
    Object.defineProperty(navigator.connection, 'rtt', {get: () => 50});
}
"""


class BrowserScraper:
    """Scrape profile pages using a headless browser to bypass anti-bot."""

    @staticmethod
    def is_available() -> bool:
        """Check if Playwright is installed and browsers are downloaded."""
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            return False
        # Check if at least Chromium browser is installed
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "--dry-run"],
                capture_output=True, text=True, timeout=10,
            )
            # If "chromium" appears as already installed, we're good
            if "chromium" in result.stdout.lower() and "installed" in result.stdout.lower():
                return True
            # Fallback: try launching to verify
            with sync_playwright() as p:
                _ns = os.getenv("COOKIE_NO_SANDBOX", "0") == "1" or (
                    getattr(os, "geteuid", lambda: -1)() == 0
                )
                _ns_args = ["--no-sandbox"] if _ns else []
                browser = p.chromium.launch(headless=True, args=_ns_args)
                browser.close()
                return True
        except Exception:
            return False

    @staticmethod
    def install_browser() -> bool:
        """Auto-install Chromium browser for Playwright. Returns True on success."""
        try:
            import subprocess
            _log.info("Đang tự động cài đặt Chromium cho Playwright...")
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                _log.info("Cài đặt Chromium thành công")
                return True
            _log.warning("Cài đặt Chromium thất bại: %s", result.stderr)
            return False
        except Exception as e:
            _log.warning("Không thể tự động cài đặt Chromium: %s", e)
            return False

    @staticmethod
    def scrape_profile(
        profile_url: str,
        max_videos: int = 50,
        timeout_ms: int = 30000,
        headless: bool = True,
        proxy: Optional[str] = None,
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
        ua = _stealth.pick_user_agent()

        for attempt in range(3):
            try:
                with sync_playwright() as p:
                    _BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

                    launch_args = [
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process",
                    ]
                    _needs_ns = os.getenv("COOKIE_NO_SANDBOX", "0") == "1" or (
                        getattr(os, "geteuid", lambda: -1)() == 0
                    )
                    if _needs_ns:
                        launch_args.append("--no-sandbox")

                    proxy_settings = None
                    if proxy:
                        proxy_settings = {"server": proxy}

                    context = p.chromium.launch_persistent_context(
                        user_data_dir=str(_BROWSER_DATA_DIR),
                        headless=headless,
                        args=launch_args,
                        proxy=proxy_settings,
                        user_agent=ua,
                        viewport={"width": 1920, "height": 1080},
                        locale="en-US",
                        java_script_enabled=True,
                        ignore_default_args=["--enable-automation"],
                    )

                    context.add_init_script(_STEALTH_JS)
                    page = context.new_page()

                    # Block heavy resources to speed up
                    page.route(
                        re.compile(r"\.(png|jpg|jpeg|gif|svg|mp4|webm|woff2?)$"),
                        lambda route: route.abort(),
                    )

                    # Extra webdriver evasion via CDP
                    try:
                        cdp = context.new_cdp_session(page)
                        cdp.send("Page.addScriptToEvaluateOnNewDocument", {
                            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                        })
                    except Exception:
                        pass

                    page.goto(profile_url, wait_until="domcontentloaded", timeout=timeout_ms)

                    # Detect CAPTCHA / verification
                    captcha_detected = False
                    captcha_selectors = [
                        'text="Drag the slider"',
                        'text="Verify to continue"',
                        'text="Log in"',
                        '[class*="captcha"]',
                        '[class*="verify"]',
                        '#captcha-verify-image',
                        'text="Slide to verify"',
                        'text="Security check"',
                    ]
                    for sel in captcha_selectors:
                        try:
                            if page.query_selector(sel):
                                captcha_detected = True
                                break
                        except Exception:
                            pass

                    if captcha_detected and not headless:
                        _log.info("CAPTCHA detected — solve it in the browser window")
                        page.wait_for_timeout(60000)
                    elif captcha_detected:
                        _log.warning("CAPTCHA detected in headless mode, retrying")
                        context.close()
                        ua = _stealth.pick_user_agent()
                        time.sleep(2 * (attempt + 1))
                        continue

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

                        if len(video_ids) == prev_count and scroll_attempts > 2:
                            break
                        prev_count = len(video_ids)

                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(random.randint(1200, 2500))

                    context.close()

                # Got results, return immediately
                if video_ids:
                    break

            except Exception as e:
                _log.warning("Browser scraping attempt %d failed: %s", attempt + 1, e)
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    ua = _stealth.pick_user_agent()

        # Build URLs
        username_match = re.search(r"@([a-zA-Z0-9_.\-]+)", profile_url)
        username = username_match.group(1) if username_match else ""
        base = "https://www.douyin.com" if "douyin.com" in profile_url else "https://www.tiktok.com"
        return [f"{base}/@{username}/video/{vid}" for vid in video_ids[:max_videos]]
