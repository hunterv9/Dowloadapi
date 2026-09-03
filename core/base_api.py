"""Shared base class for TikTok & Douyin platform API clients.

Houses all HTTP/session handling, streaming downloads, short-link
resolution, regex video-ID extraction and subtitle (caption) discovery
that both platforms share — eliminating duplication between
:mod:`core.tiktok_api` and :mod:`core.douyin_api`.
"""

import json
import logging
import re
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
)

import requests

_log = logging.getLogger(__name__)

__all__ = ["BasePlatformAPI", "IPHONE_USER_AGENT", "PC_USER_AGENT"]

IPHONE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)
PC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# JSON keys that may contain subtitle/caption data inside parsed payloads.
_SUBTITLE_KEYS = (
    "subtitles",
    "subtitle",
    "subtitleInfos",
    "caption",
    "captions",
    "video_subtitle",
    "srt_info",
)


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Strip characters that are illegal on Windows/Unix and collapse spaces."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_length]


class BasePlatformAPI:
    """Abstract base for a platform-specific (TikTok / Douyin) API client."""

    #: human readable platform tag, e.g. ``"tiktok"``
    PLATFORM = "unknown"
    #: Accept-Language fallback sent with requests
    ACCEPT_LANGUAGE = "en-US,en;q=0.9"
    #: canonical referer header
    REFERER = "https://unknown.com/"

    def __init__(self, cookie_string: Optional[str] = None):
        self.cookie_string = cookie_string or ""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": IPHONE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": self.REFERER,
        })
        if self.cookie_string:
            self.session.headers["Cookie"] = self.cookie_string

    # -- cookie / session helpers --------------------------------------- #
    def _recreate_session(self) -> None:
        """Create a fresh ``requests.Session`` (new TLS handshake)."""
        self.session.close()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": IPHONE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": self.REFERER,
        })
        if self.cookie_string:
            self.session.headers["Cookie"] = self.cookie_string

    def set_cookie_string(self, cookie_string: str) -> None:
        """Set (or clear) the Cookie header used for authenticated requests."""
        self.cookie_string = cookie_string or ""
        if self.cookie_string:
            self.session.headers["Cookie"] = self.cookie_string
        elif "Cookie" in self.session.headers:
            del self.session.headers["Cookie"]

    def _headers(
        self,
        user_agent: Optional[str] = None,
        referer: Optional[str] = None,
        accept_language: Optional[str] = None,
    ) -> Dict[str, str]:
        """Build per-request headers while preserving any active cookie."""
        headers: Dict[str, str] = {
            "User-Agent": user_agent or IPHONE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": referer or self.REFERER,
        }
        if accept_language:
            headers["Accept-Language"] = accept_language
        elif self.ACCEPT_LANGUAGE:
            headers["Accept-Language"] = self.ACCEPT_LANGUAGE
        if self.cookie_string:
            headers["Cookie"] = self.cookie_string
        return headers

    # -- short-link resolution ------------------------------------------ #
    def resolve_shortlink(self, raw_url: str, short_markers) -> str:
        """Follow redirects for short-links.

        Returns the cleaned (query-stripped) URL; falls back to the raw
        input when the request fails.
        """
        raw_url = raw_url.strip()
        if any(marker in raw_url for marker in short_markers):
            try:
                r = self.session.head(raw_url, allow_redirects=True, timeout=10)
                return r.url.split("?")[0]
            except Exception:
                pass
        return raw_url.split("?")[0]

    # -- HTML / JSON extraction helpers -------------------------------- #
    @staticmethod
    def extract_json_script(html: str, script_id: str) -> Optional[Dict[str, Any]]:
        """Parse JSON embedded in ``<script id=...>`` blocks.

        Handles both quoted JSON (``<script id="x">{...}</script>``) and
        unquoted JSON (``window._ROUTER_DATA = {...}</script>``).
        """
        patterns = (
            re.compile(
                rf'<script id="{re.escape(script_id)}"[^>]*>([\s\S]*?)</script>', re.I
            ),
            re.compile(
                rf'window\.{re.escape(script_id)}\s*=\s*(\{{[\s\S]*?\}})\s*</script>',
                re.I,
            ),
        )
        for pattern in patterns:
            match = pattern.search(html)
            if match:
                try:
                    return json.loads(match.group(1))
                except (json.JSONDecodeError, TypeError):
                    continue
        return None

    @staticmethod
    def extract_video_ids(html: str, max_videos: int) -> List[str]:
        """Collect unique numeric video IDs from ``/video/<id>`` matches."""
        video_ids: List[str] = []
        seen: set = set()
        for match in re.finditer(r"/video/(\d+)", html):
            vid = match.group(1)
            if vid and vid not in seen:
                seen.add(vid)
                video_ids.append(vid)
            if len(video_ids) >= max_videos:
                break
        return video_ids

    # -- caption / subtitle discovery ---------------------------------- #
    @staticmethod
    def find_subtitle_entries(value: Any, max_items: int = 20) -> List[Dict[str, str]]:
        """Recursively walk JSON and collect caption entries.

        Returns a list of ``{"lang": ..., "url": ...}`` dicts. Tolerates
        multiple payload shapes so it keeps working as platforms evolve.
        """
        results: List[Dict[str, str]] = []

        def is_subtitle_key(key: Any) -> bool:
            return isinstance(key, str) and key in _SUBTITLE_KEYS

        def push_lang(entry: dict) -> str:
            code = entry.get("LanguageCode") or entry.get("lang") or entry.get("language")
            return str(code).lower() if code else "auto"

        def first_url(entry: dict) -> Optional[str]:
            url = entry.get("url")
            if isinstance(url, str) and url:
                return url
            url_list = entry.get("url_list")
            if isinstance(url_list, list) and url_list and isinstance(url_list[0], str):
                return url_list[0]
            return None

        def walk(node: Any):
            if len(results) >= max_items:
                return
            if isinstance(node, list):
                for child in node:
                    walk(child)
                return
            if not isinstance(node, dict):
                return
            for key, value in node.items():
                if is_subtitle_key(key) and isinstance(value, list):
                    for entry in value:
                        url = first_url(entry) if isinstance(entry, dict) else None
                        if url:
                            results.append({"lang": push_lang(entry), "url": url})
                            if len(results) >= max_items:
                                return
                walk(value)

        walk(value)
        return results

    # -- retry helper ---------------------------------------------------- #
    def _request_with_retry(
        self, method: str, url: str, max_retries: int = 3, **kwargs
    ) -> requests.Response:
        """HTTP request with automatic retry on transient failures.

        On SSL errors the session is recreated to get a fresh TLS handshake.
        """
        kwargs.setdefault("timeout", 15)
        last_exc = None
        for attempt in range(max_retries):
            try:
                resp = self.session.request(method, url, **kwargs)
                if resp.status_code < 500:
                    return resp
                last_exc = Exception(f"HTTP {resp.status_code}")
            except requests.exceptions.SSLError as e:
                last_exc = e
                _log.warning("SSL error on attempt %d, recreating session: %s", attempt + 1, e)
                self._recreate_session()
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
            if attempt < max_retries - 1:
                import time
                time.sleep(1 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    # -- streaming download — shared by both platforms -------------------- #
    def download_stream(
        self,
        download_url: str,
        output_file: str,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> str:
        """Stream a media file to disk in 64KB chunks, reporting progress."""
        headers = self._headers(user_agent=IPHONE_USER_AGENT, referer=self.REFERER)
        headers["Range"] = "bytes=0-"

        output_path = Path(output_file)
        if not output_path.suffix:
            output_path = output_path.with_suffix(".mp4")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        resp = self.session.get(
            download_url, headers=headers, stream=True, allow_redirects=True, timeout=30
        )
        resp.raise_for_status()

        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 64 * 1024

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    percent = (downloaded / total_size * 100) if total_size > 0 else 0
                    progress_callback(downloaded, total_size, percent)

        return str(output_path)

    # -- subcontractors must implement ------------------------------------ #
    def extract_video_id(self, url: str) -> Optional[str]:
        raise NotImplementedError

    def get_video_info(self, url: str) -> Dict[str, Any]:
        raise NotImplementedError

    def scrape_profile_urls(self, profile_url: str, max_videos: int = 50) -> List[str]:
        """Scrape a profile for video URLs (up to *max_videos*).

        Strategy (in order):
          1. yt-dlp — handles playlist extraction and anti-bot logic
          2. Headless browser (Playwright) — renders JS, bypasses WAF
          3. HTML regex + embedded JSON — last resort (platform-specific)
        """
        profile_url = self.resolve_shortlink(profile_url, self.SHORT_MARKERS)
        limit = max_videos or None  # 0 → unlimited

        # --- 1. yt-dlp ---
        urls = self._scrape_via_ytdlp(profile_url, limit)
        if urls:
            return urls

        # --- 2. Headless browser ---
        from .browser_scraper import BrowserScraper
        fallback = limit or 50
        if not BrowserScraper.is_available():
            _log.info("Playwright chưa sẵn sàng, đang thử tự động cài đặt Chromium...")
            BrowserScraper.install_browser()
        if BrowserScraper.is_available():
            for headless in (True, False):
                try:
                    urls = BrowserScraper.scrape_profile(
                        profile_url, fallback, headless=headless
                    )
                except Exception as e:
                    _log.warning(
                        "Browser profile scrape failed (headless=%s): %s",
                        headless,
                        e,
                    )
                    continue
                if urls:
                    return urls
        else:
            _log.warning(
                "Không thể cài đặt Playwright. Chạy 'pip install playwright && playwright install chromium' để bật tính năng quét profile tự động."
            )

        # --- 3. HTML fallback (platform-specific) ---
        return self._scrape_via_html(profile_url, fallback)

    def _scrape_via_ytdlp(
        self, profile_url: str, max_videos: Optional[int]
    ) -> List[str]:
        """Use yt-dlp to list video URLs from a profile (handles anti-bot)."""
        import os
        import time
        try:
            import yt_dlp
        except ImportError:
            _log.warning("yt-dlp not installed, falling back to HTML scraping")
            return []

        # Suppress yt-dlp's direct stderr prints (e.g. "Unable to extract
        # secondary user ID") which bypass the quiet/logger settings.
        _orig_stderr = None
        try:
            _orig_stderr = os.dup(2)
            os.dup2(os.open(os.devnull, os.O_WRONLY), 2)
        except OSError:
            _orig_stderr = None

        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "ignoreerrors": True,
            "socket_timeout": 30,
            "geo_bypass": True,
            "no_check_certificates": True,
        }
        if max_videos:
            ydl_opts["playlistend"] = max_videos
        if self.cookie_string:
            ydl_opts["cookiefile"] = None
            ydl_opts["http_headers"] = {"Cookie": self.cookie_string}

        try:
            for attempt in range(3):
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(profile_url, download=False)
                    if not info or "entries" not in info:
                        return []
                    urls = []
                    for entry in info["entries"]:
                        if not entry:
                            continue
                        url = entry.get("webpage_url") or entry.get("url")
                        if url:
                            urls.append(url)
                        if max_videos and len(urls) >= max_videos:
                            break
                    if urls:
                        return urls
                except Exception as e:
                    _log.warning("yt-dlp attempt %d failed: %s", attempt + 1, e)
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
            return []
        finally:
            # Restore stderr
            if _orig_stderr is not None:
                try:
                    os.close(2)
                    os.dup2(_orig_stderr, 2)
                    os.close(_orig_stderr)
                except OSError:
                    pass

    def _scrape_via_html(self, profile_url: str, max_videos: int) -> List[str]:
        """Platform-specific HTML fallback. Subclasses must override."""
        raise NotImplementedError