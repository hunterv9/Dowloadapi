"""Douyin API client — extracts metadata, captions and direct CDN streams.

Built on :class:`core.base_api.BasePlatformAPI` so the HTTP/session and
streaming support is shared with the TikTok client.
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

__all__ = ["DouyinAPI"]


class DouyinAPI(BasePlatformAPI):
    """100% Official direct Douyin engine — clean & isolated module."""

    PLATFORM = "douyin"
    ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,en;q=0.8"
    REFERER = "https://www.douyin.com/"
    SHORT_MARKERS = ("v.douyin.com",)

    def extract_video_id(self, url: str) -> Optional[str]:
        """Pull a numeric Douyin video ID from a URL or bare ID."""
        url = url.strip()
        match = re.search(r"/video/(\d+)", url) or re.search(r"modal_id=(\d+)", url)
        if match:
            return match.group(1)
        match_id = re.search(r"^\d+$", url)
        if match_id:
            return match_id.group(0)
        return None

    def get_video_info(self, url_or_id: str) -> Dict[str, Any]:
        """Extract Douyin metadata, captions and direct CDN stream URL."""
        url = url_or_id.strip()
        video_id = self.extract_video_id(url)

        if not url.startswith("http"):
            url = f"https://www.douyin.com/video/{video_id or url}"
        else:
            url = self.resolve_shortlink(url, self.SHORT_MARKERS)
            video_id = video_id or self.extract_video_id(url)

        if not video_id:
            raise Exception("Không thể nhận diện ID video Douyin từ liên kết.")

        headers = self._headers(
            user_agent=IPHONE_USER_AGENT,
            accept_language=self.ACCEPT_LANGUAGE,
            referer=self.REFERER,
        )

        title = "Douyin Video"
        user_id = "douyin_user"
        nickname = "Douyin Creator"
        thumbnail_url = ""
        duration = 0
        stream_url = None
        captions: List[Dict[str, str]] = []

        # 1) Official Douyin mobile share endpoint
        ies_url = f"https://www.iesdouyin.com/share/video/{video_id}"
        resp = self._request_with_retry("GET", ies_url, headers=headers)
        if resp.status_code == 200:
            data = self.extract_json_script(resp.text, "_ROUTER_DATA")
            if data:
                loader = data.get("loaderData", {})
                for value in loader.values():
                    if isinstance(value, dict) and "videoInfoRes" in value:
                        items = value.get("videoInfoRes", {}).get("item_list", [])
                        if not items:
                            continue
                        it = items[0]
                        title = it.get("desc") or title
                        author = it.get("author", {}) or {}
                        if isinstance(author, dict):
                            nickname = author.get("nickname") or nickname
                            user_id = (
                                author.get("unique_id")
                                or author.get("short_id")
                                or user_id
                            )
                        vid_info = it.get("video", {}) or {}
                        cover_list = (vid_info.get("cover") or {}).get("url_list") or []
                        if cover_list:
                            thumbnail_url = cover_list[0]
                        duration = (it.get("duration") or 0) / 1000
                        play_urls = (
                            (vid_info.get("play_addr") or {}).get("url_list") or []
                        )
                        if play_urls:
                            stream_url = play_urls[0].replace("/playwm/", "/play/")
                        captions.extend(self.find_subtitle_entries(it))
                        break
# 2) Fallback: direct official Douyin play endpoint
        if not stream_url:
            stream_url = (
                f"https://aweme.snssdk.com/aweme/v1/play/"
                f"?video_id={video_id}&ratio=1080p&line=0"
            )

        return {
            "success": True,
            "platform": self.PLATFORM,
            "id": video_id,
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

        sec_user_id = None
        max_cursor = 0
        has_more = False

        data = self.extract_json_script(html, "_ROUTER_DATA")
        if data:
            loader = data.get("loaderData", {})
            for value in loader.values():
                if not isinstance(value, dict):
                    continue
                user_info = (
                    value.get("user", {}).get("userInfo", {}).get("user", {}) or {}
                )
                sec_user_id = sec_user_id or user_info.get("sec_uid") or user_info.get("secUid")
                if "videoList" in value:
                    items = value.get("videoList", {})
                    if isinstance(items, dict):
                        for item in items.get("list", []):
                            vid = str(item.get("id", "") or item.get("video_id", ""))
                            if vid and vid not in video_ids:
                                video_ids.append(vid)
                            if len(video_ids) >= max_videos:
                                break
                        if isinstance(items.get("has_more"), bool):
                            has_more = items.get("has_more")
                        elif isinstance(items.get("hasMore"), bool):
                            has_more = items.get("hasMore")
                        max_cursor = items.get("max_cursor") or items.get("maxCursor") or max_cursor

        pages = 0
        max_pages = max(50, (max_videos // 18) + 5)
        while len(video_ids) < max_videos and sec_user_id and has_more and pages < max_pages:
            pages += 1
            try:
                r = self.session.get(
                    "https://www.douyin.com/aweme/v1/web/aweme/post/",
                    params={
                        "sec_user_id": sec_user_id,
                        "max_cursor": max_cursor,
                        "count": 18,
                        "device_platform": "webapp",
                    },
                    headers=self._headers(
                        user_agent=PC_USER_AGENT,
                        accept_language=self.ACCEPT_LANGUAGE,
                        referer=self.REFERER,
                    ),
                    timeout=15,
                )
                r.raise_for_status()
                body = r.json()
            except Exception:
                break
            for item in (body.get("aweme_list") or []):
                vid = str(item.get("aweme_id", "") or item.get("id", ""))
                if vid and vid not in video_ids:
                    video_ids.append(vid)
                if len(video_ids) >= max_videos:
                    break
            has_more = bool(body.get("has_more"))
            max_cursor = body.get("max_cursor") or max_cursor

        user_match = re.search(r"/@([a-zA-Z0-9_.\-]+)", profile_url)
        username = f"@{user_match.group(1)}" if user_match else ""

        return [
            f"https://www.douyin.com/{username}/video/{vid}"
            for vid in video_ids[:max_videos]
        ]