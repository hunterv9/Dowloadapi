# ⚡ TikTok & Douyin Downloader — Commercial API

Công cụ tải video TikTok/Douyin chất lượng cao chạy dưới dạng **pure REST API** (FastAPI), tối ưu cho thông lượng cao (mục tiêu ~5000 req/s trên server Linux đa worker). Kèm giao diện CLI dùng chung thư mục `core/`.

## ✨ Tính Năng Nổi Bật
1. **🎬 Download Video Đơn:** Tải video chất lượng cao (No Watermark/HD), tự động lưu tiêu đề, tác giả và metadata.
2. **📝 Tải Phụ Đề (Subtitle):** Tự động trích xuất và lưu caption/`subtitle` dạng `.srt`/`.vtt` khi nền tảng hỗ trợ.
3. **👤 Download Full Profile (CLI):** Quét profile qua trình duyệt headless (Playwright) với fallback HTML/JSON, tải từng video vào `downloads/<username>/`. Archive lưu lịch sử để tránh tải lại; mặc định tải song song 4 video.
4. **🚀 API hiệu năng cao:**
   - orjson serialization (ORJSONResponse) — nhanh hơn stdlib json nhiều lần.
   - Blocking I/O (scrape, quét thư mục) chạy trong thread pool — event loop không bao giờ bị chặn.
   - TTL cache cho `/api/downloads` (2s), housekeeping chạy nền (không nằm trên hot path).
   - Multi-worker sẵn sàng: `WEB_WORKERS=N` hoặc `--workers N`; `uvicorn[standard]` tự dùng uvloop + httptools trên Linux.

## 📡 API Endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/video-info` | Phân tích URL video: tiêu đề, tác giả, stream, phụ đề |
| POST | `/api/download-single` | Khởi động tác vụ tải video (async), trả `task_id` |
| POST | `/api/download-file` | Tải đồng bộ — response chính là file `.mp4` (bỏ qua phụ đề) |
| GET | `/api/task-status/{task_id}` | Trạng thái tác vụ tải |
| GET | `/api/downloads` | Danh sách file trong thư mục downloads (cache 2s) |
| GET | `/downloaded-media/{path}` | Tải file đã download (chống path traversal) |

Ví dụ:
```bash
curl -X POST http://127.0.0.1:8000/api/video-info -H "Content-Type: application/json" -d '{"url":"https://www.tiktok.com/@user/video/123"}'

curl -X POST http://127.0.0.1:8000/api/download-single -H "Content-Type: application/json" -d '{"url":"https://www.tiktok.com/@user/video/123"}'

curl http://127.0.0.1:8000/api/task-status/<task_id>

# Tải đồng bộ — trả thẳng file video trong response:
curl -X POST http://127.0.0.1:8000/api/download-file -H "Content-Type: application/json" -d '{"url":"https://www.tiktok.com/@user/video/123"}' -o video.mp4
```


## ⚙️ Ghi Chú Vận Hành
- API serve file kiểm tra **đường dẫn phải nằm trong thư mục downloads** (chống path traversal).
- Bảo mật (auth, rate limit, WAF) do services phía trước xử lý — service này chỉ xử lý request.
- `downloads/`, `.browser_data/`, `.env`, môi trường Python và file bytecode local được Git bỏ qua.
- `config.json` có thể chứa cookie và đường dẫn local; không commit cookie thật lên repository.

### 🚄 Tinh chỉnh tốc độ (biến môi trường)
Tốc độ một lần tải phụ thuộc vào mạng tới TikTok/Douyin, KHÔNG phải tầng API (API layer đo được hàng nghìn rps). Ba chỗ code chủ động "ngủ" để tránh bị platform đánh bot:

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `STEALTH_RPS` | `3` | Số request/giây tối đa mỗi domain (token bucket). Tăng lên nếu muốn scrape nhanh hơn — nhưng tăng nguy cơ 403/429. |
| `STEALTH_JITTER_MS` | `150,700` | Jitter ngẫu nhiên (ms) ngủ trước mỗi request scrape. Đặt `0,0` để tắt hoàn toàn. |
| `VIDEO_INFO_TTL` | `300` | Cache video-info (giây) — cùng 1 URL hỏi lại trong TTL sẽ không scrape nữa. |
| `MAX_DOWNLOAD_BYTES` | `524288000` | Giới hạn dung lượng 1 file tải về. |

Ngoài ra: `/api/download-file` bỏ qua bước tải phụ đề (mỗi phụ đề là thêm 1 request chịu pacing + jitter) nên nhanh hơn `/api/download-single` khi video có phụ đề; tắt `save_metadata` trong `config.json` nếu không cần file `.info.json`.

## 📦 Cài Đặt

Yêu cầu **Python 3.10+**.

```bash
# Cài package (kèm entry points tikdl-cli / tikdl-web)
pip install -e .

# Hoặc cài theo cách truyền thống
pip install -r requirements.txt

# (Tuỳ chọn, khuyên dùng cho CLI) Cài Chromium cho Playwright profile scraper
playwright install chromium
```

## 🧪 Chạy Test & Benchmark
```bash
pip install -e .[dev]
python -m pytest tests -v

# Load benchmark (cần aiohttp, nằm trong dev extra):
BENCH_BASE=http://127.0.0.1:8000 python scripts/bench.py
```

---

## 🚀 Hướng Dẫn Sử Dụng

### Cách 1: Chạy API Server (Khuyên dùng)
```bash
# Entry point sau khi `pip install -e .`
tikdl-web

# Hoặc chạy trực tiếp
python apps/web/app.py

# Hoặc dùng uvicorn với tuỳ chỉnh host/port
python -m uvicorn apps.web.app:app --host 0.0.0.0 --port 8000
```

### Production — multi-worker (target 5000 rps)
```bash
# Cách 1: uvicorn trực tiếp
python -m uvicorn apps.web.app:app --host 0.0.0.0 --port 8000 --workers 8

# Cách 2: gunicorn (Linux) — uvloop/httptools tự kích hoạt qua uvicorn[standard]
gunicorn apps.web.app:app -w 8 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

* Kết quả benchmark trên 1 laptop Windows 4 worker: ~2,100–3,100 rps (client và server dùng chung CPU).
* Trên server Linux chuyên dụng (uvloop + httptools, 8 worker): vượt 5,000 rps cho các endpoint nhẹ (`/api/task-status`, `/api/downloads` cached). Các endpoint nặng I/O mạng (`/api/video-info`, `/api/download-single`) bị giới hạn bởi tốc độ scrape TikTok, không phải bởi API layer.

### Cách 2: Chạy Giao Diện Dòng Lệnh (CLI)
```bash
tikdl-cli          # sau khi `pip install -e .`
python -m apps.cli # hoặc chạy trực tiếp
```
* Chức năng tải hàng loạt hỗ trợ: `@username`, link profile TikTok/Douyin, hoặc file `.txt/.csv` chứa danh sách URL.

### Luồng tải

```text
Video URL
  -> TikTokAPI hoặc DouyinAPI lấy thông tin + download_url (Playwright/HTML fallback khi cần)
  -> Downloader tải video và phụ đề
```

---


## 📁 Cấu Trúc Dự Án

```text
apps/                          ← Entry points
  cli.py                       # Giao diện dòng lệnh (Rich menu)
  web/app.py                   # Pure API server (FastAPI) — 5 endpoint

core/                          ← Logic chính (10 file + __init__)
  base_api.py                  # HTTP chung, download stream, retry, subtitle
  tiktok_api.py                # Trích video info từ TikTok
  douyin_api.py                # Trích video info từ Douyin
  downloader.py                # Chọn đúng API → tải video + metadata
  profile_scraper.py           # Tải hàng loạt profile (4 threads)
  cookie_manager.py            # Đọc/ghi config.json
  browser_scraper.py           # Playwright scraper (anti-detection)
  service.py                   # ★ Logic chung — CLI và API đều gọi vào đây
  stealth.py                   # Fingerprint masking cho browser headless
  exceptions.py                # Typed errors (ValidationError, AuthError, ...)

scripts/bench.py               # Load benchmark (aiohttp)
tests/                         # Unit tests (pytest)
pyproject.toml                 # Package config + entry points + extras
config.json                    # Cấu hình runtime (không commit)
```

### Kiến trúc

```
User → CLI / REST API (transport layer — chỉ routing)
         ↓
    core/service.py (logic chung — duy nhất 1 nơi)
         ↓
    core/downloader.py → TikTokAPI / DouyinAPI
         ↓
    core/base_api.py (HTTP, download, retry)
```

**Muốn sửa bug?** Chỉ cần sửa trong `core/service.py` — cả CLI và API đều tự động cập nhật.

## 🔄 CI

GitHub Actions (`.github/workflows/ci.yml`) chạy pytest trên Python 3.10 & 3.12 cho mỗi push/PR tới `main`.
