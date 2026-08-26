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
* Nhấp đúp `run_gui.bat` hoặc:
  ```bash
  python -m uvicorn web.app:app --host 127.0.0.1 --port 8080
  ```
* Mở `http://127.0.0.1:8080` trên trình duyệt.

### Cách 2: Chạy Giao Diện Dòng Lệnh (CLI)
* Nhấp đúp `run_cli.bat` hoặc chạy:
  ```bash
  python cli.py
  ```
* Chức năng tải hàng loạt hỗ trợ: `@username`, link profile TikTok/Douyin, hoặc file `.txt/.csv` chứa danh sách URL.

### Cách 3: Chạy Desktop Electron
* Cài dependency Node.js một lần:
  ```bash
  npm install
  ```
* Khởi chạy bằng `run_desktop.bat` hoặc:
  ```bash
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
```
tiktok-downloader/
├── core/
│   ├── base_api.py            # Base class dùng chung (HTTP, download stream, subtitle, retry)
│   ├── browser_scraper.py     # Playwright fallback cho profile
│   ├── tiktok_api.py          # Client TikTok và profile resolver
│   ├── douyin_api.py          # Client Douyin và profile resolver
│   ├── cookie_manager.py     # Quản lý cấu hình + cookie thủ công
│   ├── downloader.py          # Tải video đơn + subtitle
│   └── profile_scraper.py     # Quét & tải toàn bộ kênh (song song)
├── web/
│   ├── app.py                 # FastAPI backend (+ path-safety)
│   └── static/                # Giao diện Web/Desktop (HTML, CSS, JS)
├── desktop/
│   └── ws_server.py           # WebSocket backend cho Electron
├── electron/                  # Electron shell (main.js, preload.js)
├── tests/                     # Bộ kiểm thử pytest
├── cli.py                    # Menu tương tác dòng lệnh
├── run_cli.bat / run_gui.bat / run_desktop.bat
├── config.json               # Cấu hình lưu trữ
└── requirements.txt          # Danh sách thư viện cần thiết
```

Thư mục `downloads/` và dữ liệu browser là dữ liệu runtime local, không thuộc source code của repository.
