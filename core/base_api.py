"""Shared base class for TikTok & Douyin platform API clients.

Houses all HTTP/session handling, streaming downloads, short-link
resolution, regex video-ID extraction and subtitle (caption) discovery
that both platforms share — eliminating duplication between
:mod:`core.tiktok_api` and :mod:`core.douyin_api`.
"""

import json
import logging
import os
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

from . import stealth as _stealth
from .exceptions import AuthError, NotFoundError, PlatformError, RateLimitError
from .url_validator import validate_url, validate_stream_url

_log = logging.getLogger(__name__)

__all__ = ["BasePlatformAPI", "IPHONE_USER_AGENT", "PC_USER_AGENT"]

# Single source: core/stealth.py (Chrome 126). Re-exported here for compat.
from .stealth import IPHONE_USER_AGENT, PC_USER_AGENT  # noqa: F401,E402

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
        # Keep-alive pool sized for thread concurrency (batch downloads).
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, pool_maxsize=32, max_retries=0)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        if self.cookie_string:
            self.session.headers["Cookie"] = self.cookie_string

    @staticmethod
    def _bucket_for(url: str) -> str:
        """Bucket name for pacing — the request host, fallback 'scrape'."""
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or ""
            return host.lower() or "scrape"
        except Exception:
            return "scrape"

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
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, pool_maxsize=32, max_retries=0)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
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
        """Build per-request headers while preserving any active cookie.

        Uses a rotated browser-like header set (anti-fingerprint) unless a
        specific *user_agent* is requested (e.g. mobile UA for CDN streams).
        """
        headers = _stealth.browser_like_headers(
            user_agent=user_agent, referer=referer or self.REFERER)
        if accept_language:
            headers["Accept-Language"] = accept_language
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
        validate_url(raw_url)
        if any(marker in raw_url for marker in short_markers):
            try:
                r = self.session.head(raw_url, allow_redirects=True, timeout=10)
                validate_url(r.url)
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
        """HTTP request with pacing, jittered retry and 429 compliance.

        * every attempt is paced per-domain (token bucket + jitter) so
          concurrent workers can't produce metronome-like bursts;
        * 429 honours ``Retry-After`` and triggers a cool-down every 3rd
          consecutive hit on the same host;
        * 5xx / network errors use exponential backoff with full jitter;
        * other 4xx fail fast (retrying them only burns quota and flags us).
        On SSL errors the session is recreated to get a fresh TLS handshake.
        """
        validate_url(url)
        kwargs.setdefault("timeout", 15)
        bucket = self._bucket_for(url)
        last_exc = None
        for attempt in range(max_retries):
            _stealth.pace_before_request(bucket)
            try:
                resp = self.session.request(method, url, **kwargs)
                if resp.status_code == 429:
                    wait = _stealth.retry_after_seconds(resp.headers.get("Retry-After"))
                    if wait:
                        import time
                        time.sleep(wait)
                    _stealth.note_429(bucket)
                    last_exc = RateLimitError(f"HTTP 429", status_code=429)
                elif resp.status_code >= 500:
                    last_exc = PlatformError(f"HTTP {resp.status_code}", status_code=resp.status_code)
                elif resp.status_code >= 400:
                    # ponytail: ceiling=4xx fail fast no retry; upgrade path=retry-after/backoff for 429 only.
                    code = resp.status_code
                    msg = f"HTTP {code}"
                    if code in (401, 403):
                        raise AuthError(msg, status_code=code)
                    if code == 404:
                        raise NotFoundError(msg, status_code=code)
                    if code == 429:
                        raise RateLimitError(msg, status_code=code)
                    raise PlatformError(msg, status_code=code)
                else:
                    _stealth.note_success(bucket)
                    return resp
            except requests.exceptions.SSLError as e:
                last_exc = e
                _log.warning("SSL error on attempt %d, recreating session: %s", attempt + 1, e)
                self._recreate_session()
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
            if attempt < max_retries - 1:
                _stealth.backoff_sleep(attempt)
        raise last_exc  # type: ignore[misc]

    # -- streaming download — shared by both platforms -------------------- #
    @staticmethod
    def _max_download_bytes() -> int:
        """Cap for a single streamed download (default 500MB)."""
        try:
            return int(os.getenv("MAX_DOWNLOAD_BYTES", str(500 * 1024 * 1024)))
        except (TypeError, ValueError):
            return 500 * 1024 * 1024

    def download_stream(
        self,
        download_url: str,
        output_file: str,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> str:
        """Stream a media file to disk in 64KB chunks, reporting progress."""
        validate_stream_url(download_url)
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

        limit = self._max_download_bytes()
        try:
            total_size = int(resp.headers.get("content-length", 0))
        except (TypeError, ValueError):
            total_size = 0
        if total_size > limit:
            raise PlatformError(
                f"Content-Length {total_size} exceeds limit {limit}",
                status_code=413,
            )
        downloaded = 0
        chunk_size = 64 * 1024

        try:
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > limit:
                        raise PlatformError(
                            f"Download exceeded limit {limit}",
                            status_code=413,
                        )
                    if progress_callback:
                        percent = (downloaded / total_size * 100) if total_size > 0 else 0
                        progress_callback(downloaded, total_size, percent)
        except Exception:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        # Refuse symlink escapes: final file must resolve inside target dir.
        resolved = output_path.resolve(strict=True)
        if output_path.is_symlink() or not resolved.is_relative_to(
            output_path.parent.resolve()
        ):
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise PlatformError("Refusing symlink download path")

        return str(output_path)

    # -- subcontractors must implement ------------------------------------ #
    def extract_video_id(self, url: str) -> Optional[str]:
        raise NotImplementedError

    def get_video_info(self, url: str) -> Dict[str, Any]:
        raise NotImplementedError

    def scrape_profile_urls(self, profile_url: str, max_videos: int = 50) -> List[str]:
        """Scrape a profile for video URLs (up to *max_videos*).

        Strategy (in order):
          1. Headless browser (Playwright) — renders JS, bypasses WAF
          2. HTML regex + embedded JSON — last resort (platform-specific)
        """
        profile_url = self.resolve_shortlink(profile_url, self.SHORT_MARKERS)
        limit = max_videos or None  # 0 → unlimited

        # --- 1. Headless browser ---
        from .browser_scraper import BrowserScraper
        fallback = limit or 50
        if BrowserScraper.is_available():
            # Headed fallback (solving CAPTCHA by hand) is opt-in only:
            # on a headless Ubuntu server it would crash/hang the request.
            modes = (True, False) if _stealth.headed_allowed() else (True,)
            for headless in modes:
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
            # No mid-request installs: `playwright install` can take minutes
            # and would stall API requests. Install at deploy time instead.
            _log.warning(
                "Playwright chưa có. Chạy 'pip install playwright && playwright install chromium' để bật quét profile tự động."
            )

        # --- 2. HTML fallback (platform-specific) ---
        return self._scrape_via_html(profile_url, fallback)

    def _scrape_via_html(self, profile_url: str, max_videos: int) -> List[str]:
        """Platform-specific HTML fallback. Subclasses must override."""
        raise NotImplementedError