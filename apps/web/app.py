"""FastAPI REST backend for the TikTok & Douyin Downloader.

Pure API service, optimized for high request throughput:
  - No UI/static serving, no WebSocket, no per-request housekeeping.
  - orjson response serialization (ORJSONResponse).
  - Blocking work (network scrapes, directory scans) offloaded to threads
    so the event loop is never starved.
  - TTL cache for the downloads listing.

All business logic lives in core/service.py.

Endpoints:
    POST /api/video-info             Analyze a video URL (title, author, streams…)
    POST /api/download-single        Start an async single-video download task
    POST /api/download-file          Download now, stream the .mp4 back directly
    GET  /api/task-status/{task_id}  Poll a download task
    GET  /api/downloads              List files in the downloads directory (2s TTL cache)
    GET  /downloaded-media/{path}    Serve a downloaded file (path-traversal guarded)
"""

import asyncio
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, ORJSONResponse
from pydantic import BaseModel

# Ensure project root is on sys.path so `from core import …` works
# regardless of whether the app is launched as `python apps/web/app.py`,
# `python -m apps.web.app` or via the installed console script.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core import service
from core.service import _friendly_error

_log = logging.getLogger(__name__)

# ── In-memory task tracking (keyed by UUID) ──────────────────────────────────

download_tasks: Dict[str, Dict[str, Any]] = {}
MAX_TASKS = 1000
_TASK_MAX_AGE_SECONDS = 3600  # cleanup tasks older than 1 hour
_TASK_CLEANUP_INTERVAL_SECONDS = 60

def _evict_tasks_if_full() -> None:
    """Bound download_tasks; evict oldest finished tasks first."""
    if len(download_tasks) < MAX_TASKS:
        return
    finished = sorted(
        ((tid, t) for tid, t in download_tasks.items()
         if t.get("status") in ("completed", "failed")),
        key=lambda kv: kv[1].get("_created_at", 0),
    )
    for tid, _ in finished:
        download_tasks.pop(tid, None)
        if len(download_tasks) < MAX_TASKS:
            return
    # No (or not enough) finished tasks: fall back to oldest overall.
    if len(download_tasks) >= MAX_TASKS:
        oldest = sorted(
            download_tasks.items(), key=lambda kv: kv[1].get("_created_at", 0)
        )
        for tid, _ in oldest[: len(download_tasks) - MAX_TASKS + 1]:
            download_tasks.pop(tid, None)

async def _periodic_cleanup() -> None:
    """Background housekeeping — removes finished tasks older than the max age.

    Runs on its own asyncio task instead of per-request, keeping request
    handlers allocation-free.
    """
    while True:
        await asyncio.sleep(_TASK_CLEANUP_INTERVAL_SECONDS)
        try:
            now = time.time()
            expired = [
                tid for tid, t in download_tasks.items()
                if t.get("status") in ("completed", "failed")
                and now - t.get("_created_at", now) > _TASK_MAX_AGE_SECONDS
            ]
            for tid in expired:
                download_tasks.pop(tid, None)
        except Exception:
            _log.exception("Task cleanup failed")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    cleanup = asyncio.create_task(_periodic_cleanup())
    yield
    cleanup.cancel()

# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="TikTok & Douyin Downloader API",
    description="High-throughput REST API for TikTok & Douyin video downloads.",
    version="3.0.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

def _cors_origins() -> list:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Public health check (no auth) --

@app.get("/")
async def health():
    return {"ok": True}

# ── Request models ───────────────────────────────────────────────────────────

class VideoInfoRequest(BaseModel):
    url: str

class DownloadSingleRequest(BaseModel):
    url: str
    custom_filename: Optional[str] = None
    custom_dir: Optional[str] = None

# ── Downloads listing (TTL cache — avoids rescanning the tree per request) ───

_LIST_TTL_SECONDS = 2.0
_list_cache: Dict[str, Any] = {"at": 0.0, "data": None}
_list_lock = asyncio.Lock()

def _invalidate_list_cache() -> None:
    _list_cache["at"] = 0.0
    _list_cache["data"] = None

@app.get("/api/downloads")
async def api_list_downloads():
    """List files in the downloads directory (cached for 2 seconds)."""
    now = time.monotonic()
    if _list_cache["data"] is not None and now - _list_cache["at"] < _LIST_TTL_SECONDS:
        return _list_cache["data"]
    async with _list_lock:
        # Double-checked locking: another request may have refreshed the
        # cache while we were waiting on the lock.
        if _list_cache["data"] is not None and time.monotonic() - _list_cache["at"] < _LIST_TTL_SECONDS:
            return _list_cache["data"]
        data = await asyncio.to_thread(service.list_downloads)
        _list_cache["at"] = time.monotonic()
        _list_cache["data"] = data
        return data

# ── Video info ───────────────────────────────────────────────────────────────

@app.post("/api/video-info")
async def api_video_info(req: VideoInfoRequest):
    try:
        # analyze_video performs blocking HTTP scrapes → run in a worker
        # thread so the event loop keeps serving other requests.
        info = await asyncio.to_thread(service.analyze_video, req.url)
        return {"success": True, "data": info}
    except Exception as e:
        raise HTTPException(status_code=400, detail=_friendly_error(e, req.url))

# ── Single download ──────────────────────────────────────────────────────────

def _run_single_task(task_id: str, url: str, custom_dir: Optional[str]):
    """Background worker for single-video download (runs in the threadpool)."""
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
        _invalidate_list_cache()
    except Exception as e:
        error_msg = _friendly_error(e, url)
        download_tasks[task_id].update(status="failed", error=error_msg)

def _validate_custom_dir(custom_dir: Optional[str]) -> None:
    if not custom_dir:
        return
    stripped = custom_dir.strip()
    if not stripped:
        return
    if Path(stripped).is_absolute() or stripped.startswith("/"):
        raise HTTPException(status_code=400, detail="custom_dir must be relative")
    if service.safe_media_path(custom_dir) is None:
        raise HTTPException(status_code=400, detail="custom_dir escapes downloads directory")

@app.post("/api/download-single")
async def api_download_single(req: DownloadSingleRequest, bg: BackgroundTasks):
    _validate_custom_dir(req.custom_dir)
    _evict_tasks_if_full()
    task_id = str(uuid.uuid4())
    bg.add_task(_run_single_task, task_id, req.url, req.custom_dir)
    return {"success": True, "task_id": task_id}

# ── Direct file download (synchronous) ───────────────────────────────────────

@app.post("/api/download-file")
async def api_download_file(req: DownloadSingleRequest):
    """Download the video and stream the .mp4 straight back to the caller.

    Synchronous: the HTTP response IS the video file. Skips subtitle
    fetching (subtitles are extra paced requests and cannot be returned in
    the same response anyway) — use /api/download-single when subtitles,
    progress tracking or long-running downloads are needed.
    """
    _validate_custom_dir(req.custom_dir)
    try:
        res = await asyncio.to_thread(
            service.download_single_video, req.url, req.custom_dir, None, False
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=_friendly_error(e, req.url))
    saved = res.get("saved_path", "")
    target = service.safe_media_path(saved) if saved else None
    if not target or not target.is_file():
        raise HTTPException(status_code=500, detail="Tải xong nhưng file không tìm thấy")
    _invalidate_list_cache()
    return FileResponse(
        target,
        media_type="video/mp4",
        filename=res.get("filename") or target.name,
    )

# ── Task status ──────────────────────────────────────────────────────────────

@app.get("/api/task-status/{task_id}")
async def api_task_status(task_id: str):
    task = download_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    return task

# ── Media serving ────────────────────────────────────────────────────────────

@app.get("/downloaded-media/{file_path:path}")
async def serve_downloaded_media(file_path: str):
    target = service.safe_media_path(file_path)
    if not target or not target.is_file():
        raise HTTPException(status_code=404, detail="File không tồn tại")
    return FileResponse(target)

def main(host: str = "127.0.0.1", port: Optional[int] = None) -> None:
    """Entry point for `python apps/web/app.py` and the `tikdl-web` console script."""
    import uvicorn
    if port is None:
        port = int(os.getenv("WEB_PORT", "8000"))
    workers = int(os.getenv("WEB_WORKERS", "1"))
    if workers > 1:
        # Multi-process mode requires an import string (not the app object).
        uvicorn.run("apps.web.app:app", host=host, port=port, workers=workers)
    else:
        uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
