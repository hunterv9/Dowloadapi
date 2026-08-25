# ⚡ TikTok Video & Profile Downloader

Công cụ tải video TikTok/Douyin không logo/watermark, hỗ trợ tải toàn bộ video từ Profile song song, kèm phụ đề và đã được nâng cấp (refactor + bảo mật + test).

## ✨ Tính Năng Nổi Bật
1. **🎬 Download Video Đơn:** Tải video chất lượng cao (No Watermark/HD), tự động lưu tiêu đề, tác giả và metadata.
2. **👤 Download Full Profile:** Nhập `@username` hoặc liên kết profile TikTok/Douyin để tải toàn bộ video vào `downloads/<username>/`, archive lưu lịch sử để tránh tải lại. Tải song song 4 video cùng lúc.
3. **📝 Tải Phụ Đề (Subtitle):** Tự động trích xuất và lưu caption/`subtitle` dạng `.srt`/`.vtt` khi nền tảng hỗ trợ.
4. **⏳ Phân Trang (Pagination):** Quét profile theo nhiều trang qua API chính thức (best-effort, tự fallback nếu cần chữ ký).
5. **🌐 Giao diện Đa dạng:**
   - **CLI Console (Rich Menu):** Menu màu sắc, thanh tiến trình.
   - **Web Dashboard GUI:** Dark Mode Glassmorphism tại `http://127.0.0.1:8080`.

## 🔒 Bảo Mật (đã nâng cấp)
- CORS giới hạn nguồn `localhost` (không còn wildcard + credentials).
- Các API xóa/mở file kiểm tra **đường dẫn phải nằm trong thư mục downloads** (chống path traversal).
- Chống command injection khi mở file trong Explorer (dùng argv thay vì chuỗi).

## 🧪 Chạy Test
```bash
python -m pip install -r requirements.txt
python -m pytest tests -v
```

---
## 🚀 Hướng Dẫn Sử Dụng

### Cách 1: Chạy Giao Diện Web (Khuyên dùng)
* Nhấp đúp `run_gui.bat` hoặc:
  ```bash
  python -m uvicorn web.app:app --host 127.0.0.1 --port 8080
  ```

### Cách 2: Chạy Giao Diện Dòng Lệnh (CLI)
* Nhấp đúp `run_cli.bat` hoặc chạy:
  ```bash
  python cli.py
  ```
* Menu 2 (tải kênh/batch) hỗ trợ: `@username`, link profile TikTok/Douyin, file `.txt/.csv` chứa danh sách URL.

---
## 📁 Cấu Trúc Dự Án
```
tiktok-downloader/
├── core/
│   ├── base_api.py            # Base class dùng chung (HTTP, download stream, subtitle, retry)
│   ├── tiktok_api.py          # Client TikTok (api-data, oEmbed, pagination)
│   ├── douyin_api.py          # Client Douyin (_ROUTER_DATA, pagination)
│   ├── cookie_manager.py     # Quản lý cấu hình + cookie thủ công
│   ├── downloader.py          # Tải video đơn + subtitle
│   └── profile_scraper.py     # Quét & tải toàn bộ kênh (song song)
├── web/
│   ├── app.py                # FastAPI backend (+ path-safety)
│   └── static/               # Giao diện Web (HTML, CSS, JS)
├── desktop/
│   └── ws_server.py          # WebSocket server cho Electron Desktop
├── electron/                  # App Electron (main.js, preload.js)
├── tests/                     # Bộ test pytest (17 test)
├── cli.py                    # Menu tương tác dòng lệnh
├── run_cli.bat / run_gui.bat / run_desktop.bat
├── config.json               # Cấu hình lưu trữ
└── requirements.txt          # Danh sách thư viện cần thiết
```
