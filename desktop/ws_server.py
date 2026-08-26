import os
import sys
import json
import base64
import hashlib
import struct
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Set, Callable

# Ensure root directory in python path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.cookie_manager import CookieManager
from core.downloader import TikTokDownloader
from core.profile_scraper import ProfileScraper

cookie_mgr = CookieManager()
downloader = TikTokDownloader(cookie_mgr)
scraper = ProfileScraper(cookie_mgr)


def _safe_media_path(requested: str) -> Optional[Path]:
    """Resolve a client-supplied path, restricting it to the downloads dir."""
    try:
        base = Path(cookie_mgr.config.get("download_dir", "downloads")).resolve()
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    candidate = Path(requested or "").expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(base):
        return None
    return candidate

# Connected WebSocket clients
CLIENTS: Set[asyncio.StreamWriter] = set()

# Standard WebSocket Server Implementation via asyncio
WS_MAGIC_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

async def ws_handshake(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
    request_line = await reader.readline()
    if not request_line:
        return False
    
    headers = {}
    while True:
        line = await reader.readline()
        if not line or line == b"\r\n":
            break
        try:
            k, v = line.decode("utf-8").strip().split(":", 1)
            headers[k.strip().lower()] = v.strip()
        except Exception:
            pass

    key = headers.get("sec-websocket-key")
    if not key:
        return False

    # Compute Sec-WebSocket-Accept
    accept_val = base64.b64encode(hashlib.sha1((key + WS_MAGIC_GUID).encode("utf-8")).digest()).decode("utf-8")
    
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept_val}\r\n\r\n"
    )
    writer.write(response.encode("utf-8"))
    await writer.drain()
    return True

async def ws_recv_frame(reader: asyncio.StreamReader) -> Optional[str]:
    try:
        head = await reader.readexactly(2)
        b1, b2 = head[0], head[1]
        opcode = b1 & 0x0F
        if opcode == 0x8:  # Close frame
            return None

        masked = (b2 & 0x80) != 0
        payload_len = b2 & 0x7F

        if payload_len == 126:
            ext_len = await reader.readexactly(2)
            payload_len = struct.unpack("!H", ext_len)[0]
        elif payload_len == 127:
            ext_len = await reader.readexactly(8)
            payload_len = struct.unpack("!Q", ext_len)[0]

        mask = b""
        if masked:
            mask = await reader.readexactly(4)

        payload = await reader.readexactly(payload_len)
        if masked:
            payload = bytes([payload[i] ^ mask[i % 4] for i in range(len(payload))])

        return payload.decode("utf-8", errors="ignore")
    except Exception:
        return None

async def ws_send_frame(writer: asyncio.StreamWriter, message: str):
    try:
        payload = message.encode("utf-8")
        payload_len = len(payload)
        header = bytearray([0x81])  # FIN + Text frame

        if payload_len <= 125:
            header.append(payload_len)
        elif payload_len <= 65535:
            header.append(126)
            header.extend(struct.pack("!H", payload_len))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", payload_len))

        writer.write(header + payload)
        await writer.drain()
    except Exception:
        pass

async def broadcast(message: Dict[str, Any]):
    msg_str = json.dumps(message, ensure_ascii=False)
    for client in list(CLIENTS):
        await ws_send_frame(client, msg_str)

async def handle_message(writer: asyncio.StreamWriter, req: Dict[str, Any]):
    action = req.get("action", "")
    req_id = req.get("id")
    payload = req.get("payload", {})

    async def reply(status: str, data: Any = None, error: str = None):
        res = {"id": req_id, "action": action, "status": status, "data": data, "error": error}
        await ws_send_frame(writer, json.dumps(res, ensure_ascii=False))

    try:
        if action == "GET_CONFIG":
            cfg = cookie_mgr.config
            await reply("success", {
                "config": cfg,
            })

        elif action == "SAVE_CONFIG":
            cookie_mgr.save_config(payload)
            downloader.cookie_manager = cookie_mgr
            scraper.cookie_manager = cookie_mgr
            await reply("success", {"config": cookie_mgr.config})

        elif action == "ANALYZE_VIDEO":
            url = payload.get("url", "").strip()
            if not url:
                await reply("error", error="Liên kết video không được để trống")
                return
            
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, downloader.get_video_info, url)
            await reply("success", info)

        elif action == "DOWNLOAD_SINGLE":
            url = payload.get("url", "").strip()
            task_id = payload.get("task_id", "task_single")

            def on_progress(downloaded: int, total: int, percent: float):
                asyncio.run_coroutine_threadsafe(
                    broadcast({
                        "event": "DOWNLOAD_PROGRESS",
                        "task_id": task_id,
                        "percent": round(percent, 1),
                        "downloaded": downloaded,
                        "total": total
                    }),
                    loop
                )

            loop = asyncio.get_running_loop()
            await reply("started", {"task_id": task_id})

            try:
                res = await loop.run_in_executor(None, downloader.download_video, url, None, on_progress)
                await broadcast({
                    "event": "DOWNLOAD_COMPLETED",
                    "task_id": task_id,
                    "result": res
                })
            except Exception as e:
                await broadcast({
                    "event": "DOWNLOAD_FAILED",
                    "task_id": task_id,
                    "error": str(e)
                })

        elif action == "DOWNLOAD_PROFILE":
            profile = payload.get("profile", "")
            urls = payload.get("urls") or []
            max_videos = payload.get("max_videos") or 0
            custom_dir = payload.get("custom_dir") or None
            task_id = payload.get("task_id", "task_batch")
            username = scraper.extract_username(profile)
            # Resolve a bare profile into its concrete video URLs when needed.
            if urls:
                url_list = list(urls)
                if max_videos:
                    url_list = url_list[:max_videos]
            else:
                loop = asyncio.get_running_loop()
                url_list = await loop.run_in_executor(
                    None, scraper.resolve_video_urls, profile, max_videos
                )

            if not url_list:
                await reply(
                    "error",
                    error="Không tìm thấy video trong profile. Kiểm tra username hoặc link kênh.",
                )
                return

            def on_batch_hook(d):
                asyncio.run_coroutine_threadsafe(
                    broadcast({
                        "event": "BATCH_PROGRESS",
                        "task_id": task_id,
                        "status": d.get("status"),
                        "index": d.get("index"),
                        "total": d.get("total"),
                        "title": d.get("title", ""),
                        "message": f"[{d.get('index', 1)}/{d.get('total', 1)}] Đang tải: {d.get('title', '')[:40]}"
                    }),
                    loop
                )

            loop = asyncio.get_running_loop()
            await reply("started", {"task_id": task_id, "total": len(url_list)})

            try:
                res = await loop.run_in_executor(
                    None,
                    scraper.download_video_list,
                    url_list,
                    username,
                    custom_dir,
                    on_batch_hook,
                )
                if res.get("failed", 0) and not res.get("downloaded", 0):
                    await broadcast({
                        "event": "BATCH_FAILED",
                        "task_id": task_id,
                        "error": (
                            f"Không tải được video nào; {res.get('failed', 0)} video gặp lỗi "
                            "khi lấy thông tin hoặc tải CDN."
                        ),
                    })
                else:
                    await broadcast({
                        "event": "BATCH_COMPLETED",
                        "task_id": task_id,
                        "result": res
                    })
            except Exception as e:
                await broadcast({
                    "event": "BATCH_FAILED",
                    "task_id": task_id,
                    "error": str(e)
                })

        elif action == "GET_DOWNLOADS":
            download_dir = Path(cookie_mgr.config.get("download_dir", "downloads"))
            files = []
            total_bytes = 0
            if download_dir.exists():
                for p in download_dir.rglob("*.mp4"):
                    try:
                        stat = p.stat()
                        total_bytes += stat.st_size
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
                            "size_mb": round(stat.st_size / (1024 * 1024), 2),
                            "modified": stat.st_mtime,
                            "title": meta.get("title", p.stem),
                            "author": meta.get("uploader") or meta.get("nickname", "Unknown"),
                            "thumbnail": meta.get("thumbnail", ""),
                            "platform": "Douyin" if "douyin" in p.name.lower() else "TikTok"
                        })
                    except Exception:
                        pass

            files.sort(key=lambda x: x["modified"], reverse=True)
            await reply("success", {
                "files": files,
                "count": len(files),
                "total_size_mb": round(total_bytes / (1024 * 1024), 2),
                "download_dir": str(download_dir)
            })

        elif action == "OPEN_FOLDER":
            download_dir = Path(cookie_mgr.config.get("download_dir", "downloads"))
            download_dir.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(download_dir))
            await reply("success", {"message": "Đã mở thư mục"})

        elif action == "OPEN_FILE":
            file_path = payload.get("path")
            safe_path = _safe_media_path(file_path) if file_path else None
            if safe_path and safe_path.exists():
                import subprocess
                subprocess.Popen(["explorer", f"/select,{safe_path}"])
                await reply("success")
            else:
                await reply("error", error="File không tồn tại")

        elif action == "DELETE_DOWNLOAD":
            file_path = payload.get("path")
            safe_path = _safe_media_path(file_path) if file_path else None
            if safe_path and safe_path.exists():
                p = Path(safe_path)
                p.unlink(missing_ok=True)
                p.with_suffix(".info.json").unlink(missing_ok=True)
                await reply("success")
            else:
                await reply("error", error="File không tồn tại")

        else:
            await reply("error", error=f"Unknown action: {action}")

    except Exception as e:
        await reply("error", error=str(e))

async def client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    if not await ws_handshake(reader, writer):
        writer.close()
        return

    CLIENTS.add(writer)
    try:
        while True:
            msg_text = await ws_recv_frame(reader)
            if msg_text is None:
                break
            try:
                req_obj = json.loads(msg_text)
                await handle_message(writer, req_obj)
            except Exception:
                pass
    finally:
        CLIENTS.discard(writer)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def run_server(host="127.0.0.1", port=8765):
    server = await asyncio.start_server(client_handler, host, port)
    print(f"[Desktop Engine]: WebSocket Server running on ws://{host}:{port}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        print("\nShutdown Desktop WebSocket Server.")
