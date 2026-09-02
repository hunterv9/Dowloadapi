# ⚡ TikTok & Douyin Downloader

Công cụ tải video TikTok/Douyin chất lượng cao, hỗ trợ tải video đơn, tải profile hàng loạt, tải phụ đề và lưu metadata. Dự án có ba giao diện độc lập: CLI, Web và Desktop; các giao diện dùng chung thư mục `core/`.

## ✨ Tính Năng Nổi Bật
1. **🎬 Download Video Đơn:** Tải video chất lượng cao (No Watermark/HD), tự động lưu tiêu đề, tác giả và metadata.
2. **👤 Download Full Profile:** `yt-dlp` lấy danh sách `webpage_url` từ profile, sau đó Core lấy thông tin và tải từng video riêng vào `downloads/<username>/`. Archive lưu lịch sử để tránh tải lại; mặc định tải song song 4 video.
3. **📝 Tải Phụ Đề (Subtitle):** Tự động trích xuất và lưu caption/`subtitle` dạng `.srt`/`.vtt` khi nền tảng hỗ trợ.
4. **🔎 Lấy dữ liệu Profile:** Ưu tiên `yt-dlp`, sau đó fallback sang Playwright và HTML/JSON nhúng nếu cần. Nếu TikTok trả HTTP 429, có thể cần cookie đăng nhập hoặc giảm tốc độ yêu cầu.
5. **🌐 Giao diện Đa dạng:**
   - **CLI Console (Rich Menu):** Menu màu sắc, thanh tiến trình.
  - **Web Dashboard:** FastAPI backend và giao diện tại `http://127.0.0.1:8080`.
  - **Desktop App:** Electron tải giao diện tĩnh và tự khởi động Python WebSocket backend.

## 🔒 Bảo Mật (đã nâng cấp)
- CORS giới hạn nguồn `localhost` (không còn wildcard + credentials).
- Các API xóa/mở file kiểm tra **đường dẫn phải nằm trong thư mục downloads** (chống path traversal).
- Chống command injection khi mở file trong Explorer (dùng argv thay vì chuỗi).
- `downloads/`, `.browser_data/`, môi trường Python, `node_modules/` và file bytecode local được Git bỏ qua.
- `config.json` có thể chứa cookie và đường dẫn local; không commit cookie thật lên repository.

## 🧪 Chạy Test
```bash
python -m pip install -r requirements.txt
python -m pytest tests -v
```

Nếu dùng Playwright fallback, cài trình duyệt Chromium một lần:

```bash
python -m playwright install chromium
```

---
## 🚀 Hướng Dẫn Sử Dụng

### Cách 1: Chạy Giao Diện Web (Khuyên dùng)
```bash
python -m uvicorn web.app:app --host 127.0.0.1 --port 8080
```
* Mở `http://127.0.0.1:8080` trên trình duyệt.

### Cách 2: Chạy Giao Diện Dòng Lệnh (CLI)
```bash
python cli.py
```
* Chức năng tải hàng loạt hỗ trợ: `@username`, link profile TikTok/Douyin, hoặc file `.txt/.csv` chứa danh sách URL.

### Cách 3: Chạy Desktop Electron
```bash
npm install   # lần đầu
npm start
```

### Luồng tải Profile

```text
Profile URL
  -> yt-dlp lấy danh sách webpage_url
  -> ProfileScraper xử lý từng URL
  -> TikTokAPI hoặc DouyinAPI lấy download_url
  -> Downloader tải video và phụ đề
```

`yt-dlp` chỉ dùng để lấy danh sách video trong profile. Việc tải thực tế vẫn đi qua Core để dùng chung cơ chế cookie, chất lượng, metadata, phụ đề và archive cho cả CLI và Web.

---
## 📁 Cấu Trúc Dự Án

Chỉ có **20 file code** — mỗi file có mục đích rõ ràng:

```
core/                          ← Logic chính (8 file)
  base_api.py                  # HTTP chung, download stream, retry, subtitle
  tiktok_api.py                # Trích video info từ TikTok
  douyin_api.py                # Trích video info từ Douyin
  downloader.py                # Chọn đúng API → tải video + metadata
  profile_scraper.py           # Tải hàng loạt profile (4 threads)
  cookie_manager.py            # Đọc/ghi config.json
  browser_scraper.py           # Playwright fallback (anti-detection)
  service.py                   # ★ Logic chung — Web và Desktop đều gọi vào đây

web/app.py                     # Web server (FastAPI) — chỉ routing
desktop/ws_server.py           # Desktop server (WebSocket) — chỉ protocol
cli.py                         # Giao diện dòng lệnh (Rich menu)
electron/main.js               # Electron desktop app
electron/preload.js            # Electron security bridge

frontend/src/main.jsx          # Giao diện UI (React, 4 views)
frontend/src/styles.css        # CSS styles

config.json                    # Cấu hình runtime
requirements.txt               # Python dependencies
package.json                   # Node.js dependencies
vite.config.js                 # Vite build config
```

### Kiến trúc

```
User → CLI / Web / Desktop (transport layer — chỉ routing)
         ↓
    core/service.py (logic chung — duy nhất 1 nơi)
         ↓
    core/downloader.py → TikTokAPI / DouyinAPI
         ↓
    core/base_api.py (HTTP, download, retry)
```

**Muốn sửa bug?** Chỉ cần sửa trong `core/service.py` — cả Web và Desktop đều tự động cập nhật.
