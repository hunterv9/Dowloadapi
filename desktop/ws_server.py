"""WebSocket backend for the Electron desktop app.

This file handles only the WebSocket protocol (handshake, frame parsing,
client management).  All business logic is delegated to core/service.py.
"""

import json
import base64
import hashlib
import struct
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional, Set

import sys
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core import service


def _friendly_error(exc: Exception) -> str:
    """Convert technical exceptions into user-friendly Vietnamese messages."""
    msg = str(exc).lower()
    raw = str(exc)
    if "invalid url" in msg or "not a valid" in msg or "unsupported url" in msg:
        return "Link không hợp lệ. Kiểm tra lại đường dẫn TikTok hoặc Douyin."
    if "private" in msg or "login" in msg or "403" in msg:
        return "Video ở chế độ riêng tư hoặc yêu cầu đăng nhập."
    if "not found" in msg or "404" in msg:
        return "Video không tồn tại hoặc đã bị xóa."
    if "timeout" in msg or "timed out" in msg:
        return "Kết nối quá chậm. Thử lại sau."
    if "connection" in msg or "network" in msg:
        return "Không thể kết nối mạng. Kiểm tra internet."
    if "rate limit" in msg or "429" in msg:
        return "Tải quá nhanh. Chờ vài giây rồi thử lại."
    return f"Đã xảy ra lỗi: {raw[:120]}" if len(raw) > 120 else f"Đã xảy ra lỗi: {raw}"


# ── WebSocket protocol helpers ───────────────────────────────────────────────

CLIENTS: Set[asyncio.StreamWriter] = set()
WS_MAGIC_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


async def _handshake(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
    """Perform the WebSocket upgrade handshake. Returns True on success."""
    request_line = await reader.readline()
    if not request_line:
        return False

    headers: Dict[str, str] = {}
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

    accept = base64.b64encode(
        hashlib.sha1((key + WS_MAGIC_GUID).encode()).digest()
    ).decode()

    writer.write(
        f"HTTP/1.1 101 Switching Protocols\r\n"
        f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode()
    )
    await writer.drain()
    return True


async def _recv_frame(reader: asyncio.StreamReader) -> Optional[str]:
    """Read one WebSocket text frame. Returns None on close/error."""
    try:
        b1, b2 = (await reader.readexactly(2))
        if (b1 & 0x0F) == 0x8:  # Close frame
            return None

        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", await reader.readexactly(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", await reader.readexactly(8))[0]

        mask = await reader.readexactly(4) if (b2 & 0x80) else b""
        payload = await reader.readexactly(length)
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return payload.decode("utf-8", errors="ignore")
    except Exception:
        return None


async def _send_frame(writer: asyncio.StreamWriter, message: str):
    """Send one WebSocket text frame."""
    try:
        payload = message.encode("utf-8")
        header = bytearray([0x81])  # FIN + text
        n = len(payload)
        if n <= 125:
            header.append(n)
        elif n <= 65535:
            header.extend([126, *struct.pack("!H", n)])
        else:
            header.extend([127, *struct.pack("!Q", n)])
        writer.write(header + payload)
        await writer.drain()
    except Exception:
        pass


async def _broadcast(event: Dict[str, Any]):
    """Send a JSON message to all connected clients."""
    msg = json.dumps(event, ensure_ascii=False)
    for client in list(CLIENTS):
        await _send_frame(client, msg)


# ── Message handler ──────────────────────────────────────────────────────────

async def _handle(writer: asyncio.StreamWriter, req: Dict[str, Any]):
    """Dispatch a JSON-RPC request to the appropriate service function."""
    action = req.get("action", "")
    req_id = req.get("id")
    payload = req.get("payload", {})

    async def reply(status: str, data: Any = None, error: str = None):
        await _send_frame(writer, json.dumps(
            {"id": req_id, "action": action, "status": status, "data": data, "error": error},
            ensure_ascii=False,
        ))

    loop = asyncio.get_running_loop()

    try:
        # ── Config ──────────────────────────────────────────────────────
        if action == "GET_CONFIG":
            await reply("success", service.get_config())

        elif action == "SAVE_CONFIG":
            result = service.save_config(payload)
            await reply("success", result)

        # ── Video analysis ──────────────────────────────────────────────
        elif action == "ANALYZE_VIDEO":
            info = await loop.run_in_executor(None, service.analyze_video, payload.get("url", ""))
            await reply("success", info)

        # ── Single download ─────────────────────────────────────────────
        elif action == "DOWNLOAD_SINGLE":
            url = payload.get("url", "").strip()
            task_id = payload.get("task_id", "task_single")
            await reply("started", {"task_id": task_id})

            def on_progress(downloaded: int, total: int, percent: float):
                asyncio.run_coroutine_threadsafe(_broadcast({
                    "event": "DOWNLOAD_PROGRESS", "task_id": task_id,
                    "percent": round(percent, 1), "downloaded": downloaded, "total": total,
                }), loop)

            try:
                res = await loop.run_in_executor(
                    None, service.download_single_video, url, None, on_progress
                )
                await _broadcast({"event": "DOWNLOAD_COMPLETED", "task_id": task_id, "result": res})
            except Exception as e:
                await _broadcast({"event": "DOWNLOAD_FAILED", "task_id": task_id, "error": _friendly_error(e)})

        # ── Profile download ────────────────────────────────────────────
        elif action == "DOWNLOAD_PROFILE":
            profile = payload.get("profile", "")
            urls = payload.get("urls") or []
            max_videos = payload.get("max_videos") or 0
            custom_dir = payload.get("custom_dir") or None
            task_id = payload.get("task_id", "task_batch")

            username = await loop.run_in_executor(None, service.extract_username, profile)

            if urls:
                url_list = list(urls[:max_videos]) if max_videos else list(urls)
            else:
                url_list = await loop.run_in_executor(
                    None, service.resolve_profile_urls, profile, max_videos
                )

            if not url_list:
                await reply("error", error="Không tìm thấy video trong profile.")
                return

            await reply("started", {"task_id": task_id, "total": len(url_list)})

            def on_batch_hook(d: Dict[str, Any]):
                asyncio.run_coroutine_threadsafe(_broadcast({
                    "event": "BATCH_PROGRESS", "task_id": task_id,
                    "status": d.get("status"), "index": d.get("index"), "total": d.get("total"),
                    "title": d.get("title", ""),
                    "message": f"[{d.get('index', 1)}/{d.get('total', 1)}] Đang tải: {d.get('title', '')[:40]}",
                }), loop)

            try:
                res = await loop.run_in_executor(
                    None, service.download_video_list, url_list, username, custom_dir, on_batch_hook
                )
                if res.get("failed", 0) and not res.get("downloaded", 0):
                    await _broadcast({
                        "event": "BATCH_FAILED", "task_id": task_id,
                        "error": f"Không tải được video nào; {res.get('failed', 0)} video lỗi.",
                    })
                else:
                    await _broadcast({"event": "BATCH_COMPLETED", "task_id": task_id, "result": res})
            except Exception as e:
                await _broadcast({"event": "BATCH_FAILED", "task_id": task_id, "error": _friendly_error(e)})

        # ── File management ─────────────────────────────────────────────
        elif action == "GET_DOWNLOADS":
            result = await loop.run_in_executor(None, service.list_downloads)
            await reply("success", result)

        elif action == "OPEN_FOLDER":
            result = await loop.run_in_executor(None, service.open_downloads_folder)
            await reply("success", result)

        elif action == "OPEN_FILE":
            result = await loop.run_in_executor(
                None, service.reveal_file, payload.get("path", "")
            )
            if result.get("success"):
                await reply("success")
            else:
                await reply("error", error=result.get("error", "File không tồn tại"))

        elif action == "DELETE_DOWNLOAD":
            result = await loop.run_in_executor(
                None, service.delete_download, payload.get("path", "")
            )
            if result.get("success"):
                await reply("success")
            else:
                await reply("error", error=result.get("error", "File không tồn tại"))

        else:
            await reply("error", error=f"Unknown action: {action}")

    except Exception as e:
        await reply("error", error=_friendly_error(e))


# ── Client connection handler ────────────────────────────────────────────────

async def _client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    if not await _handshake(reader, writer):
        writer.close()
        return

    CLIENTS.add(writer)
    try:
        while True:
            msg = await _recv_frame(reader)
            if msg is None:
                break
            try:
                await _handle(writer, json.loads(msg))
            except Exception:
                pass
    finally:
        CLIENTS.discard(writer)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ── Entry point ──────────────────────────────────────────────────────────────

async def run_server(host: str = "127.0.0.1", port: int = 8765):
    server = await asyncio.start_server(_client_handler, host, port)
    print(f"[Desktop Engine]: WebSocket Server running on ws://{host}:{port}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        print("\nShutdown Desktop WebSocket Server.")
