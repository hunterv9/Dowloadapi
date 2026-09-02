"""Shared business logic used by both Web (FastAPI) and Desktop (WebSocket) backends.

This module eliminates code duplication between web/app.py and desktop/ws_server.py.
All download, config, file management operations live here.
"""

import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .cookie_manager import CookieManager
from .downloader import TikTokDownloader
from .profile_scraper import ProfileScraper

_log = logging.getLogger(__name__)

# ── Shared instances ─────────────────────────────────────────────────────────
cookie_mgr = CookieManager()
downloader = TikTokDownloader(cookie_mgr)
scraper = ProfileScraper(cookie_mgr)


# ── Path helpers ─────────────────────────────────────────────────────────────

def get_downloads_dir() -> Path:
    """Return the configured downloads directory, creating it if needed."""
    dir_path = Path(cookie_mgr.config.get("download_dir", "downloads"))
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def safe_media_path(requested: str) -> Optional[Path]:
    """Resolve *requested* to an absolute path under the downloads directory.

    Returns ``None`` if the path escapes the downloads root (path-traversal
    guard).  Both backends call this before any file-management operation.
    """
    try:
        base = get_downloads_dir().resolve()
    except OSError:
        return None
    candidate = Path(requested or "").expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(base):
        return None
    return candidate


# ── Config operations ────────────────────────────────────────────────────────

def get_config() -> Dict[str, Any]:
    """Return current app configuration."""
    return {"config": cookie_mgr.config}


def save_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Merge *updates* into config and persist to disk."""
    cookie_mgr.save_config(updates)
    downloader.cookie_manager = cookie_mgr
    scraper.cookie_manager = cookie_mgr
    return {"success": True, "config": cookie_mgr.config}


# ── Video analysis ───────────────────────────────────────────────────────────

def analyze_video(url: str) -> Dict[str, Any]:
    """Fetch metadata for a single video URL.

    Raises on invalid/unreachable URLs.
    """
    if not url or not url.strip():
        raise ValueError("Liên kết video không được để trống")
    return downloader.get_video_info(url.strip())


def download_subtitles(url: str) -> Dict[str, Any]:
    """Download subtitle files for a video. Returns list of saved file paths."""
    if not url or not url.strip():
        raise ValueError("Liên kết không được để trống")
    files = downloader.download_subtitles(url.strip())
    return {"success": True, "files": files, "count": len(files)}


# ── Single download ──────────────────────────────────────────────────────────

def download_single_video(
    url: str,
    custom_dir: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Download one video.  Returns the result dict from TikTokDownloader."""
    return downloader.download_video(
        url=url,
        custom_output_dir=custom_dir,
        progress_callback=progress_callback,
    )


# ── Profile / batch download ─────────────────────────────────────────────────

def resolve_profile_urls(profile: str, max_videos: int = 0) -> List[str]:
    """Resolve a profile URL/username into a list of video URLs."""
    return scraper.resolve_video_urls(profile, max_videos=max_videos)


def extract_username(profile: str) -> Optional[str]:
    """Extract the bare username from a profile URL or handle."""
    return scraper.extract_username(profile)


def download_video_list(
    url_list: List[str],
    username: Optional[str] = None,
    output_dir: Optional[str] = None,
    progress_hook: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Batch-download a list of video URLs. Returns summary dict."""
    return scraper.download_video_list(
        url_list,
        username=username,
        output_dir=output_dir,
        progress_hook=progress_hook,
    )


# ── File listing ─────────────────────────────────────────────────────────────

def list_downloads() -> Dict[str, Any]:
    """Scan the downloads directory and return metadata for all .mp4 files."""
    download_dir = get_downloads_dir()
    files: List[Dict[str, Any]] = []
    total_bytes = 0

    for p in download_dir.rglob("*.mp4"):
        try:
            stat = p.stat()
            total_bytes += stat.st_size
            rel_path = str(p.relative_to(download_dir)).replace("\\", "/")

            # Load sidecar metadata JSON if present
            json_path = p.with_suffix(".info.json")
            meta: Dict[str, Any] = {}
            if json_path.exists():
                try:
                    with open(json_path, "r", encoding="utf-8") as jf:
                        meta = json.load(jf)
                except Exception:
                    pass

            files.append({
                "name": p.name,
                "path": str(p),
                "relative_path": rel_path,
                "stream_url": f"/downloaded-media/{rel_path}",
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "size_bytes": stat.st_size,
                "modified": stat.st_mtime,
                "title": meta.get("title", p.stem),
                "author": meta.get("uploader") or meta.get("nickname", "Unknown"),
                "thumbnail": meta.get("thumbnail", ""),
                "platform": "Douyin" if "douyin" in p.name.lower() else "TikTok",
            })
        except Exception:
            pass

    files.sort(key=lambda x: x["modified"], reverse=True)
    return {
        "files": files,
        "count": len(files),
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        "download_dir": str(download_dir),
    }


# ── File operations ──────────────────────────────────────────────────────────

def open_downloads_folder() -> Dict[str, Any]:
    """Open the downloads directory in the OS file manager."""
    download_dir = get_downloads_dir()
    if sys.platform == "win32":
        os.startfile(str(download_dir))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(download_dir)])
    else:
        subprocess.Popen(["xdg-open", str(download_dir)])
    return {"success": True, "message": "Đã mở thư mục"}


def reveal_file(file_path: str) -> Dict[str, Any]:
    """Open Explorer/Finder and select the given file."""
    safe_path = safe_media_path(file_path) if file_path else None
    if not safe_path or not safe_path.exists():
        return {"success": False, "error": "File không tồn tại"}
    if sys.platform == "win32":
        subprocess.Popen(["explorer", f"/select,{safe_path}"])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(safe_path)])
    else:
        subprocess.Popen(["xdg-open", str(safe_path.parent)])
    return {"success": True}


def delete_download(file_path: str) -> Dict[str, Any]:
    """Delete a downloaded file and its sidecar metadata."""
    safe_path = safe_media_path(file_path) if file_path else None
    if not safe_path or not safe_path.exists():
        return {"success": False, "error": "File không tồn tại"}
    p = Path(safe_path)
    p.unlink(missing_ok=True)
    p.with_suffix(".info.json").unlink(missing_ok=True)
    return {"success": True}
