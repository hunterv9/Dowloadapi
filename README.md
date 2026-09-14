# ⚡ TikTok & Douyin Downloader

Công cụ tải video TikTok/Douyin chất lượng cao, hỗ trợ tải video đơn, tải profile hàng loạt, tải phụ đề và lưu metadata. Dự án có **hai giao diện độc lập** — CLI và Web — dùng chung thư mục `core/`.

## ✨ Tính Năng Nổi Bật
1. **🎬 Download Video Đơn:** Tải video chất lượng cao (No Watermark/HD), tự động lưu tiêu đề, tác giả và metadata.
2. **👤 Download Full Profile:** Quét profile qua trình duyệt headless (Playwright) với fallback HTML/JSON, tải từng video vào `downloads/<username>/`. Archive lưu lịch sử để tránh tải lại; mặc định tải song song 4 video.
3. **📝 Tải Phụ Đề (Subtitle):** Tự động trích xuất và lưu caption/`subtitle` dạng `.srt`/`.vtt` khi nền tảng hỗ trợ.
4. **🔎 Lấy dữ liệu Profile:** Ưu tiên Playwright (render JS, qua WAF), fallback sang HTML/JSON nhúng. Nếu TikTok trả HTTP 429, có thể cần cookie đăng nhập hoặc giảm tốc độ yêu cầu.
5. **🌐 Giao diện Đa dạng:**
   - **CLI Console (Rich Menu):** Menu màu sắc, thanh tiến trình.
   - **Web Dashboard:** FastAPI backend (REST + WebSocket tiến trình) và giao diện React tại `http://127.0.0.1:8080`.

## 🔒 Bảo Mật
- CORS giới hạn nguồn `localhost` (không wildcard + credentials).
- Các API xóa/mở file kiểm tra **đường dẫn phải nằm trong thư mục downloads** (chống path traversal).
- Chống command injection khi mở file trong Explorer (dùng argv thay vì chuỗi).
- `downloads/`, `.browser_data/`, môi trường Python, `node_modules/` và file bytecode local được Git bỏ qua.
- `config.json` có thể chứa cookie và đường dẫn local; không commit cookie thật lên repository.

## 📦 Cài Đặt

Yêu cầu **Python 3.10+** và **Node.js 20+** (chỉ cần khi build giao diện).

```bash
# Cài package (kèm entry points tikdl-cli / tikdl-web)
pip install -e .

# Hoặc cài theo cách truyền thống
pip install -r requirements.txt

# (Tuỳ chọn, khuyên dùng) Cài Chromium cho Playwright profile scraper
playwright install chromium

# Cài dependencies frontend (lần đầu)
npm install
```

## 🧪 Chạy Test
```bash
pip install -e .[dev]
python -m pytest tests -v
```

---

## 🚀 Hướng Dẫn Sử Dụng

### Cách 1: Chạy Giao Diện Web (Khuyên dùng)
```bash
# Entry point sau khi `pip install -e .`
tikdl-web

# Hoặc chạy trực tiếp
python apps/web/app.py

# Hoặc dùng uvicorn với tuỳ chỉnh host/port
python -m uvicorn apps.web.app:app --host 127.0.0.1 --port 8080
```
* Mở `http://127.0.0.1:8000` (khi chạy trực tiếp) hoặc `http://127.0.0.1:8080` (khi dùng uvicorn) trên trình duyệt.

### Cách 2: Chạy Giao Diện Dòng Lệnh (CLI)
```bash
tikdl-cli          # sau khi `pip install -e .`
python -m apps.cli # hoặc chạy trực tiếp
python apps/cli.py # cách cũ (yêu cầu chạy từ root)
```
* Chức năng tải hàng loạt hỗ trợ: `@username`, link profile TikTok/Douyin, hoặc file `.txt/.csv` chứa danh sách URL.

### Build giao diện production
```bash
python scripts/build.py   # Vite build → apps/web/static (FastAPI phục vụ trực tiếp)
# hoặc chỉ: npm run build
```

### Luồng tải Profile

```text
Profile URL
  -> Playwright headless (fallback: HTML/JSON nhúng) lấy danh sách video
  -> ProfileScraper xử lý từng URL
  -> TikTokAPI hoặc DouyinAPI lấy download_url
  -> Downloader tải video và phụ đề
```

Việc tải thực tế đi qua Core để dùng chung cơ chế cookie, chất lượng, metadata, phụ đề và archive cho cả CLI và Web.

---

## 📁 Cấu Trúc Dự Án

```text
apps/                          ← Entry points
  cli.py                       # Giao diện dòng lệnh (Rich menu)
  web/app.py                   # Web server (FastAPI) — chỉ routing
  web/static/                  # Frontend build output (Vite)

core/                          ← Logic chính (8 file)
  base_api.py                  # HTTP chung, download stream, retry, subtitle
  tiktok_api.py                # Trích video info từ TikTok
  douyin_api.py                # Trích video info từ Douyin
  downloader.py                # Chọn đúng API → tải video + metadata
  profile_scraper.py           # Tải hàng loạt profile (4 threads)
  cookie_manager.py            # Đọc/ghi config.json
  browser_scraper.py           # Playwright scraper (anti-detection)
  service.py                   # ★ Logic chung — CLI và Web đều gọi vào đây

frontend/src/main.jsx          # Giao diện UI (React, 4 views)
frontend/src/styles.css        # CSS styles

scripts/build.py               # Build frontend → apps/web/static
tests/                         # Unit tests (pytest)
pyproject.toml                 # Package config + entry points + extras
config.json                    # Cấu hình runtime (không commit)
```

### Kiến trúc

```
User → CLI / Web (transport layer — chỉ routing)
         ↓
    core/service.py (logic chung — duy nhất 1 nơi)
         ↓
    core/downloader.py → TikTokAPI / DouyinAPI
         ↓
    core/base_api.py (HTTP, download, retry)
```

**Muốn sửa bug?** Chỉ cần sửa trong `core/service.py` — cả CLI và Web đều tự động cập nhật.

## 🔄 CI

GitHub Actions (`.github/workflows/ci.yml`) chạy trên mỗi push/PR tới `main`:
- **Python tests**: pytest trên Python 3.10 & 3.12 (`pip install -e .[dev]`).
- **Frontend build**: `npm ci && npm run build` trên Node 20, kiểm tra `apps/web/static/index.html` tồn tại.
