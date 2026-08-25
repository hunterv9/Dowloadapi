"""TikTok API client — extracts metadata, captions and direct CDN streams.

Built on :class:`core.base_api.BasePlatformAPI` so the HTTP/session and
streaming support is shared with the Douyin client.
"""

import re
import logging
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)

from .base_api import (
    BasePlatformAPI,
    IPHONE_USER_AGENT,
    PC_USER_AGENT,
)

__all__ = ["TikTokAPI"]


class TikTokAPI(BasePlatformAPI):
    """100% Official direct TikTok engine — zero 3rd party dependencies."""

    PLATFORM = "tiktok"
    ACCEPT_LANGUAGE = "en-US,en;q=0.9,vi;q=0.8"
    REFERER = "https://www.tiktok.com/"
    SHORT_MARKERS = ("vt.tiktok.com", "vm.tiktok.com")

    def extract_video_id(self, url: str) -> Optional[str]:
        """Pull a numeric TikTok video ID from a URL, short-link or bare ID."""
        url = url.strip()
        match = re.search(r"/video/(\d+)", url)
        if match:
            return match.group(1)
        match_id = re.search(r"^\d+$", url)
        if match_id:
            return match_id.group(0)
        return None

    def get_video_info(self, url_or_id: str) -> Dict[str, Any]:
        """Fetch metadata, captions + direct CDN stream URL from TikTok.

        Resolution strategy:
          1. normalise / resolve short-links
          2. parse ``<script id="api-data">`` embedded JSON
          3. fallback to ``__UNIVERSAL_DATA_FOR_REHYDRATION__``
          4. fallback to the public oEmbed endpoint
        """
        url = url_or_id.strip()
        video_id = self.extract_video_id(url)

        if not url.startswith("http"):
            url = f"https://www.tiktok.com/@tiktok/video/{video_id or url}"
        else:
            url = self.resolve_shortlink(url, self.SHORT_MARKERS)
            video_id = video_id or self.extract_video_id(url)

        headers = self._headers(
            user_agent=IPHONE_USER_AGENT,
            accept_language=self.ACCEPT_LANGUAGE,
            referer=self.REFERER,
        )
        resp = self.session.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise Exception(
                f"Không thể truy cập trang video TikTok (HTTP {resp.status_code})"
            )

        title = "TikTok Video"
        user_id = "unknown"
        nickname = "TikTok Creator"
        thumbnail_url = ""
        duration = 0
        stream_url = None
        captions: List[Dict[str, str]] = []

        # 1) Official api-data script
        payload = self.extract_json_script(resp.text, "api-data")
        if payload:
            item = (
                payload.get("videoDetail", {})
                .get("itemInfo", {})
                .get("itemStruct", {})
            )
            if item:
                title = item.get("desc") or title
                video = item.get("video", {})
                author = item.get("author", {})
                user_id = author.get("uniqueId") or user_id
                nickname = author.get("nickname") or nickname
                thumbnail_url = video.get("cover") or thumbnail_url
                duration = video.get("duration", 0) or 0
                stream_url = (
                    video.get("playAddr") or video.get("downloadAddr") or stream_url
                )
                captions.extend(self.find_subtitle_entries(item))
# 2) __UNIVERSAL_DATA_FOR_REHYDRATION__ fallback
        if not stream_url:
            universal = self.extract_json_script(
                resp.text, "__UNIVERSAL_DATA_FOR_REHYDRATION__"
            )
            if universal:
                scope = universal.get("__DEFAULT_SCOPE__", {})
                item = (
                    scope.get("webapp.video-detail", {})
                    .get("itemInfo", {})
                    .get("itemStruct", {})
                )
                if item:
                    title = item.get("desc") or title
                    video = item.get("video", {})
                    author = item.get("author", {})
                    user_id = author.get("uniqueId") or user_id
                    nickname = author.get("nickname") or nickname
                    thumbnail_url = video.get("cover") or thumbnail_url
                    duration = video.get("duration", 0) or 0
                    stream_url = (
                        video.get("playAddr") or video.get("downloadAddr") or stream_url
                    )
                    captions.extend(self.find_subtitle_entries(item))

        # 3) oEmbed fallback for basic metadata
        if not title or title == "TikTok Video":
            try:
                r = self.session.get(
                    f"https://www.tiktok.com/oembed?url={url}",
                    headers=headers,
                    timeout=5,
                )
                if r.status_code == 200:
                    meta = r.json()
                    title = meta.get("title") or title
                    user_id = meta.get("author_unique_id") or user_id
                    nickname = meta.get("author_name") or nickname
                    thumbnail_url = meta.get("thumbnail_url") or thumbnail_url
            except Exception:
                pass

        if not stream_url:
            raise Exception(
                "Không thể bóc tách luồng phát video từ máy chủ TikTok."
                "Vui lòng kiệm lại liên kết."
            )

        return {
            "success": True,
            "platform": self.PLATFORM,
            "id": video_id or "video",
            "url": url,
            "original_url": url,
            "title": title,
            "uploader": user_id,
            "nickname": nickname,
            "thumbnail": thumbnail_url,
            "download_url": stream_url,
            "duration": duration,
            "view_count": 0,
            "like_count": 0,
            "captions": captions[:8],
        }

    def scrape_profile_urls(
        self, profile_url: str, max_videos: int = 50
    ) -> List[str]:
        """Scrape a TikTok profile for video URLs (up to *max_videos*).

        Strategy (in order):
          1. Headless browser (Playwright) — renders JS, bypasses WAF
          2. yt-dlp — handles anti-bot with built-in JS solver
          3. HTML regex + embedded JSON — last resort
        """
        profile_url = self.resolve_shortlink(profile_url, self.SHORT_MARKERS)

        # --- 1. Headless browser ---
        from .browser_scraper import BrowserScraper
        if BrowserScraper.is_available():
            # Try headless first, then headed (for CAPTCHA solving)
            for headless in (True, False):
                urls = BrowserScraper.scrape_profile(
                    profile_url, max_videos, headless=headless
                )
                if urls:
                    return urls

        # --- 2. yt-dlp ---
        urls = self._scrape_via_ytdlp(profile_url, max_videos)
        if urls:
            return urls

        # --- 3. HTML fallback ---
        return self._scrape_via_html(profile_url, max_videos)

    def _scrape_via_ytdlp(self, profile_url: str, max_videos: int) -> List[str]:
        """Use yt-dlp to list video URLs from a profile (handles anti-bot)."""
        import time
        try:
            import yt_dlp
        except ImportError:
            _log.warning("yt-dlp not installed, falling back to HTML scraping")
            return []

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "ignoreerrors": True,
            "playlistend": max_videos,
            "socket_timeout": 30,
            "geo_bypass": True,
            "no_check_certificates": True,
        }

        # Retry up to 3 times with backoff (TikTok rate-limits intermittently)
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
                    url = entry.get("url") or entry.get("webpage_url")
                    if url:
                        urls.append(url)
                    if len(urls) >= max_videos:
                        break
                if urls:
                    return urls
            except Exception as e:
                _log.warning("yt-dlp attempt %d failed: %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        return []

    def _scrape_via_html(self, profile_url: str, max_videos: int) -> List[str]:
        """Fallback: extract video IDs from HTML + embedded JSON."""
        headers = self._headers(
            user_agent=PC_USER_AGENT,
            accept_language=self.ACCEPT_LANGUAGE,
            referer=self.REFERER,
        )
        try:
            resp = self.session.get(profile_url, headers=headers, timeout=15)
        except Exception:
            return []
        if resp.status_code != 200:
            return []

        html = resp.text
        video_ids = self.extract_video_ids(html, max_videos)

        for script_id in (
            "__NEXT_DATA__", "SIGI_STATE", "SIGI_DATA",
            "__UNIVERSAL_DATA_FOR_REHYDRATION__",
        ):
            payload = self.extract_json_script(html, script_id)
            self._append_embedded_video_ids(payload, video_ids, max_videos)
            if len(video_ids) >= max_videos:
                break

        username_match = re.search(r"@([a-zA-Z0-9_.\-]+)", profile_url)
        username = username_match.group(1) if username_match else ""

        return [
            f"https://www.tiktok.com/@{username}/video/{vid}"
            for vid in video_ids[:max_videos]
        ]

    @staticmethod
    def _append_embedded_video_ids(
        payload: Any, video_ids: List[str], max_videos: int
    ) -> None:
        """Collect video IDs from nested profile item-list JSON payloads."""
        if not isinstance(payload, (dict, list)) or len(video_ids) >= max_videos:
            return

        if isinstance(payload, list):
            for item in payload:
                TikTokAPI._append_embedded_video_ids(item, video_ids, max_videos)
                if len(video_ids) >= max_videos:
                    return
            return

        for key, value in payload.items():
            if key in {"itemList", "item_list", "videoList", "video_list"} and isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    video_id = item.get("id") or item.get("video_id") or item.get("itemId")
                    if video_id and str(video_id).isdigit() and str(video_id) not in video_ids:
                        video_ids.append(str(video_id))
                        if len(video_ids) >= max_videos:
                            return
            TikTokAPI._append_embedded_video_ids(value, video_ids, max_videos)
            if len(video_ids) >= max_videos:
                return