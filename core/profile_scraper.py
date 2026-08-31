"""Profile / batch scraper — resolve TikTok & Douyin profiles and download.

Responsibilities:
  * normalise profile input (TikTok or Douyin username / URL / file path)
  * resolve a profile or file into a concrete list of video URLs
  * download a batch of videos with an archive file to avoid re-downloads
  * concurrent downloads via ThreadPoolExecutor for speed
"""

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .base_api import sanitize_filename
from .cookie_manager import CookieManager
from .downloader import TikTokDownloader

__all__ = ["ProfileScraper"]

_FILE_MARKERS = (".txt", ".csv", ".list")

# Default concurrency — sweet spot for TikTok/Douyin rate limits
_DEFAULT_WORKERS = 4


def _is_douyin_input(value: str) -> bool:
    """Best-effort guess of which platform a bare handle targets."""
    return False  # bare handles default to TikTok; tracks carry their own domain


class ProfileScraper:
    """Resolve profile URLs or file-based URL lists and bulk download."""

    def __init__(self, cookie_manager: Optional[CookieManager] = None):
        self.cookie_manager = cookie_manager or CookieManager()
        self.downloader = TikTokDownloader(self.cookie_manager)
        self._archive_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # URL / username helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_username_from_url(url: str) -> Optional[str]:
        """Return a bare username from a TikTok/Douyin profile URL, if any."""
        at_handle = re.search(r"@([a-zA-Z0-9_.\-]+)", url)
        if at_handle:
            return at_handle.group(1)
        match = re.search(r"/(?:user|profile|@)/?([a-zA-Z0-9_.\-]+)", url)
        return match.group(1) if match else None

    def normalize_profile_url(self, profile_input: str) -> str:
        """Build a canonical profile URL for an @handle or profile URL."""
        profile_input = profile_input.strip()
        if profile_input.startswith(("http://", "https://")):
            username = self._extract_username_from_url(profile_input)
            if "tiktok.com" in profile_input and username:
                return f"https://www.tiktok.com/@{username}"
            if "douyin.com" in profile_input and username:
                return f"https://www.douyin.com/@{username}"
            return profile_input

        username = profile_input.lstrip("@")
        domain = "douyin.com" if _is_douyin_input(profile_input) else "tiktok.com"
        return f"https://www.{domain}/@{username}"

    def extract_username(self, profile_input: str) -> str:
        """Return a safe directory name for the given profile/input."""
        url = self.normalize_profile_url(profile_input)
        username = self._extract_username_from_url(url)
        if username:
            return username
        return sanitize_filename(profile_input.lstrip("@"))

    @staticmethod
    def is_file_input(target: str) -> bool:
        """Return True when *target* points to a local URL-list file."""
        t = target.strip().lower()
        return any(marker in t for marker in _FILE_MARKERS) and "://" not in t

    # ------------------------------------------------------------------ #
    # Archive helpers (thread-safe)
    # ------------------------------------------------------------------ #
    def load_archive(self, archive_path: Path) -> set:
        if not archive_path.exists():
            return set()
        with open(archive_path, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}

    def append_archive(self, archive_path: Path, video_id: str) -> None:
        with self._archive_lock:
            with open(archive_path, "a", encoding="utf-8") as f:
                f.write(f"{video_id}\n")

    # ------------------------------------------------------------------ #
    # URL resolution
    # ------------------------------------------------------------------ #
    def _read_file_list(self, file_path: str) -> List[str]:
        path = Path(file_path)
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def _api_for(self, profile_input: str):
        """Return the platform API client for a given profile URL/input."""
        if "douyin.com" in profile_input or self.downloader.is_douyin(profile_input):
            return self.downloader.douyin_api
        return self.downloader.tiktok_api

    def resolve_video_urls(
        self, profile_input: str, max_videos: int = 0
    ) -> List[str]:
        """Turn a profile, file path or URL list into concrete video URLs.

        When *max_videos* is 0 or falsy, fetches ALL available videos.
        """
        profile_input = profile_input.strip()
        if not profile_input:
            return []

        # File-based list of URLs
        if self.is_file_input(profile_input):
            urls = self._read_file_list(profile_input)
            return urls[:max_videos] if max_videos else urls

        # Multi-line / comma-separated inline URL list
        if "\n" in profile_input or "," in profile_input:
            parts = re.split(r"[\n,]+", profile_input)
            urls = [p.strip() for p in parts if p.strip()]
            return urls[:max_videos] if max_videos else urls

        # A single video URL. Profile URLs must continue to the scraper.
        is_video_url = (
            re.search(r"/(?:video|photo)/\d+", profile_input) is not None
            or "modal_id=" in profile_input
            or any(marker in profile_input for marker in ("vt.tiktok.com", "vm.tiktok.com", "v.douyin.com"))
        )
        if is_video_url:
            return [profile_input]

        # Otherwise treat as a whole profile URL
        profile_url = self.normalize_profile_url(profile_input)
        if "tiktok.com" in profile_url or "douyin.com" in profile_url:
            api = self._api_for(profile_url)
            return api.scrape_profile_urls(profile_url, max_videos)

        return []

    # ------------------------------------------------------------------ #
    # Single video download (used by concurrent workers)
    # ------------------------------------------------------------------ #
    def _download_one(
        self,
        url: str,
        user_dir: Path,
        archive_path: Path,
        archived_ids: set,
        idx: int,
        total: int,
        progress_hook: Optional[Callable[[Dict[str, Any]], None]],
    ) -> Dict[str, Any]:
        """Download a single video. Returns a result dict for aggregation."""
        try:
            info = self.downloader.get_video_info(url)
            vid = str(info.get("id", ""))

            # Atomic check-and-reserve to prevent duplicate downloads
            with self._archive_lock:
                if vid in archived_ids:
                    if progress_hook:
                        progress_hook({
                            "status": "skipped",
                            "index": idx,
                            "total": total,
                            "title": info.get("title"),
                            "id": vid,
                        })
                    return {"status": "skipped", "id": vid}
                # Reserve this ID immediately so other threads skip it
                archived_ids.add(vid)

            if progress_hook:
                progress_hook({
                    "status": "downloading_item",
                    "index": idx,
                    "total": total,
                    "title": info.get("title"),
                    "id": vid,
                })

            # Use download_video_with_info to avoid fetching info twice
            self.downloader.download_video_with_info(
                url, info, custom_output_dir=str(user_dir)
            )
            self.append_archive(archive_path, vid)
            return {"status": "downloaded", "id": vid}

        except Exception as e:
            if progress_hook:
                progress_hook({
                    "status": "error_item",
                    "index": idx,
                    "total": total,
                    "error": str(e),
                })
            return {"status": "failed", "url": url, "error": str(e)}

    # ------------------------------------------------------------------ #
    # Batch download (concurrent)
    # ------------------------------------------------------------------ #
    def download_video_list(
        self,
        urls_or_ids: List[str],
        username: str,
        output_dir: Optional[str] = None,
        progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
        workers: int = _DEFAULT_WORKERS,
    ) -> Dict[str, Any]:
        """Download a list of video URLs/IDs concurrently into the profile folder."""
        base_dir = Path(
            output_dir or self.cookie_manager.config.get("download_dir", "downloads")
        )
        user_dir = base_dir / username
        user_dir.mkdir(parents=True, exist_ok=True)

        archive_path = user_dir / "download_archive.txt"
        archived_ids = self.load_archive(archive_path)

        results: List[Dict[str, Any]] = []
        total = len(urls_or_ids)

        # Use ThreadPoolExecutor for concurrent downloads
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for idx, item in enumerate(urls_or_ids, 1):
                clean_item = item.strip()
                if not clean_item:
                    continue
                future = executor.submit(
                    self._download_one,
                    clean_item, user_dir, archive_path, archived_ids,
                    idx, total, progress_hook,
                )
                futures[future] = idx

            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({"status": "failed", "error": str(e)})

        downloaded_count = sum(1 for r in results if r["status"] == "downloaded")
        skipped_count = sum(1 for r in results if r["status"] == "skipped")
        failed_count = sum(1 for r in results if r["status"] == "failed")
        errors = [
            {"url": r.get("url", ""), "error": r.get("error", "unknown")}
            for r in results if r["status"] == "failed"
        ]

        return {
            "success": failed_count == 0 or downloaded_count > 0,
            "username": username,
            "folder": str(user_dir),
            "downloaded": downloaded_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "total": total,
            "errors": errors,
        }

    def download_profile(
        self,
        profile_input: str,
        output_dir: Optional[str] = None,
        max_videos: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Resolve a profile and download ALL its videos (or up to *max_videos*)."""
        username = self.extract_username(profile_input)
        urls = self.resolve_video_urls(profile_input, max_videos=max_videos or 0)
        if not urls:
            return {
                "success": False,
                "username": username,
                "message": "Không tìm thấy video nào trong profile.",
                "total": 0,
                "downloaded": 0,
                "skipped": 0,
                "failed": 0,
            }
        return self.download_video_list(urls, username=username, output_dir=output_dir)

    def download_profile_or_list(
        self,
        target: str,
        max_videos: int = 0,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        """CLI-friendly entry point: resolve *target* and download the batch.

        When *max_videos* is 0, downloads ALL available videos.
        """
        urls = self.resolve_video_urls(target, max_videos)

        def hook(d: Dict[str, Any]) -> None:
            if progress_callback:
                idx = d.get("index", 1)
                total = d.get("total", len(urls))
                progress_callback(idx, total, str(d.get("title", "")))

        username = self.extract_username(target)
        if not urls:
            return {
                "success": False,
                "username": username,
                "total": 0,
                "downloaded": 0,
                "skipped": 0,
                "failed": 0,
            }
        return self.download_video_list(urls, username=username, progress_hook=hook)
