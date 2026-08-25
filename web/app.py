import os
import sys
import uuid
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.cookie_manager import CookieManager
from core.downloader import TikTokDownloader
from core.profile_scraper import ProfileScraper

app = FastAPI(title="TikTok & Douyin Ultra Downloader - Desktop & Web Engine")

# Local-only CORS — never a wildcard with credentials. The REST server is
# intentionally bound to 127.0.0.1, so we only trust local origins.
_LOCAL_ORIGINS = [
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_LOCAL_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cookie_mgr = CookieManager()
downloader = TikTokDownloader(cookie_mgr)
scraper = ProfileScraper(cookie_mgr)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def get_downloads_dir() -> Path:
    dir_path = Path(cookie_mgr.config.get("download_dir", "downloads"))
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def safe_media_path(requested: str) -> Path:
    """Resolve a client-supplied path, guaranteeing it stays under downloads.

    Guards against path traversal (``..``/absolute paths) on every file
    management endpoint.
    """
    base = get_downloads_dir().resolve()
    candidate = Path(requested or "").expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(base):
        raise HTTPException(
            status_code=403,
            detail="Đường không được nange under thư mục downloads.",
        )
    return candidate

# Mount downloads for direct in-app video playback/preview
downloads_path = get_downloads_dir()

download_tasks: Dict[str, Dict[str, Any]] = {}

class VideoInfoRequest(BaseModel):
    url: str

class DownloadSingleRequest(BaseModel):
    url: str
    custom_filename: Optional[str] = None
    custom_dir: Optional[str] = None

class DownloadProfileRequest(BaseModel):
    profile: str
    urls: Optional[List[str]] = None
    max_videos: Optional[int] = 0  # 0 = download ALL videos

class ConfigUpdateRequest(BaseModel):
    browser: Optional[str] = None
    download_dir: Optional[str] = None
    custom_cookie_string: Optional[str] = None
    video_quality: Optional[str] = None
    save_metadata: Optional[bool] = None

class OpenPathRequest(BaseModel):
    path: Optional[str] = None

class DeleteFileRequest(BaseModel):
    path: str

@app.get("/downloaded-media/{file_path:path}")
async def serve_downloaded_media(file_path: str):
    target_file = safe_media_path(file_path)
    if not target_file.is_file():
        raise HTTPException(status_code=404, detail="File không tồn tại")
    return FileResponse(target_file)

@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/config")
async def get_config():
    return {
        "config": cookie_mgr.config,
    }

@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    cookie_mgr.save_config(updates)
    # Refresh downloader and scraper with updated cookies
    downloader.cookie_manager = cookie_mgr
    scraper.cookie_manager = cookie_mgr
    return {"success": True, "config": cookie_mgr.config}

@app.post("/api/video-info")
async def get_video_info(req: VideoInfoRequest):
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập liên kết hợp lệ")
    try:
        info = downloader.get_video_info(req.url.strip())
        return {"success": True, "data": info}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/subtitles")
async def download_subtitles(req: VideoInfoRequest):
    """Download subtitle(s) attached to a video as ``.srt``/``.vtt`` files."""
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="Liên kết không được để trống")
    try:
        files = downloader.download_subtitles(req.url.strip())
        return {"success": True, "files": files, "count": len(files)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def run_single_download_task(task_id: str, url: str, custom_dir: Optional[str] = None):
    download_tasks[task_id] = {
        "status": "downloading",
        "progress": 0,
        "downloaded_bytes": 0,
        "total_bytes": 0,
        "filename": "",
        "error": None
    }
    
    def progress_callback(downloaded: int, total: int, percent: float):
        download_tasks[task_id]["progress"] = round(percent, 1)
        download_tasks[task_id]["downloaded_bytes"] = downloaded
        download_tasks[task_id]["total_bytes"] = total

    try:
        res = downloader.download_video(
            url=url,
            custom_output_dir=custom_dir,
            progress_callback=progress_callback
        )
        download_tasks[task_id]["status"] = "completed"
        download_tasks[task_id]["progress"] = 100
        download_tasks[task_id]["filename"] = res.get("filename", "")
        download_tasks[task_id]["result"] = res
    except Exception as e:
        download_tasks[task_id]["status"] = "failed"
        download_tasks[task_id]["error"] = str(e)

@app.post("/api/download-single")
async def download_single(req: DownloadSingleRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    background_tasks.add_task(run_single_download_task, task_id, req.url, req.custom_dir)
    return {"success": True, "task_id": task_id}

def run_profile_download_task(task_id: str, profile: str, urls: Optional[List[str]] = None, max_videos: int = 0):
    download_tasks[task_id] = {
        "status": "resolving",
        "progress": 0,
        "message": "Đang phân tích và chuẩn bị tải danh sách...",
        "current_item": "",
        "total_items": len(urls) if urls else 0,
        "completed_items": 0,
        "error": None
    }

    try:
        username = scraper.extract_username(profile)
        # Resolve a bare profile into its concrete video URLs when none supplied.
        url_list = urls if urls else scraper.resolve_video_urls(profile, max_videos=max_videos)
        download_tasks[task_id]["total_items"] = len(url_list)

        if not url_list:
            download_tasks[task_id]["status"] = "failed"
            download_tasks[task_id]["error"] = (
                "Không tìm thấy video trong profile. Kiểm tra username hoặc link kênh."
            )
            return

        def hook(d):
            if d.get("status") == "downloading_item":
                idx = d.get("index", 1)
                total = d.get("total", len(url_list))
                pct = round((idx / total) * 100, 1) if total > 0 else 0
                download_tasks[task_id]["status"] = "downloading"
                download_tasks[task_id]["progress"] = pct
                download_tasks[task_id]["completed_items"] = idx
                download_tasks[task_id]["current_item"] = d.get("title", "")
                download_tasks[task_id]["message"] = (
                    f"[{idx}/{total}] Đang tải: {d.get('title', '')[:40]}..."
                )
            elif d.get("status") == "skipped":
                download_tasks[task_id]["message"] = f"Bỏ qua video cũ: {d.get('id')}"

        res = scraper.download_video_list(url_list, username=username, progress_hook=hook)
        failed = res.get("failed", 0)
        downloaded = res.get("downloaded", 0)
        download_tasks[task_id]["status"] = "failed" if failed and not downloaded else "completed"
        download_tasks[task_id]["progress"] = 100
        download_tasks[task_id]["message"] = (
            f"Đã lưu {downloaded} video vào thư mục @{username}"
            + (f"; {failed} video lỗi." if failed else "")
        )
        download_tasks[task_id]["result"] = res
        if failed and not downloaded:
            download_tasks[task_id]["error"] = (
                f"Không tải được video nào; {failed} video gặp lỗi khi lấy thông tin hoặc tải CDN."
            )
    except Exception as e:
        download_tasks[task_id]["status"] = "failed"
        download_tasks[task_id]["error"] = str(e)

@app.post("/api/download-profile")
async def download_profile(req: DownloadProfileRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    background_tasks.add_task(run_profile_download_task, task_id, req.profile, req.urls, req.max_videos or 0)
    return {"success": True, "task_id": task_id}

@app.get("/api/task-status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    return download_tasks[task_id]

@app.get("/api/downloads")
async def list_downloads():
    download_dir = get_downloads_dir()
    if not download_dir.exists():
        return {"files": [], "total_size_mb": 0, "count": 0}
    
    files = []
    total_bytes = 0
    for p in download_dir.rglob("*.mp4"):
        try:
            stat = p.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            total_bytes += stat.st_size
            rel_path = str(p.relative_to(download_dir)).replace("\\", "/")
            
            # Check if json metadata exists
            json_path = p.with_suffix(".info.json")
            meta = {}
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
                "size_mb": size_mb,
                "size_bytes": stat.st_size,
                "modified": stat.st_mtime,
                "title": meta.get("title", p.stem),
                "author": meta.get("uploader") or meta.get("nickname", "Unknown"),
                "thumbnail": meta.get("thumbnail", ""),
                "platform": "Douyin" if "douyin" in p.name.lower() else "TikTok"
            })
        except Exception:
            pass

    files.sort(key=lambda x: x["modified"], reverse=True)
    return {
        "files": files,
        "count": len(files),
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        "download_dir": str(download_dir)
    }

@app.post("/api/open-folder")
async def open_folder(req: Optional[OpenPathRequest] = None):
    """Open folder in native Windows File Explorer (downloads-relative only)."""
    if req and req.path:
        target_path = safe_media_path(req.path)
    else:
        target_path = get_downloads_dir()
    target_path.mkdir(parents=True, exist_ok=True)

    try:
        if sys.platform == "win32":
            os.startfile(str(target_path))
        else:
            subprocess.Popen(["xdg-open", str(target_path)])
        return {"success": True, "message": "Đã mở thư mục"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/open-file")
async def open_file(req: OpenPathRequest):
    """Reveal and highlight file in Windows File Explorer (downloads only)."""
    target_file = safe_media_path(req.path) if req.path else None
    if not target_file or not target_file.exists():
        raise HTTPException(status_code=404, detail="File không tồn tại")

    try:
        if sys.platform == "win32":
            # Pass the path as a single argv element (no string interpolation)
            # to avoid command injection via embedded quotes.
            subprocess.Popen(["explorer", f"/select,{target_file}"])
        else:
            subprocess.Popen(["xdg-open", str(target_file.parent)])
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/delete-download")
async def delete_download(req: DeleteFileRequest):
    """Delete downloaded video + metadata (downloads-relative only)."""
    target_file = safe_media_path(req.path)
    if not target_file.exists():
        raise HTTPException(status_code=404, detail="File không tồn tại")

    try:
        target_file.unlink(missing_ok=True)
        meta_file = target_file.with_suffix(".info.json")
        if meta_file.exists():
            meta_file.unlink(missing_ok=True)
        return {"success": True, "message": "Đã xóa file thành công"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
