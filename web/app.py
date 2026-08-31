"""FastAPI REST backend for the TikTok & Douyin Downloader web UI.

This file is a thin routing layer — all business logic lives in core/service.py.
"""

import uuid
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import service

_log = logging.getLogger(__name__)

# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="TikTok & Douyin Ultra Downloader")

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

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory task tracking (keyed by UUID)
download_tasks: Dict[str, Dict[str, Any]] = {}
_TASK_MAX_AGE_SECONDS = 3600  # cleanup tasks older than 1 hour


def _cleanup_old_tasks() -> None:
    """Remove completed/failed tasks older than _TASK_MAX_AGE_SECONDS."""
    now = time.time()
    expired = [
        tid for tid, t in download_tasks.items()
        if t.get("status") in ("completed", "failed")
        and now - t.get("_created_at", now) > _TASK_MAX_AGE_SECONDS
    ]
    for tid in expired:
        del download_tasks[tid]


# ── Request models ───────────────────────────────────────────────────────────

class VideoInfoRequest(BaseModel):
    url: str

class DownloadSingleRequest(BaseModel):
    url: str
    custom_filename: Optional[str] = None
    custom_dir: Optional[str] = None

class DownloadProfileRequest(BaseModel):
    profile: str
    urls: Optional[List[str]] = None
    max_videos: Optional[int] = 0
    custom_dir: Optional[str] = None

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


# ── Static / media serving ───────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/downloaded-media/{file_path:path}")
async def serve_downloaded_media(file_path: str):
    target = service.safe_media_path(file_path)
    if not target or not target.is_file():
        raise HTTPException(status_code=404, detail="File không tồn tại")
    return FileResponse(target)


# ── Config endpoints ─────────────────────────────────────────────────────────

@app.get("/api/config")
async def api_get_config():
    return service.get_config()

@app.post("/api/config")
async def api_update_config(req: ConfigUpdateRequest):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    return service.save_config(updates)


# ── Video info / subtitles ───────────────────────────────────────────────────

@app.post("/api/video-info")
async def api_video_info(req: VideoInfoRequest):
    try:
        info = service.analyze_video(req.url)
        return {"success": True, "data": info}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/subtitles")
async def api_subtitles(req: VideoInfoRequest):
    try:
        return service.download_subtitles(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Single download ──────────────────────────────────────────────────────────

def _run_single_task(task_id: str, url: str, custom_dir: Optional[str]):
    """Background worker for single-video download."""
    download_tasks[task_id] = {
        "status": "downloading", "progress": 0,
        "downloaded_bytes": 0, "total_bytes": 0, "filename": "", "error": None,
        "_created_at": time.time(),
    }

    def on_progress(downloaded: int, total: int, percent: float):
        download_tasks[task_id]["progress"] = round(percent, 1)
        download_tasks[task_id]["downloaded_bytes"] = downloaded
        download_tasks[task_id]["total_bytes"] = total

    try:
        res = service.download_single_video(url, custom_dir, on_progress)
        download_tasks[task_id].update(
            status="completed", progress=100,
            filename=res.get("filename", ""), result=res,
        )
    except Exception as e:
        download_tasks[task_id].update(status="failed", error=str(e))

@app.post("/api/download-single")
async def api_download_single(req: DownloadSingleRequest, bg: BackgroundTasks):
    _cleanup_old_tasks()
    task_id = str(uuid.uuid4())
    bg.add_task(_run_single_task, task_id, req.url, req.custom_dir)
    return {"success": True, "task_id": task_id}


# ── Profile / batch download ─────────────────────────────────────────────────

def _run_profile_task(
    task_id: str, profile: str,
    urls: Optional[List[str]], max_videos: int, custom_dir: Optional[str],
):
    """Background worker for profile/batch download."""
    download_tasks[task_id] = {
        "status": "resolving", "progress": 0,
        "message": "Đang phân tích và chuẩn bị tải danh sách...",
        "current_item": "", "total_items": len(urls) if urls else 0,
        "completed_items": 0, "error": None,
        "_created_at": time.time(),
    }

    try:
        username = service.extract_username(profile)
        url_list = urls if urls else service.resolve_profile_urls(profile, max_videos)
        download_tasks[task_id]["total_items"] = len(url_list)

        if not url_list:
            download_tasks[task_id].update(
                status="failed",
                error="Không tìm thấy video trong profile. Kiểm tra username hoặc link kênh.",
            )
            return

        def hook(d: Dict[str, Any]):
            if d.get("status") == "downloading_item":
                idx, total = d.get("index", 1), d.get("total", len(url_list))
                pct = round((idx / total) * 100, 1) if total else 0
                download_tasks[task_id].update(
                    status="downloading", progress=pct, completed_items=idx,
                    current_item=d.get("title", ""),
                    message=f"[{idx}/{total}] Đang tải: {d.get('title', '')[:40]}...",
                )
            elif d.get("status") == "skipped":
                download_tasks[task_id]["message"] = f"Bỏ qua video cũ: {d.get('id')}"

        res = service.download_video_list(url_list, username, custom_dir, hook)
        failed, downloaded = res.get("failed", 0), res.get("downloaded", 0)
        download_tasks[task_id].update(
            status="failed" if failed and not downloaded else "completed",
            progress=100,
            message=f"Đã lưu {downloaded} video vào thư mục @{username}"
                    + (f"; {failed} video lỗi." if failed else ""),
            result=res,
        )
        if failed and not downloaded:
            download_tasks[task_id]["error"] = (
                f"Không tải được video nào; {failed} video gặp lỗi."
            )
    except Exception as e:
        download_tasks[task_id].update(status="failed", error=str(e))

@app.post("/api/scan-profile")
async def api_scan_profile(req: VideoInfoRequest):
    try:
        urls = service.resolve_profile_urls(req.url, max_videos=0)
        return {"success": True, "count": len(urls), "urls": urls}
    except Exception as e:
        _log.error("Scan profile failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/download-profile")
async def api_download_profile(req: DownloadProfileRequest, bg: BackgroundTasks):
    _cleanup_old_tasks()
    task_id = str(uuid.uuid4())
    bg.add_task(_run_profile_task, task_id, req.profile, req.urls, req.max_videos or 0, req.custom_dir)
    return {"success": True, "task_id": task_id}


# ── Task status ──────────────────────────────────────────────────────────────

@app.get("/api/task-status/{task_id}")
async def api_task_status(task_id: str):
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    return download_tasks[task_id]


# ── File management ──────────────────────────────────────────────────────────

@app.get("/api/downloads")
async def api_list_downloads():
    return service.list_downloads()

@app.post("/api/open-folder")
async def api_open_folder(req: Optional[OpenPathRequest] = None):
    try:
        return service.open_downloads_folder()
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/open-file")
async def api_open_file(req: OpenPathRequest):
    result = service.reveal_file(req.path or "")
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result

@app.post("/api/delete-download")
async def api_delete_download(req: DeleteFileRequest):
    result = service.delete_download(req.path)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return {"success": True, "message": "Đã xóa file thành công"}
