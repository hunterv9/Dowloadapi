"""Unified TikTok / Douyin direct video downloader."""

import re
import json
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List

from .base_api import sanitize_filename
from .cookie_manager import CookieManager
from .tiktok_api import TikTokAPI
from .douyin_api import DouyinAPI


class TikTokDownloader:
    """Unified direct video downloader for TikTok & Douyin — zero 3rd party APIs."""

    def __init__(self, cookie_manager: Optional[CookieManager] = None):
        self.cookie_manager = cookie_manager or CookieManager()
        self.tiktok_api = TikTokAPI()
        self.douyin_api = DouyinAPI()
        self._refresh_cookies()

    # -- cookie management --------------------------------------------------
    def _refresh_cookies(self) -> None:
        """Re-read cookies from the cookie manager and propagate to API clients."""
        cookie_str = self.cookie_manager.get_active_cookie_string()
        self.tiktok_api.set_cookie_string(cookie_str)
        self.douyin_api.set_cookie_string(cookie_str)

    def refresh_cookies(self) -> None:
        """Public entry point to refresh cookies after a config change."""
        self._refresh_cookies()

    # -- routing helpers ----------------------------------------------------
    def is_douyin(self, url: str) -> bool:
        return "douyin.com" in url or "iesdouyin.com" in url

    def get_api(self, url: str):
        """Return the appropriate API client for *url* with fresh cookies."""
        self._refresh_cookies()
        if self.is_douyin(url):
            return self.douyin_api
        return self.tiktok_api

    def sanitize_filename(self, name: str) -> str:
        return sanitize_filename(name)

    # -- public API ---------------------------------------------------------
    def get_video_info(self, url: str) -> Dict[str, Any]:
        api = self.get_api(url)
        return api.get_video_info(url)

    def get_info(self, url: str) -> Dict[str, Any]:
        """Alias for :meth:`get_video_info` — backward compatibility."""
        return self.get_video_info(url)

    def download_video_with_info(
        self,
        url: str,
        info: Dict[str, Any],
        custom_output_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> Dict[str, Any]:
        """Download a video using pre-fetched info (avoids duplicate API call)."""
        api = self.get_api(url)

        download_dir = Path(
            custom_output_dir or self.cookie_manager.config.get("download_dir", "./downloads")
        )
        download_dir.mkdir(parents=True, exist_ok=True)

        uploader = sanitize_filename(info.get("uploader") or "creator")
        title = sanitize_filename(info.get("title") or "video")
        video_id = info.get("id") or "video"
        platform = "douyin" if self.is_douyin(url) else "tiktok"

        filename = f"{platform}_{uploader}_{video_id}_{title}.mp4"
        output_file = str(download_dir / filename)

        # Download stream
        saved_path = api.download_stream(
            download_url=info["download_url"],
            output_file=output_file,
            progress_callback=progress_callback,
        )

        # Save metadata if configured
        if self.cookie_manager.config.get("save_metadata", True):
            meta_file = download_dir / f"{platform}_{uploader}_{video_id}_{title}.info.json"
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2, ensure_ascii=False)

        info["saved_path"] = saved_path
        info["filename"] = filename

        # Capture download alongside when available (reuses already-fetched info)
        subtitles = (
            self.download_subtitles(url, base_dir=download_dir, info=info)
            if info.get("captions")
            else []
        )
        if subtitles:
            info["subtitle_files"] = subtitles
        return info

    def download_video(
        self,
        url: str,
        custom_output_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> Dict[str, Any]:
        """Resolve, then download a single TikTok or Douyin video."""
        api = self.get_api(url)
        info = api.get_video_info(url)
        return self.download_video_with_info(
            url, info,
            custom_output_dir=custom_output_dir,
            progress_callback=progress_callback,
        )

    def download_subtitles(
        self,
        url: str,
        base_dir=None,
        info: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Download every caption attached to a video as ``.srt``/``.vtt``.

        Returns the list of written subtitle file paths (empty when the
        platform provides no captions).
        """
        if info is None:
            info = self.get_video_info(url)
        captions = info.get("captions") or []
        if not captions:
            return []

        api = self.get_api(url)
        download_dir = Path(base_dir or self.cookie_manager.config.get("download_dir", "./downloads"))
        download_dir.mkdir(parents=True, exist_ok=True)

        uploader = sanitize_filename(info.get("uploader") or "creator")
        title = sanitize_filename(info.get("title") or "video")
        video_id = info.get("id") or "video"
        platform = "douyin" if self.is_douyin(url) else "tiktok"
        stem = f"{platform}_{uploader}_{video_id}_{title}"

        saved = []
        for caption in captions:
            raw_lang = sanitize_filename(caption.get("lang") or "auto") or "auto"
            lang = raw_lang[:8]
            caption_url = caption.get("url")
            if not caption_url:
                continue
            try:
                r = api.session.get(caption_url, headers=api._headers(), timeout=15)
                if r.status_code != 200:
                    continue
                content_type = r.headers.get("content-type", "")
                ext = ".vtt" if "webvtt" in content_type.lower() else ".srt"
                target = download_dir / f"{stem}.{lang}{ext}"
                target.write_bytes(r.content)
                saved.append(str(target))
            except Exception:
                continue

        return saved
